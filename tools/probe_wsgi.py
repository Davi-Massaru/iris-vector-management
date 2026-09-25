import iris
for q in [
    "SELECT Name,DefaultValue FROM %Dictionary.ParameterDefinition WHERE parent='Security.Datatype.ApplicationType'",
    "SELECT Name,Type FROM %Dictionary.PropertyDefinition WHERE parent='%Dictionary.ParameterDefinition'",
    "SELECT Name,Description,InitialExpression FROM %Dictionary.PropertyDefinition WHERE parent='Security.Applications' AND Name IN ('Type','WSGIType','CSPZENEnabled')",
    "SELECT Name,FormalSpec FROM %Dictionary.MethodDefinition WHERE parent='Security.Users' AND Name IN ('Create','Modify')",
    "SELECT parent,Name,FormalSpec FROM %Dictionary.MethodDefinition WHERE parent IN ('Security.Resources','Security.Roles') AND Name='Create'",
    "SELECT Name FROM %Dictionary.ParameterDefinition WHERE parent='Security.Datatype.ApplicationType'",
    "SELECT Name,SqlFieldName FROM %Dictionary.CompiledProperty WHERE parent='%Dictionary.ParameterDefinition' AND Name='Default'",
    "SELECT Name,Type,CSPZENEnabled,WSGIType,WSGIAppName,WSGIAppLocation FROM Security.Applications WHERE Name='/vector-admin'",
]:
    try: print(q, list(iris.sql.exec(q)))
    except Exception as e: print(str(e))
for name in ['VALUELIST', 'DISPLAYLIST']:
    obj = iris.cls('%Dictionary.ParameterDefinition')._OpenId('Security.Datatype.ApplicationType||' + name)
    if obj: print(name, obj.Default)
