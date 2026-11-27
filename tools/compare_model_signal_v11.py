"""Offline seven-method replay. Original bytes and all private results stay outside Git."""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess

from tools.replay_model_signal import add, percent

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('smooth24', 'smooth36', 'yoy24', 'rolling12_yoy24', 'zscore24', 'mad24', 'minmax24')
EXPECTED = (62.50, 56.94, 37.50, 75.00, 57.34, 61.08, 49.68)


def transform(series, period, method):
    if method == 'rolling12_yoy24':
        current = sum(series[add(period, n)] for n in range(-11, 1))
        base = sum(series[add(period, n)] for n in range(-23, -11))
        if base <= 0: raise ValueError('zero_denominator')
        return 100 * (current / base - 1)
    if method == 'yoy24': return percent(series, period)
    return sum((percent(series, add(period, n)) for n in (-2, -1, 0)), F()) / 3


def position(series, period, method):
    count = 36 if method == 'smooth36' else 24
    value = transform(series, period, method)
    refs = [transform(series, add(period, n), method) for n in range(-count, 0)]
    if min(refs) == max(refs): raise ValueError('degenerate_reference')
    if method in ('smooth24', 'smooth36', 'yoy24', 'rolling12_yoy24'):
        return F(100 * (2 * sum(r < value for r in refs) + sum(r == value for r in refs)), 2 * count)
    if method == 'minmax24': return max(F(0), min(F(100), 100 * (value-min(refs)) / (max(refs)-min(refs))))
    if method == 'zscore24':
        center, scale = statistics.mean(refs), statistics.pstdev(refs)
    else:
        center = statistics.median(refs)
        scale = 1.4826 * float(statistics.median(abs(r-center) for r in refs))
    if not scale: raise ValueError('zero_scale')
    return 50 * (1 + math.erf(float(value-center) / float(scale) / math.sqrt(2)))


def weather(score):
    return sum(score >= x for x in (25, 50, 75))


def summary(points):
    scores = [p['score'] for p in points]
    changes = [abs(b-a) for a, b in zip(scores, scores[1:])]
    return dict(months=len(points), first=points[0]['period'] if points else None,
                last=points[-1]['period'] if points else None,
                mean_absolute_monthly_change=statistics.mean(changes) if changes else None,
                max_absolute_monthly_change=max(changes, default=None),
                weather_transitions=sum(a['weather'] != b['weather'] for a, b in zip(points, points[1:])))


