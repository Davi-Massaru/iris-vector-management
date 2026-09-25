"""Small read-only runtime check for the clean container image."""
import json
import sys

import iris

sys.path.insert(0, '/usr/irissys/csp/vector-admin')
from vector_admin.configs import list_configs


assets = list(iris.sql.exec(
    "SELECT p.parent,p.Name,p.Type FROM %Dictionary.CompiledProperty p "
    "WHERE p.Type IN ('%Library.Vector','%Embedding.Vector','%Library.Embedding') "
    "AND p.parent %STARTSWITH 'VectorFixture.' ORDER BY p.parent,p.Name"
))
assert any(row[0] == 'VectorFixture.Raw' for row in assets)
assert any(row[0] == 'VectorFixture.Managed' for row in assets)
assert any(row[0] == 'VectorFixture.Mapped' for row in assets)

page = list(iris.sql.exec(
    'SELECT TOP 25 ID,CASE WHEN Embedding IS NULL THEN 0 ELSE 1 END '
    'FROM VectorFixture.Raw ORDER BY ID'
))
assert page and len(page[0]) == 2

query = (
    "SELECT TOP 3 ID,VECTOR_COSINE(Embedding,TO_VECTOR('[1,0,0]',DOUBLE)) AS Score "
    "FROM VectorFixture.Raw ORDER BY Score DESC"
)
results = list(iris.sql.exec(query))
plan = '\n'.join(str(row[0]) for row in iris.sql.exec('EXPLAIN ' + query))
assert len(results) == 3
assert 'Read index map VectorFixture.Raw.RawHNSW' in plan

managed = list(iris.sql.exec(
    "SELECT TOP 3 ID,VECTOR_COSINE(Embedding,EMBEDDING(?,?)) AS Score "
    "FROM VectorFixture.Managed ORDER BY Score DESC",
    'vector search', 'vector-fixture-tiny'
))
assert len(managed) == 3

configs = list_configs()
assert any(item['name'] == 'vector-fixture-tiny' for item in configs)
assert all('apiKey' not in item['settings'] for item in configs)

storage = list(iris.sql.exec(
    "SELECT DataLocation,IndexLocation FROM %Dictionary.CompiledStorage "
    "WHERE parent='VectorFixture.Mapped'"
))
assert storage and storage[0][0] == '^VectorFixtureMappedD'
assert storage[0][1] == '^VectorFixtureMappedI'

print('VECTOR_SMOKE_OK')
print(json.dumps({
    'assets': len(assets),
    'pageRows': len(page),
    'rawSearchRows': len(results),
    'managedSearchRows': len(managed),
    'plan': 'HNSW used',
    'mappedDataGlobal': storage[0][0],
    'mappedIndexGlobal': storage[0][1],
}))
