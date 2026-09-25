import iris
for name in ['WSGIType','WSGIAppName','WSGICallable','DispatchClass']:
    prop=iris.cls('%Dictionary.PropertyDefinition')._OpenId('Security.Applications||'+name)
    print(name,prop.Description)
    for key in ['VALUELIST','DISPLAYLIST']:
        print(key,prop.Parameters.GetAt(key))
print(list(iris.sql.exec("SELECT Name,NameSpace,Type,AutheEnabled,Enabled,CSPZENEnabled,DispatchClass,WSGIAppName,WSGICallable,WSGIAppLocation,WSGIType,Recurse,Resource FROM Security.Applications WHERE Name='/vector-admin'")))
