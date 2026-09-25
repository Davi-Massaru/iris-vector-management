import iris
import inspect
print('exec',inspect.signature(iris.sql.exec))
print('prepare',inspect.signature(iris.sql.prepare))
print(iris.sql.exec.__doc__)
for q in [
    "SELECT parent,Name,FormalSpec FROM %Dictionary.CompiledMethod WHERE parent IN ('%SQL.Statement','%SQL.StatementResult','%SYSTEM.Process') AND (Name LIKE '%ime%' OR Name LIKE '%imeout%' OR Name LIKE '%Priv%')",
    "SELECT TOP 1 %EXTERNAL(Embedding) FROM VectorFixture.Raw",
]:
    try: print(q,list(iris.sql.exec(q)))
    except Exception as exc: print(str(exc))
try: print('permission',iris.cls('%SYSTEM.Security').CheckUserPermission(iris.system.Process.UserName(),'VectorAdmin_Read','U'))
except Exception as exc: print(str(exc))
