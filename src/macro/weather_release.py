"""Transactional monthly staging and revalidation. No approval issuer/network API."""
import datetime as dt
import json
import hashlib
import hmac
import re
import os
from pathlib import Path
from . import weather_publication as gate,weather_diagnostic as engine

PUBLIC_FILES=('site/data/market_weather_index.json','site/data/market_weather_archive.json')


def need(condition,code):
    if not condition:raise gate.GateError(code)


def key(payload):return payload['content_id']+':'+str(payload['revision'])


def _entry(payload,not_after):
    return dict(key=key(payload),content_id=payload['content_id'],revision=payload['revision'],
                editorial_revision=payload['editorial_revision'],reference_period=payload['reference_period'],
                title=payload['title'],issued_at=payload['issued_at'],not_after=not_after,
                content_sha256=engine.digest(payload))


def documents(grants):
    entries=sorted([_entry(v['content'],v['not_after']) for v in grants.values()],
                   key=lambda e:(e['reference_period'],e['revision']),reverse=True)
    return (dict(schema_version=1,kind='approved_market_weather_index',latest=entries[0]['key'] if entries else None,entries=entries),
            dict(schema_version=1,kind='approved_market_weather_archive',contents={k:v['content'] for k,v in sorted(grants.items())}))


def catalog(root,before=None):
    root=Path(root);present=[(root/name).exists() for name in PUBLIC_FILES]
    need(all(present) or not any(present),'monthly_pair_incomplete')
    if not any(present):return None
    need(all(not (root/name).is_symlink() for name in PUBLIC_FILES),'monthly_symlink_forbidden')
    index,archive=[engine.read(root/name) for name in PUBLIC_FILES]
    need(set(index) in ({'schema_version','kind','latest','entries'},{'schema_version','kind','latest','entries','seal'}) and index['schema_version']==1 and index['kind']=='approved_market_weather_index','monthly_index_shape_invalid')
    need(set(archive)=={'schema_version','kind','contents'} and archive['schema_version']==1 and archive['kind']=='approved_market_weather_archive','monthly_archive_shape_invalid')
    need(isinstance(archive['contents'],dict) and bool(archive['contents']) and isinstance(index['entries'],list),'monthly_archive_empty_or_invalid')
    grants={}
    for entry in index['entries']:
        k=entry.get('key');need(isinstance(k,str) and k not in grants and k in archive['contents'],'monthly_catalog_identity_invalid')
        payload=archive['contents'][k]
        need(k==key(payload) and set(payload)==set(json.loads(gate.SCHEMA.read_text())['required']),'monthly_content_contract_invalid')
        need(payload['schema_version']==2 and payload['overall_state']=='withheld' and payload['analysis_mode']=='retrospective_current_vintage','monthly_content_contract_invalid')
        need(set(payload['metrics'])==set(engine.CORE),'monthly_unapproved_indicator')
        gate.public_time(entry['not_after']);need(engine.stamp(entry['not_after'])>=engine.stamp(payload['issued_at']),'monthly_expiry_invalid')
        need(entry==_entry(payload,entry['not_after']),'monthly_catalog_hash_or_metadata_mismatch')
        grants[k]={'content':payload,'not_after':entry['not_after']}
    need(set(grants)==set(archive['contents']),'monthly_catalog_archive_mismatch')
    expected_index,expected_archive=documents(grants)
    if 'seal' in index:
        need(isinstance(index['seal'],str) and re.fullmatch('[a-f0-9]{64}',index['seal']),'monthly_seal_invalid')
        expected_index['seal']=index['seal']
    need(index==expected_index and archive==expected_archive,'monthly_catalog_order_or_latest_invalid')
    if before is not None:
        old=catalog(before)
        if old:
            need(set(old[1]['contents'])<=set(archive['contents']),'monthly_published_edition_lost')
            for k,payload in old[1]['contents'].items():need(payload==archive['contents'][k],'monthly_published_edition_changed')
            for e in old[0]['entries']:need(e in index['entries'],'monthly_approved_entry_changed')
    return index,archive


def signing_key():
    raw=os.environ.get('MARKET_WEATHER_SIGNING_KEY','')
    need(re.fullmatch('[a-f0-9]{64}',raw) is not None,'monthly_signing_key_required')
    return bytes.fromhex(raw)


def seal(documents):
    index,archive=documents
    unsigned={k:v for k,v in index.items() if k!='seal'}
    message=('market-weather-catalog-v1:'+engine.digest([unsigned,archive])).encode()
    return hmac.new(signing_key(),message,hashlib.sha256).hexdigest()


