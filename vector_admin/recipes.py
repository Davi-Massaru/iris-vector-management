"""Versioned vector recipes: inert draft, preflight, publish, schedule and execution."""
import ast,hashlib,json,math,re,time,uuid
from . import auth,settings,catalog,audit,generators
from .errors import Problem
from .sql import namespace,rows,identifier,integer

def _digest(payload): return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()

_SIMPLE_SELECT=re.compile(r'^\s*SELECT\s+([A-Za-z][A-Za-z0-9_]*)\s*,\s*([A-Za-z][A-Za-z0-9_]*)\s+FROM\s+([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)\s*$',re.I)

def _new_payload(body):
    policy=body.get('selectionMode','CHANGED')
    if policy not in ('ALL','CHANGED','MISSING'):
        raise Problem('INVALID_RECIPE','Choose ALL, CHANGED or MISSING.',422)
    ns=str(body.get('namespace','')).upper(); auth.scope(settings.INSTANCE,ns)
    schema=str(body.get('schema','')); table_name=str(body.get('table','')); column=str(body.get('targetColumn','')).strip()
    relation=str(body.get('relationColumn','')).strip(); source_sql=str(body.get('sourceSql','')).strip()
    match=_SIMPLE_SELECT.fullmatch(source_sql)
    if not match or '--' in source_sql or '/*' in source_sql or ';' in source_sql:
        raise Problem('INVALID_SOURCE_SQL','Use one simple SELECT with two columns: SELECT Key, Text FROM schema.table.',422)
    source_key,source_text,source_schema,source_table=match.groups()
    for value in (schema,table_name,column,relation,source_key,source_text,source_schema,source_table): identifier(value)
    with namespace(ns):
        target_cols=rows('SELECT COLUMN_NAME,DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=?',(schema,table_name),limit=201)
        source_cols=rows('SELECT COLUMN_NAME,DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=?',(source_schema,source_table),limit=201)
    target_map={str(x[0]).upper():x[0] for x in target_cols}; source_map={str(x[0]).upper():x[0] for x in source_cols}
    if not target_cols: raise Problem('INVALID_TARGET','Target table was not found.',422)
    if relation.upper() not in target_map: raise Problem('INVALID_TARGET','Relationship column was not found in the target table.',422)
    if column.upper() in target_map: raise Problem('TARGET_EXISTS','The new vector column already exists.',409)
    if source_key.upper() not in source_map or source_text.upper() not in source_map: raise Problem('INVALID_SOURCE_SQL','The SELECT columns were not found.',422)
    generation=str(body.get('generationMode','MODEL')).upper(); dimensions=integer(body.get('dimensions'),1,settings.MAX_DIMENSIONS,'Dimensions')
    payload={'instance':settings.INSTANCE,'namespace':ns,'schema':schema,'table':table_name,'targetColumn':column,
             'relationColumn':target_map[relation.upper()],'sourceSchema':source_schema,'sourceTable':source_table,
             'sourceKey':source_map[source_key.upper()],'sourceText':source_map[source_text.upper()],
             'sourceSql':source_sql,'dimensions':dimensions,'generationMode':generation,'selectionMode':policy}
    if generation=='MODEL':
        config=str(body.get('config','')).strip()
        with namespace(ns): found=rows('SELECT VectorLength FROM %Embedding.Config WHERE Name=?',(config,),limit=1)
        if not found: raise Problem('INVALID_GENERATOR','Embedding configuration was not found.',422)
        if found[0][0] and int(found[0][0])!=dimensions: raise Problem('GENERATOR_CONTRACT_ERROR','Dimensions do not match the selected model.',422)
        payload['config']=config
    elif generation=='PYTHON':
        code=str(body.get('pythonCode',''))
        validation=generators.validate(code)
        if not validation['valid']: raise Problem('INVALID_GENERATOR',f"Line {validation['line']}: {validation['message']}",422)
        payload['pythonCode']=code; payload['codeDigest']=hashlib.sha256(code.encode()).hexdigest()
    else: raise Problem('INVALID_GENERATOR','Generation mode must be MODEL or PYTHON.',422)
    return payload

def _generate_python(code,row,dimensions):
    safe={'len':len,'min':min,'max':max,'sum':sum,'float':float,'int':int,'str':str,'range':range,'abs':abs,'round':round}
    space={'__builtins__':safe}; exec(compile(code,'<published-vector-generator>','exec'),space,space)
    result=space['generate'](dict(row),{'dimensions':dimensions})
    if not isinstance(result,(list,tuple)) or len(result)!=dimensions or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(float(x)) for x in result):
        raise ValueError('Generator must return a finite numeric vector with the declared dimensions')
    return json.dumps([float(x) for x in result],separators=(',',':'))

