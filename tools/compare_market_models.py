"""Offline Phase 2-C research. Writes private results outside the repository only.

No collector, network, approval, publication or production-model mutation.
The existing JS model validates/contracts/scores; Fraction is a research oracle.
"""
import argparse
import hashlib
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path
from tools.replay_model_signal import add, decimal, percent, rank

ROOT = Path(__file__).resolve().parents[1]
NODE = r'''
const fs=require('fs'),m=require('./site/market-signal-model.js');
const db=JSON.parse(fs.readFileSync(process.argv[1]));
const result=m.run(db,{as_of_period:process.argv[2]});
let futureFailures=0;const stress=[];
for(const p of result.backtest.points.filter(p=>p.status==='observed')){
 const copy=structuredClone(db);
 for(const i of copy.indicators)for(const o of i.observations||[])if(o.period>p.reference_period)o.value=-999;
 const next=m.evaluate(copy,{reference_period:p.reference_period,as_of_period:m.addMonth(p.reference_period,1)});
 const original=m.evaluate(db,{reference_period:p.reference_period,as_of_period:m.addMonth(p.reference_period,1)});
 if(JSON.stringify(next)!==JSON.stringify(original))futureFailures++;
}
if(result.status==='observed')for(const id of m.IDS){
 for(const kind of ['missing','minus_one','plus_one','minus_one_percent','plus_one_percent']){
  const copy=structuredClone(db),i=copy.indicators.find(i=>i.id===id),p=result.reference_period;
  if(kind==='missing')i.observations=i.observations.filter(o=>o.period!==p);
  else {const o=i.observations.find(o=>o.period===p),d=kind.endsWith('percent')?Math.max(1,Math.round(o.value/100)):1;
   o.value+=kind.startsWith('minus')?-d:d;o.revision_status='revised';}
  const options={reference_period:p,as_of_period:process.argv[2]};
  const a=m.evaluate(copy,options),b=m.evaluate(copy,options);
  stress.push({kind:'counterfactual_not_official_revision',indicator:id,change:kind,status:a.status,
   score:a.score,weather:a.weather,reason:a.reason,deterministic:JSON.stringify(a)===JSON.stringify(b)});
 }
}
process.stdout.write(JSON.stringify({result,future_poison_failures:futureFailures,stress}));
'''


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, code):
    if not condition:
        raise ValueError(code)


def output_path(path):
    path = Path(path).resolve()
    require(path != ROOT and ROOT not in path.parents and path not in ROOT.parents,
            'external_output_required')
    require(not path.exists(), 'new_output_required')
    return path


def pearson(x, y):
    require(len(x) == len(y), 'pair_length_mismatch')
    if len(x) < 3:
        return None
    x, y = list(map(Fraction, x)), list(map(Fraction, y))
    mx, my = sum(x) / len(x), sum(y) / len(y)
    a, b = [v - mx for v in x], [v - my for v in y]
    xx, yy = sum(v*v for v in a), sum(v*v for v in b)
    if not xx or not yy:
        return None
    xy = sum(u*v for u, v in zip(a, b))
    return max(-1.0, min(1.0, float(xy) / math.sqrt(float(xx*yy))))


def midranks(values):
    values = list(map(Fraction, values))
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [None] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        for i in order[start:end]:
            result[i] = Fraction(start + 1 + end, 2)
        start = end
    return result


def spearman(x, y):
    require(len(x) == len(y), 'pair_length_mismatch')
    return pearson(midranks(x), midranks(y))


def transform(series, kind):
    if kind == 'levels':
        return {p: Fraction(v) for p, v in series.items()}
    growth = {p: percent(series, p) for p in series
              if add(p, -12) in series and series[add(p, -12)] > 0}
    if kind == 'yoy':
        return growth
    require(kind == 'smoothed_yoy', 'transform_invalid')
    return {p: sum((growth[add(p, n)] for n in (-2, -1, 0)), Fraction()) / 3
            for p in growth if all(add(p, n) in growth for n in (-2, -1, 0))}


def footprint(period, kind):
    offsets = {'levels': [0], 'yoy': [0, -12],
               'smoothed_yoy': [0, -1, -2, -12, -13, -14]}[kind]
    return [add(period, n) for n in offsets]


