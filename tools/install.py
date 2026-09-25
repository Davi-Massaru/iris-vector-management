"""Run inside an administrative IRIS session in the portal namespace."""
import iris
import secrets
from pathlib import Path

root=Path('/workspace') if Path('/workspace/iris').is_dir() else Path('/usr/irissys/csp/vector-admin')
for class_file in ('Runtime.cls','SeedTask.cls'):
    status=iris.cls('%SYSTEM.OBJ').Load(str(root/'iris'/class_file),'ck')
    if str(status)!='1': raise RuntimeError(iris.system.Status.GetErrorText(status))
key=Path('/usr/irissys/mgr/vector-admin.key')
if not key.exists():
    key.write_bytes(secrets.token_bytes(48))
    key.chmod(0o600)
tables={
    'SeedRow': 'RecipeId VARCHAR(32), KeyHash VARCHAR(64), SourceHash VARCHAR(64), GeneratorHash VARCHAR(64), UpdatedAt DOUBLE, PRIMARY KEY (RecipeId,KeyHash)',
    'SeedMetrics': 'RunId VARCHAR(32) PRIMARY KEY, CreatedCount INTEGER, MissingCount INTEGER, Policy VARCHAR(16)',
    'FixtureRegistry': 'Name VARCHAR(128) PRIMARY KEY, CreatedAt DOUBLE',
    'Audit': 'EventId VARCHAR(32) PRIMARY KEY, Actor VARCHAR(128), Action VARCHAR(80), Target VARCHAR(512), State VARCHAR(32), CreatedAt DOUBLE, Evidence VARCHAR(8192)',
    'Operation': 'OperationId VARCHAR(32) PRIMARY KEY, Actor VARCHAR(128), State VARCHAR(32), CreatedAt DOUBLE, UpdatedAt DOUBLE, ExpiresAt DOUBLE, Payload VARCHAR(16000), Outcome VARCHAR(32000)',
    'VectorRecipe': 'RecipeId VARCHAR(32), Revision INTEGER, Name VARCHAR(128), State VARCHAR(24), Payload VARCHAR(16000), Fingerprint VARCHAR(64), CreatedBy VARCHAR(128), CreatedAt DOUBLE, PublishedAt DOUBLE, PRIMARY KEY (RecipeId,Revision)',
    'SeedSchedule': 'TaskId INTEGER PRIMARY KEY, RecipeId VARCHAR(32), Revision INTEGER, CreatedBy VARCHAR(128), CreatedAt DOUBLE',
    'SeedRun': 'RunId VARCHAR(32) PRIMARY KEY, RecipeId VARCHAR(32), Revision INTEGER, TaskId INTEGER, State VARCHAR(32), SelectedCount INTEGER, UpdatedCount INTEGER, SkippedCount INTEGER, FailedCount INTEGER, LastKey VARCHAR(512), HeartbeatAt DOUBLE, StartedAt DOUBLE, FinishedAt DOUBLE, ErrorSummary VARCHAR(2048)',
}
for name,columns in tables.items():
    if not list(iris.sql.exec('SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA=? AND TABLE_NAME=?','VectorAdmin',name)):
        iris.sql.exec(f'CREATE TABLE VectorAdmin.{name} ({columns})')
print('Portal runtime, signing key and operational schema installed.')

# Development data is seeded at build time, never through the portal UI.
import os
if os.getenv('VECTOR_ADMIN_SEED') == '1':
    import sys
    sys.path.insert(0, str(root))
    sys.path.insert(0, '/usr/irissys/mgr/python')
    from vector_admin.documents import seed
    if not list(iris.sql.exec("SELECT Name FROM VectorAdmin.FixtureRegistry WHERE Name='USER/data.Document'")):
        result=seed({'namespace':'USER','action':'append','count':20})
        print('Build fixture: data.Document seeded with',result['total'],'Faker documents.')
