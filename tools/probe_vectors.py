import iris
for query in ["SELECT TOP 1 Embedding FROM VectorFixture.Raw", "SELECT TOP 1 TO_CHAR(Embedding) FROM VectorFixture.Raw", "SELECT TOP 1 VECTOR_DOT_PRODUCT(Embedding,Embedding) FROM VectorFixture.Raw"]:
    try:
        rows=list(iris.sql.exec(query))
        print(query, [(type(r[0]).__name__,str(r[0])[:100]) for r in rows])
    except Exception as exc: print(str(exc))
for name in ['%SQL.Statement','%SQL.StatementResult']:
    print(name,list(iris.sql.exec('SELECT Name,Type FROM %Dictionary.PropertyDefinition WHERE parent=? AND Name LIKE ?',name,'%Timeout%')))
print('user',iris.system.Process.UserName())
for parent in ['%SYSTEM.Security','%SYSTEM.SQL','%SYSTEM.SQL.Util','%Library.Vector']:
    print(parent,list(iris.sql.exec('SELECT Name,FormalSpec FROM %Dictionary.MethodDefinition WHERE parent=?',parent)))
