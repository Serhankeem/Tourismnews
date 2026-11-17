"""Independent editorial/publication gate. No approval issuer, file writer or scheduler.

Receipt hashes must be pinned by a trusted operator OUTSIDE the supplied records.
JSON status/actor strings alone never authorize a release. Python callers and the
host supplying Trust are part of the trust boundary; this is not a signing service.
"""
from dataclasses import dataclass
import copy
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re

from . import weather_diagnostic as engine, weather_shadow as shadow

SCHEMA = engine.ROOT/'schemas/market_weather_public_v2.schema.json'


class GateError(ValueError):
    """Only fixed, non-sensitive reason codes may leave the gate."""


def require(condition, code):
    if not condition:raise GateError(code)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def decode(raw):return json.loads(raw.decode('utf-8'),object_pairs_hook=engine.unique)


def public_time(value):
    require(isinstance(value,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})',value),'public_timestamp_format_invalid')
    return engine.stamp(value)


@dataclass(frozen=True)
class Anchor:
    record_sha256: str
    approver: str
    approved_at: str
    revoked: bool = False


@dataclass(frozen=True)
class Trust:
    editorial: tuple = ()
    publication: tuple = ()


@dataclass(frozen=True)
class Context:
    manuscript: bytes
    editorial_record: bytes
    bundle_manifest: bytes
    diagnostic: dict
    snapshot_config: dict
    archive: dict
    snapshot_policy: dict


def trust_file(path):
    """Operator-managed read-only pins, never loaded from a receipt or public file."""
    path=Path(path)
    require(not path.is_symlink() and path.is_file(),'trust_file_invalid')
    resolved=path.resolve()
    require(engine.ROOT not in resolved.parents and resolved!=engine.ROOT,'external_trust_required')
    require(path.stat().st_mode & 0o222 == 0,'readonly_trust_required')
    doc=engine.read(path)
    require(set(doc)=={'version','editorial','publication'} and doc['version']==1,'trust_shape_invalid')
    groups={}
    for role in ('editorial','publication'):
        require(isinstance(doc[role],list),'trust_shape_invalid')
        pins=[]
        for row in doc[role]:
            require(set(row)=={'record_sha256','approver','approved_at','revoked'},'trust_shape_invalid')
            require(re.fullmatch('[a-f0-9]{64}',row['record_sha256']) and type(row['revoked']) is bool,'trust_shape_invalid')
            pins.append(Anchor(**row))
        require(len({a.record_sha256 for a in pins})==len(pins),'duplicate_trust_anchor')
        groups[role]=tuple(pins)
    return Trust(**groups)


def receipt(raw, role, trust, now):
    require(raw is not None,role+'_approval_missing')
    pins=[a for a in getattr(trust,role) if a.record_sha256==sha(raw)]
    require(len(pins)==1,role+'_approval_untrusted')
    anchor=pins[0];require(not anchor.revoked,role+'_approval_revoked')
    doc=decode(raw);row=doc[role]
    require(row['status']=='approved',role+'_approval_not_approved')
    require(row['approver_github_login']==anchor.approver and row['approved_at']==anchor.approved_at,role+'_identity_or_time_mismatch')
    require(engine.stamp(row['approved_at'])<=now,role+'_approval_in_future')
    return doc


def load_context(editorial_path, trust, now):
    path=Path(editorial_path).resolve()
    require(engine.ROOT not in path.parents,'external_editorial_record_required')
    raw=path.read_bytes()
    record=receipt(raw,'editorial',trust,now)  # authenticate pin BEFORE following embedded paths
    manuscript=path.parent/record['manuscript_file']
    require(manuscript.resolve().parent==path.parent and not manuscript.is_symlink(),'manuscript_path_invalid')
    bundle=Path(record['input_snapshot']['source_bundle']).resolve()
    require(engine.ROOT not in bundle.parents,'external_snapshot_required')
    shadow.verify_bundle(bundle)
    return Context(manuscript.read_bytes(),raw,(bundle/'manifest.json').read_bytes(),
                   engine.read(bundle/'diagnostic-private.json'),engine.read(bundle/'inputs/config.json'),
                   engine.read(bundle/'inputs/archive.json'),engine.read(bundle/'inputs/policy.json'))


