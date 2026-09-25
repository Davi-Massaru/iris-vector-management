import iris
for obj in ['VectorFixture.Raw','"VectorFixture"."Raw"']:
    for action in ['s','a']:
        result=iris.cls('%SYSTEM.SQL').CheckPriv('irisowner',obj,action,'USER')
        print(obj,action,repr(result),iris.system.Status.GetErrorText(result))
print('security',list(iris.sql.exec("SELECT Name,FormalSpec FROM %Dictionary.CompiledMethod WHERE parent='%SYSTEM.SQL.Security' AND Name LIKE 'Check%'")))
print('columns',list(iris.sql.exec("SELECT p.parent,p.Name,p.Type,c.SqlSchemaName,c.SqlTableName FROM %Dictionary.CompiledProperty p JOIN %Dictionary.CompiledClass c ON p.parent=c.Name WHERE p.Type IN ('%Library.Vector','%Library.Embedding')")))
