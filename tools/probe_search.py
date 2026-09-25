import sys
sys.path.insert(0,'/workspace')
import iris
from vector_admin import catalog,search
asset=next(a for a in catalog.discover('USER')['items'] if a['table']=='Managed')
query,args=search.build(asset,{'text':'vector search','k':3})
for q in [query,'EXPLAIN '+query]:
    try: print(q,list(iris.sql.exec(q,*(args if not q.startswith('EXPLAIN') else []))))
    except Exception as e: print('FAILED',q,type(e).__name__,str(e))