def test_python(body):
    auth.require('VectorAdmin_Maintain')
    p=_new_payload({**body,'generationMode':'PYTHON'})
    with namespace(p['namespace']):
        sample=rows('SELECT TOP 1 '+identifier(p['sourceKey'])+','+identifier(p['sourceText'])+' FROM '+identifier(p['sourceSchema'])+'.'+identifier(p['sourceTable'])+' ORDER BY '+identifier(p['sourceKey']),limit=1)
        if not sample: raise Problem('EMPTY_SOURCE','Add documents before testing a sample.',422)
        started=time.monotonic()
        try: result=json.loads(_generate_python(p['pythonCode'],{'key':sample[0][0],'text':sample[0][1]},p['dimensions']))
        except Exception: raise Problem('GENERATOR_CONTRACT_ERROR','The function failed or returned a vector with invalid values or dimensions.',422)
    return {'valid':True,'sampleKey':str(sample[0][0]),'dimensions':len(result),'elapsedMs':round((time.monotonic()-started)*1000),'persisted':False}

def _load(recipe_id,revision=None):
    if not isinstance(recipe_id,str) or len(recipe_id)!=32: raise Problem('NOT_FOUND','Recipe not found.',404)
    query='SELECT TOP 1 RecipeId,Revision,Name,State,Payload,Fingerprint,CreatedBy,CreatedAt,PublishedAt FROM VectorAdmin.VectorRecipe WHERE RecipeId=?'; args=[recipe_id]
    if revision is not None: query+=' AND Revision=?'; args.append(integer(revision,1,2147483647,'Revision'))
    query+=' ORDER BY Revision DESC'
    with namespace(settings.ADMIN_NAMESPACE): result=rows(query,args,limit=1)
    if not result: raise Problem('NOT_FOUND','Recipe not found.',404)
    item=dict(zip(('id','revision','name','state','payload','fingerprint','createdBy','createdAt','publishedAt'),result[0])); item['payload']=json.loads(item['payload']); return item

def _asset(payload):
    auth.scope(settings.INSTANCE,payload['namespace'])
    with namespace(payload['namespace']):
        entry=rows('SELECT p.parent,p.Name,p.SqlFieldName,p.Type,c.SqlSchemaName,c.SqlTableName FROM %Dictionary.CompiledProperty p JOIN %Dictionary.CompiledClass c ON p.parent=c.Name WHERE p.parent=? AND p.Name=?',(payload['class'],payload['property']),limit=1)
        if not entry: raise Problem('CATALOG_CHANGED','The target asset no longer exists.',409)
        return catalog.build(payload['namespace'],*entry[0])

def create_draft(body):
    auth.require('VectorAdmin_Maintain')
    if body.get('targetColumn'):
        payload=_new_payload(body); name=str(body.get('name','')).strip()
        if not name or len(name)>128: raise Problem('INVALID_RECIPE','Recipe name is required and limited to 128 characters.',422)
        recipe=uuid.uuid4().hex; fingerprint=_digest(payload); now=time.time()
        with namespace(settings.ADMIN_NAMESPACE): rows('INSERT INTO VectorAdmin.VectorRecipe (RecipeId,Revision,Name,State,Payload,Fingerprint,CreatedBy,CreatedAt,PublishedAt) VALUES (?,?,?,?,?,?,?,?,?)',(recipe,1,name,'DRAFT',json.dumps(payload),fingerprint,auth.principal(),now,0.0),limit=0)
        audit.record('recipe.draft',recipe,'DRAFT',{'fingerprint':fingerprint}); return _load(recipe,1)
    asset=catalog.lookup(body.get('assetId',''))
    if asset['type']!='EMBEDDING' or len(asset['sourceColumns'])!=1 or asset['config']=='Unknown' or not asset['key']:
        raise Problem('RECIPE_INELIGIBLE','Choose a managed EMBEDDING asset with one source column, configuration and stable key.',422)
    mode=body.get('selectionMode','MISSING'); name=str(body.get('name','')).strip()
    if mode not in ('MISSING','ALL'): raise Problem('INVALID_RECIPE','Selection mode must be MISSING or ALL.',422)
    if not name or len(name)>128: raise Problem('INVALID_RECIPE','Recipe name is required and limited to 128 characters.',422)
    recipe=uuid.uuid4().hex
    payload={'instance':settings.INSTANCE,'namespace':asset['namespace'],'class':asset['class'],'property':asset['property'],'schema':asset['schema'],'table':asset['table'],'key':asset['key'],'sourceColumn':asset['sourceColumns'][0],'targetColumn':asset['column'],'config':asset['config'],'dimensions':asset['dimensions'],'selectionMode':mode,'assetFingerprint':asset['fingerprint']}
    fingerprint=_digest(payload); now=time.time()
    with namespace(settings.ADMIN_NAMESPACE): rows('INSERT INTO VectorAdmin.VectorRecipe (RecipeId,Revision,Name,State,Payload,Fingerprint,CreatedBy,CreatedAt,PublishedAt) VALUES (?,?,?,?,?,?,?,?,?)',(recipe,1,name,'DRAFT',json.dumps(payload),fingerprint,auth.principal(),now,0.0),limit=0)
    audit.record('recipe.draft',recipe,'DRAFT',{'fingerprint':fingerprint}); return _load(recipe,1)