def amount(raw):
    match=re.fullmatch(r'(?:(\d[\d,]*)억\s*)?(?:(\d[\d,]*)만\s*)?(\d[\d,]*)?',raw.strip())
    require(match is not None and any(match.groups()),'manuscript_number_invalid')
    return sum(int(v.replace(',',''))*scale for v,scale in zip(match.groups(),(100000000,10000,1)) if v)


def parse_manuscript(raw, diagnostic):
    """Private compatibility check; preserves all five approved prose sections.

    Only known review-status/reference metadata above the article is omitted from
    a future public projection. Never rewrites or summarizes approved prose.
    """
    text=raw.decode('utf-8')
    require(len(raw)<=100000 and '<' not in text and '>' not in text and '```' not in text,'unsupported_manuscript_markup')
    pieces=re.split(r'^## (.+)\n',text,flags=re.M)
    require(len(pieces)==11 and pieces[0].startswith('# '),'manuscript_sections_invalid')
    header=pieces[0].strip().split('\n')
    require(len([x for x in header if x.strip()])==4,'manuscript_header_invalid')
    subtitle=re.search(r'^\*\*(.+)\*\*$',pieces[0],re.M)
    require(subtitle is not None,'manuscript_subtitle_missing')
    require(0<len(header[0][2:])<=600 and 0<len(subtitle[1])<=600,'article_bounds_invalid')
    period=diagnostic['target_period'];year,month=map(int,period.split('-'))
    require(f'자료 기준월: {year}년 {month}월' in pieces[0],'manuscript_period_mismatch')
    require('발행 상태: 편집 검토 중 · 미발행' in pieces[0],'review_metadata_invalid')
    sections=[dict(heading=pieces[i],markdown=pieces[i+1].strip()) for i in range(1,len(pieces),2)]
    require(all(0<len(s['heading'])<=600 and 0<len(s['markdown'])<=6000 for s in sections),'article_bounds_invalid')
    require(sections[1]['heading'].startswith('01. ') and sections[2]['heading'].startswith('02. '),'evidence_sections_invalid')
    require('종합 판정' in sections[3]['markdown'] and '보류' in sections[3]['markdown'],'overall_withheld_note_missing')
    urls=re.findall(r'\]\((https://[^\s)]+)\)',text)
    require(urls==[diagnostic['axes'][k]['provenance']['source_url'] for k in engine.CORE],'source_urls_mismatch')
    require('retrospective_current_vintage' in sections[4]['markdown'],'vintage_note_missing')
    for index,key in enumerate(engine.CORE,1):
        row=diagnostic['axes'][key];block=sections[index]['markdown'];unit='명' if key=='kto_inbound' else '달러'
        current=re.search(r'\*\*([0-9,억만\s]+)'+unit+r'\*\*',block)
        require(current is not None and amount(current[1])==row['value'],'article_current_value_mismatch')
        for rate,base_key in (('yoy_pct','yoy_base_period'),('mom_pct','mom_base_period')):
            base_period=row['comparisons'][base_key];by,bm=map(int,base_period.split('-'))
            base=re.search(fr'{by}년 {bm}월의 ([0-9,억만\s]+)'+unit,block)
            baseline=row['comparison_observations'].get(base_period,{}).get('value')
            require(base is not None and baseline is not None and amount(base[1])==baseline,'article_baseline_mismatch')
            raw_rate=row['comparisons'][rate];require(raw_rate is not None,'article_rate_unavailable')
            pct=Decimal(raw_rate);display=format(abs(pct).quantize(Decimal('.01'),rounding=ROUND_HALF_UP),'.2f')
            word='증가' if pct>0 else '감소' if pct<0 else '동일'
            require(display+'% '+word in block,'article_rate_or_direction_mismatch')
    return dict(title=header[0][2:],subtitle=subtitle[1],sections=sections)


