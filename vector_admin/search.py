import json
import math
import re
import time
from . import settings, auth
from .sql import rows,identifier,table,integer
from .errors import Problem

def vector_input(value, dimensions, element_type):
    if not isinstance(value,list) or len(value)!=dimensions or len(value)>settings.MAX_DIMENSIONS:
        raise Problem('INVALID_DIMENSION','Vector length must match the declared dimension.')
    if element_type not in ('DOUBLE','DECIMAL','FLOAT','INTEGER'):
        raise Problem('UNSUPPORTED_VERSION','Vector element type has not been validated.')
    for x in value:
        if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x):
            raise Problem('INVALID_VECTOR','Every vector element must be a finite number.')
        if element_type=='INTEGER' and int(x)!=x:
            raise Problem('INVALID_VECTOR','This asset requires integer vector elements.')
    return json.dumps(value,allow_nan=False,separators=(',',':'))

def build(asset, body):
    k=integer(body.get('k',10),1,settings.MAX_K,'Top K')
    distance=body.get('distance','Cosine')
    if distance not in ('Cosine','DotProduct'):
        raise Problem('INVALID_DISTANCE','Choose Cosine or DotProduct.')
    fn='VECTOR_COSINE' if distance=='Cosine' else 'VECTOR_DOT_PRODUCT'
    if body.get('mode','auto') not in ('auto','indexed'):
        raise Problem('INVALID_MODE','Choose auto or indexed execution.')
    if body.get('mode')=='indexed' and not any(x['distance']==distance for x in asset['indexes']):
        raise Problem('INDEX_INELIGIBLE','No index matches the selected distance.')
    if 'text' in body:
        if not asset['sourceColumns'] or asset['config']=='Unknown':
            raise Problem('SOURCE_UNKNOWN','Text search requires a verified embedding configuration.')
        # IRIS enforces the SQL %USE_EMBEDDING privilege when EMBEDDING executes.
        # It is a SQL privilege, not a Security.Resources permission.
        if not isinstance(body['text'],str) or not 1<=len(body['text'])<=4000:
            raise Problem('QUERY_LIMIT','Query text must contain 1–4,000 characters.')
        expression='EMBEDDING(?, ?)'
        args=[body['text'],asset['config']]
    else:
        expression=f'TO_VECTOR(?, {asset["elementType"]})'
        args=[vector_input(body.get('vector'),asset['dimensions'],asset['elementType'])]
    score=f'{fn}({identifier(asset["column"])},{expression})'
    key=identifier(asset['key']) if asset['key'] else 'NULL'
    query=f'SELECT TOP {k} {key}, {score} AS Score FROM {table(asset)}'
    filters=body.get('filters',[])
    if not isinstance(filters,list) or len(filters)>5:
        raise Problem('QUERY_LIMIT','At most five typed filters are allowed.')
    clauses=[]
    for item in filters:
        column=item.get('column')
        dtype=asset['columns'].get(column)
        op=item.get('operator')
        if column==asset['column'] or dtype not in ('integer','bigint','smallint','varchar') or op not in ('=','>','<','>=','<='):
            raise Problem('INVALID_FILTER','Filter column, type or operator is not allowed.')
        value=item.get('value')
        if dtype=='varchar':
            if not isinstance(value,str) or len(value)>256:
                raise Problem('INVALID_FILTER','Text filter values are limited to 256 characters.')
        elif isinstance(value,bool) or not isinstance(value,int):
            raise Problem('INVALID_FILTER','An integer filter value is required.')
        clauses.append(identifier(column)+op+'?')
        args.append(value)
    if clauses:
        query+=' WHERE '+' AND '.join(clauses)
    query+=' ORDER BY Score DESC'
    return query,args

def diagnosis(plan, asset):
    # Require an actual Read index map line referencing a catalog-proven HNSW index.
    for index in asset['indexes']:
        target=asset['schema']+'.'+asset['table']+'.'+index['name']
        if re.search(r'Read index map\s+'+re.escape(target)+r'[,\s]',plan,re.I):
            return 'HNSW used'
    if re.search(r'Read (master map|extent bitmap)',plan,re.I) and not re.search(r'Read index map',plan,re.I):
        return 'Full scan'
    return 'Undetermined'

def execute(asset,body):
    import iris
    query,args=build(asset,body)
    # IRIS locks span all WSGI processes and are automatically released on process exit.
    slot=int(iris.cls('VectorAdmin.Runtime').SearchSlot())
    if slot<0:
        raise Problem('QUERY_LIMIT','All search slots are in use. Try again shortly.',429)
    try:
        started=time.monotonic()
        # EXPLAIN compiles the parameterized statement; it has no execution bind slots.
        plan='\n'.join(str(r[0]) for r in rows('EXPLAIN '+query,limit=100))
        result=rows(query,args,limit=settings.MAX_K)
        return {'items':[{'key':r[0],'score':r[1]} for r in result], 'elapsedMs':round((time.monotonic()-started)*1000,2),
                'plan':plan,'diagnosis':diagnosis(plan,asset),'sql':query,
                'warning':'Zero vectors are excluded from a Cosine HNSW index.' if body.get('distance','Cosine')=='Cosine' else None}
    finally:
        iris.cls('VectorAdmin.Runtime').ReleaseSearch(slot)
