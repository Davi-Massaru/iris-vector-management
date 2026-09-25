"""Read-only monitoring for portal-owned IRIS Task Manager jobs."""
from . import settings
from .errors import Problem
from .sql import integer

TASK_CLASS = 'VectorAdmin.SeedTask'

def _is_vector_task(definition):
    return definition.get('TaskClass') == TASK_CLASS

def _recipe(settings_value):
    if not isinstance(settings_value, dict):
        return None
    value = settings_value.get('RecipeRevision') or settings_value.get('recipeRevision')
    return str(value)[:128] if value not in (None, '') else None

def normalized_state(manager_status, summary, info):
    if manager_status in ('Suspended', 'Not running') or summary.get('Suspended') or info.get('Suspended'):
        return 'SUSPENDED'
    status = str(info.get('Status', ''))
    if status == '-1': return 'RUNNING'
    if status in ('-2', '-3', '-4', '-5'): return 'FAILED'
    if info.get('LastFinished') and status in ('', '1'): return 'SUCCEEDED'
    if summary.get('NextScheduled') or info.get('NextScheduled'): return 'SCHEDULED'
    return 'UNKNOWN'

def inventory(client, max_rows=100, run_lookup=None):
    limit = integer(max_rows, 1, settings.MAX_PAGE_SIZE, 'Page size')
    manager = client.get('/v2/task/manager') or {}
    manager_status = manager.get('Status', 'Unknown')
    summaries = client.get('/v2/tasks', filter='VectorAdmin', maxRows=limit)
    items = []
    for summary in summaries:
        task_id = summary.get('Id')
        if not isinstance(task_id, int): continue
        definition = client.get('/v2/task', id=task_id)
        if not _is_vector_task(definition): continue
        info = client.get('/v2/task/info', id=task_id)
        recipe = _recipe(definition.get('Settings'))
        if run_lookup is None:
            from .recipes import list_runs
            run_lookup=list_runs
        run_items=run_lookup(task_id)['items']
        latest=run_items[0] if run_items else None
        scheduler_state='UNLINKED' if not recipe else normalized_state(manager_status,summary,info)
        state=latest['state'] if latest and latest['state'] in ('RUNNING','SUCCEEDED','SUCCEEDED_WITH_ERRORS','FAILED','CANCELLED','UNKNOWN') else scheduler_state
        items.append({'id':task_id,'name':summary.get('Name') or definition.get('Name') or f'Task {task_id}',
            'namespace':summary.get('Namespace') or definition.get('NameSpace') or 'Unknown',
            'recipeRevision':recipe or 'Unknown','state':state,'run':latest,
            'suspended':bool(summary.get('Suspended') or info.get('Suspended')),
            'lastStarted':info.get('LastStarted') or '','lastFinished':info.get('LastFinished') or summary.get('LastFinished') or '',
            'nextScheduled':info.get('NextScheduled') or summary.get('NextScheduled') or '',
            'irisStatus':info.get('Status'),'error':(info.get('Error') or '')[:512]})
    return {'manager':manager_status,'items':items}

def detail(client, task_id, max_rows=50):
    task_id = integer(task_id, 1, 2147483647, 'Task id')
    limit = integer(max_rows, 1, settings.MAX_PAGE_SIZE, 'Page size')
    definition = client.get('/v2/task', id=task_id)
    if not _is_vector_task(definition): raise Problem('NOT_FOUND','Vector task not found.',404)
    info = client.get('/v2/task/info', id=task_id)
    history = client.get('/v2/task/history', taskId=task_id, userOnly=1, maxRows=limit)
    safe = {key:definition.get(key) for key in ('Name','TaskClass','NameSpace','RunAsUser','Description','StartDate','EndDate','TimePeriod','DailyFrequency','DailyFrequencyTime','MirrorStatus','Priority','IsBatch')}
    safe['RecipeRevision'] = _recipe(definition.get('Settings')) or 'Unknown'
    keys=('LastStart','Completed','Status','Result','TaskId','Namespace','Pid','ErrDate','ErrNumber','Username','LogDatetime')
    from .recipes import list_runs
    return {'definition':safe,'info':info,'history':[{key:row.get(key) for key in keys} for row in history],
            'runs':list_runs(task_id)['items']}

def run_now(client, task_id):
    from . import auth,audit
    auth.require('VectorAdmin_Maintain')
    task_id=integer(task_id,1,2147483647,'Task id')
    definition=client.get('/v2/task',id=task_id)
    if not _is_vector_task(definition): raise Problem('NOT_FOUND','Vector task not found.',404)
    recipe=_recipe(definition.get('Settings'))
    if not recipe: raise Problem('RECIPE_NOT_PUBLISHED','Task is not linked to a recipe.',409)
    client.post('/v2/task/run',{'RunNow':True,'Datetime':''},id=task_id)
    audit.record('schedule.run',str(task_id),'ACCEPTED',{'operation':recipe})
    return {'taskId':task_id,'state':'QUEUED','recipeRevision':recipe}