def validate_editorial(ctx, trust, now, config, policy):
    require(now.tzinfo is not None,'timezone_required')
    record=receipt(ctx.editorial_record,'editorial',trust,now)
    require(record['record_type']=='user_confirmed_editorial_approval_with_identity_and_basis_time','editorial_record_type_invalid')
    require(record['manuscript_sha256']==sha(ctx.manuscript)==record['editorial']['approved_content_sha256'],'manuscript_hash_mismatch')
    period=record['reference_period'];engine.valid_period(period)
    require(record['content_id']=='market-weather-'+period and re.fullmatch(r'r[1-9][0-9]*',record['editorial_revision']),'editorial_scope_invalid')
    scope=record['editorial'].get('scope')
    require(scope=='exact_manuscript_only' or (scope=='exact_r2_manuscript_only' and record['editorial_revision']=='r2'),'editorial_scope_invalid')
    snapshot=record['input_snapshot']
    require(snapshot['source_bundle_manifest_sha256']==sha(ctx.bundle_manifest),'snapshot_manifest_mismatch')
    inputs={'config':ctx.snapshot_config,'archive':ctx.archive,'policy':ctx.snapshot_policy}
    require({k:engine.digest(v) for k,v in inputs.items()}==snapshot['canonical_json_input_hashes']==ctx.diagnostic['input_hashes'],'snapshot_input_mismatch')
    bundle=decode(ctx.bundle_manifest)
    # The editorial pin binds the original manifest; its raw diagnostic digest
    # additionally binds the supplied diagnostic without relying on status flags.
    diagnostic_bytes=(json.dumps(ctx.diagnostic,ensure_ascii=False,indent=2)+'\n').encode()
    require(bundle['files']['diagnostic-private.json']==sha(diagnostic_bytes),'diagnostic_hash_mismatch')
    require(ctx.diagnostic['methodology_version']==snapshot['methodology_version']==engine.VERSION,'methodology_mismatch')
    require(ctx.diagnostic['target_period']==period==snapshot['reference_period'],'reference_period_mismatch')
    cutoff=engine.stamp(ctx.diagnostic['input_cutoff'])
    public_time(ctx.diagnostic['input_cutoff'])
    require(ctx.diagnostic['input_cutoff']==snapshot['input_cutoff'] and cutoff<=now,'cutoff_mismatch')
    analysis=engine.stamp(ctx.diagnostic['analysis_at'])
    require(snapshot.get('original_analysis_at')==ctx.diagnostic['analysis_at'] and cutoff<=analysis<=engine.stamp(record['editorial']['approved_at']),'editorial_precedes_analysis')
    sources=[s for s in config['sources'] if s['id']=='tourgo_tourism_balance']
    require(len(sources)==1,'statistics_not_currently_eligible')
    source=sources[0]
    require(source.get('activation_conditions')==dict(noncommercial=True,free_access=True,no_ads=True,attribution=True),'statistics_not_currently_eligible')
    for action in ('collection','publication'):
        allowed=engine.tourgo.approved_range(source,action)
        require('2021-01'<=allowed['period_from']<=allowed['period_through']<='2026-09','tourgo_scope_expansion_forbidden')
    # Reuses BOTH current collection/publication permissions, terms, definitions,
    # units and data validators. Old editorial approval cannot bypass new revocation.
    current=engine.diagnose(config,ctx.archive,policy,period,cutoff,now)
    require(current['target_ready'] and current['status']=='partial_monitor','statistics_not_currently_eligible')
    require(ctx.diagnostic['overall_status']=='withheld' and ctx.diagnostic['publication_approved'] is False,'diagnostic_scope_invalid')
    require(set(ctx.diagnostic['axes'])==set(engine.CORE),'unapproved_indicators')
    for key in engine.CORE:
        for field in ('value','unit','period','comparisons','comparison_observations','provenance'):
            require(current['axes'][key][field]==ctx.diagnostic['axes'][key][field],'statistics_or_vintage_mismatch')
        provenance=ctx.diagnostic['axes'][key]['provenance']
        require(len(provenance['source_url'])<=2000,'public_source_bounds_invalid')
        if provenance['original_publication_at'] is not None:public_time(provenance['original_publication_at'])
    article=parse_manuscript(ctx.manuscript,ctx.diagnostic)
    return record,article


def validate_publication(ctx, raw, trust, now, editorial):
    record=receipt(raw,'publication',trust,now);pub=record['publication']
    require(record['record_type']=='publication_approval','publication_record_type_invalid')
    for key in ('content_id','reference_period','editorial_revision','manuscript_sha256'):
        require(record[key]==editorial[key],'publication_scope_mismatch')
    require(pub['scope']=='website_content' and type(pub['public_revision']) is int and pub['public_revision']==1,'publication_release_scope_invalid')
    require(pub['editorial_record_sha256']==sha(ctx.editorial_record),'editorial_receipt_binding_mismatch')
    require(pub['archive_sha256']==editorial['input_snapshot']['canonical_json_input_hashes']['archive'],'publication_snapshot_mismatch')
    require(pub['contract_sha256']==sha(SCHEMA.read_bytes()) and pub['implementation_sha256']==sha(Path(__file__).read_bytes()),'projection_contract_mismatch')
    start,end=engine.stamp(pub['valid_from']),engine.stamp(pub['valid_until'])
    approved=engine.stamp(pub['approved_at']);release=public_time(pub['release_at'])
    require(approved>=engine.stamp(editorial['editorial']['approved_at']),'publication_precedes_editorial')
    require(approved<=start<=release<=now<=end,'publication_expired_or_not_yet_valid')
    return record


