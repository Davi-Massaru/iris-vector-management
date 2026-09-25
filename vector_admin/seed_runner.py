"""Repeatable row updates. The vector and its signatures commit together."""
import hashlib
import json
import time
import uuid
from . import settings, catalog
from .errors import Problem
from .sql import namespace, rows, identifier

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()

def should_generate(policy, present, previous, source_hash, generator_hash):
    if not present or policy == 'ALL': return True
    if policy == 'MISSING': return False
    return previous != [source_hash, generator_hash]

def check_keys(p):
    # Keyset paging and matching must never silently drop duplicate/null keys.
    for schema, table, key in ((p['sourceSchema'],p['sourceTable'],p['sourceKey']),
                               (p['schema'],p['table'],p['relationColumn'])):
        target=identifier(schema)+'.'+identifier(table); field=identifier(key)
        if rows('SELECT TOP 1 '+field+' FROM '+target+' WHERE '+field+' IS NULL',limit=1):
            raise Problem('INVALID_RELATION','Relationship keys must not be null.',422)
        if rows('SELECT TOP 1 '+field+' FROM '+target+' GROUP BY '+field+' HAVING COUNT(*)>1',limit=1):
            raise Problem('INVALID_RELATION','Source and destination relationship keys must be unique.',422)

def generator_fingerprint(p):
    definition={k:p.get(k) for k in ('generationMode','dimensions','config','codeDigest')}
    if p['generationMode']=='MODEL':
        definition['configuration']=rows('SELECT EmbeddingClass,Configuration,VectorLength FROM %Embedding.Config WHERE Name=?',(p['config'],),limit=1)
        if not definition['configuration']: raise Problem('INVALID_GENERATOR','Model configuration no longer exists.',409)
    return digest(definition)

def ensure_column(p):
    target=identifier(p['schema'])+'.'+identifier(p['table'])
    existing=rows('SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=? AND COLUMN_NAME=?',
                  (p['schema'],p['table'],p['targetColumn']),limit=1)
    if not existing:
        rows('ALTER TABLE '+target+' ADD '+identifier(p['targetColumn'])+' VECTOR(DOUBLE,'+str(p['dimensions'])+')',limit=0,timeout=120)
    entry=rows('SELECT p.parent,p.Name,p.Type FROM %Dictionary.CompiledProperty p JOIN %Dictionary.CompiledClass c ON p.parent=c.Name WHERE c.SqlSchemaName=? AND c.SqlTableName=? AND p.SqlFieldName=?',
               (p['schema'],p['table'],p['targetColumn']),limit=1)
    if not entry: raise Problem('CATALOG_CHANGED','Vector column metadata could not be verified.',409)
    params=catalog.parameters(entry[0][0],entry[0][1],['LEN','DATATYPE'])
    if entry[0][2]!='%Library.Vector' or str(params.get('LEN'))!=str(p['dimensions']) or params.get('DATATYPE')!='DOUBLE':
        raise Problem('CATALOG_CHANGED','Existing column does not match the published vector type and dimensions.',409)

