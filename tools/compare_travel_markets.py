"""Private four-series research; reuse frozen JS validation and rank algorithm.

Inbound production edition is untouched. Outbound exists only in this process,
with its own exact source definitions; no registry, UI or pipeline registration.
"""
import argparse
import csv
import datetime as dt
import hashlib
import itertools
import json
import subprocess
from fractions import Fraction
from pathlib import Path
from src.macro import tourgo
from tools.compare_market_models import correlation_record, band, stability
from tools.collect_kto_research import external_new
from tools.replay_model_signal import add, rank, percent, decimal

ROOT = Path(__file__).resolve().parents[1]
IDS = ('kto_inbound', 'kto_tourism_receipts', 'kto_outbound', 'kto_tourism_expenditure')
COUNTRIES = ('cn', 'jp', 'tw', 'us', 'vn')
NODE = r'''
const fs=require('fs'),m=require('./site/market-signal-model.js');
const db=JSON.parse(fs.readFileSync(process.argv[1]));
const sources=JSON.parse(fs.readFileSync('macro_sources.json'));
const cfg=JSON.parse(JSON.stringify(m.CONFIG));cfg.model_version='research-outbound-v0.1-draft';
cfg.methodology.scope='outbound_demand_and_nominal_general_travel_expenditure_only';
for(const [n,id] of ['kto_outbound','kto_tourism_expenditure'].entries()){
 const item=sources.indicators.find(i=>i.id===id),e=cfg.indicators[n];
 e.id=id;e.revision='research-1';e.label=item.name;e.weight_label=item.name;
 e.contract.definition=item.definition;e.contract.source=item.source_id;
 e.contract.publisher=item.publisher;e.contract.unit=item.unit;
}
const outbound=m.createModel(cfg),outputs={},failures={},missing=[];
for(const [name,model] of [['A_inbound',m],['B_outbound',outbound]]){
 const result=model.run(db,{as_of_period:process.argv[2]});outputs[name]=result;failures[name]=0;
 for(const p of result.backtest.points.filter(p=>p.status==='observed')){
  const copy=structuredClone(db);for(const i of copy.indicators)for(const o of i.observations||[])if(o.period>p.reference_period)o.value=-999;
  const opts={reference_period:p.reference_period,as_of_period:model.addMonth(p.reference_period,1)};
  if(JSON.stringify(model.evaluate(copy,opts))!==JSON.stringify(model.evaluate(db,opts)))failures[name]++;
 }
 for(const id of model.IDS){
  const copy=structuredClone(db),i=copy.indicators.find(i=>i.id===id);
  i.observations=i.observations.filter(o=>o.period!==result.reference_period);
  const next=model.evaluate(copy,{reference_period:result.reference_period,as_of_period:process.argv[2]});
  missing.push({market:name,missing_id:id,status:next.status,score:next.score});
 }
}
process.stdout.write(JSON.stringify({outputs,outbound_config:cfg,future_poison_failures:failures,missing_stress:missing}));
'''


def require(test, code):
    if not test:
        raise ValueError(code)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_reference(db, archive, config, date):
    require(db.get('mode') == 'verified_official_statistics', 'verified_reference_required')
    source = next(s for s in config['sources'] if s['id'] == tourgo.SOURCE)
    pair = tourgo.public_pair(source, archive, date)
    require(set(pair) == set(tourgo.IDS), 'manual_reference_approval_or_evidence_invalid')
    maps = {}
    for ident in IDS:
        items = [i for i in db['indicators'] if i['id'] == ident]
        require(len(items) == 1 and items[0]['enabled'] and items[0]['connected'], 'reference_identity_invalid')
        obs = items[0]['observations']
        require(len(obs) == 69 and len({o['period'] for o in obs}) == 69, 'reference_months_invalid')
        require({o['period'] for o in obs} == {add('2021-01', n) for n in range(69)}, 'reference_scope_changed')
        maps[ident] = {o['period']: o['value'] for o in obs}
        if ident in pair:
            require(all(pair[ident]['observations'].get(p, {}).get('value') == value
                        for p, value in maps[ident].items()), 'manual_ledger_projection_disagrees')
    return maps


