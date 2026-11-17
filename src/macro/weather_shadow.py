"""Manual private shadow briefing and current-vintage sensitivity audit. No network."""
import argparse
import copy
import datetime as dt
from decimal import Decimal, localcontext, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path

from . import weather_diagnostic as engine
from .model import valid_period

VERSION = 'weather-shadow-v0.1'
LABELS = {'kto_inbound': '방한 외래관광객', 'kto_tourism_receipts': '일반여행수입(명목 US$, 국제수지)'}
LIMITS = [
    '산업 활동 핵심 자료가 없어 관광시장 전체 종합 판정을 보류합니다.',
    '현재 빈티지 회고 분석이며 과거 당시 정보 기반 실시간 백테스트가 아닙니다.',
    '원계열 MoM은 비계절조정 비교입니다. 팬데믹 기저와 통계 정정을 함께 검토해야 합니다.',
    '방한객과 일반여행수입의 모집단은 동일하지 않으며 1인당 소비로 환산하지 않습니다.',
]


def check(condition, code):
    if not condition:raise ValueError(code)


def months(start, end):
    valid_period(start)
    valid_period(end)
    if start > end:raise ValueError('period_order_invalid')
    year, month = map(int, start.split('-'))
    while f'{year:04}-{month:02}' <= end:
        yield f'{year:04}-{month:02}'
        year, month = (year+1, 1) if month == 12 else (year, month+1)


def expected_rate(current, base):
    """Independent integer-difference formula; never infer a rate from rounded output."""
    if base is None or base == 0:return None
    with localcontext() as ctx:
        ctx.prec = 80
        return format((Decimal(current-base)*100/Decimal(base)).quantize(Decimal('.000001'), rounding=ROUND_HALF_UP), 'f')


def retrospective(config, archive, policy, start, end, cutoff, now):
    results = [engine.diagnose(config, archive, policy, p, cutoff, now) for p in months(start, end)]
    checked = 0
    for result in results:
        for key, row in result['axes'].items():
            if row['status'] != 'observed':continue
            for rate, base_key in (('yoy_pct', 'yoy_base_period'), ('mom_pct', 'mom_base_period')):
                base = row['comparison_observations'].get(row['comparisons'][base_key], {}).get('value')
                check(row['comparisons'][rate] == expected_rate(row['value'], base), 'rate_mismatch')
                checked += base is not None and base != 0
        check(result['overall_status'] == 'withheld' and not result['publication_approved'], 'private_contract_invalid')
    return dict(mode='retrospective_current_vintage', start=start, end=end, results=results,
                target_months=len(results), ready_months=sum(r['target_ready'] for r in results),
                verified_nonnull_comparisons=checked, historic_as_of_verified=False)


def sensitivity(config, archive, policy, target, cutoff, now):
    """Explicit counterfactual mutations of COPIES, never new official observations."""
    original_hash = engine.digest(archive)
    cases = []
    prior_year = f'{int(target[:4])-1:04}-{target[5:]}'
    for name in ('round_up_tiny', 'round_down_tiny', 'missing_prior', 'zero_prior', 'extreme_base', 'revised_baseline', 'missing_target'):
        changed = copy.deepcopy(archive)
        obs = changed['indicators']['kto_inbound']['observations']
        if name.startswith('round_'):
            obs[prior_year]['value'] = 10**12
            obs[target]['value'] = 10**12 + (1 if name == 'round_up_tiny' else -1)
        elif name == 'missing_prior':obs.pop(prior_year, None)
        elif name in ('zero_prior', 'extreme_base'):obs[prior_year]['value'] = 0 if name == 'zero_prior' else 1
        elif name == 'revised_baseline':
            obs[prior_year]['value'] += 1
            obs[prior_year]['revision_status'] = 'revised'
        else:obs.pop(target, None)
        result = engine.diagnose(config, changed, policy, target, cutoff, now)
        if name == 'missing_target':check(not result['target_ready'], 'missing_target_not_withheld')
        else:
            row = result['axes']['kto_inbound']
            base = obs.get(prior_year, {}).get('value')
            check(row['comparisons']['yoy_pct'] == expected_rate(obs[target]['value'], base), 'scenario_rate_mismatch')
            evidence = next(e for e in result['evidence'] if e['indicator'] == 'kto_inbound')
            check(evidence['direction'] == engine.direction(obs[target]['value'], base), 'scenario_direction_mismatch')
            if name == 'revised_baseline':check('revised_comparison_baseline' in row['warnings'], 'revision_warning_missing')
        check(not result['publication_approved'] and result['overall_status'] == 'withheld', 'private_contract_invalid')
        cases.append(dict(name=name, scenario_kind='counterfactual_copy', passed=True, result=result))
    check(engine.digest(archive) == original_hash, 'input_mutated')
    return dict(scenario_kind='counterfactual_copy', cases=cases, input_unchanged=True)


