import hashlib
import json
from . import auth, settings
from .sql import rows, select_privilege, namespace
from .errors import Problem

VECTOR_TYPES = ('%Library.Vector', '%Embedding.Vector', '%Library.Embedding')

def parameters(class_name, property_name, keys, kind='CompiledProperty'):
    import iris
    obj = iris.cls('%Dictionary.' + kind)._OpenId(class_name + '||' + property_name)
    if isinstance(obj,str):
        return {}
    return {k: obj.Parameters.GetAt(k) for k in keys}

def indexes(class_name, property_name):
    result = []
    for name, sql_name, type_class, properties, posint, idkey in rows(
        'SELECT Name, SqlName, TypeClass, Properties, PosInt, IdKey FROM %Dictionary.CompiledIndex WHERE parent=?', (class_name,)):
        if property_name not in str(properties).split(',') or type_class != '%SQL.Index.HNSW':
            continue
        params = parameters(class_name, name, ['Distance', 'M', 'efConstruction'], 'CompiledIndex')
        result.append({'name': sql_name or name, 'className': name, 'typeClass': type_class,
                       'distance': params.get('Distance') or 'Unknown', 'M': params.get('M') or 'Unknown',
                       'efConstruction': params.get('efConstruction') or 'Unknown', 'status': 'Defined'})
    return result

def discover(ns, after='', page_size=25, schema='', kind='', indexed=''):
    auth.scope(settings.INSTANCE, ns)
    output = []
    with namespace(ns):
        # Dictionary declares VECTOR correctly; INFORMATION_SCHEMA reports varchar on 2026.2.
        entries = rows('SELECT TOP 1001 p.parent, p.Name, p.SqlFieldName, p.Type, c.SqlSchemaName, c.SqlTableName '
                       'FROM %Dictionary.CompiledProperty p JOIN %Dictionary.CompiledClass c ON p.parent=c.Name '
                       'WHERE (p.Type = ? OR p.Type = ? OR p.Type = ?) AND p.parent %STARTSWITH ? '
                       'ORDER BY p.parent, p.Name', (*VECTOR_TYPES, ''), limit=1001)
        if len(entries) > 1000:
            raise Problem('QUERY_LIMIT', 'Catalog scope exceeds 1,000 vector columns. Configure a narrower namespace.')
        for cls, prop, field, dtype, sch, tbl in entries:
            if str(cls).startswith('%') or not sch or not tbl:
                continue
            key = str(cls) + '|' + str(prop)
            if key <= after or (schema and sch != schema):
                continue
            asset = build(ns, cls, prop, field, dtype, sch, tbl)
            try:
                select_privilege(asset)
            except Problem:
                continue
            if kind and asset['type'] != kind:
                continue
            if indexed == 'yes' and not asset['indexes'] or indexed == 'no' and asset['indexes']:
                continue
            asset['id'] = auth.token({'kind': 'asset', 'actor': auth.principal(), 'namespace': ns,
                                      'instance': settings.INSTANCE, 'class': cls, 'property': prop}, 3600)
            output.append(asset)
            if len(output) > page_size:
                break
    return {'items': output[:page_size], 'next': output[page_size-1]['catalogKey'] if len(output) > page_size else None,
            'countMethod': 'Unavailable'}

