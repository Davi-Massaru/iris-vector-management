"""Faker test data; modify only a table registered as this portal's fixture."""
import time
from . import auth, settings, audit
from .errors import Problem
from .sql import namespace, rows, integer

def seed(body):
    auth.require('VectorAdmin_Maintain')
    ns=body.get('namespace','USER'); auth.scope(settings.INSTANCE,ns)
    action=body.get('action','append')
    if action not in ('append','change'): raise Problem('INVALID_ACTION','Use append or change.',422)
    count=integer(body.get('count',10),1,100,'Documents')
    from faker import Faker
    fake=Faker('pt_BR')
    name=ns+'/data.Document'
    with namespace(settings.ADMIN_NAMESPACE):
        registered=rows('SELECT Name FROM VectorAdmin.FixtureRegistry WHERE Name=?',(name,),limit=1)
    with namespace(ns):
        exists=rows("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='data' AND TABLE_NAME='Document'",limit=1)
        if exists and not registered:
            raise Problem('FIXTURE_CONFLICT','data.Document already exists and is not registered as portal test data.',409)
        if not exists:
            rows('CREATE TABLE data.Document (ID INTEGER IDENTITY, Description VARCHAR(4000), CreatedAt TIMESTAMP, UpdatedAt TIMESTAMP)',limit=0)
            if not registered:
                with namespace(settings.ADMIN_NAMESPACE):
                    rows('INSERT INTO VectorAdmin.FixtureRegistry (Name,CreatedAt) VALUES (?,?)',(name,time.time()),limit=0)
        changed=0
        if action=='append':
            for _ in range(count):
                rows('INSERT INTO data.Document (Description,CreatedAt,UpdatedAt) VALUES (?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)',(fake.paragraph(nb_sentences=5),),limit=0)
                changed+=1
        else:
            ids=rows('SELECT TOP '+str(count)+' ID FROM data.Document ORDER BY ID',limit=count)
            for (key,) in ids:
                rows('UPDATE data.Document SET Description=?,UpdatedAt=CURRENT_TIMESTAMP WHERE ID=?',(fake.paragraph(nb_sentences=5),key),limit=0)
                changed+=1
        total=rows('SELECT COUNT(*) FROM data.Document',limit=1)[0][0]
        sample=rows('SELECT TOP 5 ID,Description,CreatedAt,UpdatedAt FROM data.Document ORDER BY ID',limit=5)
    audit.record('fixture.'+action,name,'SUCCEEDED',{'count':changed})
    return {'table':'data.Document','action':action,'changed':changed,'total':total,
            'sample':[dict(zip(('id','description','createdAt','updatedAt'),r)) for r in sample]}
