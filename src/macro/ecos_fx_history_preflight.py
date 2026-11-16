"""Fixed 70-month FX audit; manual Actions only, memory-only, no collector.

First verify the three previously authenticated months, then the remaining 67.
Reuse the authenticated client, decimal parser and pinned baseline fingerprints.
Never output values, response bodies/hashes, credentials or exception messages.
"""
import contextlib
import datetime as dt
import json
import os
from . import ecos, ecos_decimal, ecos_market_preflight as p
from .model import months

KEY='market_fxavg'
WINDOWS=(('2026-08','2026-10'),('2021-01','2026-07'))


def read_window(item,client,start,end,now):
    rows=client.rows('StatisticSearch','731Y004','M',start.replace('-',''),end.replace('-',''),'0000001','0000100')
    if not rows:raise p.ProbeError('no_observations')
    periods=[ecos.period(r.get('TIME')) for r in rows]
    if len(set(periods))!=len(periods):raise p.ProbeError('duplicate_months')
    if set(periods)!=set(months(start,end)):raise p.ProbeError('missing_months')
    try:
        return ecos_decimal.parse(rows,item,start,end,now,client.response_hashes,'preflight_memory_only')
    except (ValueError,TypeError,KeyError):
        raise p.ProbeError('series_invalid') from None


def metadata(item,client,now):
    tables=client.rows('StatisticTableList','731Y004')
    if (len(tables)!=1 or tables[0].get('STAT_CODE')!='731Y004'
            or tables[0].get('SRCH_YN')!='Y' or 'M' not in tables[0].get('CYCLE','').split(',')):
        raise p.ProbeError('metadata_invalid')
    lookup={}
    for row in client.rows('StatisticItemList','731Y004'):
        if row.get('CYCLE')!='M':continue
        pair=row.get('GRP_CODE'),row.get('ITEM_CODE')
        if pair in lookup:raise p.ProbeError('metadata_invalid')
        lookup[pair]=row
    for n,(code,name) in enumerate(zip(item['item_codes'],item['item_names']),1):
        row=lookup.get((f'Group{n}',code),{})
        if (row.get('STAT_CODE')!='731Y004' or row.get('ITEM_NAME')!=name
                or row.get('UNIT_NAME') not in ('원',None) or (n==1 and row.get('UNIT_NAME')!='원')
                or ecos.period(row.get('START_TIME'))>'2021-01'
                or not '2026-10'<=ecos.period(row.get('END_TIME'))<now.strftime('%Y-%m')):
            raise p.ProbeError('metadata_invalid')


def probe(config,baseline,client=None,now=None):
    simulated=client is not None
    result=dict(status='failed',authentication='not_verified',phase='not_started',
        response_count=0,matched_count=0,correction_candidate_count=0,unqueried_count=70,
        correction_periods=[])
    try:
        p.validate_baseline(baseline);item=p.registry(config)[KEY]
        now=now or dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
        if now.strftime('%Y-%m')<='2026-10':raise p.ProbeError('invalid_period')
        client=ecos.Client() if client is None else client
        result['phase']='metadata';metadata(item,client,now)
        for phase,(start,end) in zip(('gate_3','history_67'),WINDOWS):
            result['phase']=phase
            records=read_window(item,client,start,end,now)
            changes=[period for period,row in records.items()
                     if p.fingerprint(KEY,period,row['value'])!=baseline['series'][KEY]['fingerprints'][period]]
            result['response_count']+=len(records)
            result['matched_count']+=len(records)-len(changes)
            result['correction_candidate_count']+=len(changes)
            result['unqueried_count']-=len(records)
            result['correction_periods']+=sorted(changes)
            result['authentication']='not_verified' if simulated else 'verified_fx_observations'
            if changes:
                result['error']='corrections_require_review'
                # A gate mismatch prevents expansion; history mismatches never
                # update the baseline or any existing validated observation.
                return result
        result.update(status='simulation_only' if simulated else 'passed',phase='complete')
    except BaseException as exc:
        code=p.error_code(exc);result['error']=code
        if code in ('credential_missing','authentication_rejected','auth_or_access_denied'):
            result['authentication']=code
    return result


def render(result):
    allowed={'status','authentication','phase','response_count','matched_count','correction_candidate_count','unqueried_count','correction_periods','error'}
    if (set(result)-allowed or result.get('status') not in ('failed','passed','simulation_only')
            or result.get('authentication') not in ('not_verified','verified_fx_observations','credential_missing','authentication_rejected','auth_or_access_denied')
            or result.get('phase') not in ('not_started','metadata','gate_3','history_67','complete')
            or result.get('error') not in p.ERROR_CODES|{'corrections_require_review',None}):
        raise p.ProbeError('configuration_invalid')
    fields=('response_count','matched_count','correction_candidate_count','unqueried_count')
    if (any(type(result.get(k)) is not int or not 0<=result[k]<=70 for k in fields)
            or result['response_count']+result['unqueried_count']!=70
            or result['matched_count']+result['correction_candidate_count']!=result['response_count']
            or not isinstance(result.get('correction_periods'),list)
            or len(set(result['correction_periods']))!=len(result['correction_periods'])
            or len(result['correction_periods'])!=result['correction_candidate_count']
            or any(x not in months('2021-01','2026-10') for x in result['correction_periods'])
            or (result['status'] in ('passed','simulation_only') and (result['phase']!='complete' or result['matched_count']!=70))):
        raise p.ProbeError('configuration_invalid')
    lines=['## Market Weather FX History Preflight','',
        '- Fixed series: 731Y004 / 0000001 / 0000100 / M / 원',
        '- Fixed coverage: 2021-01..2026-10 (70 months)',
        '- No production writes, independent-source certification, or approvals.']
    for k in ('status','authentication','phase',*fields):lines.append('- '+k+': '+str(result[k]))
    if result.get('error'):lines.append('- error: '+result['error'])
    if result['correction_periods']:lines.append('- correction_periods: '+', '.join(sorted(result['correction_periods'])))
    return '\n'.join(lines)+'\n'


def main():
    if not (os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch'
            and os.environ.get('GITHUB_REF')=='refs/heads/main'):
        print('FX history preflight requires a manual main Actions run.');return 1
    fd=None
    try:
        with contextlib.redirect_stdout(p.Discard()),contextlib.redirect_stderr(p.Discard()):
            fd=p.summary_fd(os.environ)
            baseline=p.load_baseline()
            config=json.loads((p.ROOT/'macro_sources.json').read_text())
            result=probe(config,baseline)
            body=render(result);key=os.environ.get('ECOS_API_KEY','')
            if key and key in body:return 1
            with os.fdopen(fd,'a') as stream:
                fd=None;stream.write(body)
        return 0 if result['status']=='passed' else 1
    except BaseException:
        return 1
    finally:
        if fd is not None:os.close(fd)


if __name__=='__main__':raise SystemExit(main())
