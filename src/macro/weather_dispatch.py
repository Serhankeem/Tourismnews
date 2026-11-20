"""One explicit main Deploy dispatch authorizes one hash-bound frozen candidate.

GitHub's authenticated run title binds BOTH input hashes. No boolean environment
variable, supplied status or local receipt authorizes a publication. A persistent
HMAC seals issued catalogs; recurring deployments need no draft/approval files.
"""
import argparse
import base64
import datetime as dt
import json
import os
from pathlib import Path
import re
import zlib
import urllib.error
import urllib.request

from . import weather_publication as gate, weather_release as release, weather_shadow as shadow
from .tourgo_delivery import GitHub as BaseGitHub

REPOSITORY='Serhankeem/tourismnews'
NAMES={'bundle_manifest':'manifest.json','diagnostic':'diagnostic-private.json',
       'config':'inputs/config.json','archive':'inputs/archive.json','policy':'inputs/policy.json'}
LIMIT=2*1024*1024


class GitHub(BaseGitHub):
    """Monthly-only read client; never prints HTTP bodies, URLs or credentials."""
    def __init__(self,token):
        gate.require(isinstance(token,str) and bool(token) and not any(c.isspace() for c in token),'monthly_token_missing')
        super().__init__(token)

    def get(self,path):
        run_path=re.fullmatch('repos/'+REPOSITORY+r'/actions/runs/[1-9][0-9]*',path) is not None
        role_path=re.fullmatch('repos/'+REPOSITORY+r'/collaborators/[A-Za-z0-9][A-Za-z0-9-]{0,38}/permission',path) is not None
        gate.require(run_path or role_path,'monthly_api_path_invalid')
        prefix='monthly_run_api_' if run_path else 'monthly_role_api_'
        request=urllib.request.Request('https://api.github.com/'+path,headers={
            'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json',
            'X-GitHub-Api-Version':'2022-11-28','User-Agent':'currentourism-monthly-read-check'})
        try:
            with self.open(request,timeout=30) as response:raw=response.read(LIMIT+1)
        except urllib.error.HTTPError as exc:
            code=prefix+{401:'unauthenticated',403:'forbidden',404:'not_found',429:'rate_limited'}.get(exc.code,'unavailable')
            if exc.code==403 and exc.headers and exc.headers.get('X-RateLimit-Remaining')=='0':code=prefix+'rate_limited'
            raise gate.GateError(code) from None
        except Exception:raise gate.GateError(prefix+'unavailable') from None
        gate.require(len(raw)<=LIMIT,prefix+'invalid_response')
        try:doc=gate.decode(raw)
        except Exception:raise gate.GateError(prefix+'invalid_response') from None
        gate.require(isinstance(doc,dict),prefix+'invalid_response')
        return doc


def encoded(doc):return (json.dumps(doc,ensure_ascii=False,separators=(',',':'))+'\n').encode()


def candidate(raw,manuscript_hash,candidate_hash):
    gate.require(gate.sha(raw)==candidate_hash,'candidate_hash_mismatch')
    doc=gate.decode(raw)
    gate.require(set(doc)=={'version','revision','period','manuscript',*NAMES} and doc['version']==1,'candidate_shape_invalid')
    gate.engine.valid_period(doc['period'])
    gate.require(isinstance(doc['revision'],str) and re.fullmatch('r[1-9][0-9]*',doc['revision']),'candidate_revision_invalid')
    manuscript=doc['manuscript'].encode()
    gate.require(gate.sha(manuscript)==manuscript_hash,'manuscript_hash_mismatch')
    parsed={k:gate.decode(doc[k].encode()) for k in NAMES}
    manifest=parsed['bundle_manifest']
    gate.require(manifest['publication_approved'] is False,'candidate_not_private')
    for key,name in NAMES.items():
        if key!='bundle_manifest':
            gate.require(manifest['files'][name]==gate.sha(doc[key].encode()),'candidate_snapshot_file_mismatch')
    ctx=gate.Context(manuscript,b'',doc['bundle_manifest'].encode(),parsed['diagnostic'],
                     parsed['config'],parsed['archive'],parsed['policy'])
    diag=ctx.diagnostic
    snapshot=dict(source_bundle_manifest_sha256=gate.sha(ctx.bundle_manifest),
                  canonical_json_input_hashes=diag['input_hashes'],methodology_version=diag['methodology_version'],
                  reference_period=doc['period'],input_cutoff=diag['input_cutoff'],original_analysis_at=diag['analysis_at'])
    return doc,ctx,snapshot