def build(ns, cls, prop, field, dtype, sch, tbl):
    params = parameters(cls, prop, ['LEN', 'DATATYPE', 'MODEL', 'SOURCE', 'CONFIGURATION'])
    dimensions = int(params['LEN']) if str(params.get('LEN', '')).isdigit() else None
    managed = dtype != '%Library.Vector' or bool(params.get('MODEL'))
    source = str(params.get('SOURCE') or '')
    config = params.get('MODEL') or params.get('CONFIGURATION') or 'Unknown'
    storage = rows('SELECT Name, Type, DataLocation, IdLocation, IndexLocation, StreamLocation, SqlRowIdName '
                   'FROM %Dictionary.CompiledStorage WHERE parent=?', (cls,))
    idx = indexes(cls, prop)
    columns = rows('SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=? ORDER BY ORDINAL_POSITION', (sch, tbl))
    idkeys = rows('SELECT Properties,PosInt FROM %Dictionary.CompiledIndex WHERE parent=? AND IdKey=1', (cls,))
    key = None
    if len(idkeys) == 1 and ',' not in str(idkeys[0][0]):
        keyprops = rows('SELECT SqlFieldName,Name FROM %Dictionary.CompiledProperty WHERE parent=? AND Name=?', (cls,idkeys[0][0]))
        if keyprops:
            key = keyprops[0][0] or keyprops[0][1]
    if not key and len(storage)==1 and storage[0][6]:
        key = storage[0][6]
    source_columns = [x.strip() for x in source.split(',') if x.strip()]
    valid_columns = {str(r[0]): str(r[1]) for r in columns}
    if any(x not in valid_columns for x in source_columns):
        source_columns = []
    # General scalar data is opt-in. Only identity and verified embedding sources are selected.
    asset = {'instance': settings.INSTANCE, 'namespace': ns, 'schema': sch, 'table': tbl, 'column': field or prop,
             'class': cls, 'property': prop, 'catalogKey': cls + '|' + prop,
             'type': 'EMBEDDING' if managed else 'VECTOR', 'elementType': params.get('DATATYPE') or 'Unknown',
             'dimensions': dimensions, 'generation': 'Managed' if managed else 'External/Unknown',
             'sourceColumns': source_columns, 'sourceStatus': 'Bound' if source_columns else 'Source unavailable',
             'config': config if managed else 'Unknown', 'model': 'Unknown', 'key': key,
             'columns': valid_columns, 'indexes': idx, 'countMethod': 'Unavailable',
             'bitmapIds': bool(idkeys and idkeys[0][1]),
             'storage': [dict(zip(['name','type','data','id','index','stream','rowId'],r)) for r in storage]}
    if managed and config != 'Unknown':
        from .configs import sanitize
        try:
            config_rows=rows('SELECT EmbeddingClass,Configuration FROM %Embedding.Config WHERE Name=?',(config,),limit=1)
            if config_rows:
                asset['provider']=config_rows[0][0]
                asset['model']=sanitize(config_rows[0][1]).get('modelName','Unknown')
        except Problem:
            asset['provider']='Unknown'
    asset['fingerprint'] = hashlib.sha256(json.dumps(asset,sort_keys=True,default=str).encode()).hexdigest()
    return asset

def lookup(handle):
    payload = auth.verify(handle, 'asset')
    auth.scope(payload['instance'], payload['namespace'])
    with namespace(payload['namespace']):
        entry = rows('SELECT p.parent,p.Name,p.SqlFieldName,p.Type,c.SqlSchemaName,c.SqlTableName '
                     'FROM %Dictionary.CompiledProperty p JOIN %Dictionary.CompiledClass c ON p.parent=c.Name '
                     'WHERE p.parent=? AND p.Name=?', (payload['class'],payload['property']), limit=1)
        if not entry or entry[0][3] not in VECTOR_TYPES:
            raise Problem('CATALOG_CHANGED', 'The vector asset no longer matches the catalog.', 409)
        asset = build(payload['namespace'], *entry[0])
        select_privilege(asset)
        asset['id'] = handle
        return asset

def source_tables(ns):
    """Return application tables that have one usable, stable scalar key."""
    auth.scope(settings.INSTANCE, ns)
    output=[]
    with namespace(ns):
        tables=rows("SELECT TOP 101 TABLE_SCHEMA,TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' AND TABLE_SCHEMA <> 'VectorAdmin' ORDER BY TABLE_SCHEMA,TABLE_NAME",limit=101)
        for schema,table_name in tables:
            class_name=str(schema)+'.'+str(table_name)
            columns=rows('SELECT COLUMN_NAME,DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=? ORDER BY ORDINAL_POSITION',(schema,table_name),limit=201)
            key=next((str(c[0]) for c in columns if str(c[0]).upper()=='ID'),None)
            if not key:
                key=next((str(c[0]) for c in columns if str(c[0]).upper().endswith('ID')),None)
            if key:
                output.append({'schema':schema,'table':table_name,'class':class_name,'key':key,
                               'columns':[{'name':c[0],'type':c[1]} for c in columns]})
    return {'items':output}
