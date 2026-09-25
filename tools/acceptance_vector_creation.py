"""IRIS-side acceptance check for create-column vector recipes."""
import sys
sys.path.insert(0, '/usr/irissys/csp/vector-admin')

import iris
from vector_admin import recipes
from vector_admin.sql import rows

table='VectorFixture.VectorCreationAcceptance'
print('STAGE fixture',flush=True)
if list(iris.sql.exec("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='VectorFixture' AND TABLE_NAME='VectorCreationAcceptance'")):
    iris.sql.exec('DROP TABLE '+table)
iris.sql.exec('CREATE TABLE '+table+' (ID INTEGER PRIMARY KEY, Description VARCHAR(200))')
iris.sql.exec('INSERT INTO '+table+' (ID,Description) VALUES (1,?)','database vector')
iris.sql.exec('INSERT INTO '+table+' (ID,Description) VALUES (2,?)','vector search')

print('STAGE draft',flush=True)
draft=recipes.create_draft({'name':'Acceptance new vector','namespace':'USER','schema':'VectorFixture',
    'table':'VectorCreationAcceptance','targetColumn':'DescriptionVector','relationColumn':'ID',
    'sourceSql':'SELECT ID, Description FROM VectorFixture.VectorCreationAcceptance','dimensions':16,
    'generationMode':'MODEL','config':'vector-fixture-tiny'})
print('STAGE preflight',flush=True)
proposal=recipes.preflight(draft['id'])
print('STAGE publish',flush=True)
recipes.publish(draft['id'],{'token':proposal['token'],'confirmation':proposal['target']})
print('STAGE run',flush=True)
try:
    recipes.run_recipe(draft['id'])
except Exception:
    print('COLUMNS',list(iris.sql.exec("SELECT COLUMN_NAME,DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='VectorFixture' AND TABLE_NAME='VectorCreationAcceptance'")),flush=True)
    raise
print('STAGE verify',flush=True)
result=rows('SELECT COUNT(*),SUM(CASE WHEN DescriptionVector IS NOT NULL THEN 1 ELSE 0 END) FROM '+table,limit=1)
assert result==[[2,2]],result
print('VECTOR_CREATION_OK',draft['id'],proposal['ddl'],result)
