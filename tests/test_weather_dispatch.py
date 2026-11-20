"""Synthetic GitHub run/values only. No live approval, Secret or deployment."""
import base64
import copy
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

from src.macro import weather_dispatch as d, weather_release as r, weather_publication as g
from src.pipeline import runner
from src.pipeline.layout import ROOT, copy_data, configuration, hashes
from src.pipeline.policy import project
from test_weather_publication import setup, encoded, NOW
from test_pipeline import PipelineHarness


def inputs():
    ctx,_,_,_,_=setup()
    doc=dict(version=1,revision='r3',period='2026-09',manuscript=ctx.manuscript.decode())
    for key,value in [('diagnostic',ctx.diagnostic),('config',ctx.snapshot_config),('archive',ctx.archive),('policy',ctx.snapshot_policy)]:doc[key]=encoded(value).decode()
    doc['bundle_manifest']=encoded({'publication_approved':False,'files':{d.NAMES[k]:g.sha(doc[k].encode()) for k in d.NAMES if k!='bundle_manifest'}}).decode()
    raw=d.encoded(doc);return doc,raw,g.sha(ctx.manuscript),g.sha(raw)


class API:
    def __init__(self,mh,ch):
        self.run=dict(id=123,event='workflow_dispatch',status='in_progress',path='.github/workflows/deploy.yml',
                      head_branch='main',head_sha='a'*40,display_title='Market Weather publish '+mh+' / '+ch,
                      run_attempt=1,repository={'full_name':d.REPOSITORY,'id':1},head_repository={'id':1},
                      actor={'login':'synthetic-owner','id':2},triggering_actor={'id':2},created_at=(NOW-dt.timedelta(minutes=5)).isoformat())
        self.permission={'permission':'admin','user':{'id':2}}
    def get(self,path):return copy.deepcopy(self.run if '/actions/runs/' in path else self.permission)