def verify_live_kto(folder, db):
    folder = Path(folder)
    result = json.loads((folder/'result.json').read_text())
    if result.get('status') != 'live_public_download_validated' or result.get('actual_network_collection') is not True:
        return dict(status='not_live_validated', model_uses_retained_official_reference=True)
    requests = json.loads((folder/'requests.json').read_text())
    for r in requests:
        require(Path(r['file']).name == r['file'] and sha(folder/r['file']) == r['sha256'], 'live_evidence_hash_mismatch')
    snapshot = json.loads((folder/'snapshot.json').read_text())
    require(snapshot['file_sha256'] in {r['sha256'] for r in requests}
            and snapshot['crosscheck_sha256'] in {r['sha256'] for r in requests}, 'live_workbooks_missing')
    differences = []
    for i in db['indicators']:
        if i['id'] not in snapshot['values']:
            continue
        for o in i['observations']:
            if snapshot['values'][i['id']].get(o['period']) != o['value']:
                differences.append(dict(indicator_id=i['id'], period=o['period']))
    return dict(status='live_validated', reference_period=snapshot['reference_period'],
                compared_observations=sum(len(i['observations']) for i in db['indicators'] if i['id'] in snapshot['values']),
                differences=differences, source_file_sha256=snapshot['file_sha256'],
                crosscheck_sha256=snapshot['crosscheck_sha256'],
                model_uses_retained_official_reference=bool(differences),
                comparison_vintage='newly_collected_file_vs_current_public_projection')


def composition(db):
    lookup = {i['id']: {o['period']: o['value'] for o in i.get('observations', [])} for i in db['indicators']}
    rows = []
    for p, total in sorted(lookup['kto_inbound'].items()):
        require(total > 0, 'zero_total_for_composition')
        values = {c: lookup['kto_inbound_'+c][p] for c in COUNTRIES}
        require(all(v >= 0 for v in values.values()) and sum(values.values()) <= total, 'composition_inconsistent')
        rows.append(dict(period=p, selected_market_shares_pct={c: decimal(Fraction(100*v, total)) for c, v in values.items()},
                         selected_five_coverage_pct=decimal(Fraction(100*sum(values.values()), total)),
                         residual_label='unresolved composition; not one country',
                         independent_model_weights=False))
    return rows


