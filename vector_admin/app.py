"""Small same-origin WSGI router, loaded by IRIS Embedded Python only."""
import json
import re
from http import HTTPStatus
from urllib.parse import parse_qs,unquote
from . import auth,settings,catalog,capabilities,explorer,search,indexes,configs,placement,audit,tasks,recipes
from .errors import Problem
from .sql import namespace,integer
from .sysadmin_client import SysAdmin

SECURITY_HEADERS=[('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),
                  ('Referrer-Policy','no-referrer'),('X-Frame-Options','DENY'),
                  ('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")]

def json_body(environ):
    length=integer(environ.get('CONTENT_LENGTH') or '0',1,settings.MAX_BODY,'Body size')
    if environ.get('CONTENT_TYPE','').split(';')[0]!='application/json':
        raise Problem('INVALID_BODY','Use an application/json request body.',415)
    try:
        body=json.loads(environ['wsgi.input'].read(length),parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(body,dict):
            raise ValueError()
        return body
    except (ValueError,UnicodeError):
        raise Problem('INVALID_BODY','The JSON body must be a valid object.')

def dispatch(environ):
    auth.require()
    method=environ.get('REQUEST_METHOD','GET')
    path=environ.get('PATH_INFO','/')
    prefix=environ.get('SCRIPT_NAME','').rstrip('/')
    # IRIS releases differ in whether the web-application prefix is exposed
    # through SCRIPT_NAME or retained in PATH_INFO.
    for candidate in (prefix, '/vector-admin'):
        if candidate and (path == candidate or path.startswith(candidate + '/')):
            path=path[len(candidate):] or '/'
            break
    query={k:v[-1] for k,v in parse_qs(environ.get('QUERY_STRING',''),keep_blank_values=True).items()}
    if method=='GET' and path in ('','/'):
        return (settings.ROOT/'vector_admin/static/index.html').read_bytes(),'text/html; charset=utf-8',200
    if method=='GET' and path in ('/assets/script','/assets/style'):
        name,content_type=('app.js','application/javascript') if path.endswith('script') else ('app.css','text/css')
        file=settings.ROOT/'vector_admin/static'/name
        payload=file.read_bytes()
        if name=='app.js':
            # IRIS WSGI may transcode bytes above ASCII. JS escapes preserve labels.
            payload=payload.decode('utf-8').encode('ascii',errors='backslashreplace')
        return payload,content_type+'; charset=utf-8',200
    if method not in ('GET','POST'):
        raise Problem('METHOD_NOT_ALLOWED','This method is not supported.',405)
    if method=='POST':
        auth.csrf(environ)
    if path=='/api/capabilities' and method=='GET':
        return capabilities.inspect()
    match=re.fullmatch(r'/api/instances/([^/]+)/namespaces',path)
    if match and method=='GET':
        if match[1]!=settings.INSTANCE:
            raise Problem('NOT_FOUND','Instance not found.',404)
        results=SysAdmin(environ).get('/v2/namespaces',maxRows=1001)
        return {'items':[{'name':r['Name'],'defaultGlobals':r.get('Globals'),'defaultRoutines':r.get('Routines')}
                         for r in results if r['Name'] in settings.NAMESPACES]}
    match=re.fullmatch(r'/api/instances/([^/]+)/namespaces/([^/]+)/vectors',path)
    if match and method=='GET':
        ns=unquote(match[2])
        auth.scope(match[1],ns)
        capabilities.require_verified()
        return catalog.discover(ns,query.get('after',''),integer(query.get('size',25),1,100,'Page size'),
                                query.get('schema',''),query.get('type',''),query.get('indexed',''))
    match=re.fullmatch(r'/api/instances/([^/]+)/embedding-configs',path)
    if match and method=='GET':
        ns=query.get('namespace','')
        auth.scope(match[1],ns)
        with namespace(ns):
            return {'items':configs.list_configs()}
    match=re.fullmatch(r'/api/instances/([^/]+)/source-tables',path)
    if match and method=='GET':
        ns=query.get('namespace','')
        auth.scope(match[1],ns)
        return catalog.source_tables(ns)
    match=re.fullmatch(r'/api/vectors/([^/]+)(.*)',path)
    if match:
        capabilities.require_verified()
        asset=catalog.lookup(match[1])
        suffix=match[2]
        with namespace(asset['namespace']):
            if method=='GET' and suffix=='':
                try:
                    asset['placement']=placement.inspect(asset,SysAdmin(environ))
                except Problem as exc:
                    asset['placement']={'state':'Unresolved','reason':exc.message,'code':exc.code}
                return asset
            if method=='GET' and suffix=='/rows':
                return explorer.page(asset,integer(query.get('size',25),1,100,'Page size'),query.get('after'))
            preview=re.fullmatch(r'/rows/([^/]+)/preview',suffix)
            if method=='GET' and preview:
                return explorer.preview(asset,unquote(preview[1]))
            if method=='POST' and suffix=='/search':
                return search.execute(asset,json_body(environ))
            if method=='POST' and suffix=='/indexes/preflight':
                audit.record('index.preflight.request',asset['catalogKey'],'ATTEMPT')
                return indexes.preflight(asset,json_body(environ))
    if method=='POST' and path=='/api/operations':
        audit.record('index.execute.request','operation','ATTEMPT')
        return indexes.execute(json_body(environ))
    match=re.fullmatch(r'/api/operations/([a-f0-9]{32})',path)
    if match and method=='GET':
        return indexes.get(match[1])
    if path=='/api/vector-recipes':
        if method=='GET': return recipes.list_recipes()
        if method=='POST': return recipes.create_draft(json_body(environ))
    if path=='/api/python/validate' and method=='POST':
        auth.require('VectorAdmin_Maintain')
        from .generators import validate
        return validate(json_body(environ).get('code'))
    if path=='/api/python/test' and method=='POST':
        return recipes.test_python(json_body(environ))
    match=re.fullmatch(r'/api/vector-recipes/([a-f0-9]{32})/(preflight|publish|schedules)',path)
    if match and method=='POST':
        if match[2]=='preflight': return recipes.preflight(match[1])
        if match[2]=='publish': return recipes.publish(match[1],json_body(environ))
        return recipes.create_schedule(match[1],json_body(environ),SysAdmin(environ))
    if path=='/api/seed-runs' and method=='GET':
        return recipes.list_runs(query.get('taskId'))
    if path=='/api/schedules/status' and method=='GET':
        return tasks.inventory(SysAdmin(environ),integer(query.get('size',100),1,100,'Page size'))
    match=re.fullmatch(r'/api/schedules/(\d+)',path)
    if match and method=='GET':
        return tasks.detail(SysAdmin(environ),match[1],integer(query.get('size',50),1,100,'Page size'))
    match=re.fullmatch(r'/api/schedules/(\d+)/run',path)
    if match and method=='POST':
        return tasks.run_now(SysAdmin(environ),match[1])
    raise Problem('NOT_FOUND','The requested resource was not found.',404)

def application(environ,start_response):
    budget=None
    principal_token=auth.begin_request(environ)
    try:
        auth.require()
        import iris
        request_path=environ.get('PATH_INFO','')
        request_budget=120 if re.search(r'/api/vector-recipes/[a-f0-9]{32}/preflight$',request_path) else settings.QUERY_SECONDS
        budget=iris.cls('VectorAdmin.Runtime').BeginBudget(request_budget)
        result=dispatch(environ)
        if isinstance(result,tuple):
            payload,content_type,status=result
        else:
            payload=json.dumps(result,ensure_ascii=True,allow_nan=False,default=str).encode()
            content_type,status='application/json; charset=utf-8',200
    except Problem as exc:
        status=exc.status
        payload=json.dumps({'code':exc.code,'message':exc.message}).encode()
        content_type='application/problem+json'
    except Exception:
        status=500
        payload=b'{"code":"INTERNAL_ERROR","message":"The operation could not be completed. Check the installed capability and permission gates."}'
        content_type='application/problem+json'
    finally:
        if budget:
            try:
                iris.cls('VectorAdmin.Runtime').EndBudget(budget)
            except Exception:
                status=503
                payload=b'{"code":"QUERY_LIMIT","message":"Query cancellation is still being finalized."}'
                content_type='application/problem+json'
        auth.end_request(principal_token)
    headers=SECURITY_HEADERS+[('Content-Type',content_type),('Content-Length',str(len(payload)))]
    if status==401:
        headers.append(('WWW-Authenticate','Basic realm="IRIS Vector Admin", charset="UTF-8"'))
    start_response(f'{status} {HTTPStatus(status).phrase}',headers)
    return [payload]
