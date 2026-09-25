import iris
import json

print(iris.system.Version.GetVersion())
for query in [
    'SELECT Name,"Default" FROM %Dictionary.ParameterDefinition WHERE parent IN (\'Security.Datatype.ApplicationType\',\'Security.Datatype.Authentication\')',
    "SELECT Name,Description FROM %Dictionary.PropertyDefinition WHERE parent = 'Security.Applications' AND Name IN ('WSGIType','Enabled','AutheEnabled')",
    "SELECT Name,DataLocation,IndexLocation,IdLocation,Type FROM %Dictionary.CompiledStorage WHERE parent='VectorFixture.Raw'",
    "SELECT Name,Type FROM %Dictionary.PropertyDefinition WHERE parent = '%Dictionary.CompiledIndex'",
    "CREATE INDEX RawHNSW ON TABLE VectorFixture.Raw (Embedding) AS HNSW(Distance='Cosine', M=24, efConstruction=100)",
    "SELECT Name,Type,Data,IdKey FROM %Dictionary.CompiledIndex WHERE parent='VectorFixture.Raw'",
    "SELECT Name,Type FROM %Dictionary.PropertyDefinition WHERE parent = '%Dictionary.CompiledPropertyParameter'",
    "SELECT TOP 3 ID,VECTOR_COSINE(Embedding,TO_VECTOR('[1,0,0]',DOUBLE)) AS Score FROM VectorFixture.Raw ORDER BY Score DESC",
    "EXPLAIN SELECT TOP 3 ID,VECTOR_COSINE(Embedding,TO_VECTOR('[1,0,0]',DOUBLE)) AS Score FROM VectorFixture.Raw ORDER BY Score DESC",
]:
    try:
        print(query, list(iris.sql.exec(query)))
    except Exception as exc:
        print(type(exc).__name__, str(exc))
try:
    prop = iris.cls('%Dictionary.CompiledProperty')._OpenId('VectorFixture.Raw||Embedding')
    for key in ['TYPE', 'LEN', 'MAXLEN', 'VECTORLEN', 'DIMENSION']:
        print('parameter', key, prop.Parameters.GetAt(key))
except Exception as exc:
    print(str(exc))
