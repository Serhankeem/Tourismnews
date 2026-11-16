"""Private read-only partial monitor. No collector, scheduler or public export."""
import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
from . import tourgo, balance, kto
from .model import valid_period, decimal_comparisons

ROOT=Path(__file__).resolve().parents[2]
VERSION='weather-diagnostic-v0.1'
CORE=('kto_inbound','kto_tourism_receipts')
CONTRACT=ROOT/'fixtures/weather_contract_v01.json'
PIN='0143b5f51af491ab864ef1ba395088c85d4040823e37ebf58e682934ff1a4f76'


def unique(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError('duplicate_json_key')
        out[k]=v
    return out


def read(path):return json.loads(Path(path).read_text(),object_pairs_hook=unique)


def digest(doc):return hashlib.sha256(json.dumps(doc,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def stamp(s):
    t=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('timezone_required')
    return t


def eligible(config,archive,policy,key,contracts,cutoff,now):
    items=[i for i in config['indicators'] if i['id']==key]
    if len(items)!=1:raise ValueError('indicator_contract_invalid')
    item=items[0];contract=contracts[key]
    if not item.get('enabled') or any(item.get(k)!=v for k,v in contract.items()):raise ValueError('indicator_contract_invalid')
    sources=[s for s in config['sources'] if s['id']==item['source_id']]
    if len(sources)!=1 or not sources[0].get('enabled'):raise ValueError('source_disabled')
    source=sources[0];saved=archive['indicators'].get(key,{})
    if any(saved.get(k)!=item.get(k) for k in ('unit','definition')):raise ValueError('archive_definition_invalid')
    if source['id']==tourgo.SOURCE:
        if (not tourgo.terms_confirmed(source,policy,now.date()) or
                any(not tourgo.permitted(source,a,now.date()) for a in ('collection','publication'))):raise ValueError('approval_required')
        pair=tourgo.public_pair(source,archive,now.date())
        if key not in pair:raise ValueError('tourgo_pair_invalid')
        observations=pair[key]['observations']
        ranges=[tourgo.approved_range(source,a) for a in ('collection','publication')]
    else:
        if source.get('method')!='official_public_xlsx':raise ValueError('source_method_invalid')
        if source.get('requires_approval') and any(not balance.permitted(source,a,now.date()) for a in ('collection','publication')):raise ValueError('approval_required')
        observations=saved.get('observations');ranges=[]
    if not isinstance(observations,dict):raise ValueError('observation_shape_invalid')
    accepted={}
    for period,o in observations.items():
        valid_period(period)
        if any(not r['period_from']<=period<=r['period_through'] for r in ranges):continue
        if (type(o.get('value')) is not int or not 0<=o['value']<=2**53-1
                or o.get('unit')!=item['unit'] or o.get('frequency')!='M'
                or o.get('publisher')!=item['publisher'] or o.get('finality') not in ('not_stated','provisional','final')
                or not re.fullmatch('[a-f0-9]{64}',o.get('file_sha256',''))
                or not o.get('source_url','').startswith('https://')):raise ValueError('observation_invalid')
        first,last=stamp(o['first_collected_at']),stamp(o['last_collected_at'])
        if first>last:raise ValueError('vintage_invalid')
        if source['id']!=tourgo.SOURCE:
            kto.release_url(o['source_url'])
            kto.public_url(o.get('file_url'))
        if source['id']!=tourgo.SOURCE and (o.get('collection_method')!='official_public_xlsx'
                or o.get('verification_status')!='official_file_validated' or o.get('rights')!='KOGL-0'):raise ValueError('kto_provenance_invalid')
        if any(stamp(o[k])>cutoff for k in ('release_published_at','original_publication_at') if o.get(k)):continue
        if last>cutoff or period>=cutoff.strftime('%Y-%m'):continue
        accepted[period]=copy.deepcopy(o)
    return accepted


def diagnose(config,archive,policy,target,cutoff,now):
    valid_period(target)
    if cutoff.tzinfo is None or now.tzinfo is None or cutoff>now:raise ValueError('invalid_analysis_time')
    contracts=read(CONTRACT)
    if hashlib.sha256(json.dumps(contracts,ensure_ascii=False,sort_keys=True).encode()).hexdigest()!=PIN:raise ValueError('contract_hash_invalid')
    out=dict(schema_version=1,methodology_version=VERSION,target_period=target,analysis_at=now.isoformat(),
        input_cutoff=cutoff.isoformat(),mode='retrospective_current_vintage',visibility='private_review_draft',
        publication_approved=False,editorial_review_required=True,overall_status='withheld',
        overall_reason='industry_activity_unavailable',industry_activity={'status':'missing'},
        status='withheld',target_ready=False,axes={},supporting={},evidence=[],warnings=['industry_activity_unavailable'],
        input_hashes={'config':digest(config),'archive':digest(archive),'policy':digest(policy)},excluded_unapproved_series=True)
    available={}
    for key in contracts:
        try:available[key]=eligible(config,archive,policy,key,contracts,cutoff,now)
        except (ValueError,KeyError,TypeError,AttributeError):
            out['warnings'].append(key+':ineligible');available[key]={}
    common=set(available[CORE[0]])&set(available[CORE[1]])
    choices=[p for p in common if p<=target];aligned=max(choices) if choices else None
    out['aligned_period']=aligned
    if aligned!=target:out['warnings'].append('target_period_unavailable_or_delayed')
    for key,obs in available.items():
        bucket=out['axes'] if key in CORE else out['supporting']
        if aligned is None or aligned not in obs:
            bucket[key]={'status':'missing'};continue
        o=obs[aligned];rates=decimal_comparisons({p:{'value':str(v['value'])} for p,v in obs.items()},aligned)
        rates.pop('aggregation_policy',None)
        warnings=[]
        if rates['yoy_pct'] is None:warnings.append('yoy_unavailable_or_zero_baseline')
        if rates['mom_pct'] is None:warnings.append('mom_unavailable_or_zero_baseline')
        # No economic cutoff: warn whenever a YoY uses a pandemic-era baseline.
        if rates['yoy_base_period'][:4] in ('2020','2021','2022'):warnings.append('pandemic_baseline_context_required')
        if o.get('revision_status')=='revised' or any(r.get('period')==aligned for r in archive['indicators'][key].get('revisions',[])):warnings.append('revised_observation')
        provenance={k:copy.deepcopy(o.get(k)) for k in ('source_url','publisher','file_sha256','file_url','first_collected_at','last_collected_at','original_publication_at','release_published_at','finality','revision_status')}
        bucket[key]=dict(status='observed',period=aligned,value=o['value'],unit=o['unit'],comparisons=rates,
            comparison_observations={p:copy.deepcopy(obs[p]) for p in (rates['mom_base_period'],rates['yoy_base_period']) if p in obs},
            provenance=provenance,warnings=warnings)
        if key in CORE:
            out['evidence'].append(dict(indicator=key,period=aligned,text=key+'의 원자료 및 동일 기준월 비교',
                direction='unavailable' if rates['yoy_pct'] is None else 'increase' if rates['yoy_pct'][0]!='-' and rates['yoy_pct']!='0.000000' else 'decrease' if rates['yoy_pct'][0]=='-' else 'unchanged',
                source=provenance))
    if aligned==target:
        out['status']='partial_monitor';out['target_ready']=True
        signs=[e['direction'] for e in out['evidence']]
        out['flow_relation']='mixed' if 'increase' in signs and 'decrease' in signs else 'not_aggregated'
        if 'unavailable' in signs:out['warnings'].append('comparative_judgment_withheld')
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--target',required=True);p.add_argument('--cutoff',required=True)
    args=p.parse_args()
    try:
        output=args.output.resolve();snapshot=args.snapshot.resolve()
        if output.exists() or output==ROOT or ROOT in output.parents or output in ROOT.parents or output==snapshot or snapshot in output.parents:raise ValueError('fresh_external_output_required')
        cfg=read(ROOT/'macro_sources.json');archive=read(snapshot/'collector_state/macro_archive.json');policy=read(ROOT/'operating_policy.json')
        result=diagnose(cfg,archive,policy,args.target,stamp(args.cutoff),dt.datetime.now(dt.timezone.utc))
        output.mkdir(parents=True,mode=0o700);path=output/'diagnostic-private.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
        print(json.dumps({'status':result['status'],'overall_status':'withheld','publication_approved':False}));return 0
    except Exception:
        print('private_diagnostic_validation_failed');return 1


if __name__=='__main__':raise SystemExit(main())
