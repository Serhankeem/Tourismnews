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


def load_pending(payload,path,bundle):
    """Compatibility only. A draft manifest is never an approval or Trust pin."""
    from src.macro import weather_publication as gate
    path=Path(path).resolve()
    if engine.ROOT==path or engine.ROOT in path.parents or path.is_symlink():raise ValueError('external_draft_required')
    doc=engine.read(path)
    expected={'version','revision','reference_period','issue_month','actual_publication_date','manuscript_file','manuscript_sha256',
              'parent_manuscript_sha256','source_bundle_manifest_sha256','editorial_status','publication_status'}
    if (set(doc)!=expected or doc['version']!=1 or doc['revision']!='r3' or doc['editorial_status']!='pending'
            or doc['publication_status']!='not_requested' or doc['actual_publication_date'] is not None):raise ValueError('pending_draft_only')
    candidate=path.parent/doc['manuscript_file']
    if candidate.resolve().parent!=path.parent or candidate.is_symlink():raise ValueError('draft_path_invalid')
    raw=candidate.read_bytes()
    if gate.sha(raw)!=doc['manuscript_sha256']:raise ValueError('draft_hash_mismatch')
    if gate.sha((Path(bundle)/'manifest.json').read_bytes())!=doc['source_bundle_manifest_sha256']:raise ValueError('draft_snapshot_mismatch')
    if doc['reference_period']!=payload['diagnostic']['target_period']:raise ValueError('draft_period_mismatch')
    article=gate.parse_manuscript(raw,payload['diagnostic'])
    if doc['issue_month']!='2026-11' or doc['reference_period']!='2026-09':raise ValueError('draft_edition_mismatch')
    expected_cover='\n\n'.join(['한국 관광의 날씨는? / MONTHLY REPORT','2026년 11월 Market Weather',
        '2026년 9월 검증 자료 기반','2026.11 · VOL. 01','발행: 2026년 11월\n통계 기준: 2026년 9월',
        '공식 관광통계를 바탕으로 시장의 주요 변화 신호를 살펴봅니다. 산업 전체의 종합 경기 판정은 보류합니다.'])
    if article['title']!='2026년 11월 관광시장 진단' or not article['sections'][0]['markdown'].startswith(expected_cover+'\n\n'):
        raise ValueError('draft_cover_mismatch')
    payload['pending_editorial']={**doc,'article':article}
    return payload


def create_server(bundle=None, port=0, editorial_record=None, trust_policy=None, review_manifest=None):
    payload = load_preview(bundle)
    if review_manifest is not None:
        if bundle is None or editorial_record is not None:raise ValueError('draft_inputs_invalid')
        payload=load_pending(payload,review_manifest,bundle)
    if editorial_record is not None:
        from src.macro import weather_publication as gate
        if bundle is None or trust_policy is None:raise ValueError('private_editorial_inputs_required')
        now=dt.datetime.now(dt.timezone.utc);trust=gate.trust_file(trust_policy)
        ctx=gate.load_context(editorial_record,trust,now)
        report=gate.audit(ctx,None,trust,now,engine.read(engine.ROOT/'macro_sources.json'),engine.read(engine.ROOT/'operating_policy.json'))
        if not report['editorial_verified']:raise ValueError('editorial_verification_required')
        if engine.digest(payload['diagnostic'])!=engine.digest({k:v for k,v in ctx.diagnostic.items() if k!='supporting'}):raise ValueError('preview_snapshot_mismatch')
        payload['editorial_private']={'article':gate.parse_manuscript(ctx.manuscript,ctx.diagnostic),'gate':report}
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
            paths = {'/':'index.html','/monthly.css':'monthly.css','/monthly.js':'monthly.js',
                     '/monthly-market-weather.css':'shared_css','/monthly-market-weather-view.js':'shared_view'}
            if self.path in paths:
                asset={'shared_css':engine.ROOT/'site/monthly-market-weather.css',
                       'shared_view':engine.ROOT/'site/monthly-market-weather-view.js'}.get(paths[self.path],ASSETS/paths[self.path])
                suffix = asset.suffix
                kind = {'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8'}[suffix]
                return self.respond(200,asset.read_bytes(),kind,cookie=self.path=='/')
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
    parser.add_argument('--editorial-record',type=Path)
    parser.add_argument('--trust-policy',type=Path)
    parser.add_argument('--review-manifest',type=Path)
    args=parser.parse_args()
    try:
        server=create_server(args.bundle,args.port,args.editorial_record,args.trust_policy,args.review_manifest)
        print(f'Local private review: http://127.0.0.1:{server.server_port}/',flush=True)
        server.serve_forever()
    except KeyboardInterrupt:return 0
    except Exception:
        print('private_preview_validation_failed');return 1


if __name__ == '__main__':raise SystemExit(main())
