"""Allowlisted operator diagnostics. No provider messages or Git stderr."""
import re

ENGINES={'news','reports','macro'}
CODES={'data_push_failed_no_deployment','git_remote_blob_limit','git_blob_size_limit_preflight',
       'git_permission_denied','git_remote_policy_rejected','git_transport_failure','git_push_rejected_unknown',
       'git_push_outcome_unverified','git_push_confirmation_failed','main_changed_retry_latest_code',
       'newer_code_or_data_no_stale_deployment','newer_snapshot_do_not_deploy_stale_artifact',
       'policy_day_changed_retry_before_deploy','remote_data_changed_retry_collection','conflict_retry_exhausted',
       'collector_timeout','collector_process_failed','collector_failed_or_timed_out','engine_wrote_other_dataset',
       'publication_gate_projection_mismatch','macro_publication_gate_projection_mismatch',
       'monthly_publication_gate_rejected','monthly_catalog_invalid','snapshot_checksum_mismatch',
       'unexpected_snapshot_tree_entry','unexpected_or_missing_data_inventory','production_operation_requires_main_actions',
       'tourgo_manual_transaction_failed_no_data_committed','discovery_storage_roundtrip_failed',
       'monthly_guard_snapshot_missing','monthly_guard_snapshot_changed','monthly_guard_artifact_changed',
       'monthly_guard_artifact_symlink','validation_or_execution_failed'}
CODES|={'discovery_logical_size_limit','discovery_storage_integrity_invalid','discovery_storage_envelope_invalid'}


def safe_code(value):return value if isinstance(value,str) and value in CODES else 'validation_or_execution_failed'


def error_code(exc):
    if type(exc).__name__=='TimeoutExpired':return 'collector_timeout'
    return safe_code(getattr(exc,'reason_code',str(exc)))


def collection(result):
    statuses=[r.get('status') for r in result.get('engines',{}).values()]
    if not statuses:return 'not_started'
    if 'failed' in statuses:return 'failed'
    if 'running' in statuses:return 'running'
    return 'partial' if 'partial' in statuses else 'success'


def sources(health,allowed):
    doc=health.get('discovery',{});rows=doc.get('sources',[])
    permitted={'http','network','timeout','parse','access_policy','tls','http_error','connection_error'}
    failed=[r for r in rows if r.get('status')=='error'];codes={}
    for r in failed:
        code=r.get('error_kind') if r.get('error_kind') in permitted else 'source_fetch_failed'
        codes[code]=codes.get(code,0)+1
    return dict(successful_sources=sum(r.get('status')=='ok' for r in rows),failed_sources=len(failed),
                failed_source_ids=sorted({r['id'] for r in failed if r.get('id') in allowed}),failure_codes=codes,
                publication_result=doc.get('publication_result') if doc.get('publication_result') in ('ok','partial','failed') else 'unknown')


def action(result,deployment='skipped'):
    code=result.get('error_code')
    if code in ('git_remote_blob_limit','git_blob_size_limit_preflight','discovery_logical_size_limit'):return 'review_storage_capacity'
    if code=='git_permission_denied':return 'check_repository_access'
    if code=='git_remote_policy_rejected':return 'review_repository_rules'
    if code=='git_push_confirmation_failed' or result.get('storage_status')=='unverified':return 'confirm_remote_head'
    if code in ('git_transport_failure','git_push_rejected_unknown','data_push_failed_no_deployment','remote_data_changed_retry_collection','conflict_retry_exhausted','main_changed_retry_latest_code','newer_code_or_data_no_stale_deployment','newer_snapshot_do_not_deploy_stale_artifact','policy_day_changed_retry_before_deploy'):return 'retry_latest_snapshot_after_review'
    if code:return 'review_validation_and_permissions'
    if deployment in ('failure','cancelled') or (result.get('data_committed') and not result.get('ready')):return 'review_saved_snapshot_before_redeploy'
    if collection(result) in ('failed','partial'):return 'review_source_health'
    return 'none'


def failure(result,exc):
    code=error_code(exc)
    result.update(failure_phase=result.get('phase','authorization'),error_kind=type(exc).__name__ if type(exc).__name__ in
                  ('StoreError','Conflict','ValidationError','DataError','ValueError','OSError','RuntimeError','TimeoutExpired') else 'ExecutionError',
                  error=safe_code(str(exc)),error_code=code,ready=False,previous_public_preserved=True)
    if result.get('phase')=='persist':
        result['storage_status']='unverified' if str(exc)=='git_push_outcome_unverified' else 'failed'
        if result['storage_status']=='unverified':
            result.update(data_commit=None,data_committed=None,new_records={k:None for k in ('news','reports','macro_observations')})
    result['collection_status']=collection(result);result['operator_action']=action(result)
    result['retry_required']=result['operator_action']!='none'


def sha(value):return value if isinstance(value,str) and re.fullmatch('[0-9a-f]{40,64}',value) else 'unverified'