def correlation_record(a, b, kind, raw_after=None):
    ta, tb = transform(a, kind), transform(b, kind)
    periods = sorted(set(ta) & set(tb))
    if raw_after:
        periods = [p for p in periods if min(footprint(p, kind)) > raw_after]
    x, y = [ta[p] for p in periods], [tb[p] for p in periods]
    return dict(transform=kind, raw_after=raw_after, n=len(periods),
                first=periods[0] if periods else None, last=periods[-1] if periods else None,
                pearson=pearson(x, y), spearman=spearman(x, y),
                min_a=float(min(x)) if x else None, max_a=float(max(x)) if x else None,
                min_b=float(min(y)) if y else None, max_b=float(max(y)) if y else None,
                p_value=None, effective_independent_sample_size=None)


def band(score):
    return 'rain' if score < 25 else 'cloudy' if score < 50 else 'partly' if score < 75 else 'sunny'


def stability(points):
    changes = [abs(Fraction(b['exact']) - Fraction(a['exact']))
               for a, b in zip(points, points[1:]) if add(a['period'], 1) == b['period']]
    scores = [Fraction(p['exact']) for p in points]
    return dict(n=len(points), first=points[0]['period'] if points else None,
                last=points[-1]['period'] if points else None,
                minimum=float(min(scores)) if scores else None,
                maximum=float(max(scores)) if scores else None,
                consecutive_comparisons=len(changes),
                mean_absolute_monthly_change=float(sum(changes)/len(changes)) if changes else None,
                maximum_absolute_monthly_change=float(max(changes)) if changes else None)


def domain_view(axes):
    # Domain count is never used as an automatic weight, nor are absent domains filled.
    grouped = {}
    for axis in axes:
        grouped.setdefault(axis['domain'], []).append(Fraction(axis['percentile']))
    domains = {key: str(sum(values) / len(values)) for key, values in grouped.items()}
    missing = [d for d in ('demand', 'consumption', 'industry') if d not in domains]
    return dict(domains=domains, missing_required_domains=missing,
                whole_market_status='withheld', whole_market_score=None,
                reason='industry_and_domestic_coverage_not_established')