def list_recipes():
    auth.require('VectorAdmin_Read')
    with namespace(settings.ADMIN_NAMESPACE): result=rows('SELECT RecipeId,Revision,Name,State,Payload,Fingerprint,CreatedBy,CreatedAt,PublishedAt FROM VectorAdmin.VectorRecipe ORDER BY CreatedAt DESC',limit=101)
    items=[]
    for row in result:
        item=dict(zip(('id','revision','name','state','payload','fingerprint','createdBy','createdAt','publishedAt'),row)); payload=json.loads(item.pop('payload')); item.update({k:payload.get(k) for k in ('namespace','schema','table','targetColumn','sourceColumn','sourceSql','selectionMode','generationMode','config')}); items.append(item)
    return {'items':items}

def preflight(recipe_id):
    auth.require('VectorAdmin_Maintain'); item=_load(recipe_id)
    if item['state']!='DRAFT': raise Problem('INVALID_RECIPE','Only a draft can be preflighted.',409)
    if 'sourceSql' in item['payload']:
        p=item['payload']; target=identifier(p['schema'])+'.'+identifier(p['table']); source=identifier(p['sourceSchema'])+'.'+identifier(p['sourceTable'])
        with namespace(p['namespace']):
            from .seed_runner import check_keys
            check_keys(p)
            existing=rows('SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=? AND COLUMN_NAME=?',(p['schema'],p['table'],p['targetColumn']),limit=1)
            if existing: raise Problem('TARGET_EXISTS','The new vector column already exists.',409)
            sample=rows('SELECT TOP 1 '+identifier(p['sourceKey'])+','+identifier(p['sourceText'])+' FROM '+source+' ORDER BY '+identifier(p['sourceKey']),limit=1)
            if sample and sample[0][1] is not None:
                if p['generationMode']=='MODEL':
                    sample_text=str(sample[0][1])[:settings.TEXT_LIMIT]
                    rows('SELECT VECTOR_COSINE(EMBEDDING(?,?),EMBEDDING(?,?)) FROM '+source+' WHERE '+identifier(p['sourceKey'])+'=?',(sample_text,p['config'],sample_text,p['config'],sample[0][0]),limit=1,timeout=120)
                else: _generate_python(p['pythonCode'],{'key':sample[0][0],'text':sample[0][1]},p['dimensions'])
        ddl='ALTER TABLE '+target+' ADD '+identifier(p['targetColumn'])+' VECTOR(DOUBLE,'+str(p['dimensions'])+')'
        confirmation=f'{p["namespace"]}/{p["schema"]}.{p["table"]}/{p["targetColumn"]}'
        token=auth.token({'kind':'recipe_publish','actor':auth.principal(),'recipe':item['id'],'revision':item['revision'],'fingerprint':item['fingerprint'],'confirmation':confirmation},300)
        audit.record('recipe.preflight',confirmation,'PREPARED',{'fingerprint':item['fingerprint'],'ddl':ddl})
        return {'recipeId':item['id'],'revision':item['revision'],'target':confirmation,'sampleKey':str(sample[0][0]) if sample else None,'ddl':ddl,'token':token}
    asset=_asset(item['payload'])
    if asset['fingerprint']!=item['payload']['assetFingerprint']: raise Problem('CATALOG_CHANGED','Asset metadata changed. Create a new draft.',409)
    p=item['payload']; target=identifier(p['schema'])+'.'+identifier(p['table']); condition=' WHERE '+identifier(p['targetColumn'])+' IS NULL' if p['selectionMode']=='MISSING' else ''
    with namespace(p['namespace']):
        sample=rows('SELECT TOP 1 '+identifier(p['key'])+','+identifier(p['sourceColumn'])+' FROM '+target+condition+' ORDER BY '+identifier(p['key']),limit=1)
        if sample and sample[0][1] is not None:
            probe='SELECT VECTOR_COSINE('+identifier(p['targetColumn'])+',EMBEDDING(?,?)) FROM '+target+' WHERE '+identifier(p['key'])+'=?'
            if not rows(probe,(str(sample[0][1])[:settings.TEXT_LIMIT],p['config'],sample[0][0]),limit=1,timeout=120): raise Problem('GENERATOR_CONTRACT_ERROR','Embedding test returned no result.',422)
    confirmation=f'{p["namespace"]}/{p["schema"]}.{p["table"]}/{p["targetColumn"]}'
    token=auth.token({'kind':'recipe_publish','actor':auth.principal(),'recipe':item['id'],'revision':item['revision'],'fingerprint':item['fingerprint'],'confirmation':confirmation},300)
    audit.record('recipe.preflight',confirmation,'PREPARED',{'fingerprint':item['fingerprint']})
    return {'recipeId':item['id'],'revision':item['revision'],'target':confirmation,'sampleKey':str(sample[0][0]) if sample else None,'token':token}