def display_rate(value):
    if value is None:return '비교 불가'
    rounded = Decimal(value).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    # Avoid negative zero and distinguish display precision from factual direction.
    return format(abs(rounded) if rounded == 0 else rounded, '.2f') + '%'


def historical_sensitivity(config, archive, policy, report, cutoff, now):
    tested, skipped = [], []
    inbound = archive['indicators']['kto_inbound']['observations']
    for result in report['results']:
        target = result['target_period']
        prior = f'{int(target[:4])-1:04}-{target[5:]}'
        if not result['target_ready'] or prior not in inbound:
            skipped.append(dict(period=target, reason='target_or_prior_year_unavailable'))
            continue
        tested.append(dict(period=target, **sensitivity(config,archive,policy,target,cutoff,now)))
    return dict(scenario_kind='counterfactual_copy', historic_as_of_verified=False,
                tested_months=len(tested), scenario_count=sum(len(r['cases']) for r in tested),
                skipped=skipped, results=tested)


def briefing(result):
    if result['status'] != 'partial_monitor' or not result['target_ready']:
        raise ValueError('target_not_ready')
    if result['publication_approved'] or result['mode'] != 'retrospective_current_vintage':
        raise ValueError('private_contract_invalid')
    check(result['overall_status'] == 'withheld' and result['editorial_review_required'] and
          result['visibility'] == 'private_review_draft' and set(result['axes']) == set(engine.CORE), 'diagnostic_scope_invalid')
    evidence = []
    for key in engine.CORE:
        row = result['axes'][key]
        comp = row['comparisons']
        base = comp['yoy_base_period']
        sign = next(e['direction'] for e in result['evidence'] if e['indicator'] == key)
        word = {'increase':'증가', 'decrease':'감소', 'unchanged':'동일', 'unavailable':'비교 불가'}[sign]
        text = (f"{LABELS[key]}: {row['period']} {row['value']:,} {row['unit']}; "
                f"{base} 대비 {word}, YoY {display_rate(comp['yoy_pct'])}; "
                f"{comp['mom_base_period']} 대비 원계열 MoM {display_rate(comp['mom_pct'])}")
        if comp['yoy_pct'] is not None and Decimal(comp['yoy_pct']).quantize(Decimal('.01')) == 0 and sign in ('increase','decrease'):
            text += ' (표시 정밀도에서는 0.00%이나 원값의 변화 방향은 유지)'
        text += '.'
        evidence.append(dict(indicator=key, text=text, source=row['provenance'],
                             comparison_observations=row['comparison_observations'], warnings=row['warnings']))
    return dict(title=f"Market Weather {result['target_period']} — 비공개 부분 모니터",
                target_period=result['target_period'], mode=result['mode'], evidence=evidence,
                overall_status='withheld', publication_approved=False, limitations=LIMITS,
                editorial_review={'status':'pending', 'reviewer':None, 'reviewed_at':None},
                analysis_at=result['analysis_at'], input_cutoff=result['input_cutoff'])


def markdown(draft):
    lines = [f"# {draft['title']}", '', '비공개 편집 검토 초안 · 실제 홈페이지 발행물 아님', '',
             f"기준월: {draft['target_period']} / 분석시각: {draft['analysis_at']} / 입력 마감: {draft['input_cutoff']}",
             '', '## 주요 근거 (2개)', '']
    for e in draft['evidence']:
        lines.extend([e['text'], '', f"출처: {e['source']['publisher']} — {e['source']['source_url']}",
                      f"원본 해시: {e['source']['file_sha256']}; 경고: {', '.join(e['warnings']) or '없음'}", ''])
    lines += ['## 해석 한계와 검토 상태', ''] + ['- '+s for s in draft['limitations']]
    lines += ['', '종합 판정: 보류 / 편집 검토: 대기 / 실제 게시 승인: false', '']
    return '\n'.join(lines)


