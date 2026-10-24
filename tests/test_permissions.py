import copy
import http.cookiejar
import importlib.util
import json
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

spec = importlib.util.spec_from_file_location('sandy_server', Path(__file__).parents[1] / 'server.py')
sandy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sandy)

class PermissionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        sandy.DATA = Path(cls.temp.name)
        cls.password = secrets.token_urlsafe(24)
        for role in sandy.ROLES:
            sandy.create_user(role, cls.password, role)
        cls.server = sandy.ThreadingHTTPServer(('127.0.0.1', 0), sandy.Handler)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()

    def client(self, role=None):
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        if role:
            self.assertEqual(self.request(client, '/api/login', {'name': role, 'password': self.password})[0], 200)
        return client

    def request(self, client, path, body=None, header=True):
        headers = {'Content-Type': 'application/json'}
        if header:
            headers['X-Sandy-Request'] = '1'
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            response = client.open(req)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def setUp(self):
        with sandy.connect() as c:
            c.execute('DELETE FROM catalog')
        self.catalog = {'settings': {'nav': {}, 'types': ['Formal']}, 'categories': [], 'tickets': [], 'speeches': [], 'favorites': {'tickets': [], 'speeches': []}}
        self.dev = self.client('developer')
        self.assertEqual(self.request(self.dev, '/api/catalog', {'data': self.catalog, 'revision': 0})[0], 200)

    def test_anonymous_and_private_files(self):
        anonymous = self.client()
        self.assertEqual(self.request(anonymous, '/api/catalog')[0], 401)
        for path in ('/.data/sandy.sqlite3', '/server.py', '/.git/config', '/../server.py'):
            self.assertEqual(self.request(anonymous, path)[0], 404)

    def test_reader_cannot_write_or_create_users(self):
        reader = self.client('usuario')
        self.assertEqual(self.request(reader, '/api/catalog')[0], 200)
        self.assertEqual(self.request(reader, '/api/catalog', {'data': self.catalog, 'revision': 1})[0], 403)
        self.assertEqual(self.request(reader, '/api/users', {})[0], 403)

    def test_admin_edits_content_but_not_design_or_accounts(self):
        admin = self.client('admin')
        data = copy.deepcopy(self.catalog)
        data['categories'] = [{'id':'one','name':'Soporte','description':'Ayuda','icon':'folder','color':'#2587f5'}]
        data['tickets'] = [{'id':'ticket','categoryId':'one','title':'Prueba','description':'Original','purpose':'Ayuda','steps':'Paso uno','info':'Datos','tags':[]}]
        self.assertEqual(self.request(admin, '/api/catalog', {'data':data,'revision':1})[0],200)
        data['tickets'][0]['description']='Descripción actualizada'
        self.assertEqual(self.request(admin, '/api/catalog', {'data':data,'revision':2})[0],200)
        data['settings']['appName']='Cambio prohibido'
        self.assertEqual(self.request(admin, '/api/catalog', {'data':data,'revision':3})[0],403)
        self.assertEqual(self.request(admin, '/api/users', {})[0],403)
        stored=self.request(admin,'/api/catalog')[1]['data']
        self.assertEqual(stored['tickets'][0]['description'],'Descripción actualizada')
        self.assertNotIn('appName',stored['settings'])

    def test_developer_design_accounts_conflict_logout_and_csrf(self):
        data=copy.deepcopy(self.catalog)
        data['settings']['appName']='Mi Sandy'
        self.assertEqual(self.request(self.dev,'/api/catalog',{'data':data,'revision':1})[0],200)
        self.assertEqual(self.request(self.dev,'/api/catalog',{'data':data,'revision':1})[0],409)
        self.assertEqual(self.request(self.dev,'/api/catalog',{'data':data,'revision':2},header=False)[0],403)
        self.assertEqual(self.request(self.dev,'/api/users',{'name':'nuevo','password':self.password,'role':'usuario'})[0],201)
        self.assertEqual(self.request(self.dev,'/api/users',{'name':'otro','password':self.password,'role':'superadmin'})[0],400)
        self.assertEqual(self.request(self.dev,'/api/logout',{})[0],200)
        self.assertEqual(self.request(self.dev,'/api/catalog')[0],401)

    def test_bad_login_and_invalid_catalog(self):
        self.assertEqual(self.request(self.client(),'/api/login',{'name':'developer','password':'incorrecta'})[0],401)
        self.assertEqual(self.request(self.dev,'/api/catalog',{'data':{},'revision':1})[0],400)
        self.assertEqual(self.request(self.dev,'/api/catalog')[1]['revision'],1)

if __name__ == '__main__':
    unittest.main()
