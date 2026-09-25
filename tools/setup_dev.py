"""Creates credentials only in the disposable development instance."""
import iris
import secrets
from pathlib import Path

directory = Path('/workspace/.local')
directory.mkdir(exist_ok=True)
password = secrets.token_urlsafe(30)
for resource in ['VectorAdmin_Read', 'VectorAdmin_Maintain', 'VectorAdmin_Admin']:
    status = iris.cls('Security.Resources').Create(resource, 'Vector portal permission', '', 0)
    if str(status) != '1' and not iris.cls('Security.Resources').Exists(resource):
        raise RuntimeError('Resource creation failed: ' + iris.system.Status.GetErrorText(status))
status = iris.cls('Security.Roles').Create('VectorAdminReader', 'Portal reader and administrative inventory', 'VectorAdmin_Read:U,%DB_USER:R,%Admin_Manage:U')
if str(status) != '1':
    raise RuntimeError('Reader role creation failed: ' + iris.system.Status.GetErrorText(status))
status = iris.cls('Security.Users').Create('vector_dev', 'VectorAdminReader', password, 'Local portal validation', 'USER', '', '', 0, 1)
if str(status) != '1':
    raise RuntimeError('Development account creation failed: ' + iris.system.Status.GetErrorText(status))
(directory / 'dev-password').write_text(password)
print('Development user created; credential stored in ignored .local/dev-password')
