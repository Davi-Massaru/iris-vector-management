"""Test-only source mutation, invoked through an IRIS session, not a web route."""
import sys
sys.path.insert(0,'/usr/irissys/csp/vector-admin')
sys.path.insert(0,'/usr/irissys/mgr/python')
from vector_admin.documents import seed
seed({'namespace':'USER','action':'append','count':2})
seed({'namespace':'USER','action':'change','count':1})
print('MUTATION_OK')
