"""Exercise real SysAdmin-created tasks, repeat runs and the editor API."""
import base64
import json
import time
import uuid
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

base='http://127.0.0.1:52773/vector-admin/'
credentials=base64.b64encode(('_SYSTEM:'+Path('/run/secrets/iris_password').read_text().strip()).encode()).decode()
csrf=''
def api(path,body=None):
    headers={'Authorization':'Basic '+credentials}
    if body is not None: headers.update({'Content-Type':'application/json','X-CSRF-Token':csrf})
    request=Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    try:
        with urlopen(request,timeout=130) as response: return json.load(response)
    except HTTPError as exc: raise RuntimeError(str(exc.code)+' '+exc.read().decode()) from None

csrf=api('api/capabilities')['csrf']
assert api('api/python/validate',{'code':'def generate(row, context):\n    return [1,,2]'})['line']==2
assert api('api/python/validate',{'code':'def generate(row, context):\n    return [1.0, 2.0, 3.0]'})['valid']
tables=api('api/instances/local/source-tables?namespace=USER')['items']
assert any(t['schema']=='data' and t['table']=='Document' for t in tables)

def make_task(policy):
    body={'name':'VectorAdmin repeat '+policy,'namespace':'USER','schema':'data','table':'Document',
          'targetColumn':'TestVector'+uuid.uuid4().hex[:8], 'relationColumn':'ID',
          'sourceSql':'SELECT ID, Description FROM data.Document','dimensions':3,'generationMode':'PYTHON',
          'selectionMode':policy,'pythonCode':'def generate(row, context):\n    return [float(len(row["text"])), float(row["key"]), 1.0]'}
    sample=api('api/python/test',body); assert sample['valid'] and not sample['persisted']
    draft=api('api/vector-recipes',body); proposal=api('api/vector-recipes/'+draft['id']+'/preflight',{})
    api('api/vector-recipes/'+draft['id']+'/publish',{'token':proposal['token'],'confirmation':proposal['target']})
    task=api('api/vector-recipes/'+draft['id']+'/schedules',{})
    print('TASK',policy,task['taskId'],body['targetColumn'],flush=True)
    return task['taskId']

def run(task):
    before={r['id'] for r in api('api/seed-runs?taskId='+str(task))['items']}
    api('api/schedules/'+str(task)+'/run',{})
    deadline=time.monotonic()+100
    while time.monotonic()<deadline:
        runs=api('api/seed-runs?taskId='+str(task))['items']
        current=next((r for r in runs if r['id'] not in before),None)
        if current and current['state']!='RUNNING':
            print('RUN',json.dumps(current),flush=True)
            assert current['state']=='SUCCEEDED',current
            return current
        time.sleep(1)
    raise AssertionError('Task did not finish within 100 seconds')

changed=make_task('CHANGED')
first=run(changed); assert first['created']==first['selected'] and first['created']>=20
second=run(changed); assert second['created']==second['updated']==0 and second['skipped']==first['selected']
def mutate_fixture():
    commands='zn "USER"\nset runner=##class(%SYS.Python).Import("runpy") do runner."run_path"("/usr/irissys/csp/vector-admin/tools/acceptance_mutate_documents.py")\nhalt\n'
    result=subprocess.run(['iris','session','IRIS'],input=commands,text=True,capture_output=True,timeout=30)
    assert 'MUTATION_OK' in result.stdout,result.stdout
mutate_fixture()
third=run(changed); assert third['created']==2 and third['updated']==1
missing=make_task('MISSING'); run(missing)
mutate_fixture()
result=run(missing); assert result['created']==2 and result['updated']==0
all_rows=make_task('ALL'); run(all_rows)
result=run(all_rows); assert result['updated']==result['selected'] and result['created']==0
detail=api('api/schedules/'+str(changed)); assert len(detail['runs'])>=3
print('REPEATABLE_HTTP_OK',flush=True)
