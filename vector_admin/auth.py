import base64
import hashlib
import hmac
import json
import secrets
import time
from contextvars import ContextVar
from .errors import Problem
from . import settings

_request_principal = ContextVar('vector_admin_principal', default=None)

def begin_request(environ):
    try:
        scheme,encoded=environ.get('HTTP_AUTHORIZATION','').split(' ',1)
        username=base64.b64decode(encoded,validate=True).decode().split(':',1)[0]
        if scheme.lower()!='basic' or not username: raise ValueError()
        return _request_principal.set(username)
    except (ValueError,UnicodeError):
        return _request_principal.set(None)

def end_request(token):
    _request_principal.reset(token)

def principal():
    request_user=_request_principal.get()
    if request_user:
        return request_user
    import iris
    user = str(iris.system.Process.UserName())
    if not user or user.lower() == 'unknownuser':
        raise Problem('MISSING_PRIVILEGE', 'An authenticated portal operator is required.', 401)
    return user

def allowed(resource, user=None):
    import iris
    return bool(int(iris.cls('%SYSTEM.Security').CheckUserPermission(user or principal(), resource, 'U')))

def require(resource='VectorAdmin_Read'):
    user = principal()
    if not allowed(resource, user):
        raise Problem('MISSING_PRIVILEGE', 'This action requires ' + resource + '.', 403)
    return user

def scope(instance, namespace):
    if instance != settings.INSTANCE or namespace not in settings.NAMESPACES:
        raise Problem('MISSING_PRIVILEGE', 'The requested instance or namespace is outside the configured scope.', 403)

def secret():
    import os
    from pathlib import Path
    # Provisioned once at install; shared by every WSGI worker, never browser-visible.
    path = Path(os.getenv('VECTOR_ADMIN_KEY_FILE', '/usr/irissys/mgr/vector-admin.key'))
    if not path.is_file():
        raise Problem('UNSUPPORTED_VERSION', 'Portal signing key has not been provisioned.', 503)
    return path.read_bytes()

def token(data, ttl=900):
    raw = json.dumps({**data, 'expires': int(time.time()) + ttl}, sort_keys=True, separators=(',', ':')).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip('=')
    signature = hmac.new(secret(), body.encode(), hashlib.sha256).hexdigest()
    return body + '.' + signature

def verify(value, kind):
    try:
        body, signature = value.split('.')
        expected = hmac.new(secret(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
        if data['expires'] < time.time() or data['kind'] != kind or data['actor'] != principal():
            raise ValueError()
        return data
    except (ValueError, KeyError, TypeError):
        raise Problem('INVALID_TOKEN', 'The request token is invalid or expired. Refresh and try again.', 403)

def csrf(environ):
    verify(environ.get('HTTP_X_CSRF_TOKEN', ''), 'csrf')
    origin = environ.get('HTTP_ORIGIN')
    expected = environ.get('wsgi.url_scheme', 'http') + '://' + environ.get('HTTP_HOST', '')
    if origin and origin != expected:
        raise Problem('CSRF_REJECTED', 'The request origin does not match this application.', 403)
