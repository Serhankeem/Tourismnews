"""Loopback-only monthly UI review. Never builds, collects, publishes or writes data."""
import argparse
import datetime as dt
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets

from src.macro import weather_diagnostic as engine, weather_shadow as shadow

ASSETS = engine.ROOT/'preview/market-weather'


def load_preview(bundle):
    """Project verified private inputs, rechecking CURRENT collection/publication scope."""
    if bundle is None:return {'state':'no_data', 'publication_approved':False}
    bundle = Path(bundle).resolve()
    if bundle == engine.ROOT or engine.ROOT in bundle.parents:raise ValueError('external_bundle_required')
    manifest = shadow.verify_bundle(bundle)
    diagnostic = engine.read(bundle/'diagnostic-private.json')
    briefing = engine.read(bundle/'briefing-private.json')
    shadow.briefing(diagnostic)  # enforce the private target/axis/overall contract
    if manifest['target_period'] != diagnostic['target_period'] or briefing['target_period'] != diagnostic['target_period']:
        raise ValueError('target_mismatch')
    archive = engine.read(bundle/'inputs/archive.json')
    config = engine.read(engine.ROOT/'macro_sources.json')
    policy = engine.read(engine.ROOT/'operating_policy.json')
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = engine.stamp(diagnostic['input_cutoff'])
    if cutoff > now:raise ValueError('future_cutoff')
    contracts = engine.read(engine.CONTRACT)
    history = {}
    for key in engine.CORE:
        obs = engine.eligible(config,archive,policy,key,contracts,cutoff,now)
        target = diagnostic['target_period']
        if target not in obs or obs[target]['value'] != diagnostic['axes'][key]['value']:
            raise ValueError('current_approval_or_value_invalid')
        # Only the two approved cores, at most twelve calendar months. No new indicators.
        y,m = map(int,target.split('-'))
        begin = f'{y-1 if m<12 else y:04}-{m+1 if m<12 else 1:02}'
        history[key] = [{'period':p,'value':obs.get(p,{}).get('value')} for p in shadow.months(begin,target)]
    projected = {k:v for k,v in diagnostic.items() if k != 'supporting'}
    return dict(state='private_review',publication_approved=False,diagnostic=projected,
                briefing=briefing,history=history,methodology_version=manifest['methodology_version'],
                edition_revision=manifest.get('edition_revision'),
                revision_count=len(manifest['revision_history']))


def create_server(bundle=None, port=0):
    payload = load_preview(bundle)
    session = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass  # no private data, paths or session in logs

        def respond(self,code,body,kind='text/plain; charset=utf-8',cookie=False):
            self.send_response(code)
            self.send_header('Content-Type',kind)
            self.send_header('Cache-Control','no-store, max-age=0')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Robots-Tag','noindex, nofollow, noarchive')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Cross-Origin-Resource-Policy','same-origin')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            if cookie:self.send_header('Set-Cookie',f'weather_review={session}; HttpOnly; SameSite=Strict; Path=/')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

        def do_GET(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != origin.removeprefix('http://'):
                return self.respond(403,b'loopback_host_required')
            if self.headers.get('Origin',origin) != origin or self.headers.get('Sec-Fetch-Site','same-origin') not in ('same-origin','none'):
                return self.respond(403,b'same_origin_required')
            paths = {'/':'index.html','/monthly.css':'monthly.css','/monthly.js':'monthly.js'}
            if self.path in paths:
                suffix = Path(paths[self.path]).suffix
                kind = {'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8'}[suffix]
                return self.respond(200,(ASSETS/paths[self.path]).read_bytes(),kind,cookie=self.path=='/')
            if self.path == '/api/preview':
                try:
                    cookies=SimpleCookie(self.headers.get('Cookie',''))
                    valid=secrets.compare_digest(cookies['weather_review'].value,session)
                except (KeyError,ValueError):valid=False
                if not valid:return self.respond(403,b'local_session_required')
                return self.respond(200,json.dumps(payload,ensure_ascii=False).encode(),'application/json; charset=utf-8')
            return self.respond(404,b'not_found')

    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path)
    parser.add_argument('--port',type=int,default=8044)
    args=parser.parse_args()
    try:
        server=create_server(args.bundle,args.port)
        print(f'Local private review: http://127.0.0.1:{server.server_port}/',flush=True)
        server.serve_forever()
    except KeyboardInterrupt:return 0
    except Exception:
        print('private_preview_validation_failed');return 1


if __name__ == '__main__':raise SystemExit(main())