def compare(macro, archive, kto_evidence, protocol):
    require(sha(macro) == protocol['input_sha256'] and sha(archive) == protocol['archive_sha256'], 'reference_hash_mismatch')
    for name, expected in protocol['engine_hashes'].items():
        require(sha(ROOT/name) == expected, 'fixed_engine_or_contract_changed')
    require(protocol['scope'] == ['2021-01', '2026-09'] and protocol['weights'] == ['1/2', '1/2'], 'research_scope_changed')
    db = json.loads(Path(macro).read_text())
    config = json.loads((ROOT/'macro_sources.json').read_text())
    maps = verify_reference(db, json.loads(Path(archive).read_text()), config, dt.date.fromisoformat(protocol['as_of_date']))
    kto_result = verify_live_kto(kto_evidence, db)
    run = subprocess.run(['node', '-e', NODE, str(Path(macro).resolve()), protocol['as_of_date'][:7]],
                         cwd=ROOT, capture_output=True, text=True, check=True, timeout=90)
    audit = json.loads(run.stdout)
    private, summaries, oracle_checks = {}, {}, 0
    for market, pair_ids in [('A_inbound', IDS[:2]), ('B_outbound', IDS[2:])]:
        r = audit['outputs'][market]
        require(r['status'] == 'observed' and r['backtest']['invariant_failures'] == 0
                and audit['future_poison_failures'][market] == 0, 'market_validation_failed')
        points, variants = [], []
        for p in r['backtest']['points']:
            if p['status'] != 'observed':
                continue
            month = p['reference_period']
            ranks = []
            for ident, axis in zip(pair_ids, p['axes']):
                position, smooth = rank(maps[ident], month)
                require(decimal(position) == axis['percentile'] and decimal(smooth) == axis['smoothed_yoy_pct']
                        and decimal(percent(maps[ident], month)) == axis['yoy_pct'], 'fraction_axis_mismatch')
                ranks.append(position)
                oracle_checks += 3
            score = sum(ranks)/2
            require(abs(float(score)-p['score']) < 1e-12 and band(score) == p['weather'], 'fraction_score_mismatch')
            oracle_checks += 1
            points.append(dict(period=month, exact=str(score), score=float(score), weather=band(score)))
            for w in map(Fraction, protocol['weight_sensitivity_first_axis']):
                v = w*ranks[0]+(1-w)*ranks[1]
                variants.append(dict(period=month, weight=str(w), score=float(v),
                                     absolute_delta=float(abs(v-score)), band_changed=band(v) != band(score)))
        private[market] = dict(points=points, variants=variants)
        summaries[market] = dict(current_period=r['reference_period'], research_score=r['score_display'],
                                 research_display_bin=r['weather'], display_bin_is_not_a_validated_business_cycle_label=True,
                                 scored_months=len(points), withheld_months=r['backtest']['withheld_months'],
                                 full=stability(points),
                                 cutoff_sensitivity={cutoff: stability([p for p in points if add(p['period'], -38)>cutoff])
                                                     for cutoff in protocol['raw_cutoff_sensitivity']},
                                 weight_variants=len(variants), band_changes=sum(v['band_changed'] for v in variants),
                                 maximum_weight_score_change=max(v['absolute_delta'] for v in variants),
                                 actual_publication_dates_verified=False)
    a, b = private['A_inbound']['points'], private['B_outbound']['points']
    require([p['period'] for p in a] == [p['period'] for p in b], 'market_evaluation_period_mismatch')
    correlations = []
    for left, right in itertools.combinations(IDS, 2):
        for cutoff in (None, *protocol['raw_cutoff_sensitivity']):
            for kind in protocol['transformations']:
                c = correlation_record(maps[left], maps[right], kind, cutoff)
                for key in ['min_a', 'min_b', 'max_a', 'max_b']:
                    c.pop(key)
                correlations.append(dict(left=left, right=right, **c))
    comp = composition(db)
    direction_conflicts = sum((percent(maps['kto_inbound'],p)>0) != (percent(maps['kto_outbound'],p)>0)
                              for p in maps['kto_inbound'] if add(p,-12) in maps['kto_inbound'])
    summary = dict(model_comparison=summaries, common_scored_months=len(a),
                   inbound_outbound_different_display_bins=sum(x['weather']!=y['weather'] for x,y in zip(a,b)),
                   inbound_outbound_yoy_direction_conflicts=direction_conflicts,
                   country_composition_current=comp[-1], country_observation_count=len(comp)*5,
                   live_kto=kto_result, financial_input_origin='retained_manual_TOURGO_not_new_API_collection',
                   additional_automatically_acquired_eligible_series_for_C=0, model_C_status='not_computed',
                   pooled_four_axis_score=None, domestic_score=None, fraction_oracle_checks=oracle_checks,
                   missing_market_inputs_withheld=all(s['status']=='withheld' and s['score'] is None for s in audit['missing_stress']),
                   historical_as_of_verified=False, prediction_accuracy_measured=False)
    return dict(summary=summary, correlations=correlations, private_markets=private,
                private_composition=comp, production_engine_audit=audit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('macro', 'archive', 'kto-evidence', 'protocol', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--protocol-sha256', required=True)
    args = parser.parse_args()
    try:
        output = external_new(args.output)
        require(sha(args.protocol) == args.protocol_sha256, 'protocol_hash_mismatch')
        report = compare(args.macro, args.archive, args.kto_evidence, json.loads(args.protocol.read_text()))
        output.mkdir(parents=True, mode=0o700)
        (output/'comparison-private.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        # Explicit provenance prevents retained manual money from being relabelled
        # as a fresh API acquisition in downstream private experiments.
        db = json.loads(args.macro.read_text())
        with (output/'normalized-research-inputs.csv').open('w', newline='') as f:
            writer = csv.writer(f, lineterminator='\n')
            writer.writerow(['indicator_id', 'period', 'value', 'unit', 'collection_method', 'acquisition_role'])
            for i in db['indicators']:
                if i['id'] not in IDS:
                    continue
                role = ('retained_manual_TOURGO' if i['id'] in tourgo.IDS else
                        'live_KTO_equal_to_reference' if report['summary']['live_kto']['status']=='live_validated'
                        and not report['summary']['live_kto']['differences'] else 'retained_official_reference')
                for o in i['observations']:
                    writer.writerow([i['id'], o['period'], o['value'], o['unit'], o['collection_method'], role])
        (output/'aggregate.json').write_text(json.dumps(dict(summary=report['summary'], correlations=report['correlations']),
                                                      ensure_ascii=False, indent=2)+'\n')
        (output/'provenance.json').write_text(json.dumps(dict(protocol_sha256=sha(args.protocol),
                     input_sha256=sha(args.macro), archive_sha256=sha(args.archive), research_code_sha256=sha(__file__)), indent=2)+'\n')
        print(json.dumps(dict(status='private_comparison_completed',
                             common_scored_months=report['summary']['common_scored_months'])))
    except Exception:
        raise SystemExit('private_research_failed_no_public_output')


if __name__ == '__main__':
    main()