def analyze(macro, protocol):
    for name, expected in protocol['engine_hashes'].items():
        require(digest(ROOT/name) == expected, 'engine_hash_mismatch')
    require(digest(macro) == protocol['source']['sha256'], 'snapshot_hash_mismatch')
    db = json.loads(Path(macro).read_text())
    ids = protocol['input']['ids']
    require(ids == ['kto_inbound', 'kto_tourism_receipts'], 'research_scope_mismatch')
    start, end = protocol['input']['period_from'], protocol['input']['period_through']
    require((start, end) == ('2021-01', '2026-09'), 'approved_scope_mismatch')
    require(protocol['models']['A']['weights'] == ['1/2', '1/2'], 'baseline_weight_mismatch')
    maps = {}
    for ident in ids:
        items = [s for s in db['indicators'] if s['id'] == ident]
        require(len(items) == 1, 'identity_mismatch')
        obs = items[0]['observations']
        require(len(obs) == 69 and len({o['period'] for o in obs}) == 69, 'monthly_count_mismatch')
        maps[ident] = {o['period']: o['value'] for o in obs}
        require(set(maps[ident]) == {add(start, n) for n in range(69)}, 'monthly_gap_or_scope')
    run = subprocess.run(['node', '-e', NODE, str(Path(macro).resolve()), protocol['input']['as_of_period']],
                         cwd=ROOT, capture_output=True, text=True, timeout=90, check=True)
    audit = json.loads(run.stdout)
    result = audit['result']
    require(result['status'] == 'observed' and result['backtest']['invariant_failures'] == 0
            and audit['future_poison_failures'] == 0, 'production_validation_failed')
    points, variants, oracle = [], [], 0
    for point in result['backtest']['points']:
        if point['status'] != 'observed':
            continue
        p = point['reference_period']
        positions = []
        for ident, axis in zip(ids, point['axes']):
            pos, smooth = rank(maps[ident], p)
            require(decimal(pos) == axis['percentile'],
                    'rank_oracle_mismatch')
            require(decimal(smooth) == axis['smoothed_yoy_pct'],
                    'smoothing_oracle_mismatch')
            require(decimal(percent(maps[ident], p)) == axis['yoy_pct'],
                    'yoy_oracle_mismatch')
            positions.append(pos)
            oracle += 3
        score = sum(positions) / 2
        require(abs(float(score)-point['score']) < 1e-12 and band(score) == point['weather'],
                'score_oracle_mismatch')
        oracle += 1
        axes = [dict(domain=d, percentile=str(positions[i]))
                for i, d in enumerate(('demand', 'consumption'))]
        points.append(dict(period=p, exact=str(score), score=float(score), weather=band(score),
                           ranks=[str(v) for v in positions], B=domain_view(axes),
                           C_core_exact=str(score), C_environment={}))
        for weight in map(Fraction, protocol['sensitivity']['inbound_weights']):
            new = weight*positions[0] + (1-weight)*positions[1]
            variants.append(dict(period=p, inbound_weight=str(weight), score=float(new),
                                 delta=float(new-score), band_changed=band(new) != band(score)))
    a, b = (maps[ident] for ident in ids)
    correlations = [correlation_record(a, b, kind, cutoff)
                    for cutoff in (None, *protocol['sensitivity']['raw_input_exclusion_through'])
                    for kind in ('levels', 'yoy', 'smoothed_yoy')]
    ablations = {ident: dict(n=len(points), band_changes=sum(
        band(Fraction(p['ranks'][i])) != p['weather'] for p in points),
        maximum_absolute_score_change=max(abs(float(Fraction(p['ranks'][i]))-p['score']) for p in points))
        for i, ident in enumerate(ids)}
    masks = {cutoff: stability([p for p in points if add(p['period'], -38) > cutoff])
             for cutoff in protocol['sensitivity']['raw_input_exclusion_through']}
    return dict(protocol_id=protocol['protocol_id'], mode='retrospective_current_vintage',
                historical_as_of_verified=False, prediction_accuracy_measured=False,
                production_audit=audit, monthly_private=points, correlations=correlations,
                aggregate=dict(current_score=result['score_display'], current_period=result['reference_period'],
                               evaluated_months=result['backtest']['evaluated_months'],
                               scored_months=len(points), withheld_months=result['backtest']['withheld_months'],
                               oracle_checks=oracle, all_months=stability(points),
                               strict_raw_cutoff_sensitivity=masks,
                               weight_variants=dict(n=len(variants), band_changes=sum(v['band_changed'] for v in variants),
                                                    max_absolute_score_change=max(abs(v['delta']) for v in variants)),
                               single_axis_ablations=ablations,
                               B_whole_market_withheld=len(points), C_exact_equal_A=len(points),
                               additional_empirical_variables=0, VIF='not_applicable_no_regression'),
                weight_variants_private=variants)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--macro', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--protocol-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        dest = output_path(args.output)
        require(digest(args.protocol) == args.protocol_sha256, 'protocol_hash_mismatch')
        p = json.loads(args.protocol.read_text())
        report = analyze(args.macro, p)
        dest.mkdir(parents=True, mode=0o700)
        (dest/'analysis-private.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        (dest/'aggregate.json').write_text(json.dumps(dict(aggregate=report['aggregate'],
             correlations=report['correlations']), ensure_ascii=False, indent=2)+'\n')
        (dest/'provenance.json').write_text(json.dumps(dict(protocol_sha256=digest(args.protocol),
             input_sha256=digest(args.macro), research_code_sha256=digest(__file__),
             engine_hashes=p['engine_hashes'], source=p['source']), indent=2)+'\n')
        print(json.dumps(dict(status='completed_private_research',
                             scored_months=report['aggregate']['scored_months'],
                             oracle_checks=report['aggregate']['oracle_checks'])))
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError):
        # Never dump subprocess stdout/stderr or private payloads on failure.
        raise SystemExit('research_validation_failed; no_public_output_generated')


if __name__ == '__main__':
    main()
