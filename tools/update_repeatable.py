"""Apply additive schema changes and initialize the requested Faker fixture once."""
import sys
import runpy
sys.path.insert(0,'/usr/irissys/csp/vector-admin')
sys.path.insert(0,'/usr/irissys/mgr/python')
runpy.run_path('/usr/irissys/csp/vector-admin/tools/install.py')
from vector_admin.documents import seed
from vector_admin.sql import rows
if not rows("SELECT Name FROM VectorAdmin.FixtureRegistry WHERE Name='USER/data.Document'",limit=1):
    result=seed({'namespace':'USER','action':'append','count':20})
    print('FAKER_DOCUMENTS',result['total'])
print('REPEATABLE_INSTALL_OK')
