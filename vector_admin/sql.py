from contextlib import contextmanager
from .errors import Problem
from . import settings

def identifier(value):
    if not isinstance(value, str) or not value or len(value) > 128 or any(ord(c) < 32 for c in value):
        raise Problem('INVALID_IDENTIFIER', 'Invalid catalog identifier.')
    return '"' + value.replace('"', '""') + '"'

def table(asset):
    return identifier(asset['schema']) + '.' + identifier(asset['table'])

def integer(value, minimum, maximum, name):
    if isinstance(value, bool) or not str(value).isdigit():
        raise Problem('QUERY_LIMIT', name + ' must be an integer.')
    result = int(value)
    if result < minimum or result > maximum:
        raise Problem('QUERY_LIMIT', f'{name} must be between {minimum} and {maximum}.')
    return result

@contextmanager
def namespace(name):
    import iris
    previous = iris.system.Process.NameSpace()
    try:
        iris.system.Process.NameSpace(name)
        yield
    finally:
        iris.system.Process.NameSpace(previous)

def rows(query, args=(), limit=1001, timeout=settings.QUERY_SECONDS):
    import iris
    budget = iris.cls('VectorAdmin.Runtime').BeginBudget(timeout)
    try:
        result = iris.sql.exec(query, *args)
        output = []
        for row in result:
            if len(output) >= limit:
                raise Problem('QUERY_LIMIT', 'The result exceeded the server limit. Narrow the scope.')
            output.append(list(row))
        if int(result.ResultSet._SQLCODE)<0:
            raise Problem('QUERY_LIMIT','IRIS cancelled the query or its execution limit was reached.',422)
        return output
    except Problem:
        raise
    except Exception:
        raise Problem('QUERY_FAILED', 'IRIS rejected the query or its execution limit was reached.', 422)
    finally:
        iris.cls('VectorAdmin.Runtime').EndBudget(budget)

def select_privilege(asset):
    import iris
    from .auth import principal
    if str(iris.cls('%SYSTEM.SQL.Security').CheckPrivilege(principal(), 1, table(asset), 's', asset['namespace'])) != '1':
        raise Problem('MISSING_PRIVILEGE', 'SELECT permission is required on this table.', 403)
