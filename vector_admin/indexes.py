import hashlib
import json
import re
import time
import uuid
from . import auth,settings,catalog,audit,capabilities
from .errors import Problem
from .sql import identifier,table,rows,namespace,integer

def proposal(asset,body):
    import iris
    capabilities.require_verified()
    reasons=[]
    if not asset['dimensions'] or asset['elementType'] not in ('DOUBLE','DECIMAL'):
        reasons.append('HNSW requires a fixed-length DOUBLE or DECIMAL column on this build.')
    if not asset['bitmapIds']:
        reasons.append('Bitmap-supported integer IDs were not proven.')
    if len(asset['storage'])!=1 or asset['storage'][0]['type']!='%Storage.Persistent':
        reasons.append('Default persistent table storage is required.')
    if asset['indexes']:
        reasons.append('This column already has an HNSW index.')
    distance=body.get('distance','Cosine')
    if distance not in ('Cosine','DotProduct'):
        reasons.append('The distance function is unsupported.')
    if distance=='DotProduct' and body.get('normalized') is not True:
        reasons.append('DotProduct requires an explicit normalized-vectors claim.')
    name=body.get('name','')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',name):
        reasons.append('Index name must contain 1–64 letters, digits or underscores and start with a letter.')
    if str(iris.cls('%SYSTEM.SQL.Security').CheckPrivilege(auth.principal(),1,table(asset),'a',asset['namespace'])) != '1':
        reasons.append('ALTER permission on the table is required.')
    if name and rows('SELECT Name FROM %Dictionary.CompiledIndex WHERE parent=? AND (Name=? OR SqlName=?)',(asset['class'],name,name)):
        reasons.append('The requested index name is already in use.')
    # Deliberately support the single fixture-validated profile until wider bounds are proven.
    if body.get('M',24)!=24 or body.get('efConstruction',100)!=100:
        reasons.append('Only the validated profile M=24, efConstruction=100 is enabled.')
    if reasons:
        raise Problem('INDEX_INELIGIBLE',' '.join(reasons),422)
    ddl=f'CREATE INDEX {identifier(name)} ON TABLE {table(asset)} ({identifier(asset["column"])}) AS HNSW(Distance=\'{distance}\', M=24, efConstruction=100)'
    return {'name':name,'distance':distance,'M':24,'efConstruction':100,'normalized':body.get('normalized') is True,'ddl':ddl}

def preflight(asset,body):
    auth.require('VectorAdmin_Maintain')
    target=f'{asset["instance"]}/{asset["namespace"]}/{asset["schema"]}.{asset["table"]}/{asset["column"]}'
    try:
        proposed=proposal(asset,body)
    except Problem as exc:
        audit.record('index.preflight',target,'FAILED',{'code':exc.code})
        raise
    operation=uuid.uuid4().hex
    now=time.time()
    payload={'asset':asset['id'],'proposal':proposed,'target':target,'fingerprint':asset['fingerprint']}
    with namespace(settings.ADMIN_NAMESPACE):
        rows('INSERT INTO VectorAdmin.Operation (OperationId,Actor,State,CreatedAt,UpdatedAt,ExpiresAt,Payload,Outcome) VALUES (?,?,?,?,?,?,?,?)',
             (operation,auth.principal(),'PREPARED',now,now,now+300,json.dumps(payload),'{}'),limit=0)
    audit.record('index.preflight',target,'PREPARED',{'operation':operation,'fingerprint':asset['fingerprint']})
    return {'id':operation,'token':auth.token({'kind':'operation','actor':auth.principal(),'id':operation},300),
            'target':target,'proposal':proposed,'expiresAt':now+300}

def get(operation):
    if not re.fullmatch('[a-f0-9]{32}',operation):
        raise Problem('NOT_FOUND','Operation not found.',404)
    with namespace(settings.ADMIN_NAMESPACE):
        result=rows('SELECT Actor,State,CreatedAt,UpdatedAt,ExpiresAt,Payload,Outcome FROM VectorAdmin.Operation WHERE OperationId=?',(operation,),limit=1)
    if not result or result[0][0]!=auth.principal():
        raise Problem('NOT_FOUND','Operation not found.',404)
    actor,state,created,updated,expires,payload,outcome=result[0]
    if state=='RUNNING' and time.time()-float(updated)>180:
        # Never retry or declare failure solely because an operation timed out.
        state='UNKNOWN'
    return {'id':operation,'actor':actor,'state':state,'createdAt':created,'updatedAt':updated,
            'expiresAt':expires,'payload':json.loads(payload),'outcome':json.loads(outcome)}

