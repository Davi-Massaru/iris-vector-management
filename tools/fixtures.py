"""Executable offline fixtures. Run inside Embedded Python in USER."""
import os
import json
import sys
from pathlib import Path
import iris

root=Path(__file__).resolve().parents[1]

sys.path.insert(0,'/usr/irissys/mgr/python')
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TOKENIZERS_PARALLELISM']='false'

def exists(table):
    return bool(list(iris.sql.exec('SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA=? AND TABLE_NAME=?','VectorFixture',table)))

if not exists('Raw'):
    iris.sql.exec('CREATE TABLE VectorFixture.Raw (ID INTEGER IDENTITY, Label VARCHAR(80), Embedding VECTOR(DOUBLE,3))')
    for i,v in enumerate([[1,0,0],[0,1,0],[0,0,1],[0.7,0.7,0]]):
        iris.sql.exec('INSERT INTO VectorFixture.Raw (Label,Embedding) VALUES (?,TO_VECTOR(?,DOUBLE))',f'Fixture {i+1}',json.dumps(v))
    iris.sql.exec("CREATE INDEX RawHNSW ON TABLE VectorFixture.Raw (Embedding) AS HNSW(Distance='Cosine', M=24, efConstruction=100)")
if not exists('Unindexed'):
    iris.sql.exec('CREATE TABLE VectorFixture.Unindexed (ID INTEGER IDENTITY, Embedding VECTOR(DOUBLE,3))')
    for v in [[1,0,0],[0,1,0],[0,0,1],[0.7,0.7,0],[0,0,0]]:
        iris.sql.exec('INSERT INTO VectorFixture.Unindexed (Embedding) VALUES (TO_VECTOR(?,DOUBLE))',json.dumps(v))
if not exists('WrongType'):
    iris.sql.exec('CREATE TABLE VectorFixture.WrongType (ID INTEGER IDENTITY, Embedding VECTOR(INTEGER,3))')
if not exists('Variable'):
    iris.sql.exec('CREATE TABLE VectorFixture.Variable (ID INTEGER IDENTITY, Embedding VECTOR(DOUBLE))')
if not exists('StringKey'):
    iris.sql.exec('CREATE TABLE VectorFixture.StringKey (Code VARCHAR(40) PRIMARY KEY, Embedding VECTOR(DOUBLE,3))')
for name in ['Mapped','StringIds']:
    status=iris.cls('%SYSTEM.OBJ').Load(str(root/'iris'/(name+'.cls')),'ck')
    if str(status)!='1': raise RuntimeError('Fixture class compilation failed')

# A tiny SentenceTransformers model for exercising schema and source binding
# offline. Random weights deliberately make this unsuitable as a quality benchmark.
from sentence_transformers import SentenceTransformer,models
from transformers import BertConfig,BertModel,BertTokenizerFast
cache_path=Path('/usr/irissys/mgr/vector-fixture-cache')
model_repo=cache_path/'models--vector-fixture--tiny-bert'
model_path=model_repo/'snapshots'/('0'*40)
if not model_path.exists():
    base=Path('/usr/irissys/mgr/vector-fixture-bert')
    base.mkdir(exist_ok=True)
    (base/'vocab.txt').write_text('\n'.join(['[PAD]','[UNK]','[CLS]','[SEP]','[MASK]','database','vector','search'])+'\n')
    tokenizer=BertTokenizerFast(vocab_file=str(base/'vocab.txt'),model_max_length=64)
    tokenizer.save_pretrained(str(base))
    BertModel(BertConfig(vocab_size=8,hidden_size=16,num_hidden_layers=1,num_attention_heads=2,intermediate_size=32,max_position_embeddings=128)).save_pretrained(str(base))
    SentenceTransformer(modules=[models.Transformer(str(base),max_seq_length=64),models.Pooling(16),models.Normalize()]).save(str(model_path))
(model_repo/'refs').mkdir(parents=True,exist_ok=True)
(model_repo/'refs'/'main').write_text('0'*40)
if not list(iris.sql.exec('SELECT Name FROM %Embedding.Config WHERE Name=?','vector-fixture-tiny')):
    iris.sql.exec('INSERT INTO %Embedding.Config (Name,EmbeddingClass,Configuration,Description) VALUES (?,?,?,?)',
                  'vector-fixture-tiny','%Embedding.SentenceTransformers',
                  json.dumps({'modelName':'vector-fixture/tiny-bert','hfCachePath':str(cache_path),'checkTokenCount':False}),
                  'Offline randomly initialized tiny BERT acceptance fixture; not a semantic benchmark.')
if exists('Managed') and list(iris.sql.exec('SELECT COUNT(*) FROM VectorFixture.Managed'))[0][0]==0:
    iris.sql.exec('DROP TABLE VectorFixture.Managed')
if not exists('Managed'):
    iris.sql.exec("CREATE TABLE VectorFixture.Managed (ID INTEGER IDENTITY, Content VARCHAR(512), Embedding EMBEDDING('vector-fixture-tiny','Content'))")
    for content in ['database vector','vector search','database search']:
        iris.sql.exec('INSERT INTO VectorFixture.Managed (Content) VALUES (?)',content)
for table in ['Raw','Unindexed','WrongType','Variable','StringKey','StringIds','Managed','Mapped']:
    statement=iris.cls('%SQL.Statement')._New()
    status=statement._Prepare('GRANT SELECT ON VectorFixture.'+table+' TO VectorAdminReader')
    if str(status)!='1': raise RuntimeError('Fixture grant preparation failed')
    result=statement._Execute()
    if int(result._SQLCODE)<0: raise RuntimeError('Fixture grant failed')
print('Fixtures created: raw, managed/local, eligible and ineligible HNSW cases.')
print('Managed property metadata:',list(iris.sql.exec("SELECT Name,Type FROM %Dictionary.CompiledProperty WHERE parent='VectorFixture.Managed'")))
prop=iris.cls('%Dictionary.CompiledProperty')._OpenId('VectorFixture.Managed||Embedding')
for key in ['LEN','DATATYPE','MODEL','SOURCE','CONFIGURATION','EMBEDDINGCONFIG','SOURCES']:
    print(key,prop.Parameters.GetAt(key))