def validate(doc,ctx,snapshot,code,at,approved_at):
    config=gate.engine.read(Path(code)/'macro_sources.json');policy=gate.engine.read(Path(code)/'operating_policy.json')
    try:return gate.validate_inputs(ctx,snapshot,doc['period'],approved_at,at,config,policy)
    except gate.GateError:raise
    except Exception:raise gate.GateError('monthly_statistics_contract_invalid') from None


def authorize(api,env,manuscript_hash,candidate_hash,code_sha,at):
    for digest in (manuscript_hash,candidate_hash):
        gate.require(re.fullmatch('[a-f0-9]{64}',digest or '') is not None,'dispatch_hashes_required')
    gate.require(env.get('GITHUB_ACTIONS')=='true' and env.get('GITHUB_EVENT_NAME')=='workflow_dispatch'
                 and env.get('GITHUB_REF')=='refs/heads/main' and env.get('GITHUB_REPOSITORY')==REPOSITORY,'manual_main_dispatch_required')
    run_id=env.get('GITHUB_RUN_ID','')
    gate.require(re.fullmatch('[1-9][0-9]*',run_id) is not None,'dispatch_run_invalid')
    run=api.get('repos/'+REPOSITORY+'/actions/runs/'+run_id)
    title='Market Weather publish '+manuscript_hash+' / '+candidate_hash
    gate.require(run.get('event')=='workflow_dispatch' and run.get('status')=='in_progress'
                 and run.get('path')=='.github/workflows/deploy.yml' and run.get('head_branch')=='main'
                 and run.get('head_sha')==code_sha==env.get('GITHUB_SHA')
                 and run.get('display_title')==title and run.get('run_attempt')==1
                 and str(run.get('id'))==run_id and run.get('repository',{}).get('full_name')==REPOSITORY
                 and run.get('head_repository',{}).get('id')==run.get('repository',{}).get('id'),
                 'github_dispatch_binding_invalid')
    actor=run.get('actor',{});login=actor.get('login','')
    gate.require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9-]{0,38}',login) is not None
                 and str(actor.get('id'))==env.get('GITHUB_ACTOR_ID')
                 and run.get('triggering_actor',{}).get('id')==actor.get('id'),'github_dispatch_actor_invalid')
    permission=api.get('repos/'+REPOSITORY+'/collaborators/'+login+'/permission')
    gate.require(permission.get('permission') in ('admin','write','maintain')
                 and permission.get('user',{}).get('id')==actor.get('id'),'github_publish_permission_required')
    approved=gate.public_time(run.get('created_at'))
    gate.require(approved<=at<=approved+dt.timedelta(hours=2),'dispatch_stale_or_future')
    return approved


class Request:
    """Constructed only after live GitHub verification, never from a permit flag."""
    def __init__(self,raw,manuscript_hash,candidate_hash,api,env,code,code_sha,at):
        self.approved_at=authorize(api,env,manuscript_hash,candidate_hash,code_sha,at)
        self.raw=bytes(raw);self.manuscript_hash=manuscript_hash;self.candidate_hash=candidate_hash
        try:doc,ctx,snapshot=candidate(self.raw,manuscript_hash,candidate_hash)
        except gate.GateError:raise
        except Exception:raise gate.GateError('monthly_candidate_contract_invalid') from None
        self.authority=None  # Existing runner distinguishes private legacy authority.
        self.release_key='market-weather-'+doc['period']+':1'
        release.signing_key()  # Fail before any public projection if not configured.
        validate(doc,ctx,snapshot,code,at,self.approved_at)

    def apply(self,stage,code,at):
        stage=Path(stage).resolve()
        gate.require(stage!=gate.engine.ROOT and gate.engine.ROOT not in stage.parents and stage not in gate.engine.ROOT.parents,'isolated_publication_stage_required')
        doc,ctx,snapshot=candidate(self.raw,self.manuscript_hash,self.candidate_hash)
        gate.require(self.release_key=='market-weather-'+doc['period']+':1','candidate_scope_mismatch')
        article=validate(doc,ctx,snapshot,code,at,self.approved_at)
        stored=release.verify(stage,code,at=at)
        # A legacy edition needs its existing authority; never silently reseal it.
        gate.require(stored is None or 'seal' in stored[0],'legacy_authority_migration_required')
        grants={} if stored is None else {e['key']:{'content':stored[1]['contents'][e['key']],'not_after':e['not_after']} for e in stored[0]['entries']}
        metadata=dict(content_id='market-weather-'+doc['period'],reference_period=doc['period'],editorial_revision=doc['revision'])
        # The one verified dispatch replaces monthly dual receipts, not the data gate.
        payload=gate._projection(ctx,metadata,{'publication':{'public_revision':1,'release_at':self.approved_at.isoformat()}},article)
        if self.release_key in grants:
            old=grants[self.release_key]['content']
            gate.require({k:v for k,v in old.items() if k!='issued_at'}=={k:v for k,v in payload.items() if k!='issued_at'},'published_edition_immutable')
            return False
        grants[self.release_key]={'content':payload,'not_after':'9999-12-31T23:59:59+00:00'}
        index,archive=release.documents(grants);index['seal']=release.seal((index,archive))
        for name,doc in zip(release.PUBLIC_FILES,(index,archive)):
            path=stage/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
        release.verify(stage,code,at=at)
        return True