def execute(item, task_id=0):
    import iris
    from .recipes import _generate_python
    p=item['payload']; policy=p.get('selectionMode','ALL')
    target=identifier(p['schema'])+'.'+identifier(p['table'])
    source=identifier(p['sourceSchema'])+'.'+identifier(p['sourceTable'])
    key=identifier(p['relationColumn']); column=identifier(p['targetColumn'])
    lock_key=digest([p['namespace'],p['schema'].lower(),p['table'].lower(),p['targetColumn'].lower()])
    run_id=uuid.uuid4().hex; counts={'selected':0,'created':0,'updated':0,'skipped':0,'failed':0,'missing':0}
    last_key=''; final='FAILED'; error=''; locked=False
    with namespace(settings.ADMIN_NAMESPACE):
        if not task_id:
            schedule=rows('SELECT TOP 1 TaskId FROM VectorAdmin.SeedSchedule WHERE RecipeId=? AND Revision=? ORDER BY CreatedAt DESC',(item['id'],item['revision']),limit=1)
            if schedule: task_id=schedule[0][0]
        rows('INSERT INTO VectorAdmin.SeedRun (RunId,RecipeId,Revision,TaskId,State,SelectedCount,UpdatedCount,SkippedCount,FailedCount,HeartbeatAt,StartedAt) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
             (run_id,item['id'],item['revision'],int(task_id),'RUNNING',0,0,0,0,time.time(),time.time()),limit=0)
        rows('INSERT INTO VectorAdmin.SeedMetrics (RunId,CreatedCount,MissingCount,Policy) VALUES (?,?,?,?)',(run_id,0,0,policy),limit=0)
    def progress():
        with namespace(settings.ADMIN_NAMESPACE):
            rows('UPDATE VectorAdmin.SeedRun SET SelectedCount=?,UpdatedCount=?,SkippedCount=?,FailedCount=?,LastKey=?,HeartbeatAt=? WHERE RunId=?',
                 (counts['selected'],counts['updated'],counts['skipped'],counts['failed'],last_key,time.time(),run_id),limit=0)
            rows('UPDATE VectorAdmin.SeedMetrics SET CreatedCount=?,MissingCount=? WHERE RunId=?',(counts['created'],counts['missing'],run_id),limit=0)
    try:
        with namespace(settings.ADMIN_NAMESPACE):
            locked=bool(iris.cls('VectorAdmin.Runtime').SeedLock(lock_key,True))
        if not locked: raise Problem('RUN_CONFLICT','Another task is writing to this vector column.',409)
        with namespace(p['namespace']):
            check_keys(p); ensure_column(p); generator_hash=generator_fingerprint(p); cursor=None
            while True:
                sql='SELECT TOP 100 '+identifier(p['sourceKey'])+','+identifier(p['sourceText'])+' FROM '+source
                args=[]
                if cursor is not None: sql+=' WHERE '+identifier(p['sourceKey'])+'>?'; args=[cursor]
                batch=rows(sql+' ORDER BY '+identifier(p['sourceKey']),args,limit=101,timeout=120)
                if not batch: break
                for source_key, text_value in batch:
                    counts['selected']+=1; cursor=source_key; last_key=str(source_key)
                    try:
                        destination=rows('SELECT CASE WHEN '+column+' IS NULL THEN 0 ELSE 1 END FROM '+target+' WHERE '+key+'=?',(source_key,),limit=2)
                        if not destination:
                            counts['missing']+=1; counts['skipped']+=1; continue
                        if len(destination)!=1: raise Problem('INVALID_RELATION','Multiple destination rows match.',422)
                        if text_value is None: counts['skipped']+=1; continue
                        present=bool(destination[0][0]); key_hash=digest([type(source_key).__name__,source_key]); source_hash=digest(text_value)
                        with namespace(settings.ADMIN_NAMESPACE):
                            previous=rows('SELECT SourceHash,GeneratorHash FROM VectorAdmin.SeedRow WHERE RecipeId=? AND KeyHash=?',(item['id'],key_hash),limit=1)
                        if not should_generate(policy,present,previous[0] if previous else None,source_hash,generator_hash):
                            counts['skipped']+=1; continue
                        # Python output is validated before starting the write transaction.
                        vector=_generate_python(p['pythonCode'],{'key':source_key,'text':text_value},p['dimensions']) if p['generationMode']=='PYTHON' else None
                        iris.cls('VectorAdmin.Runtime').SeedBegin()
                        try:
                            expression='TO_VECTOR(?,DOUBLE)' if vector is not None else 'EMBEDDING(?,?)'
                            values=[vector] if vector is not None else [str(text_value),p['config']]
                            result=iris.sql.exec('UPDATE '+target+' SET '+column+'='+expression+' WHERE '+key+'=?',*values,source_key)
                            if int(result.ResultSet._SQLCODE)<0 or int(result.ResultSet._ROWCOUNT)!=1:
                                raise Problem('TARGET_CHANGED','The destination row could not be updated.',409)
                            with namespace(settings.ADMIN_NAMESPACE):
                                if previous:
                                    rows('UPDATE VectorAdmin.SeedRow SET SourceHash=?,GeneratorHash=?,UpdatedAt=? WHERE RecipeId=? AND KeyHash=?',
                                         (source_hash,generator_hash,time.time(),item['id'],key_hash),limit=0)
                                else:
                                    rows('INSERT INTO VectorAdmin.SeedRow (RecipeId,KeyHash,SourceHash,GeneratorHash,UpdatedAt) VALUES (?,?,?,?,?)',
                                         (item['id'],key_hash,source_hash,generator_hash,time.time()),limit=0)
                            iris.cls('VectorAdmin.Runtime').SeedCommit()
                        except Exception:
                            iris.cls('VectorAdmin.Runtime').SeedRollback(); raise
                        counts['updated' if present else 'created']+=1
                    except Exception:
                        counts['failed']+=1
                        error='One or more rows failed generation or persistence; source text and vectors are not logged.'
                progress()
        final='SUCCEEDED_WITH_ERRORS' if counts['failed'] else 'SUCCEEDED'
    except Exception as exc:
        error=exc.message if isinstance(exc,Problem) else 'The run failed. Inspect the published source and target definitions.'
        raise
    finally:
        try:
            progress()
            with namespace(settings.ADMIN_NAMESPACE):
                rows('UPDATE VectorAdmin.SeedRun SET State=?,FinishedAt=?,HeartbeatAt=?,ErrorSummary=? WHERE RunId=?',(final,time.time(),time.time(),error,run_id),limit=0)
        finally:
            if locked:
                with namespace(settings.ADMIN_NAMESPACE): iris.cls('VectorAdmin.Runtime').SeedLock(lock_key,False)
    return {'id':run_id,'state':final,**counts}