def verify_seal(stored,code,at):
    need(hmac.compare_digest(stored[0]['seal'],seal(stored)),'monthly_signature_mismatch')
    config=engine.read(Path(code)/'macro_sources.json');policy=engine.read(Path(code)/'operating_policy.json')
    for entry in stored[0]['entries']:
        payload=stored[1]['contents'][entry['key']]
        need(engine.stamp(payload['issued_at'])<=at<=engine.stamp(entry['not_after']),'monthly_release_time_invalid')
        gate.validate_current_rights(config,policy,payload['reference_period'],at)
        source=next(s for s in config['sources'] if s['id']=='tourgo_tourism_balance')
        for c in payload['metrics']['kto_tourism_receipts']['comparisons'].values():
            for action in ('collection','publication'):
                scope=engine.tourgo.approved_range(source,action)
                need(scope['period_from']<=c['period']<=scope['period_through'],'statistics_not_currently_eligible')


class Authority:
    """Trusted runtime dependency. Both loaders must return FRESH external data.

    Tests inject synthetic records. Production construction uses directory() only;
    public JSON/HTTP never supplies these loaders or their paths.
    """
    def __init__(self,trust_loader,records_loader):
        self.trust_loader,self.records_loader=trust_loader,records_loader

    def grants(self,code,at):
        trust=self.trust_loader();records=self.records_loader(trust,at)
        config=engine.read(Path(code)/'macro_sources.json');policy=engine.read(Path(code)/'operating_policy.json')
        result={}
        for ctx,publication in records:
            # Actual public serialization cannot happen until BOTH approvals pass.
            payload=gate.decode(gate.public_json(ctx,publication,trust,at,config,policy))
            k=key(payload);need(k not in result,'duplicate_authority_record')
            result[k]={'content':payload,'not_after':gate.decode(publication)['publication']['valid_until']}
        return result


def directory(path):
    path=Path(path).resolve()
    need(path!=engine.ROOT and engine.ROOT not in path.parents,'external_authority_required')
    def registry():
        f=path/'authority.json'
        need(not f.is_symlink() and f.is_file() and f.stat().st_mode & 0o222==0,'readonly_authority_required')
        doc=engine.read(f)
        need(set(doc)=={'version','trust_policy','records'} and doc['version']==1 and isinstance(doc['records'],list),'authority_registry_invalid')
        return doc
    def pins():return gate.trust_file(registry()['trust_policy'])
    def records(trust,at):
        result=[]
        for record in registry()['records']:
            need(set(record)=={'editorial_record','publication_record'},'authority_record_shape_invalid')
            ctx=gate.load_context(record['editorial_record'],trust,at)
            pub=Path(record['publication_record']).read_bytes() if record['publication_record'] else None
            result.append((ctx,pub))
        return result
    return Authority(pins,records)


def environment():
    value=os.environ.get('MARKET_WEATHER_AUTHORITY_DIR')
    return directory(value) if value else None


def verify(root,code,authority=None,at=None):
    stored=catalog(root)
    if stored is None:return None
    if 'seal' in stored[0]:
        verify_seal(stored,code,at or dt.datetime.now(dt.timezone.utc))
        return stored
    authority=authority or environment();need(authority is not None,'monthly_authority_required')
    expected=authority.grants(code,at or dt.datetime.now(dt.timezone.utc))
    subset={}
    for k in stored[1]['contents']:
        need(k in expected,'monthly_authority_record_missing');subset[k]=expected[k]
    need(stored==documents(subset),'monthly_gate_projection_mismatch')
    return stored


class PublicationRequest:
    def __init__(self,authority,release_key):self.authority,self.release_key=authority,release_key

    def apply(self,stage,code,at):
        stage=Path(stage).resolve()
        need(stage!=engine.ROOT and engine.ROOT not in stage.parents and stage not in engine.ROOT.parents,'isolated_publication_stage_required')
        grants=self.authority.grants(code,at)  # before any write; missing approval leaves stage untouched
        need(self.release_key in grants,'requested_release_not_authorized')
        previous=catalog(stage)
        selected={}
        if previous:
            for k,payload in previous[1]['contents'].items():
                need(k in grants and payload==grants[k]['content'],'existing_edition_no_longer_authorized')
                selected[k]=grants[k]
            need(previous==documents(selected),'existing_catalog_changed')
        if self.release_key in selected:return False  # byte-identical idempotent retry
        selected[self.release_key]=grants[self.release_key]
        index,archive=documents(selected)
        # These writes affect a disposable transaction stage only. Persist/Pages
        # promotion is performed only after full snapshot and gate revalidation.
        for name,doc in zip(PUBLIC_FILES,(index,archive)):
            p=stage/name;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
        verify(stage,code,self.authority,at)
        return True
