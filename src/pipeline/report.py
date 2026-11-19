"""Human-readable Actions status; collection, persistence and deployment differ."""
import argparse
from pathlib import Path
from .layout import read
from . import diagnostics
from ..collector import write_atomic

PHASES={'authorization','load','collect','validate','persist','assemble','ready_for_pages','deployment_guard','tourgo_staging_evaluated'}
STATES={'not_attempted','pending','committed','unchanged','failed','unverified'}
ACTIONS={
 'none':'추가 조치 없음',
 'review_storage_capacity':'원장 압축/파일 용량을 검토하세요. 승인 전 실행하지 마세요.',
 'check_repository_access':'저장소 쓰기 권한/인증을 운영자가 확인하세요. Secret을 출력하지 마세요.',
 'review_repository_rules':'data/live 보호 규칙과 거절 분류를 확인하세요.',
 'confirm_remote_head':'push 수락 여부 미확인: 원격 head부터 확인하고 중복 실행을 판단하세요.',
 'retry_latest_snapshot_after_review':'최신 main/data/live를 확인하고 검수·승인 후 재시도를 판단하세요.',
 'review_validation_and_permissions':'데이터 검증/승인·권리 게이트를 검토하세요. 완화하거나 강제 롤백하지 마세요.',
 'review_saved_snapshot_before_redeploy':'저장된 commit을 보존하고 배포 경계/최신 head를 검토하세요.',
 'review_source_health':'일부/전체 공급원 장애를 검토하세요. 권리·검증 기준은 유지하세요.'}


def finalize(result,deployment):
    result=dict(result)
    result['deployment_status']=deployment if deployment in ('success','failure','skipped','cancelled') else 'unknown'
    result['deployment_reason']=('deployment_confirmed' if deployment=='success' else
                                 'pipeline_not_ready' if not result.get('ready') else 'deployment_not_confirmed')
    result['previous_public_preserved']=True if deployment=='skipped' else False if deployment=='success' else None
    result['operator_action']=diagnostics.action(result,result['deployment_status'])
    result['source_recovery_required']=any(row.get('source_summary',{}).get('failed_sources',0)>0 for row in result.get('engines',{}).values())
    result['retry_required']=bool(result.get('error_code') or result.get('collection_ok') is False or deployment in ('failure','cancelled'))
    return result


def render(result, deployment):
    result=finalize(result,deployment)
    phase=result.get('phase') if result.get('phase') in PHASES else 'unknown'
    storage=result.get('storage_status') if result.get('storage_status') in STATES else 'unverified'
    data_commit=diagnostics.sha(result.get('data_commit'))
    lines=['## 데이터 파이프라인 실행 결과','', '| 항목 | 결과 |','| --- | --- |',
           '| 단계 | '+phase+' |',
           '| main 자동 데이터 커밋 | 없음 |',
           '| 요청 자동화 | '+(result.get('requested') if result.get('requested') in diagnostics.ENGINES|{'none'} else '미확인')+' |',
           '| 최초 데이터 이전 | '+(('초기화 저장 확인' if result.get('data_commit') else '초기화 시도 — 저장 미확인') if result.get('bootstrap') else '기존 상태 복원 또는 미실행')+' |',
           '| 수집 결과 | '+diagnostics.collection(result)+' |',
           '| 데이터 영속 저장 | '+storage+' / 확인된 head: '+data_commit+' |',
           '| 이번 실행 신규 commit 저장 | '+str(result.get('data_committed') if type(result.get('data_committed')) is bool else '미확인')+' |',
           '| 안전한 오류 코드 | '+(diagnostics.safe_code(result['error_code']) if result.get('error_code') else '없음')+' |',
           '| Pages 배포 | '+({'success':'성공','failure':'실패/미확인 — Pages environment 확인 필요','skipped':'미실행','cancelled':'취소'}.get(deployment,'미확인'))+' |']
    quality=result.get('tourgo_verification')
    if quality:
        # Whitelisted statuses/counts only; never private hashes or input values.
        status=quality.get('status') if quality.get('status') in ('VALID','UNCHANGED','REVIEW_REQUIRED','REJECTED') else 'REJECTED'
        lines.append('| TOURGO 검증 | '+status+' |')
        for key,label in [('new_months','신규 월'),('revised_observations','정정 감지'),('anomaly_count','이상 변동')]:
            value=quality.get(key,0)
            if type(value) is int and value>=0:lines.append('| '+label+' | '+str(value)+' |')
        reasons=quality.get('reasons',[])
        allowed={'tourgo_period_scope_exceeded','tourgo_period_scope_unverified','historical_revision_requires_review','large_monthly_change_requires_review','publication_approval_required',
            'operating_mapping_not_activated','collection_approval_required','tourgo_input_validation_failed',
            'tourgo_missing_or_out_of_scope_period','tourgo_original_lost_existing_periods','tourgo_saved_source_or_unit_invalid',
            'private_input_file_hash_mismatch','private_input_manifest_hash_mismatch','tourgo_source_attestation_invalid',
            'balance_future_or_duplicate_period','balance_export_unit_or_year_mismatch','balance_identity_mismatch','tourgo_original_hash_mismatch'}
        lines.append('| TOURGO 사유 | '+', '.join(r for r in reasons if isinstance(r,str) and r in allowed)+' |')
    for engine,row in result.get('engines',{}).items():
        if engine not in diagnostics.ENGINES:continue
        status=row.get('status') if row.get('status') in ('ok','partial','not_due','failed','running') else 'unknown'
        lines.append('| '+engine+' 수집 | '+status+(' / '+diagnostics.safe_code(row['error']) if row.get('error') else '')+' |')
        summary=row.get('source_summary',{})
        for key in ('successful_sources','failed_sources'):
            value=summary.get(key)
            if type(value) is int and value>=0:lines.append('| '+engine+' '+key+' | '+str(value)+' |')
    for engine,count in result.get('new_records',{}).items():
        if engine in ('news','reports','macro_observations'):lines.append('| '+engine+' 신규 저장 | '+(str(count) if type(count) is int and count>=0 else '미확인')+' |')
    for key,value in result.get('attempted_new_records',{}).items():
        if key in ('news','reports','macro_observations') and type(value) is int and value>=0:lines.append('| '+key+' 저장 전 검증 후보 | '+str(value)+' |')
    for key,value in result.get('counts',{}).items():
        if key in ('news','archive','discovery','reports','macro_observations','private_decimal_observations','private_aviation_observations') and type(value) is int and value>=0:lines.append('| '+key+' | '+str(value)+' |')
    storage_doc=result.get('storage_diagnostics',{})
    if storage_doc.get('warning_files') or storage_doc.get('logical_warning'):lines.append('| 저장 용량 경고 | 있음 — 원장 분할 계획 검토 |')
    lines+=['','이전 공개 콘텐츠 보존: '+('확인' if result['previous_public_preserved'] is True else '이번 배포 성공' if result['previous_public_preserved'] is False else '배포 응답 확인 필요'),
            '운영자 조치: '+ACTIONS[result['operator_action']]]
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--deployment',default='skipped');args=p.parse_args()
    path=args.work/'result.json';result=finalize(read(path) if path.exists() else {},args.deployment)
    write_atomic(path,result);print(render(result,args.deployment))
if __name__=='__main__':main()