def from_environment(code,code_sha,manuscript_hash,candidate_hash,at):
    env=os.environ
    # Only transport whitespace is removed; decoded candidate bytes must still
    # match the approved hash. Clipboard line endings do not change that binding.
    value=env.get('MARKET_WEATHER_CANDIDATE_B64','')
    gate.require(bool(value),'candidate_secret_missing_or_oversized')
    try:compressed=base64.b64decode(re.sub(r'[ \t\r\n]','',value),validate=True)
    except Exception:raise gate.GateError('monthly_candidate_base64_invalid') from None
    gate.require(0<len(compressed)<=48*1024,'candidate_secret_missing_or_oversized')
    try:
        decoder=zlib.decompressobj();raw=decoder.decompress(compressed,LIMIT+1)
        gate.require(len(raw)<=LIMIT and decoder.eof and not decoder.unused_data,'candidate_size_or_encoding_invalid')
    except gate.GateError:raise
    except Exception:raise gate.GateError('candidate_size_or_encoding_invalid') from None
    return Request(raw,manuscript_hash,candidate_hash,GitHub(env.get('PIPELINE_GITHUB_TOKEN')),env,code,code_sha,at)


def main():
    """Offline preparation only: no signature, approval, public JSON or network."""
    p=argparse.ArgumentParser(description=main.__doc__)
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--manuscript',type=Path,required=True)
    p.add_argument('--revision',required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.resolve()
    gate.require(out!=gate.engine.ROOT and gate.engine.ROOT not in out.parents and out not in gate.engine.ROOT.parents and not out.exists(),'new_external_output_required')
    shadow.verify_bundle(args.bundle)
    diag=gate.engine.read(args.bundle/'diagnostic-private.json')
    doc=dict(version=1,revision=args.revision,period=diag['target_period'],manuscript=args.manuscript.read_bytes().decode('utf-8'))
    doc.update({k:(args.bundle/name).read_bytes().decode('utf-8') for k,name in NAMES.items()})
    raw=encoded(doc);mh=gate.sha(args.manuscript.read_bytes());ch=gate.sha(raw)
    parsed,ctx,snapshot=candidate(raw,mh,ch);now=dt.datetime.now(dt.timezone.utc)
    article=validate(parsed,ctx,snapshot,gate.engine.ROOT,now,now)
    secret=base64.b64encode(zlib.compress(raw,9))
    gate.require(len(secret)<48*1024,'candidate_exceeds_github_secret_limit')
    out.mkdir(parents=True,mode=0o700)
    (out/'candidate.b64').write_bytes(secret);(out/'candidate.b64').chmod(0o600)
    (out/'review.json').write_bytes(encoded(dict(manuscript_sha256=mh,candidate_sha256=ch,reference_period=parsed['period'],
        revision=parsed['revision'],sections=len(article['sections']),statistics_and_prose_verified=True,
        independent_xlsx_reparse=False,historical_as_of_verified=False,approval='not_requested',public_json_generated=False)))
    print('Candidate prepared outside repository; review.json contains both dispatch hashes. No approval or public JSON created.')


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('Monthly candidate preparation failed; no publication performed.') from None