def audit(ctx, publication_record, trust, now, config, policy):
    """Safe eligibility report, not public content or a permit object."""
    result=dict(editorial_verified=False,statistics_verified=False,manuscript_compatible=False,
                publication_verified=False,public_json_generated=False,public_site_integration_enabled=False)
    try:
        ctx=copy.deepcopy(ctx);config=copy.deepcopy(config);policy=copy.deepcopy(policy)
        editorial,article=validate_editorial(ctx,trust,now,config,policy)
        result.update(editorial_verified=True,statistics_verified=True,manuscript_compatible=True,article_sections=len(article['sections']),evidence_sections=2)
        validate_publication(ctx,publication_record,trust,now,editorial)
        result.update(publication_verified=True,reason='both_approvals_verified')
    except (GateError,ValueError,KeyError,TypeError,AttributeError,UnicodeError) as exc:
        result['reason']=str(exc) if isinstance(exc,GateError) else 'approval_or_input_invalid'
    return result


def _projection(ctx, editorial, publication, article):
    sections=article['sections'];diag=ctx.diagnostic;metrics={};sources=[];evidence=[]
    for index,key in enumerate(engine.CORE):
        row=diag['axes'][key];c=row['comparisons'];comparisons={}
        for short,rate,base in (('mom','mom_pct','mom_base_period'),('yoy','yoy_pct','yoy_base_period')):
            baseline=row['comparison_observations'].get(c[base],{}).get('value')
            comparisons[short]=dict(period=c[base],pct=c[rate],direction=engine.direction(row['value'],baseline))
        metrics[key]=dict(value=row['value'],unit=row['unit'],comparisons=comparisons)
        p=row['provenance'];source_id='source_'+str(index+1)
        sources.append(dict(id=source_id,publisher=p['publisher'],url=p['source_url'],original_publication_at=p['original_publication_at'],finality=p['finality']))
        evidence.append(dict(indicator=key,text=sections[index+1]['markdown'],source_ids=[source_id],comparison_periods=[c['yoy_base_period'],c['mom_base_period']]))
    return dict(schema_version=2,content_id=editorial['content_id'],revision=publication['publication']['public_revision'],
                editorial_revision=editorial['editorial_revision'],reference_period=editorial['reference_period'],
                issued_at=publication['publication']['release_at'],data_cutoff=diag['input_cutoff'],analysis_mode=diag['mode'],
                title=article['title'],summary=sections[0]['markdown'],overall_state='withheld',metrics=metrics,evidence=evidence,sources=sources,
                limitations=dict(industry_activity_missing=sections[3]['markdown'],nominal_bop_definition=sections[2]['markdown'].split('\n\n')[-1],
                                 nonseasonal_mom=sections[0]['markdown'].split('\n\n')[-1],vintage_and_lag=sections[4]['markdown'],
                                 base_effect_and_revisions=sections[4]['markdown'].split('\n\n')[-2]),
                article=dict(subtitle=article['subtitle'],sections=sections),methodology_version=diag['methodology_version'],correction=None)


def public_json(ctx, publication_record, trust, now, config, policy):
    """Both independent approvals MUST pass before any public object/JSON exists.

    No disk writer exists. Real Step 18 inputs are blocked here; positive tests
    use clearly synthetic receipts and data only. Callers cannot use audit output
    as a permit, and every call rechecks time, trust revocation and source rights.
    """
    ctx=copy.deepcopy(ctx);config=copy.deepcopy(config);policy=copy.deepcopy(policy)
    editorial,article=validate_editorial(ctx,trust,now,config,policy)
    publication=validate_publication(ctx,publication_record,trust,now,editorial)
    payload=_projection(ctx,editorial,publication,article)
    return json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
