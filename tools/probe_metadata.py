import iris
for class_name, identifier in [('%Dictionary.CompiledProperty','VectorFixture.Raw||Embedding'),('%Dictionary.CompiledIndex','VectorFixture.Raw||RawHNSW')]:
    obj = iris.cls(class_name)._OpenId(identifier)
    print(class_name, 'parameters', obj.Parameters.Count())
    for k in ['LEN','DATATYPE','TYPE','ELEMENTTYPE','DISTANCE','Distance','M','EFCONSTRUCTION','efConstruction']:
        print(k, obj.Parameters.GetAt(k))
for q in [
    "SELECT Name,TypeClass,Properties,PosInt FROM %Dictionary.CompiledIndex WHERE parent='VectorFixture.Raw'",
    "SELECT Name,SqlRowIdName,SqlRowIdProperty FROM %Dictionary.CompiledStorage WHERE parent='VectorFixture.Raw'",
    "SELECT TOP 1 VECTOR_DIMENSION(Embedding),VECTOR_NORM(Embedding) FROM VectorFixture.Raw",
    "SELECT TOP 1 VECTOR_TO_STRING(Embedding) FROM VectorFixture.Raw",
    "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='%Dictionary' AND TABLE_NAME LIKE '%aram%'",
]:
    try: print(q, list(iris.sql.exec(q)))
    except Exception as e: print(str(e))
