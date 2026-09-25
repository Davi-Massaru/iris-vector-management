"""Integration checks executed inside the actual Embedded Python runtime."""
import sys
import json
import io
from pathlib import Path
sys.path.insert(0,'/workspace')
import iris
from vector_admin import catalog,explorer,search,auth,capabilities
from vector_admin.app import application
from vector_admin.sql import rows

print('CAPABILITIES',json.dumps(capabilities.inspect(),default=str))
assets=catalog.discover('USER')['items']
print('ASSETS',[(a['table'],a['type'],a['dimensions'],a['elementType'],a['key']) for a in assets])
assert assets,'No vector assets discovered'
for asset in assets:
    if asset['table'] not in ('Raw','Unindexed','Managed'): continue
    print('ASSET',asset['table'],json.dumps(asset,default=str))
    print('ROWS',explorer.page(asset))
    if asset['table']=='Raw':
        print('PREVIEW',explorer.preview(asset,'1'))
        print('SEARCH',search.execute(asset,{'vector':[1,0,0],'k':3}))
        token=asset['id']
        assert catalog.lookup(token)['fingerprint']==asset['fingerprint']
        response=[]
        payload=b''.join(application({'PATH_INFO':'/api/vectors/'+token+'/rows','REQUEST_METHOD':'GET'},lambda s,h:response.append(s)))
        assert response==['200 OK'],payload
        print('WSGI_ROW_BYTES',len(payload))
print('INTEGRATION_OK')