def publish(recipe_id,body):
    auth.require('VectorAdmin_Maintain'); signed=auth.verify(body.get('token',''),'recipe_publish')
    if signed['recipe']!=recipe_id or body.get('confirmation')!=signed['confirmation']: raise Problem('CONFIRMATION_REQUIRED','Type the exact target shown by preflight.',409)
    item=_load(recipe_id,signed['revision'])
    if item['state']!='DRAFT' or item['fingerprint']!=signed['fingerprint']: raise Problem('CATALOG_CHANGED','Recipe changed. Run preflight again.',409)
    if 'sourceSql' not in item['payload']: _asset(item['payload'])
    with namespace(settings.ADMIN_NAMESPACE): rows("UPDATE VectorAdmin.VectorRecipe SET State='PUBLISHED',PublishedAt=? WHERE RecipeId=? AND Revision=? AND State='DRAFT'",(time.time(),recipe_id,item['revision']),limit=0)
    audit.record('recipe.publish',signed['confirmation'],'SUCCEEDED',{'fingerprint':item['fingerprint']}); return _load(recipe_id,item['revision'])

def create_schedule(recipe_id,body,client):
    auth.require('VectorAdmin_Maintain'); item=_load(recipe_id)
    if item['state']!='PUBLISHED': raise Problem('RECIPE_NOT_PUBLISHED','Publish the recipe before scheduling it.',409)
    p=item['payload']; name=str(body.get('name') or item['name'])[:128]
    task={'Name':name,'RunAsUser':auth.principal(),'EmailOnCompletion':[],'EmailOnError':[],'EmailOnExpiration':[],
        'EmailOutput':False,'Expires':False,'ExpiresDays':0,'ExpiresHours':0,'ExpiresMinutes':0,'OpenOutputFile':False,
        'OutputDirectory':'','OutputFilename':'','OutputFileIsBinary':False,'SuspendOnError':True,'SuspendTerminated':True,
        'Priority':'Normal','TaskClass':'VectorAdmin.SeedTask','IsBatch':False,'NameSpace':p['namespace'],
        'TimePeriod':'On Demand','TimePeriodEvery':'','TimePeriodDay':'','DailyFrequency':'Once','DailyFrequencyTime':'Hourly',
        'DailyIncrement':'','DailyStartTime':'','DailyEndTime':'','RunAfterGUID':'','StartDate':body.get('startDate') or time.strftime('%Y-%m-%d'),
        'EndDate':'','MirrorStatus':'Primary','RescheduleOnStart':False,'Description':'VectorAdmin recipe '+recipe_id,
        'Settings':{'RecipeRevision':recipe_id}}
    result=client.post('/v2/task',task)
    task_id=result.get('Id')
    if not isinstance(task_id,int): raise Problem('VERIFY_FAILED','IRIS returned no task id. Inspect Task Manager.',500)
    with namespace(settings.ADMIN_NAMESPACE): rows('INSERT INTO VectorAdmin.SeedSchedule (TaskId,RecipeId,Revision,CreatedBy,CreatedAt) VALUES (?,?,?,?,?)',(task_id,recipe_id,item['revision'],auth.principal(),time.time()),limit=0)
    audit.record('schedule.create',str(task_id),'SUCCEEDED',{'fingerprint':item['fingerprint']}); return {'taskId':task_id,'recipeId':recipe_id,'revision':item['revision']}

