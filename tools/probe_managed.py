import iris
import sys
sys.path.insert(0,'/usr/irissys/mgr/python')
for q in ["SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='VectorFixture'", "SELECT Name,Type FROM %Dictionary.CompiledProperty WHERE parent='VectorFixture.Managed'", "SELECT COUNT(*) FROM VectorFixture.Managed", "SELECT Name,Description FROM %Dictionary.CompiledMethod WHERE parent='%SYSTEM.Process' AND Name LIKE '%ime%'", "SELECT Name,FormalSpec FROM %Dictionary.CompiledMethod WHERE parent='%SYS.Python.WSGI' AND Name='ImportWSGIApplication'"]:
    try: print(q,list(iris.sql.exec(q)))
    except Exception as e: print(type(e).__name__,str(e))
prop=iris.cls('%Dictionary.CompiledProperty')._OpenId('VectorFixture.Managed||Embedding')
if not isinstance(prop,str):
    for key in ['LEN','DATATYPE','MODEL','SOURCE','CONFIGURATION','EMBEDDINGCONFIG','SOURCES']:
        print(key,prop.Parameters.GetAt(key))
for q in ["SELECT EMBEDDING('vector search','vector-fixture-local')", "INSERT INTO VectorFixture.Managed (Content) VALUES ('vector search')"]:
    try: print(q,list(iris.sql.exec(q)))
    except Exception as e: print(type(e).__name__,str(e))
