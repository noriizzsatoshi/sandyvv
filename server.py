"""Sandy: servidor local, sesiones y permisos sin dependencias externas."""
import argparse
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('SANDY_DATA_DIR', ROOT / '.data'))
ROLES = ('usuario', 'admin', 'developer')

def connect():
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    c = sqlite3.connect(DATA / 'sandy.sqlite3')
    c.row_factory = sqlite3.Row
    c.executescript('''CREATE TABLE IF NOT EXISTS users(name TEXT PRIMARY KEY, salt TEXT, password TEXT, role TEXT);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, name TEXT, expires REAL);
    CREATE TABLE IF NOT EXISTS catalog(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT, revision INTEGER);''')
    return c

def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

def create_user(name, password, role):
    if role not in ROLES or not name.strip() or len(name) > 80 or len(password) < 12:
        raise ValueError('Usuario válido, rol válido y contraseña de al menos 12 caracteres requeridos.')
    salt = secrets.token_hex(16)
    with connect() as c:
        c.execute('INSERT INTO users VALUES(?,?,?,?)', (name.strip(), salt, password_hash(password, salt), role))

def validate_catalog(data):
    if not isinstance(data, dict) or not isinstance(data.get('settings'), dict):
        raise ValueError('Catálogo inválido')
    for key in ('tickets', 'categories', 'speeches'):
        items = data.get(key)
        if not isinstance(items, list) or any(not isinstance(x, dict) or not isinstance(x.get('id'), str) for x in items):
            raise ValueError('Colección inválida')
        if len({x['id'] for x in items}) != len(items):
            raise ValueError('Identificadores duplicados')
    cats = {x['id'] for x in data['categories']}
    tickets = {x['id'] for x in data['tickets']}
    if any(x.get('categoryId') not in cats for x in data['tickets']) or any(x.get('ticketId') not in tickets for x in data['speeches']):
        raise ValueError('Referencias inválidas')
    if not isinstance(data['settings'].get('nav'), dict) or not isinstance(data['settings'].get('types'), list):
        raise ValueError('Configuración inválida')
    for key, fields in [('categories', ('name', 'description', 'icon', 'color')), ('tickets', ('title', 'description', 'purpose', 'steps', 'info')), ('speeches', ('title', 'content', 'type'))]:
        if any(any(not isinstance(x.get(f), str) for f in fields) for x in data[key]):
            raise ValueError('Campos inválidos')
    data['favorites'] = {'tickets': [], 'speeches': []}

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, value, cookie=None):
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def current_user(self):
        cookie = SimpleCookie()
        cookie.load(self.headers.get('Cookie', ''))
        token = cookie.get('sandy_session')
        if not token:
            return None
        with connect() as c:
            return c.execute('SELECT users.name, role FROM users JOIN sessions USING(name) WHERE token=? AND expires>?', (token.value, time.time())).fetchone()

    def do_GET(self):
        if self.path.startswith('/api/'):
            user = self.current_user()
            if not user:
                return self.reply(401, {'error': 'Iniciá sesión para continuar.'})
            if self.path == '/api/me':
                return self.reply(200, dict(user))
            if self.path == '/api/catalog':
                with connect() as c:
                    row = c.execute('SELECT body,revision FROM catalog WHERE id=1').fetchone()
                return self.reply(200, {'data': json.loads(row['body']) if row else None, 'revision': row['revision'] if row else 0})
            return self.reply(404, {'error': 'No encontrado'})
        # Solo archivos públicos explícitos; nunca servir SQLite ni archivos del repositorio.
        files = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css'}
        name = files.get(self.path.split('?')[0])
        if not name:
            return self.reply(404, {'error': 'No encontrado'})
        raw = (ROOT / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', {'html': 'text/html; charset=utf-8', 'js': 'text/javascript; charset=utf-8', 'css': 'text/css; charset=utf-8'}[name.split('.')[-1]])
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        # Encabezado personalizado obligatorio: bloquea envíos CSRF desde otros sitios.
        if self.headers.get('X-Sandy-Request') != '1':
            return self.reply(403, {'error': 'Solicitud no permitida'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2_000_000:
                return self.reply(413, {'error': 'Tamaño inválido'})
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Solicitud inválida')
            if self.path == '/api/login':
                with connect() as c:
                    user = c.execute('SELECT * FROM users WHERE name=?', (body.get('name'),)).fetchone()
                    salt = user['salt'] if user else '00' * 16
                    digest = password_hash(str(body.get('password', '')), salt)
                    if not user or not hmac.compare_digest(digest, user['password']):
                        return self.reply(401, {'error': 'Usuario o contraseña incorrectos.'})
                    token = secrets.token_urlsafe(32)
                    c.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
                    c.execute('INSERT INTO sessions VALUES(?,?,?)', (token, user['name'], time.time() + 28800))
                secure = '; Secure' if os.environ.get('SANDY_SECURE_COOKIE') == '1' else ''
                return self.reply(200, {'name': user['name'], 'role': user['role']}, f'sandy_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{secure}')
            user = self.current_user()
            if not user:
                return self.reply(401, {'error': 'Sesión vencida. Volvé a ingresar.'})
            if self.path == '/api/logout':
                cookie = SimpleCookie(self.headers.get('Cookie', ''))
                with connect() as c:
                    c.execute('DELETE FROM sessions WHERE token=?', (cookie['sandy_session'].value,))
                return self.reply(200, {}, 'sandy_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if self.path == '/api/users':
                if user['role'] != 'developer':
                    return self.reply(403, {'error': 'Solo developer puede crear cuentas.'})
                create_user(body.get('name', ''), body.get('password', ''), body.get('role'))
                return self.reply(201, {'ok': True})
            if self.path == '/api/catalog':
                if user['role'] not in ('admin', 'developer'):
                    return self.reply(403, {'error': 'Tu cuenta tiene acceso de solo lectura.'})
                data = body['data']
                validate_catalog(data)
                with connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    old = c.execute('SELECT body,revision FROM catalog WHERE id=1').fetchone()
                    revision = old['revision'] if old else 0
                    if body.get('revision') != revision:
                        return self.reply(409, {'error': 'Otro usuario actualizó los datos. Recargá antes de editar.'})
                    if user['role'] != 'developer' and (not old or data['settings'] != json.loads(old['body'])['settings']):
                        return self.reply(403, {'error': 'Solo developer puede modificar la página.'})
                    c.execute('INSERT OR REPLACE INTO catalog VALUES(1,?,?)', (json.dumps(data), revision + 1))
                return self.reply(200, {'revision': revision + 1})
            return self.reply(404, {'error': 'No encontrado'})
        except (ValueError, KeyError, TypeError, sqlite3.IntegrityError) as error:
            return self.reply(400, {'error': str(error) if not isinstance(error, sqlite3.IntegrityError) else 'El usuario ya existe.'})

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--create-user')
    parser.add_argument('--role', choices=ROLES, default='usuario')
    args = parser.parse_args()
    if args.create_user:
        create_user(args.create_user, getpass.getpass('Contraseña (mínimo 12 caracteres): '), args.role)
        print('Cuenta creada.')
    else:
        connect().close()
        print(f'Sandy escuchando en {args.host}:{args.port}', flush=True)
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