def compare(maps, eligible):
    results = {}
    for method in METHODS:
        points = []
        for period in eligible:
            try: axes = [position(s, period, method) for s in maps]
            except (KeyError, ZeroDivisionError, ValueError): continue
            score = sum(axes) / 2
            points.append(dict(period=period, score=float(score), weather=weather(score), axes=list(map(float, axes))))
        results[method] = dict(points=points, own_period=summary(points))
    common = sorted(set.intersection(*(set(p['period'] for p in r['points']) for r in results.values())))
    for method, result in results.items():
        points = [p for p in result['points'] if p['period'] in common]
        result['common_period'] = summary(points)
        weights, perturbations = [], []
        for p in points:
            period = p['period']; axes = [position(s, period, method) for s in maps]; base = sum(axes)/2
            for weight in (F(2, 5), F(3, 5)):
                score = weight*axes[0] + (1-weight)*axes[1]
                weights.append((abs(float(score-base)), weather(score) != weather(base)))
            # Exhaustive SINGLE raw observation stresses within this method's actual input window.
            # Fractional counterfactual copies only: never official integer observations or new data.
            history = 50 if method == 'smooth36' else 47 if method == 'rolling12_yoy24' else 36 if method == 'yoy24' else 38
            for axis, series in enumerate(maps):
                for offset in range(-history, 1):
                    changed_period = add(period, offset)
                    for delta in (F(-2, 100), F(-5, 1000), F(5, 1000), F(2, 100)):
                        changed = dict(series); changed[changed_period] *= 1+delta
                        score = (position(changed, period, method) + axes[1-axis])/2
                        perturbations.append((abs(float(score-base)), weather(score) != weather(base), str(delta)))
        result['weight_stress_common'] = dict(cases=len(weights), weather_changes=sum(v[1] for v in weights), max_score_change=max((v[0] for v in weights), default=None))
        result['single_value_stress_common'] = {
            delta:dict(cases=sum(v[2]==delta for v in perturbations), weather_changes=sum(v[1] for v in perturbations if v[2]==delta),
                       max_score_change=max((v[0] for v in perturbations if v[2]==delta), default=None))
            for delta in ('-1/50', '-1/200', '1/200', '1/50')}
        # Every raw observation, including YoY denominators, must be after the cutoff.
        history = 50 if method == 'smooth36' else 47 if method == 'rolling12_yoy24' else 36 if method == 'yoy24' else 38
        result['post_pandemic_raw_window'] = summary([p for p in result['points'] if add(p['period'], -history) > '2022-12'])
    return results, common


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--macro', required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(); output = args.output.resolve(); source = args.macro.resolve()
    if ROOT in output.parents or output == ROOT or output.exists() or ROOT in source.parents:
        raise SystemExit('new_external_output_and_input_required')
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.sha256: raise SystemExit('snapshot_hash_mismatch')
    db = json.loads(raw); output.mkdir(parents=True, mode=0o700)
    protocol = dict(source_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['site/market-signal-model.js','site/market-signal-registry.js','src/model_signal/v11.cjs','tools/compare_model_signal_v11.py']}, as_of_period='2026-11', methods=list(METHODS), input_sha256=args.sha256, target='2026-09', reference_excludes_target=True,
                    weights=['1/2', '1/2'], stress_weights=['2/5','3/5'], perturbation='one raw value at a time, all used months, exact fractional +/-0.5% and +/-2%',
                    normalization='normal CDF; population standard deviation for Z; median and 1.4826*MAD for robust Z; clipped MinMax',
                    mode='retrospective_current_vintage', prediction_accuracy_measured=False, historical_as_of_verified=False,
                    protocol_not_blind_to_user_supplied_reference_results=True)
    (output/'protocol.json').write_text(json.dumps(protocol, indent=2)+'\n')
    script = """const fs=require('fs'),m=require('./src/model_signal/v11.cjs'),raw=fs.readFileSync(process.argv[1]),db=JSON.parse(raw),o={expected_sha256:process.argv[2],as_of_period:'2026-11'};
const current=m.evaluateSnapshot(raw,o),periods=db.indicators.find(i=>i.id==='kto_tourism_receipts').observations.map(o=>o.period);
const points=periods.map(p=>m.evaluateSnapshot(raw,{...o,reference_period:p,as_of_period:require('./site/market-signal-model.js').addMonth(p,1)}));
process.stdout.write(JSON.stringify({current,points}));"""
    replay = json.loads(subprocess.check_output(['node','-e',script,str(source),args.sha256], cwd=ROOT))
    if replay['current']['score_display'] != '62.50': raise SystemExit('actual_replay_failed')
    ids = replay['current']['source_indicator_ids']
    maps = [{o['period']:F(o['value']) for o in next(i for i in db['indicators'] if i['id']==key)['observations']} for key in ids]
    eligible = sorted(set.intersection(*(set(s) for s in maps)))
    eligible = [p for p in eligible if p <= replay['current']['reference_period']]
    # The union of successful 39-month window checks must cover the whole research history.
    required = eligible[38:]
    if any(r['status'] != 'observed' for r in replay['points'] if r['reference_period'] in required):
        raise SystemExit('research_input_contract_validation_failed')
    results, common = compare(maps, eligible)
    for method, expected in zip(METHODS, EXPECTED):
        point = next(p for p in results[method]['points'] if p['period']=='2026-09')
        results[method]['target_score'] = point['score']
        results[method]['supplied_reference_rounded_match'] = abs(point['score']-expected)<.0051
    # Fraction oracle agrees with unchanged JS exact ranking at every available month.
    oracle = all(abs(next(p for p in results['smooth24']['points'] if p['period']==r['reference_period'])['score']-r['score'])<1e-12 for r in replay['points'] if r['status']=='observed')
    prefix_checks = 0
    for method, result in results.items():
        for point in result['points']:
            for series in maps:
                p = point['period']
                assert position({k:v for k,v in series.items() if k<=p},p,method) == position(series,p,method)
                prefix_checks += 1
    aggregate = dict(future_prefix_checks=prefix_checks, future_prefix_failures=0, protocol=protocol, common_evaluation_months=common, methods={k:{key:value for key,value in v.items() if key!='points'} for k,v in results.items()}, fraction_oracle_passed=oracle)
    (output/'aggregate.json').write_text(json.dumps(aggregate, indent=2)+'\n')
    (output/'comparison-private.json').write_text(json.dumps(dict(replay=replay, methods=results), indent=2)+'\n')
    if not oracle or not all(r['supplied_reference_rounded_match'] for r in results.values()): raise SystemExit('reference_reproduction_mismatch')
    print(json.dumps({k:round(v['target_score'],6) for k,v in results.items()}))


if __name__ == '__main__': main()
