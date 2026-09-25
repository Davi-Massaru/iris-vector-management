import iris
from pathlib import Path
password=Path('/workspace/.local/dev-password').read_text()
print('Login',iris.cls('%SYSTEM.Security').Login('vector_dev',password))
print('Identity',iris.system.Process.UserName())
try:
    function=iris.cls('%SYS.Python.WSGI').ImportWSGIApplication('wsgi','/usr/irissys/csp/vector-admin/','application',1)
    print('Module import',type(function).__name__)
except Exception as exc:
    print('Import failed',type(exc).__name__,str(exc)[:300])