def verify_bundle(path):
    path = Path(path)
    manifest = engine.read(path/'manifest.json')
    expected = set(manifest['files']) | {'manifest.json'}
    actual = {str(p.relative_to(path)) for p in path.rglob('*') if p.is_file()}
    if expected != actual:raise ValueError('bundle_file_set_changed')
    for name, sha in manifest['files'].items():
        p = path/name
        if p.is_symlink() or path.resolve() not in p.resolve().parents:raise ValueError('bundle_path_invalid')
        if hashlib.sha256(p.read_bytes()).hexdigest() != sha:raise ValueError('bundle_hash_mismatch')
    draft = engine.read(path/'briefing-private.json')
    if manifest['publication_approved'] or draft['publication_approved'] or draft['editorial_review']['status'] != 'pending':
        raise ValueError('bundle_private_contract_invalid')
    return manifest


def save_bundle(output, config, archive, policy, diagnostic, retrospective_report, scenarios, previous=None):
    output = Path(output).resolve()
    if engine.ROOT == output or engine.ROOT in output.parents or output in engine.ROOT.parents:
        raise ValueError('external_output_required')
    prior = None
    if previous is not None:
        previous = Path(previous).resolve()
        if output == previous or previous in output.parents or output in previous.parents:
            raise ValueError('revision_directories_must_be_disjoint')
        prior = verify_bundle(previous)
        if prior['target_period'] != diagnostic['target_period']:raise ValueError('revision_target_mismatch')
    draft = briefing(diagnostic)
    files = {'inputs/config.json':config, 'inputs/archive.json':archive, 'inputs/policy.json':policy,
             'diagnostic-private.json':diagnostic, 'briefing-private.json':draft,
             'retrospective-private.json':retrospective_report, 'sensitivity-private.json':scenarios}
    manifest = dict(schema_version=1, shadow_version=VERSION, methodology_version=engine.VERSION,
                    shadow_id='market-weather-'+diagnostic['target_period'],
                    edition_revision=1 if prior is None else prior.get('edition_revision',1)+1,
                    implementation_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                           for p in (Path(__file__),Path(engine.__file__),engine.CONTRACT)},
                    target_period=diagnostic['target_period'], mode=diagnostic['mode'],
                    input_hashes=diagnostic['input_hashes'], publication_approved=False,
                    revision_history=[] if prior is None else prior['revision_history'] + [dict(
                        previous_manifest_sha256=hashlib.sha256((Path(previous)/'manifest.json').read_bytes()).hexdigest(),
                        previous_input_hashes=prior['input_hashes'], input_hashes=diagnostic['input_hashes'],
                        input_changed=prior['input_hashes'] != diagnostic['input_hashes'],
                        detected_at=diagnostic['analysis_at'], status='review_required')], files={})
    if diagnostic['input_hashes'] != {k:engine.digest(v) for k,v in (('config',config),('archive',archive),('policy',policy))}:
        raise ValueError('snapshot_diagnostic_mismatch')
    output.mkdir(mode=0o700)  # exclusive: do not overwrite any previous issue
    for name, doc in files.items():
        p = output/name
        p.parent.mkdir(exist_ok=True, mode=0o700)
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n');p.chmod(0o600)
    p = output/'briefing-private.md';p.write_text(markdown(draft));p.chmod(0o600)
    for p in output.rglob('*'):
        if p.is_file():manifest['files'][str(p.relative_to(output))] = hashlib.sha256(p.read_bytes()).hexdigest()
    p = output/'manifest.json';p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
    verify_bundle(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target', default='2026-09')
    parser.add_argument('--start', default='2021-01')
    parser.add_argument('--end', default='2026-09')
    parser.add_argument('--previous', type=Path)
    args = parser.parse_args()
    try:
        snapshot, output = args.snapshot.resolve(), args.output.resolve()
        if output == snapshot or snapshot in output.parents:raise ValueError('snapshot_output_forbidden')
        config = engine.read(engine.ROOT/'macro_sources.json')
        policy = engine.read(engine.ROOT/'operating_policy.json')
        archive = engine.read(snapshot/'collector_state/macro_archive.json')
        now = dt.datetime.now(dt.timezone.utc)
        diagnostic = engine.diagnose(config,archive,policy,args.target,now,now)
        report = retrospective(config,archive,policy,args.start,args.end,now,now)
        scenarios = historical_sensitivity(config,archive,policy,report,now,now)
        save_bundle(output,config,archive,policy,diagnostic,report,scenarios,args.previous)
        print(json.dumps({'private_bundle_verified':True,'publication_approved':False,'months':report['ready_months']}))
        return 0
    except Exception:
        print('private_shadow_validation_failed')
        return 1


if __name__ == '__main__':raise SystemExit(main())
