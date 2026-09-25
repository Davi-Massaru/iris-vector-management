import iris
for q in [
    "SELECT Name FROM %Dictionary.ClassDefinition WHERE Name LIKE '%WSGI%'",
    "SELECT Name,Description FROM %Dictionary.MethodDefinition WHERE parent='%SYS.Python.WSGI'",
    "SELECT Name,_Default FROM %Dictionary.ParameterDefinition WHERE parent='%SYS.Python.WSGI'",
    "SELECT Name,AutheEnabled,DispatchClass,WSGIType,WSGIAppName FROM Security.Applications WHERE Name='/vector-admin'",
]:
    try: print(q,list(iris.sql.exec(q)))
    except Exception as e: print(str(e))
for method in ['DispatchREST','ImportWSGIApplication','Page','Login']:
    obj=iris.cls('%Dictionary.MethodDefinition')._OpenId('%SYS.Python.WSGI||'+method)
    if obj: print(method, obj.Implementation.Read(24000))
