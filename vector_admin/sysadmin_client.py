"""Only verified GET operations from the pinned SysAdmin contract are callable."""
import base64
import json
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from . import settings
from .errors import Problem

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

class SysAdmin:
    def __init__(self, environ):
        self.authorization = environ.get('HTTP_AUTHORIZATION', '')
        # Forward only the credentials of the current authenticated principal,
        # only to the configured local admin endpoint, never a browser-supplied URL.
        parsed = urlsplit(settings.SYSADMIN_URL)
        if parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.scheme not in ('http', 'https'):
            raise Problem('ADMIN_CONFIGURATION', 'The administrative endpoint must be a configured loopback address.', 503)
        try:
            scheme, encoded = self.authorization.split(' ', 1)
            decoded = base64.b64decode(encoded, validate=True).decode()
            username, separator, password = decoded.partition(':')
            if scheme.lower() != 'basic' or not separator or not username or not password:
                raise ValueError()
        except (ValueError, UnicodeError):
            raise Problem('ADMIN_AUTH_REQUIRED', 'SysAdmin requires verified Basic authentication for the same operator.', 403)

    def get(self, path, **parameters):
        definition = settings.CONTRACT.get(path)
        if not definition:
            raise Problem('ADMIN_CONFIGURATION', 'Administrative operation is not allowlisted.', 503)
        permitted = {p['name'] for p in definition['parameters'] if p['in'] == 'query'}
        required = {p['name'] for p in definition['parameters'] if p.get('required') and p['in'] == 'query'}
        if set(parameters) - permitted or required - set(parameters):
            raise Problem('ADMIN_CONFIGURATION', 'Administrative parameters do not match the pinned contract.', 503)
        url = settings.SYSADMIN_URL.rstrip('/') + path + ('?' + urlencode(parameters) if parameters else '')
        request = Request(url, headers={'Authorization': self.authorization, 'Accept': 'application/json'})
        try:
            with build_opener(NoRedirect()).open(request, timeout=5) as response:
                body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    raise ValueError()
                data = json.loads(body)
                status=data.get('status',{})
                if path != '/info' and ('result' not in data or status.get('errors') or status.get('Errors')):
                    raise ValueError()
                return data if path == '/info' else data['result']
        except (HTTPError, URLError, ValueError, TimeoutError):
            from .audit import record
            record('admin.read', path, 'FAILED', {'code': 'ADMIN_UNAVAILABLE'})
            raise Problem('ADMIN_UNAVAILABLE', 'The administrative request failed. Verify the API, credentials and required privileges.', 503)

    def post(self, path, body, **parameters):
        definition = settings.CONTRACT.get('POST ' + path)
        if not definition or definition.get('method') != 'POST' or not isinstance(body, dict):
            raise Problem('ADMIN_CONFIGURATION','Administrative write is not allowlisted.',503)
        permitted={p['name'] for p in definition.get('parameters',[]) if p['in']=='query'}
        required={p['name'] for p in definition.get('parameters',[]) if p.get('required') and p['in']=='query'}
        if set(parameters)-permitted or required-set(parameters): raise Problem('ADMIN_CONFIGURATION','Administrative parameters do not match the pinned contract.',503)
        url=settings.SYSADMIN_URL.rstrip('/')+path+('?' + urlencode(parameters) if parameters else '')
        request = Request(url,
            data=json.dumps(body).encode(), method='POST', headers={'Authorization':self.authorization,
            'Accept':'application/json','Content-Type':'application/json'})
        try:
            with build_opener(NoRedirect()).open(request,timeout=10) as response:
                data=json.loads(response.read(2_000_001))
                if response.status not in (200,201) or data.get('status',{}).get('Errors'):
                    raise ValueError()
                result=data.get('result',{})
                location=response.headers.get('Location','')
                match=re.search(r'[?&]id=(\d+)',location)
                if isinstance(result,dict) and match and 'Id' not in result:
                    result['Id']=int(match.group(1))
                return result
        except (HTTPError,URLError,ValueError,TimeoutError):
            from .audit import record
            record('admin.write',path,'FAILED',{'code':'ADMIN_UNAVAILABLE'})
            raise Problem('ADMIN_UNAVAILABLE','The administrative task operation failed.',503)