ENV=dict(GITHUB_ACTIONS='true',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/main',
         GITHUB_REPOSITORY=d.REPOSITORY,GITHUB_SHA='a'*40,GITHUB_RUN_ID='123',GITHUB_ACTOR_ID='2')


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.stage=self.root/'stage';self.cfg=configuration()
        copy_data(ROOT,self.stage,self.cfg);project(self.stage,ROOT,NOW)
        self.doc,self.raw,self.mh,self.ch=inputs();self.api=API(self.mh,self.ch)
        self.env=patch.dict(os.environ,{'MARKET_WEATHER_SIGNING_KEY':'ab'*32},clear=True);self.env.start();self.addCleanup(self.env.stop)
    def request(self,raw=None,mh=None,ch=None):
        return d.Request(self.raw if raw is None else raw,mh or self.mh,ch or self.ch,self.api,ENV,ROOT,'a'*40,NOW)
    def test_verified_dispatch_and_signed_catalog_need_no_approval_files_on_recurring_deploy(self):
        self.assertTrue(self.request().apply(self.stage,ROOT,NOW))
        index,archive=r.verify(self.stage,ROOT,at=NOW+dt.timedelta(days=20))
        self.assertEqual(len(index['seal']),64);self.assertEqual(archive['contents'][index['latest']]['title'],'합성 월간 원고')
        out=self.root/'pages';runner.compose(ROOT,self.stage,out,self.cfg,at=NOW)
        self.assertTrue((out/'data/market_weather_index.json').exists())
        self.assertFalse(any(p.suffix=='.md' or p.name in ('authority.json','review.json') for p in (out/'data').rglob('*')))
    def test_no_approval_flags_or_wrong_run_metadata_never_project(self):
        for field,value in [('event','push'),('path','.github/workflows/collect.yml'),('head_branch','pr'),('head_sha','b'*40),('display_title','approved'),('run_attempt',2),('status','completed'),('triggering_actor',{'id':999}),('repository',{'full_name':'other/repo','id':1})]:
            with self.subTest(field=field):
                api=API(self.mh,self.ch);api.run[field]=value
                with patch.object(g,'_projection') as projection, self.assertRaises(g.GateError):d.Request(self.raw,self.mh,self.ch,api,ENV,ROOT,'a'*40,NOW)
                projection.assert_not_called()
        self.assertFalse(any((self.stage/n).exists() for n in r.PUBLIC_FILES))
    def test_actual_permission_and_identity_required(self):
        for permission in [{'permission':'read','user':{'id':2}},{'permission':'admin','user':{'id':3}}]:
            self.api.permission=permission
            with self.assertRaisesRegex(g.GateError,'github_publish_permission_required'):self.request()
    def test_api_unavailable_is_not_approval(self):
        with patch.object(self.api,'get',side_effect=ValueError('synthetic unavailable')),self.assertRaises(ValueError):self.request()
    def test_input_hash_and_manuscript_mutation_are_blocked(self):
        with self.assertRaisesRegex(g.GateError,'candidate_hash_mismatch'):self.request(raw=self.raw+b' ')
        changed=copy.deepcopy(self.doc);changed['manuscript']+='changed';raw=d.encoded(changed);ch=g.sha(raw)
        self.api=API(self.mh,ch)
        with self.assertRaisesRegex(g.GateError,'manuscript_hash_mismatch'):self.request(raw=raw,ch=ch)
    def test_statistics_mutation_even_with_rebound_candidate_fails_existing_snapshot(self):
        changed=copy.deepcopy(self.doc);archive=g.decode(changed['archive'].encode());archive['indicators']['kto_inbound']['observations']['2026-09']['value']+=1
        changed['archive']=encoded(archive).decode();raw=d.encoded(changed);ch=g.sha(raw);self.api=API(self.mh,ch)
        with self.assertRaisesRegex(g.GateError,'candidate_snapshot_file_mismatch'):self.request(raw=raw,ch=ch)
    def test_candidate_is_rehashed_before_each_transaction_attempt(self):
        req=self.request();req.raw+=b' '
        with patch.object(g,'_projection') as projection,self.assertRaisesRegex(g.GateError,'candidate_hash_mismatch'):req.apply(self.stage,ROOT,NOW)
        projection.assert_not_called()
        self.assertFalse(any((self.stage/n).exists() for n in r.PUBLIC_FILES))
    def test_unit_rights_scope_and_terms_remain_live(self):
        self.request().apply(self.stage,ROOT,NOW)
        config=g.engine.read(ROOT/'macro_sources.json');policy=g.engine.read(ROOT/'operating_policy.json')
        for action in ('collection','publication'):
            c=copy.deepcopy(config);next(s for s in c['sources'] if s['id']=='tourgo_tourism_balance')['approval'][action]['approved']=False
            with patch.object(g.engine,'read',side_effect=lambda path: c if str(path).endswith('macro_sources.json') else policy if str(path).endswith('operating_policy.json') else json.loads(Path(path).read_text())),self.assertRaises(g.GateError):r.verify(self.stage,ROOT,at=NOW)
        with patch.object(g.engine.tourgo,'terms_confirmed',return_value=False),self.assertRaises(g.GateError):self.request()
    def test_forged_catalog_recomputed_plain_hash_cannot_replace_signature(self):
        self.request().apply(self.stage,ROOT,NOW)
        index,archive=r.catalog(self.stage);k=index['latest'];archive['contents'][k]['title']='forged'
        grants={k:{'content':archive['contents'][k],'not_after':index['entries'][0]['not_after']}}
        changed,_=r.documents(grants);changed['seal']=index['seal']
        for name,doc in zip(r.PUBLIC_FILES,(changed,archive)):(self.stage/name).write_text(json.dumps(doc))
        with self.assertRaisesRegex(g.GateError,'monthly_signature_mismatch'):r.verify(self.stage,ROOT,at=NOW)
    def test_missing_or_changed_key_blocks_promotion_and_preserves_previous_pages(self):
        self.request().apply(self.stage,ROOT,NOW);out=self.root/'pages';out.mkdir();(out/'previous').write_text('preserved')
        for value in ('','cd'*32):
            with patch.dict(os.environ,{'MARKET_WEATHER_SIGNING_KEY':value}),self.assertRaisesRegex(ValueError,'monthly_publication_gate_rejected'):runner.compose(ROOT,self.stage,out,self.cfg,at=NOW)
            self.assertEqual((out/'previous').read_text(),'preserved')
    def test_idempotent_repeat_preserves_bytes_and_does_not_reseal_changed_edition(self):
        req=self.request();req.apply(self.stage,ROOT,NOW);before=hashes(self.stage,r.PUBLIC_FILES)
        self.assertFalse(req.apply(self.stage,ROOT,NOW));self.assertEqual(before,hashes(self.stage,r.PUBLIC_FILES))
        doc=copy.deepcopy(self.doc);doc['manuscript']=doc['manuscript'].replace('합성 월간 원고','수정 월간 원고');raw=d.encoded(doc);mh=g.sha(doc['manuscript'].encode());ch=g.sha(raw);self.api=API(mh,ch)
        with self.assertRaisesRegex(g.GateError,'published_edition_immutable'):self.request(raw=raw,mh=mh,ch=ch).apply(self.stage,ROOT,NOW)
        self.assertEqual(before,hashes(self.stage,r.PUBLIC_FILES))
    def test_unsigned_catalog_cannot_be_promoted_without_authority(self):
        self.request().apply(self.stage,ROOT,NOW);index=g.engine.read(self.stage/r.PUBLIC_FILES[0]);index.pop('seal');(self.stage/r.PUBLIC_FILES[0]).write_text(json.dumps(index))
        with self.assertRaisesRegex(g.GateError,'monthly_authority_required'):r.verify(self.stage,ROOT,at=NOW)
    def test_candidate_secret_without_live_dispatch_is_not_a_permit(self):
        env=dict(ENV,MARKET_WEATHER_CANDIDATE_B64=base64.b64encode(zlib.compress(self.raw)).decode())
        env['GITHUB_EVENT_NAME']='push'
        with patch.dict(os.environ,env),patch.object(d,'GitHub',return_value=self.api),self.assertRaisesRegex(g.GateError,'manual_main_dispatch_required'):d.from_environment(ROOT,'a'*40,self.mh,self.ch,NOW)
    def test_workflow_reuses_shared_transaction_and_does_not_pass_candidate_to_regular_runs(self):
        text=(ROOT/'.github/workflows/deploy.yml').read_text();pipeline=(ROOT/'.github/workflows/pipeline.yml').read_text()
        self.assertIn('Market Weather publish {0} / {1}',text);self.assertIn('uses: ./.github/workflows/pipeline.yml',text)
        self.assertIn("inputs.monthly_manuscript_sha256 != '' && secrets.MARKET_WEATHER_CANDIDATE_B64 || ''",pipeline)
        self.assertEqual(pipeline.count('MARKET_WEATHER_SIGNING_KEY: ${{ secrets.MARKET_WEATHER_SIGNING_KEY }}'),3)


class SignedPipelineTests(PipelineHarness):
    def test_publish_then_rss_transaction_uses_only_persistent_signature_key(self):
        doc,raw,mh,ch=inputs();api=API(mh,ch)
        with patch.dict(os.environ,{'MARKET_WEATHER_SIGNING_KEY':'ab'*32},clear=True):
            request=d.Request(raw,mh,ch,api,ENV,self.code,'a'*40,NOW)
            result=runner.transact(self.code,str(self.remote),self.root/'signed-publish',self.root/'pages',collector=lambda *a:True,at=NOW,monthly_request=request)
            self.assertTrue(result['ready']);saved=hashes(self.reader().path,r.PUBLIC_FILES)
            result=runner.transact(self.code,str(self.remote),self.root/'signed-rss',self.root/'pages',requested='news',collector=self.change,at=NOW)
            self.assertTrue(result['ready']);self.assertEqual(saved,hashes(self.reader().path,r.PUBLIC_FILES))
            self.assertEqual(self.reader().tip('main'),self.main)