def list_runs(task_id=None):
    auth.require('VectorAdmin_Read')
    query='SELECT TOP 100 RunId,RecipeId,Revision,TaskId,State,SelectedCount,UpdatedCount,SkippedCount,FailedCount,LastKey,HeartbeatAt,StartedAt,FinishedAt,ErrorSummary FROM VectorAdmin.SeedRun'
    args=[]
    if task_id is not None: query+=' WHERE TaskId=?'; args.append(integer(task_id,1,2147483647,'Task id'))
    query+=' ORDER BY StartedAt DESC'
    with namespace(settings.ADMIN_NAMESPACE): result=rows(query,args,limit=101)
    keys=('id','recipeId','revision','taskId','state','selected','updated','skipped','failed','lastKey','heartbeatAt','startedAt','finishedAt','error')
    items=[dict(zip(keys,row)) for row in result]
    with namespace(settings.ADMIN_NAMESPACE):
        for item in items:
            metrics=rows('SELECT CreatedCount,MissingCount,Policy FROM VectorAdmin.SeedMetrics WHERE RunId=?',(item['id'],),limit=1)
            item.update(dict(zip(('created','missing','policy'),metrics[0])) if metrics else {'created':0,'missing':0,'policy':'LEGACY'})
    return {'items':items}

def run_recipe(recipe_id,task_id=0):
    item=_load(str(recipe_id)); p=item['payload']
    if item['state']!='PUBLISHED': raise RuntimeError('Recipe is not published')
    if 'sourceSql' in p:
        from .seed_runner import execute
        return execute(item,task_id)
    with namespace(settings.ADMIN_NAMESPACE):
        schedule=rows('SELECT TOP 1 TaskId FROM VectorAdmin.SeedSchedule WHERE RecipeId=? AND Revision=? ORDER BY CreatedAt DESC',(item['id'],item['revision']),limit=1)
    if schedule: task_id=schedule[0][0]
    run_id=uuid.uuid4().hex; now=time.time(); selected=updated=skipped=failed=0; last_key=''; final='UNKNOWN'; error=''
    with namespace(settings.ADMIN_NAMESPACE): rows('INSERT INTO VectorAdmin.SeedRun (RunId,RecipeId,Revision,TaskId,State,SelectedCount,UpdatedCount,SkippedCount,FailedCount,HeartbeatAt,StartedAt) VALUES (?,?,?,?,?,?,?,?,?,?,?)',(run_id,item['id'],item['revision'],int(task_id),'RUNNING',0,0,0,0,now,now),limit=0)
    try:
        asset=_asset(p)
        if asset['fingerprint']!=p['assetFingerprint']: raise RuntimeError('Target catalog changed')
        target=identifier(p['schema'])+'.'+identifier(p['table']); filters=[identifier(p['targetColumn'])+' IS NULL'] if p['selectionMode']=='MISSING' else []
        with namespace(p['namespace']):
            cursor=None
            while True:
                clauses=list(filters); args=[]
                if cursor is not None: clauses.append(identifier(p['key'])+'>?'); args.append(cursor)
                query='SELECT TOP 100 '+identifier(p['key'])+','+identifier(p['sourceColumn'])+' FROM '+target
                if clauses: query+=' WHERE '+' AND '.join(clauses)
                query+=' ORDER BY '+identifier(p['key'])
                batch=rows(query,args,limit=101,timeout=120)
                if not batch: break
                for source_key,text in batch:
                    selected+=1; cursor=source_key; last_key=str(source_key)
                    if text is None: skipped+=1
                    else:
                        try: rows('UPDATE '+target+' SET '+identifier(p['targetColumn'])+'=EMBEDDING(?,?) WHERE '+identifier(p['key'])+'=?',(text,p['config'],source_key),limit=0,timeout=120); updated+=1
                        except Problem: failed+=1
                with namespace(settings.ADMIN_NAMESPACE): rows('UPDATE VectorAdmin.SeedRun SET SelectedCount=?,UpdatedCount=?,SkippedCount=?,FailedCount=?,LastKey=?,HeartbeatAt=? WHERE RunId=?',(selected,updated,skipped,failed,last_key,time.time(),run_id),limit=0)
        final='SUCCEEDED_WITH_ERRORS' if failed else 'SUCCEEDED'
    except Exception as exc: final='FAILED'; error=str(exc)[:2048]; raise
    finally:
        with namespace(settings.ADMIN_NAMESPACE): rows('UPDATE VectorAdmin.SeedRun SET State=?,FinishedAt=?,HeartbeatAt=?,ErrorSummary=? WHERE RunId=?',(final,time.time(),time.time(),error,run_id),limit=0)
