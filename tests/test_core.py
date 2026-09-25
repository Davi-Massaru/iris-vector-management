import io
import json
import unittest
import base64
from unittest.mock import patch
from vector_admin.errors import Problem
from vector_admin import auth,search,placement,configs,tasks,recipes
from vector_admin.sql import integer,identifier
from vector_admin.app import application
from vector_admin.sysadmin_client import SysAdmin

class CoreTests(unittest.TestCase):
    def test_python_vector_generator_contract(self):
        code='def generate(row, context):\n    return [float(len(row["text"])), 0.0]'
        self.assertEqual(recipes._generate_python(code,{'key':1,'text':'abc'},2),'[3.0,0.0]')
        with self.assertRaises(ValueError):
            recipes._generate_python('def generate(row, context):\n    return [float("nan")]',{'key':1,'text':'x'},1)

    def test_nonfinite_and_dimension_validation(self):
        for value in [[1], [True,0,0], [1,float('nan'),0], [float('inf'),0,0], ['1',0,0]]:
            with self.assertRaises(Problem): search.vector_input(value,3,'DOUBLE')
        self.assertEqual(search.vector_input([1,0,0],3,'DOUBLE'),'[1,0,0]')

    def test_bounded_integer(self):
        for value in ['1000','-1','1; DROP TABLE X',True,'1.5']:
            with self.assertRaises(Problem): integer(value,1,100,'K')

    def test_identifiers_are_quoted_and_values_bound(self):
        self.assertEqual(identifier('a"b'),'"a""b"')
        asset={'schema':'App','table':'Document','column':'Vector','key':'ID','elementType':'DOUBLE','dimensions':3,'columns':{'ID':'integer'},'indexes':[],'sourceColumns':[],'config':'Unknown'}
        query,args=search.build(asset,{'vector':[1,0,0],'k':7,'filters':[{'column':'ID','operator':'>','value':2}]})
        self.assertIn('SELECT TOP 7',query)
        self.assertIn('TO_VECTOR(?, DOUBLE)',query)
        self.assertEqual(args,['[1,0,0]',2])
        with self.assertRaises(Problem): search.build(asset,{'vector':[1,0,0],'filters':[{'column':'ID; DROP TABLE X','operator':'=','value':1}]})
        with self.assertRaises(Problem): search.build(asset,{'text':'hello'})

    def test_config_is_strictly_allowlisted(self):
        self.assertEqual(configs.sanitize('{"apiKey":"secret","nested":{"token":"secret"},"modelName":"local","password":"secret"}'),{'modelName':'local'})
        self.assertEqual(configs.sanitize('[]'),{})

    def test_mapping_uncertainty_is_not_guessed(self):
        databases=[{'Name':'USER','Directory':'/user/'},{'Name':'DATA','Directory':'/data/'}]
        self.assertEqual(placement.resolve_global('^RawD','USER',[],databases)['database'],'USER')
        self.assertEqual(placement.resolve_global('^RawD','USER',[{'Name':'RawD','Database':'DATA'}],databases)['database'],'DATA')
        for mappings in [[{'Name':'RawD(1)','Subscript':'(1)','Database':'DATA'}],[{'Name':'Raw*','Database':'DATA'},{'Name':'RawD','Database':'USER'}]]:
            self.assertEqual(placement.resolve_global('^RawD','USER',mappings,databases)['database'],'Unresolved')
        self.assertEqual(placement.resolve_global('^RawD(1)','USER',[],databases)['database'],'Unresolved')

    def test_index_existence_is_not_plan_evidence(self):
        asset={'schema':'App','table':'Document','indexes':[{'name':'VecHNSW'}]}
        self.assertEqual(search.diagnosis('SQL: VecHNSW',asset),'Undetermined')
        self.assertEqual(search.diagnosis('Read index map App.Document.VecHNSW, looping',asset),'HNSW used')
        self.assertEqual(search.diagnosis('Read master map App.Document.IDKEY, looping',asset),'Full scan')

    def test_vector_task_inventory_uses_class_and_normalizes_state(self):
        class Client:
            def get(self,path,**params):
                if path=='/v2/task/manager': return {'Status':'Running'}
                if path=='/v2/tasks': return [{'Id':7,'Name':'Vectors','Namespace':'USER','Suspended':False,'NextScheduled':'tomorrow'},{'Id':8,'Name':'Other'}]
                if path=='/v2/task': return {'TaskClass':'VectorAdmin.SeedTask','Settings':{'RecipeRevision':'r3'},'NameSpace':'USER'} if params['id']==7 else {'TaskClass':'Other.Task'}
                if path=='/v2/task/info': return {'Status':'-1','LastStarted':'now'}
                raise AssertionError(path)
        result=tasks.inventory(Client(),run_lookup=lambda _:{'items':[]})
        self.assertEqual(result['manager'],'Running')
        self.assertEqual(len(result['items']),1)
        self.assertEqual(result['items'][0]['state'],'RUNNING')
        self.assertEqual(result['items'][0]['recipeRevision'],'r3')

    def test_vector_task_without_recipe_is_unlinked(self):
        class Client:
            def get(self,path,**params):
                if path=='/v2/task/manager': return {'Status':'Running'}
                if path=='/v2/tasks': return [{'Id':9}]
                if path=='/v2/task': return {'TaskClass':'VectorAdmin.SeedTask','Settings':{}}
                if path=='/v2/task/info': return {}
                raise AssertionError(path)
        self.assertEqual(tasks.inventory(Client(),run_lookup=lambda _:{'items':[]})['items'][0]['state'],'UNLINKED')

    def test_sysadmin_forwards_valid_basic_credentials_from_same_request(self):
        header='Basic '+base64.b64encode(b'alice:secret').decode()
        with patch('vector_admin.sysadmin_client.settings.SYSADMIN_URL','http://127.0.0.1:52773/api/admin'):
            self.assertEqual(SysAdmin({'HTTP_AUTHORIZATION':header}).authorization,header)

    def test_sysadmin_rejects_malformed_basic_credentials(self):
        for header in ('', 'Bearer token', 'Basic !!!!', 'Basic '+base64.b64encode(b'alice').decode()):
            with self.assertRaises(Problem): SysAdmin({'HTTP_AUTHORIZATION':header})

    def test_request_principal_uses_authenticated_basic_user(self):
        header='Basic '+base64.b64encode(b'alice:secret').decode()
        token=auth.begin_request({'HTTP_AUTHORIZATION':header})
        try: self.assertEqual(auth.principal(),'alice')
        finally: auth.end_request(token)

    @patch('vector_admin.auth.secret',return_value=b'test-key')
    @patch('vector_admin.auth.principal',return_value='alice')
    def test_tokens_reject_tampering_actor_and_expiration(self,*_):
        token=auth.token({'kind':'asset','actor':'alice'})
        self.assertEqual(auth.verify(token,'asset')['actor'],'alice')
        with self.assertRaises(Problem): auth.verify(token+'x','asset')
        with self.assertRaises(Problem): auth.verify(token,'csrf')
        with patch('vector_admin.auth.principal',return_value='bob'):
            with self.assertRaises(Problem): auth.verify(token,'asset')
        with self.assertRaises(Problem): auth.verify(auth.token({'kind':'asset','actor':'alice'},-1),'asset')

    @patch('vector_admin.app.auth.require',side_effect=Problem('MISSING_PRIVILEGE','Authentication required.',401))
    def test_anonymous_does_not_receive_application_or_stacktrace(self,_):
        status=[]
        body=b''.join(application({'PATH_INFO':'/','REQUEST_METHOD':'GET'},lambda s,h: status.append((s,h))))
        self.assertTrue(status[0][0].startswith('401'))
        self.assertNotIn(b'Traceback',body)
        self.assertIn(('Cache-Control','no-store'),status[0][1])

    @patch('vector_admin.app.auth.require',return_value='alice')
    @patch('vector_admin.app.auth.csrf',side_effect=Problem('INVALID_TOKEN','Invalid token.',403))
    def test_unsafe_routes_require_csrf_before_reading_body(self,*_):
        status=[]
        from vector_admin.app import dispatch
        with self.assertRaises(Problem) as caught:
            dispatch({'PATH_INFO':'/api/operations','REQUEST_METHOD':'POST'})
        self.assertEqual(caught.exception.status,403)

if __name__=='__main__': unittest.main()
