import math
from . import settings
from .sql import rows, identifier, table
from .errors import Problem

def key_required(asset):
    if not asset['key']:
        raise Problem('PARTIAL_METADATA', 'Row inspection requires a proven stable key.', 422)

def key_value(asset,value):
    if len(str(value))>256:
        raise Problem('INVALID_KEY','The key exceeds the supported length.')
    if asset['columns'].get(asset['key']) in ('integer','bigint','smallint'):
        try:
            return int(value)
        except (TypeError,ValueError):
            raise Problem('INVALID_KEY','This table requires an integer key.')
    return str(value)

def page(asset, size=25, after=None):
    key_required(asset)
    key = identifier(asset['key'])
    vector = identifier(asset['column'])
    sources = asset['sourceColumns']
    expressions = [key, f'CASE WHEN {vector} IS NULL THEN 0 ELSE 1 END']
    expressions += [f'SUBSTRING({identifier(c)},1,{settings.TEXT_LIMIT})' for c in sources]
    query = f'SELECT TOP {size+1} ' + ','.join(expressions) + ' FROM ' + table(asset)
    args = []
    if after is not None:
        query += f' WHERE {key}>?'
        args.append(key_value(asset,after))
    query += f' ORDER BY {key}'
    data = rows(query,args,limit=size+1)
    return {'items':[{'key':str(r[0]), 'vectorPresent':bool(r[1]), 'dimensions':asset['dimensions'],
                      'source':dict(zip(sources,r[2:])), 'sourceStatus':('Source null' if all(x is None for x in r[2:]) else 'Available') if sources else 'Source unavailable'}
                     for r in data[:size]],'next':str(data[size-1][0]) if len(data)>size else None}

def preview(asset, key):
    key_required(asset)
    if not asset['dimensions'] or asset['dimensions'] > settings.MAX_DIMENSIONS:
        raise Problem('QUERY_LIMIT','A bounded, known vector dimension is required for preview.')
    col=identifier(asset['column'])
    data=rows(f'SELECT %EXTERNAL({col}),VECTOR_DOT_PRODUCT({col},{col}) FROM {table(asset)} WHERE {identifier(asset["key"])}=?',(key_value(asset,key),),limit=1)
    if not data:
        raise Problem('NOT_FOUND','The row is not visible or no longer exists.',404)
    if data[0][0] is None:
        return {'values':[],'norm':None,'state':'Null'}
    values=[float(x.strip()) for x in str(data[0][0]).strip('[]').split(',')]
    return {'values':values[:settings.PREVIEW_VALUES], 'dimensions':len(values),
            'norm':math.sqrt(max(0,float(data[0][1]))), 'truncated':len(values)>settings.PREVIEW_VALUES}
