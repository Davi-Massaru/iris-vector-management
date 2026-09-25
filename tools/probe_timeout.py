import iris
for q in ["SELECT parent,Name FROM %Dictionary.CompiledProperty WHERE Name LIKE '%imeout%' AND parent LIKE '%SQL%'", "SELECT parent,Name,FormalSpec FROM %Dictionary.CompiledMethod WHERE Name LIKE '%imeout%' AND parent LIKE '%SQL%'"]:
    try: print(q,list(iris.sql.exec(q)))
    except Exception as e: print(str(e))
try: print('WSGI import',iris.cls('%SYS.Python.WSGI').ImportWSGIApplication('wsgi','/workspace','application',1))
except Exception as e: print('WSGI import failed',str(e))
