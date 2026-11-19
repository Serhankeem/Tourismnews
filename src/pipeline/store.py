"""Normal fast-forward Git transactions. Never writes application refs."""
import json
import os
import base64
import shutil
import subprocess
from pathlib import Path
from .layout import MANIFEST, CONTROL, files, hashes, copy_data, read, optional
from .validation import validate
from ..collector import write_atomic, now_kst, iso

COMPACT_AT_BYTES=8*1024*1024
MAX_BLOB_BYTES=100*1024*1024


def push_reason(stderr):
    """Classify in memory; never retain Git output, credentials or remote URLs."""
    value=(stderr or '').lower()
    if 'gh001' in value or 'exceeds github' in value or 'file size limit' in value:return 'git_remote_blob_limit'
    if any(s in value for s in ('permission denied','authentication failed','write access','error: 403','error: 401')):return 'git_permission_denied'
    if any(s in value for s in ('gh013','protected branch','repository rule','pre-receive hook declined')):return 'git_remote_policy_rejected'
    if any(s in value for s in ('could not resolve','timed out','connection reset','http 502','http 503','remote end hung')):return 'git_transport_failure'
    return 'git_push_rejected_unknown'


def prepare_storage(stage,cfg):
    """Encoding only: preserve every candidate and field; fail before Git add."""
    from ..discovery_storage import encode,decode
    path=Path(stage)/'collector_state/discovery.json';changes=[]
    if path.stat().st_size>=COMPACT_AT_BYTES:
        logical=read(path);packed=encode(logical)
        if decode(packed)!=logical:raise StoreError('discovery_storage_roundtrip_failed')
        before=path.stat().st_size;write_atomic(path,packed)
        changes.append(dict(file='collector_state/discovery.json',before_bytes=before,after_bytes=path.stat().st_size,
                            logical_bytes=packed['uncompressed_bytes'],candidates=len(logical.get('candidates',{})),lossless=True))
    sizes=[dict(file=n,bytes=(Path(stage)/n).stat().st_size) for n in files(cfg)+[CONTROL]]
    if any(v['bytes']>MAX_BLOB_BYTES for v in sizes):raise StoreError('git_blob_size_limit_preflight')
    return dict(encoding_changes=changes,largest=sorted(sizes,key=lambda v:v['bytes'],reverse=True)[:3],
                logical_warning=any(v['logical_bytes']>=256*1024*1024 for v in changes),
                warning_files=[v for v in sizes if v['bytes']>=50*1024*1024])


class StoreError(RuntimeError):
    pass


class Conflict(StoreError):
    pass


def git(directory, *args, ok=(0,)):
    # Error output can contain remote credentials. Return a stable category only.
    env=os.environ.copy()
    token=env.get('PIPELINE_GITHUB_TOKEN')
    if token:
        index=int(env.get('GIT_CONFIG_COUNT','0'))
        env['GIT_CONFIG_COUNT']=str(index+1)
        env['GIT_CONFIG_KEY_'+str(index)]='http.https://github.com/.extraheader'
        env['GIT_CONFIG_VALUE_'+str(index)]='AUTHORIZATION: basic '+base64.b64encode(('x-access-token:'+token).encode()).decode()
    r = subprocess.run(['git',*args],cwd=directory,capture_output=True,text=True,env=env)
    if r.returncode not in ok:
        raise StoreError('git_operation_failed:'+args[0])
    return r


class Store:
    def __init__(self, path, remote, cfg):
        self.path, self.remote, self.cfg = Path(path), remote, cfg
        if cfg['branch'] != 'data/live':
            raise StoreError('ref_not_allowed')
        self.path.mkdir(parents=True,exist_ok=True)
        git(self.path,'init','-b','snapshot')
        git(self.path,'config','user.name','github-actions[bot]')
        git(self.path,'config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
        git(self.path,'remote','add','origin',remote)
        self.base = None
        self.storage_diagnostics={}

    def tip(self, branch='data/live'):
        r=git(self.path,'ls-remote','--exit-code','origin','refs/heads/'+branch,ok=(0,2))
        return r.stdout.split()[0] if r.returncode==0 else None

    def load(self, seed, code_commit):
        self.base=self.tip()
        if self.base:
            git(self.path,'fetch','--no-tags','origin','refs/heads/data/live')
            git(self.path,'checkout','-B','snapshot','FETCH_HEAD')
            self.base=git(self.path,'rev-parse','HEAD').stdout.strip()
            self.cfg=optional(self.cfg,self.path)
            allowed=set(files(self.cfg)+[MANIFEST,CONTROL])
            for line in git(self.path,'ls-tree','-r','HEAD').stdout.splitlines():
                mode,kind,tail=line.split(' ',2);_,name=tail.split('\t',1)
                if mode!='100644' or kind!='blob' or name not in allowed:
                    raise StoreError('unexpected_snapshot_tree_entry')
            manifest=read(self.path/MANIFEST)
            if manifest.get('schema_version')!=1 or manifest.get('files')!=hashes(self.path,files(self.cfg)+[CONTROL]):
                raise StoreError('snapshot_checksum_mismatch')
            validate(self.path,self.cfg)
            return False
        # Only an explicitly absent ref bootstraps. Network/auth errors abort.
        self.cfg=optional(self.cfg,seed)
        counts=validate(seed,self.cfg)
        copy_data(seed,self.path,self.cfg)
        write_atomic(self.path/CONTROL,{'schema_version':1,'initialized_from_main':code_commit,
                     'initialized_at':iso(now_kst()),'initial_counts':counts,
                     'initial_file_sha256':hashes(seed,files(self.cfg)),'completed_slots':{}})
        return True

    def commit(self, stage, code_commit, before,precommit=None):
        if precommit is not None:precommit()
        self.cfg=optional(self.cfg,stage)
        self.storage_diagnostics=prepare_storage(stage,self.cfg)
        validate(stage,self.cfg,before=before)
        if self.tip()!=self.base:
            raise Conflict('remote_data_changed_retry_collection')
        for name in files(self.cfg)+[CONTROL]:
            src,dst=Path(stage)/name,self.path/name
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dst)
        checksum=hashes(self.path,files(self.cfg)+[CONTROL])
        prior=read(self.path/MANIFEST) if (self.path/MANIFEST).exists() else {}
        if prior.get('files')==checksum and prior.get('policy_code_commit')==code_commit:
            return self.base,False
        write_atomic(self.path/MANIFEST,{'schema_version':1,'policy_code_commit':code_commit,'files':checksum})
        git(self.path,'add','--',*files(self.cfg),CONTROL,MANIFEST)
        git(self.path,'commit','-m','Persist validated collection state')
        commit=git(self.path,'rev-parse','HEAD').stdout.strip()
        if precommit is not None:precommit()
        # Normal push has server-side fast-forward protection even after tip().
        pushed=git(self.path,'push','origin','HEAD:refs/heads/data/live',ok=(0,1,128))
        if pushed.returncode:
            try:actual=self.tip()  # Also handles an interrupted acknowledgement.
            except StoreError:
                error=StoreError('git_push_outcome_unverified');error.reason_code='git_push_confirmation_failed'
                raise error from None
            if actual==commit:
                return commit,True
            if actual!=self.base:
                raise Conflict('remote_data_changed_retry_collection')
            error=StoreError('data_push_failed_no_deployment')
            error.reason_code=push_reason(pushed.stderr)
            raise error
        return commit,True
