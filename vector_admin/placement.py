import re

def unresolved(reason, evidence=None):
    return {'database': 'Unresolved', 'directory': 'Unresolved', 'reason': reason, 'evidence': evidence or []}

def resolve_global(location, default, mappings, databases):
    if not location or not re.fullmatch(r'\^[%A-Za-z][A-Za-z0-9.]*', location):
        return unresolved('Storage location is missing or uses unsupported expressions/subscripts.', [location])
    name = location[1:]
    candidates = []
    for mapping in mappings:
        pattern = mapping.get('Name', '')
        base = pattern.split('(')[0]
        matches = base == name or base.endswith('*') and name.startswith(base[:-1])
        # Do not assume precedence for range/subscript mappings.
        if matches and (mapping.get('Subscript') or '(' in pattern):
            return unresolved('Subscript mappings require a more specific storage proof.', [mapping])
        if ':' in pattern or '-' in pattern:
            return unresolved('Range mapping precedence has not been validated.', [mapping])
        if matches:
            candidates.append(mapping)
    if len(candidates) > 1:
        return unresolved('Overlapping mappings require a precedence proof.', candidates)
    database = candidates[0].get('Database') if candidates else default
    record = next((r for r in databases if r.get('Name') == database), None)
    if not record:
        return unresolved('Mapped database is absent from administrative inventory.', candidates)
    return {'database': database, 'directory': record.get('Directory') or 'Unresolved',
            'evidence': candidates or [{'namespaceDefault': default}], 'global': location}

def inspect(asset, client):
    ns = asset['namespace']
    defaults = client.get('/v2/namespace', name=ns)
    mappings = client.get('/v2/namespace/global-mappings', namespace=ns, maxRows=1001)
    databases = client.get('/v2/databases', maxRows=1001)
    packages = client.get('/v2/namespace/package-mappings', namespace=ns, maxRows=1001)
    routines = client.get('/v2/namespace/routine-mappings', namespace=ns, maxRows=1001)
    if any(len(x)>1000 for x in (mappings,databases,packages,routines)):
        return {'state':'Unresolved','reason':'Administrative mapping inventory was truncated.'}
    result = {'namespace':ns,'defaultGlobals':defaults.get('Globals','Unresolved'),
              'defaultRoutines':defaults.get('Routines','Unresolved'), 'locations':{},
              'code':unresolved('Routine and package precedence has not been proven.', packages+routines)}
    if len(asset['storage']) != 1 or asset['storage'][0]['type'] != '%Storage.Persistent':
        result['state']='Unresolved'
        result['reason']='Custom, projected or multiple storage definitions are not resolved.'
        return result
    for kind in ['data','id','index','stream']:
        result['locations'][kind] = resolve_global(asset['storage'][0][kind],defaults.get('Globals'),mappings,databases)
    if not packages and not routines:
        db = next((x for x in databases if x['Name']==defaults.get('Routines')),None)
        if db:
            result['code']={'database':db['Name'],'directory':db.get('Directory','Unresolved'),'evidence':['No package or routine mappings; namespace routine default.']}
    result['state']='Partial' if any(x.get('database')=='Unresolved' for x in result['locations'].values()) else 'Resolved'
    return result