def execute(body):
    import iris
    auth.require('VectorAdmin_Maintain')
    signed=auth.verify(body.get('token',''),'operation')
    operation=get(signed['id'])
    audit.record('index.execute',operation['payload']['target'],'ATTEMPT',{'operation':operation['id']})
    if body.get('confirmation')!=operation['payload']['target']:
        raise Problem('CONFIRMATION_REQUIRED','Type the exact target shown in the preview.',409)
    if operation['state']!='PREPARED' or float(operation['expiresAt'])<time.time():
        raise Problem('INVALID_OPERATION','This proposal is expired or has already been submitted.',409)
    asset=catalog.lookup(operation['payload']['asset'])
    if asset['fingerprint']!=operation['payload']['fingerprint']:
        audit.record('index.execute',operation['payload']['target'],'FAILED',{'code':'CATALOG_CHANGED','operation':operation['id']})
        raise Problem('CATALOG_CHANGED','Catalog changed. Prepare a new proposal.',409)
    with namespace(settings.ADMIN_NAMESPACE):
        # The UPDATE is the atomic single-use claim across all WSGI processes.
        statement=iris.cls('%SQL.Statement')._New()
        status=statement._Prepare("UPDATE VectorAdmin.Operation SET State='RUNNING',UpdatedAt=? WHERE OperationId=? AND State='PREPARED'")
        if str(status)!='1':
            raise Problem('OPERATION_FAILED','Unable to prepare the operation claim.',503)
        result=statement._Execute(time.time(),operation['id'])
        if int(result._SQLCODE)<0 or int(result._ROWCOUNT)!=1:
            raise Problem('INVALID_OPERATION','This operation has already been claimed.',409)
        try:
            pid=iris.cls('VectorAdmin.Runtime').StartOperation(operation['id'])
        except Exception:
            update(operation['id'],'UNKNOWN',{'code':'WORKER_START_UNCERTAIN'})
            raise Problem('OPERATION_UNKNOWN','Worker start is uncertain. Inspect this operation; do not retry.',503)
    return {'id':operation['id'],'state':'RUNNING'}

def update(operation,state,outcome):
    with namespace(settings.ADMIN_NAMESPACE):
        rows('UPDATE VectorAdmin.Operation SET State=?, UpdatedAt=?, Outcome=? WHERE OperationId=?',
             (state,time.time(),json.dumps(outcome),operation),limit=0)

def run_operation(operation_id):
    import iris
    operation=get(operation_id)
    target=operation['payload']['target']
    locked=False
    issued=False
    try:
        auth.require('VectorAdmin_Maintain')
        locked=bool(int(iris.cls('VectorAdmin.Runtime').MaintenanceLock(1)))
        if not locked:
            raise Problem('QUERY_LIMIT','Another maintenance operation is running.',429)
        asset=catalog.lookup(operation['payload']['asset'])
        if asset['fingerprint']!=operation['payload']['fingerprint']:
            raise Problem('CATALOG_CHANGED','Catalog changed before execution.',409)
        with namespace(asset['namespace']):
            proposed=proposal(asset,operation['payload']['proposal'])
            audit.record('index.create',target,'RUNNING',{'operation':operation_id,'fingerprint':asset['fingerprint']})
            issued=True
            rows(proposed['ddl'],limit=0,timeout=120)
            fresh=catalog.lookup(operation['payload']['asset'])
            found=next((i for i in fresh['indexes'] if i['name']==proposed['name']),None)
            if not found:
                raise Problem('VERIFY_FAILED','Index definition was not found after execution.',500)
            from .search import build,diagnosis
            vector=[1.0]+[0.0]*(asset['dimensions']-1)
            query,args=build(fresh,{'vector':vector,'k':5,'distance':proposed['distance']})
            plan='\n'.join(str(r[0]) for r in rows('EXPLAIN '+query))
            outcome={'index':found,'plan':plan,'diagnosis':diagnosis(plan,fresh)}
            update(operation_id,'SUCCEEDED',outcome)
            audit.record('index.create',target,'SUCCEEDED',{'operation':operation_id,'diagnosis':outcome['diagnosis']})
    except Exception as exc:
        state='UNKNOWN' if issued else 'FAILED'
        code=exc.code if isinstance(exc,Problem) else 'OPERATION_FAILED'
        update(operation_id,state,{'code':code})
        audit.record('index.create',target,state,{'operation':operation_id,'code':code})
    finally:
        if locked:
            iris.cls('VectorAdmin.Runtime').MaintenanceLock(0)
