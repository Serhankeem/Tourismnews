"""Private loopback-only v1.1 review. Does not build Pages or write any public data."""
import argparse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT/'preview/model-signal-v11'


def load(macro, sha256, as_of):
    path = Path(macro).resolve()
    if path == ROOT or ROOT in path.parents: raise ValueError('external_snapshot_required')
    script = """const fs=require('fs'),m=require('./src/model_signal/v11.cjs');
process.stdout.write(JSON.stringify(m.evaluateSnapshot(fs.readFileSync(process.argv[1]),{expected_sha256:process.argv[2],as_of_period:process.argv[3]})));"""
    return json.loads(subprocess.check_output(['node','-e',script,str(path),sha256,as_of], cwd=ROOT))


def server(result, port=0):
    token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != origin.removeprefix('http://'):
                self.send_error(403); return
            cookie = self.path == '/'
            if self.path == '/': data, kind = (ASSETS/'index.html').read_bytes(), 'text/html; charset=utf-8'
            elif self.path == '/app.js': data, kind = (ASSETS/'app.js').read_bytes(), 'text/javascript; charset=utf-8'
            elif self.path == '/result.json':
                try:
                    cookies = SimpleCookie(self.headers.get('Cookie', ''))
                    allowed = secrets.compare_digest(cookies['model_review'].value, token)
                except (KeyError, ValueError): allowed = False
                if not allowed or self.headers.get('Origin', origin) != origin:
                    self.send_error(403); return
                data, kind = json.dumps(result, ensure_ascii=False).encode(), 'application/json; charset=utf-8'
            else: self.send_error(404); return
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Robots-Tag', 'noindex, nofollow')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            if cookie: self.send_header('Set-Cookie', f'model_review={token}; HttpOnly; SameSite=Strict; Path=/')
            self.end_headers(); self.wfile.write(data)
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--macro', required=True, type=Path); p.add_argument('--sha256', required=True)
    p.add_argument('--as-of', required=True); p.add_argument('--port', type=int, default=0)
    a = p.parse_args(); result = load(a.macro, a.sha256, a.as_of)
    with server(result, a.port) as http:
        print(f'Private local preview: http://127.0.0.1:{http.server_port}/', flush=True)
        http.serve_forever()


if __name__ == '__main__': main()
