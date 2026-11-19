"""Main-only transactional collection + validated Pages assembly.

Production refs are never changed by tests/PR jobs. The Store class is tested
against local bare repositories; this CLI requires the main Actions context.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import tempfile
from pathlib import Path
from .layout import ROOT, CONTROL, MANIFEST, configuration, files, hashes, copy_data, read, owner, DataError, optional
from .store import Store, StoreError, Conflict, git
from .validation import validate, ValidationError
from .schedule import pending
from .policy import project, verify_public
from . import diagnostics
from ..collector import write_atomic, now_kst, iso


def invoke(engine, stage, force, days):
    import subprocess
    import sys
    command=[sys.executable,'-m','src.pipeline.collect',engine,'--stage',str(stage),'--days',str(days)]
    if force:command.append('--force')
    # Keep a slow engine from consuming the whole shared lock. No provider
    # error payload or credential-bearing traceback is copied into public logs.
    result=subprocess.run(command,cwd=ROOT,capture_output=True,timeout={'news':900,'reports':1200,'macro':600}[engine])
    if result.returncode not in (0,1):raise RuntimeError('collector_process_failed')
    return result.returncode==0


def compose(code, snapshot, output, cfg, macro_config=None,monthly_authority=None,at=None):
    # Code's frozen main data is excluded, even if newer files were added there.
    cfg=optional(cfg,snapshot);validate(snapshot,cfg)
    verify_public(snapshot,code,macro_config=macro_config,monthly_authority=monthly_authority,at=at)
    output=Path(output).resolve();snapshot=Path(snapshot).resolve()
    code_path=Path(code).resolve()
    if output==snapshot or output in snapshot.parents or snapshot in output.parents or output==code_path or code_path in output.parents or output in code_path.parents:
        raise ValidationError('isolated_pages_output_required')
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix='.pages-build-',dir=output.parent));candidate=temporary/'pages';backup=temporary/'previous'
    try:
        shutil.copytree(Path(code)/'site',candidate,ignore=shutil.ignore_patterns('data','collector_state','*.pyc','__pycache__'))
        for name in cfg['public_files']:
            dest=candidate/Path(name).relative_to('site');dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(Path(snapshot)/name,dest)
        if (candidate/'collector_state').exists() or set(p.name for p in (candidate/'data').iterdir())!={Path(p).name for p in cfg['public_files']}:
            raise ValidationError('unexpected_pages_tree')
        if any(p.is_symlink() for p in candidate.rglob('*')):raise ValidationError('pages_symlink_forbidden')
        static={str(p.relative_to(candidate)) for p in candidate.rglob('*') if p.is_file() and p.relative_to(candidate).parts[0]!='data'}
        if static!=set(cfg['static_public_files']):raise ValidationError('unexpected_static_asset')
        actual_json={str(p.relative_to(candidate)) for p in candidate.rglob('*.json')}
        if actual_json!={str(Path(n).relative_to('site')) for n in cfg['public_files']}|{'assets/content-localization.json'}:
            raise ValidationError('unexpected_static_json_asset')
        if any(p.suffix=='.md' and str(p.relative_to(candidate))!='assets/README.md' for p in candidate.rglob('*')):
            raise ValidationError('private_manuscript_asset_forbidden')
        # Recheck fresh authority/rights immediately before promotion, after copying.
        verify_public(snapshot,code,macro_config=macro_config,monthly_authority=monthly_authority,at=at)
        if hashes(candidate,[str(Path(n).relative_to('site')) for n in cfg['public_files']])!={str(Path(n).relative_to('site')):v for n,v in hashes(snapshot,cfg['public_files']).items()}:
            raise ValidationError('pages_copy_changed')
        if output.exists():os.replace(output,backup)
        try:os.replace(candidate,output)
        except Exception:
            if backup.exists():os.replace(backup,output)
            raise
    finally:
        # Never delete the previous artifact if an OS-level rollback also fails.
        if not backup.exists():shutil.rmtree(temporary)
        elif output.exists():shutil.rmtree(temporary)
    return hashes(snapshot,cfg['public_files'])


def transact(code, remote, work, output, requested='none', force=False, days=90, collector=invoke, at=None, max_attempts=3, result=None, tourgo_request=None,monthly_request=None,monthly_authority=None):
    code,work=Path(code),Path(work);cfg=configuration(code);work.mkdir(parents=True,exist_ok=True)
    code_commit=git(code,'rev-parse','HEAD').stdout.strip()
    if result is None:result={}
    if tourgo_request is not None and requested!='macro':raise DataError('tourgo_manual_import_requires_macro_transaction')
    result.update(phase='load',main_auto_commit=False,code_commit=code_commit,engines={},ready=False,requested=requested,
                  collection_ok=None,collection_status='not_started',storage_status='not_attempted',data_committed=False,
                  new_records={k:0 for k in ('news','reports','macro_observations')},previous_public_preserved=True)
    for attempt in range(max_attempts):
        attempt_dir=work/('attempt-'+str(attempt));attempt_dir.mkdir()
        write_atomic(work/'result.json',result)
        store=Store(attempt_dir/'snapshot',remote,cfg)
        if store.tip('main')!=code_commit:
            raise StoreError('main_changed_retry_latest_code')
        initialized=store.load(code,code_commit)
        result.update(data_base_commit=store.base,data_commit=store.base,data_committed=False,storage_status='not_attempted')
        cfg=store.cfg
        stage=attempt_dir/'stage';copy_data(store.path,stage,cfg)
        shutil.copyfile(store.path/CONTROL,stage/CONTROL)
        before=attempt_dir/'before';copy_data(stage,before,cfg)
        clock=at or now_kst();control=read(stage/CONTROL)
        # Re-read and revalidate the reviewed private input against each freshly
        # restored snapshot, including after a normal fast-forward conflict.
        manual_ledger=tourgo_request.validate(stage,code,clock) if tourgo_request is not None else None
        quality=getattr(tourgo_request,'outcome',None)
        if quality is not None:
            result['tourgo_verification']=quality
            if quality['status']!='VALID':
                if store.tip('main')!=code_commit:raise StoreError('main_changed_retry_latest_code')
                if store.tip()!=store.base:
                    if attempt+1==max_attempts:raise Conflict('remote_data_changed_retry_collection')
                    continue
                result.update(phase='tourgo_staging_evaluated',engines={},attempt=attempt+1,bootstrap=initialized,
                    data_committed=False,data_commit=store.base,
                    ready=False,collection_ok=quality['status']=='UNCHANGED',previous_data_preserved=True,
                    counts=validate(stage,cfg),new_records={'macro_observations':0})
                return result
        due=pending(control,clock,requested)
        result.update(phase='collect',bootstrap=initialized,engines={},attempt=attempt+1)
        for engine,slot in due.items():
            checkpoint=attempt_dir/('before-'+engine);copy_data(stage,checkpoint,cfg)
            pre=hashes(stage,files(cfg))
            result['engines'][engine]={'status':'running'}
            write_atomic(work/'result.json',result)
            try:
                if engine=='macro' and tourgo_request is not None:
                    from ..macro.engine import collect as collect_macro
                    health=collect_macro(read(code/'macro_sources.json'),stage/'site/data',stage/'collector_state',
                        now=clock,force=force,tourgo_ledger=manual_ledger,operating_policy=read(code/'operating_policy.json'))
                    # A healthy KTO response must not mask an explicitly failed
                    # manual TOURGO import as a successful partial collection.
                    from ..macro.tourgo import SOURCE
                    success=next((s.get('status')=='ok' for s in health['sources'] if s['id']==SOURCE),False)
                    if success:tourgo_request.verify_projection(stage)
                else:
                    success=collector(engine,stage,force and engine==requested,days)
                after=hashes(stage,files(cfg))
                if optional(cfg,stage)['public_files']!=cfg['public_files']:
                    raise ValidationError('engine_wrote_other_dataset')
                if any(pre[p]!=after[p] and owner(p)!=engine for p in pre):
                    raise ValidationError('engine_wrote_other_dataset')
                validate(stage,cfg,before=checkpoint)
            except Exception as exc:
                shutil.rmtree(stage)
                copy_data(checkpoint,stage,cfg)
                result['engines'][engine]={'status':'failed','error_kind':type(exc).__name__ if type(exc).__name__ in ('DataError','ValidationError','TimeoutExpired','RuntimeError','OSError','ValueError') else 'ExecutionError',
                    'error':diagnostics.error_code(exc),
                    'previous_data_preserved':True}
                continue
            health_name={'news':'health','reports':'reports_health','macro':'macro_health'}[engine]
            health=read(stage/('site/data/'+health_name+'.json'))
            observed=health.get('discovery',{}).get('discovery_status') if engine=='news' else health.get('status')
            status=(observed if observed in ('partial','not_due') else 'ok') if success else 'failed'
            result['engines'][engine]={'status':status,'slot':slot,'health_file':'site/data/'+health_name+'.json'}
            if engine=='news':
                result['engines'][engine]['source_summary']=diagnostics.sources(health,{s['id'] for s in read(code/'sources.json')['sources']})
            if success:control['completed_slots'][engine]=slot
        result['collection_status']=diagnostics.collection(result)
        result['collection_ok']=all(r['status'] in ('ok','partial','not_due') for r in result['engines'].values())
        if tourgo_request is not None and result['engines'].get('macro',{}).get('status')=='failed':
            raise DataError('tourgo_manual_transaction_failed_no_data_committed')
        write_atomic(stage/CONTROL,control)
        result['phase']='validate'
        projection_clock=at or now_kst()
        project(stage,code,projection_clock)
        if monthly_request is not None:
            if monthly_authority is not monthly_request.authority:raise DataError('monthly_authority_mismatch')
            pre=hashes(stage,files(cfg));monthly_request.apply(stage,code,projection_clock)
            if any(hashes(stage,[n])[n]!=h for n,h in pre.items() if owner(n)!='weather'):
                raise ValidationError('monthly_request_wrote_other_dataset')
            cfg=optional(cfg,stage);store.cfg=cfg
        counts=validate(stage,cfg,before=before);verify_public(stage,code,monthly_authority=monthly_authority,at=projection_clock)
        old_ids={a['id'] for a in read(before/'collector_state/archive.json')['articles']}
        old_reports={a['id'] for a in read(before/'collector_state/reports_archive.json')['reports']}
        old_macro=read(before/'collector_state/macro_archive.json')['indicators']
        new_records={
            'news':sum(a['id'] not in old_ids and a.get('record_type','news')=='news' for a in read(stage/'collector_state/archive.json')['articles']),
            'reports':sum(a['id'] not in old_reports for a in read(stage/'collector_state/reports_archive.json')['reports']),
            'macro_observations':sum(len(set(a['observations'])-set(old_macro.get(i,{}).get('observations',{}))) for i,a in read(stage/'collector_state/macro_archive.json')['indicators'].items())}
        result.update(counts=counts,attempted_new_records=new_records)
        if store.tip('main')!=code_commit:
            raise StoreError('main_changed_retry_latest_code')
        result['phase']='persist'
        result['storage_status']='pending'
        try:
            monthly_present=any(n.startswith('site/data/market_weather_') for n in cfg['public_files'])
            recheck=(lambda:verify_public(stage,code,monthly_authority=monthly_authority,at=at or now_kst())) if monthly_present else None
            if recheck is None:data_commit,changed=store.commit(stage,code_commit,before)
            else:data_commit,changed=store.commit(stage,code_commit,before,precommit=recheck)
        except Conflict:
            result.setdefault('retry_events',[]).append(dict(attempt=attempt+1,code='remote_data_changed_retry_collection'))
            if attempt+1==max_attempts:raise
            continue  # Reload latest snapshot, then recollect. No JSON overwrite.
        except Exception as exc:
            result['storage_diagnostics']=store.storage_diagnostics
            diagnostics.failure(result,exc)
            raise
        result.update(data_commit=data_commit,data_committed=changed,counts=counts,new_records=new_records,
                      storage_status='committed' if changed else 'unchanged',storage_diagnostics=store.storage_diagnostics)
        if store.tip('main')!=code_commit or store.tip()!=data_commit:
            raise StoreError('newer_code_or_data_no_stale_deployment')
        result['phase']='assemble'
        public_hashes=compose(code,store.path,output,cfg,monthly_authority=monthly_authority,at=at)
        artifact_names=[str(p.relative_to(output)) for p in Path(output).rglob('*') if p.is_file()]
        write_atomic(work/'deployment.json',{'code_commit':code_commit,'data_commit':data_commit,'public_files':public_hashes,'policy_evaluated_on':projection_clock.date().isoformat(),
                                           'artifact_directory':str(Path(output).resolve()),'artifact_file_sha256':hashes(output,artifact_names)})
        result.update(phase='ready_for_pages',ready=True,data_commit=data_commit,data_committed=changed,counts=counts)
        result['collection_ok']=all(r['status'] in ('ok','partial','not_due') for r in result['engines'].values())
        result.update(operator_action=diagnostics.action(result),retry_required=not result['collection_ok'])
        return result
    raise StoreError('conflict_retry_exhausted')


def require_main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REF')!='refs/heads/main' or os.environ.get('GITHUB_EVENT_NAME') not in ('push','schedule','workflow_dispatch'):
        raise StoreError('production_operation_requires_main_actions')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('operation',choices=['run','guard'])
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--output',type=Path)
    p.add_argument('--requested',choices=['none','news','reports','macro'],default='none')
    p.add_argument('--force',action='store_true')
    p.add_argument('--days',choices=[30,60,90],type=int,default=90)
    p.add_argument('--tourgo-ledger',type=Path);p.add_argument('--tourgo-ledger-sha256')
    p.add_argument('--tourgo-receipt',type=Path);p.add_argument('--tourgo-receipt-sha256')
    p.add_argument('--tourgo-input-dir',type=Path)
    p.add_argument('--tourgo-update-input-dir',type=Path)
    p.add_argument('--monthly-authority-dir',type=Path)
    p.add_argument('--monthly-release-key')
    p.add_argument('--monthly-manuscript-sha256')
    p.add_argument('--monthly-candidate-sha256')
    args=p.parse_args();args.work.mkdir(parents=True,exist_ok=True)
    result={'phase':'authorization','ready':False,'main_auto_commit':False}
    try:
        require_main()
        from ..macro import weather_release
        authority=weather_release.directory(args.monthly_authority_dir) if args.monthly_authority_dir else weather_release.environment()
        monthly=None
        if args.monthly_release_key:
            if args.operation!='run' or authority is None:raise DataError('monthly_authority_required')
            monthly=weather_release.PublicationRequest(authority,args.monthly_release_key)
        if args.monthly_manuscript_sha256 or args.monthly_candidate_sha256:
            if args.operation!='run' or args.monthly_release_key or authority is not None or args.requested!='none':raise DataError('monthly_dispatch_arguments_invalid')
            from ..macro.weather_dispatch import from_environment
            monthly=from_environment(ROOT,git(ROOT,'rev-parse','HEAD').stdout.strip(),args.monthly_manuscript_sha256,args.monthly_candidate_sha256,now_kst())
        manual=(args.tourgo_ledger,args.tourgo_ledger_sha256,args.tourgo_receipt,args.tourgo_receipt_sha256)
        request=None
        if args.tourgo_update_input_dir is not None:
            if args.tourgo_input_dir is not None or any(v is not None for v in manual) or args.operation!='run' or args.requested!='macro':
                raise DataError('tourgo_manual_import_arguments_invalid')
            from ..macro.tourgo_update import RecurringRequest
            request=RecurringRequest(args.tourgo_update_input_dir)
        elif args.tourgo_input_dir is not None:
            if any(v is not None for v in manual) or args.operation!='run' or args.requested!='macro':
                raise DataError('tourgo_manual_import_arguments_invalid')
            from ..macro.tourgo_delivery import request as protected_request
            request=protected_request(args.tourgo_input_dir,os.environ.get('TOURGO_MANIFEST_SHA256',''))
        elif any(v is not None for v in manual):
            if not all(manual) or args.operation!='run' or args.requested!='macro':
                raise DataError('tourgo_manual_import_arguments_invalid')
            from ..macro.tourgo_release import ReleaseRequest
            request=ReleaseRequest(*manual)
        remote=git(ROOT,'remote','get-url','origin').stdout.strip()
        if args.operation=='guard':
            if (args.work/'result.json').exists():result=read(args.work/'result.json')
            result['phase']='deployment_guard'
            proof=read(args.work/'deployment.json')
            if proof['policy_evaluated_on']!=now_kst().date().isoformat():
                raise StoreError('policy_day_changed_retry_before_deploy')
            tip=git(ROOT,'ls-remote','origin','refs/heads/main','refs/heads/data/live').stdout
            found={line.split()[1]:line.split()[0] for line in tip.splitlines()}
            if found.get('refs/heads/main')!=proof['code_commit'] or found.get('refs/heads/data/live')!=proof['data_commit']:
                raise StoreError('newer_snapshot_do_not_deploy_stale_artifact')
            if any(name in proof['public_files'] for name in weather_release.PUBLIC_FILES):
                snapshots=list(args.work.glob('attempt-*/snapshot'))
                if not snapshots:raise StoreError('monthly_guard_snapshot_missing')
                snapshot=max(snapshots,key=lambda p:int(p.parent.name.split('-')[-1]))
                cfg=optional(configuration(ROOT),snapshot)
                if hashes(snapshot,cfg['public_files'])!=proof['public_files']:raise StoreError('monthly_guard_snapshot_changed')
                verify_public(snapshot,ROOT,monthly_authority=authority,at=now_kst())
                artifact=Path(proof['artifact_directory'])
                if any(p.is_symlink() for p in artifact.rglob('*')):raise StoreError('monthly_guard_artifact_symlink')
                actual=[str(p.relative_to(artifact)) for p in artifact.rglob('*') if p.is_file()]
                if set(actual)!=set(proof['artifact_file_sha256']) or hashes(artifact,actual)!=proof['artifact_file_sha256']:
                    raise StoreError('monthly_guard_artifact_changed')
            return 0
        result=transact(ROOT,remote,args.work,args.output,args.requested,args.force,args.days,result=result,tourgo_request=request,monthly_request=monthly,monthly_authority=authority)
        write_atomic(args.work/'result.json',result)
        if result['ready'] and os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('ready=true\n')
        return 0 if result['collection_ok'] else 1
    except Exception as exc:
        # Never expose endpoint queries/credential-bearing exception payloads.
        diagnostics.failure(result,exc)
        write_atomic(args.work/'result.json',result)
        return 1


if __name__=='__main__':raise SystemExit(main())
