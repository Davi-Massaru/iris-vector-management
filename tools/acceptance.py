import sys
import os
import time
import json
from pathlib import Path
sys.path.insert(0,'/workspace')
os.environ['HF_HUB_OFFLINE']='1'
import iris
from vector_admin import catalog,explorer,search,indexes,configs
from vector_admin.sql import rows
from vector_admin.errors import Problem

root=Path('/workspace') if Path('/workspace/iris').is_dir() else Path('/usr/irissys/csp/vector-admin')

report={'version':iris.system.Version.GetVersion(),'checks':{}}
assets={a['table']:a for a in catalog.discover('USER')['items']}
managed=assets['Managed']
print('CHECK managed search',flush=True)
result=search.execute(managed,{'text':'vector search','k':3})
assert len(result['items'])==3
report['checks']['managedTextSearch']=True
assert configs.list_configs()
report['checks']['sanitizedConfigs']=True
raw=assets['Unindexed']
print('CHECK index safeguards',flush=True)
before=search.execute(raw,{'vector':[1,0,0],'k':3})
report['checks']['unindexedPlan']=before['diagnosis']
for name in ['WrongType','Variable']:
    try: indexes.preflight(assets[name],{'name':'RejectedHNSW'})
    except Problem as e:
        assert e.code=='INDEX_INELIGIBLE'
        report['checks']['reject'+name]=True
    else: raise AssertionError('Ineligible index accepted')

if not raw['indexes']:
    print('CHECK guarded creation',flush=True)
    prepared=indexes.preflight(raw,{'name':'CreatedHNSW'})
    try: indexes.execute({'token':prepared['token'],'confirmation':'wrong'})
    except Problem as e: assert e.code=='CONFIRMATION_REQUIRED'
    else: raise AssertionError('Wrong target confirmation accepted')
    result=indexes.execute({'token':prepared['token'],'confirmation':prepared['target']})
    deadline=time.time()+30
    while time.time()<deadline:
        operation=indexes.get(result['id'])
        if operation['state']!='RUNNING': break
        time.sleep(.25)
    assert operation['state']=='SUCCEEDED',operation
    report['checks']['guardedCreate']=operation['outcome']['diagnosis']
    try: indexes.execute({'token':prepared['token'],'confirmation':prepared['target']})
    except Problem as e: assert e.code=='INVALID_OPERATION'
    else: raise AssertionError('Operation replay accepted')
    report['checks']['rejectReplay']=True

# Fill a dedicated raw table without fetching source rows or embedding values.
if not list(iris.sql.exec("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='VectorFixture' AND TABLE_NAME='Large'")):
    print('CHECK bounded 500,000-row fixture',flush=True)
    iris.sql.exec('CREATE TABLE VectorFixture.Large (ID INTEGER IDENTITY, Embedding VECTOR(DOUBLE,3))')
    iris.sql.exec("INSERT INTO VectorFixture.Large (Embedding) VALUES (TO_VECTOR('[1,0,0]',DOUBLE))")
    count=1
    while count<500_000:
        take=min(count,500_000-count)
        iris.sql.exec(f'INSERT INTO VectorFixture.Large (Embedding) SELECT TOP {take} Embedding FROM VectorFixture.Large')
        count+=take
asset=next(a for a in catalog.discover('USER')['items'] if a['table']=='Large')
started=time.monotonic()
page=explorer.page(asset)
elapsed=round((time.monotonic()-started)*1000,2)
payload=json.dumps(page).encode()
assert len(page['items'])==25
assert 'values' not in page['items'][0]
second=explorer.page(asset,after=page['next'])
assert int(second['items'][0]['key'])==26
report['checks']['boundedScale']={'rows':500_000,'pageRows':25,'responseBytes':len(payload),'elapsedMs':elapsed}

started=time.monotonic()
status=iris.cls('%SYSTEM.OBJ').Load(str(root/'iris/TestDelay.cls'),'ck')
assert str(status)=='1'
started=time.monotonic()
try:
    print('CHECK cancellation',flush=True)
    delayed=rows('SELECT TOP 40 VectorFixture.TestDelay_Wait(ID) FROM VectorFixture.Large',timeout=1)
    print('DELAY RESULT',len(delayed),round(time.monotonic()-started,2),flush=True)
except Problem:
    elapsed=time.monotonic()-started
    assert elapsed<6,elapsed
    report['checks']['timeoutSeconds']=round(elapsed,2)
else: raise AssertionError('Expensive query was not cancelled')

destination=root/'docs/acceptance-evidence.json'
destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
