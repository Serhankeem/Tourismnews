"""Synthetic approvals only; production refs and actual article never written."""
import copy
import datetime as dt
from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.macro import weather_release as r, weather_publication as g
from src.pipeline import runner
from src.pipeline.layout import ROOT, configuration, copy_data, files, hashes, optional, read
from src.pipeline.validation import validate
from test_weather_publication import setup, NOW
from test_pipeline import PipelineHarness


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.stage=self.root/'stage';self.cfg=configuration()
        copy_data(ROOT,self.stage,self.cfg)
        from src.pipeline.policy import project
        project(self.stage,ROOT,NOW)
        self.ctx,self.pub,self.trust,_,_=setup()
        self.authority=r.Authority(lambda:self.trust,lambda *_:[(self.ctx,self.pub)])
        self.request=r.PublicationRequest(self.authority,'market-weather-2026-09:1')

    def apply(self):return self.request.apply(self.stage,ROOT,NOW)

    def test_synthetic_gate_to_catalog_to_pages_preserves_private_boundary(self):
        self.assertTrue(self.apply());validate(self.stage,self.cfg)
        idx,archive=r.verify(self.stage,ROOT,self.authority,NOW)
        self.assertEqual(idx['latest'],'market-weather-2026-09:1')
        self.assertEqual(archive['contents'][idx['latest']]['title'],'합성 월간 원고')
        output=self.root/'pages';runner.compose(ROOT,self.stage,output,self.cfg,monthly_authority=self.authority,at=NOW)
        self.assertTrue((output/'data/market_weather_archive.json').exists())
        self.assertFalse((output/'collector_state').exists())
        self.assertFalse(any(p.name in ('authority.json','diagnostic-private.json','editorial-approval-record.json') for p in output.rglob('*')))

    def test_repeat_is_byte_identical_noop(self):
        self.apply();before=hashes(self.stage,r.PUBLIC_FILES)
        self.assertFalse(self.apply());self.assertEqual(before,hashes(self.stage,r.PUBLIC_FILES))

    def test_missing_approval_never_projects_or_writes(self):
        self.pub=None
        with patch.object(g,'_projection') as projection:
            with self.assertRaisesRegex(g.GateError,'publication_approval_missing'):self.apply()
            projection.assert_not_called()
        self.assertFalse(any((self.stage/n).exists() for n in r.PUBLIC_FILES))

    def test_changed_manuscript_is_rejected_before_write(self):
        self.ctx=replace(self.ctx,manuscript=self.ctx.manuscript+b'changed')
        with self.assertRaisesRegex(g.GateError,'manuscript_hash_mismatch'):self.apply()
        self.assertFalse((self.stage/r.PUBLIC_FILES[0]).exists())

    def test_revoked_or_expired_approval_refuses_reassembly(self):
        self.apply()
        for role in ('editorial','publication'):
            original=self.trust
            self.trust=replace(original,**{role:(replace(getattr(original,role)[0],revoked=True),)})
            with self.assertRaises(g.GateError):r.verify(self.stage,ROOT,self.authority,NOW)
            self.trust=original
        with self.assertRaises(g.GateError):r.verify(self.stage,ROOT,self.authority,NOW+dt.timedelta(days=2))

    def test_existing_release_requires_external_authority(self):
        self.apply()
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(g.GateError,'monthly_authority_required'):r.verify(self.stage,ROOT,at=NOW)

    def test_partial_pair_and_symlink_blocked(self):
        self.apply();p=self.stage/r.PUBLIC_FILES[0];p.unlink()
        with self.assertRaises(ValueError):optional(self.cfg,self.stage)
        p.symlink_to(self.stage/r.PUBLIC_FILES[1])
        with self.assertRaises(g.GateError):r.catalog(self.stage)

    def test_catalog_hash_identity_latest_and_unknown_fields_fail(self):
        self.apply();idx=read(self.stage/r.PUBLIC_FILES[0]);archive=read(self.stage/r.PUBLIC_FILES[1])
        changes=[lambda d:d.update(latest='missing'),lambda d:d['entries'].append(copy.deepcopy(d['entries'][0])),
                 lambda d:d['entries'][0].update(content_sha256='0'*64),lambda d:d.update(private='forbidden')]
        for change in changes:
            broken=copy.deepcopy(idx);change(broken);(self.stage/r.PUBLIC_FILES[0]).write_text(json.dumps(broken))
            with self.assertRaises(g.GateError):r.catalog(self.stage)
        (self.stage/r.PUBLIC_FILES[0]).write_text(json.dumps(idx))
        archive['contents'][idx['latest']]['private']='forbidden'
        (self.stage/r.PUBLIC_FILES[1]).write_text(json.dumps(archive))
        with self.assertRaises(g.GateError):r.catalog(self.stage)

    def test_previous_edition_cannot_be_mutated_or_lost(self):
        self.apply();before=self.root/'before';shutil.copytree(self.stage,before)
        for n in r.PUBLIC_FILES:(self.stage/n).unlink()
        # Full snapshot validation also detects optional pair removal against before.
        with self.assertRaises(ValueError):validate(self.stage,optional(self.cfg,before),before=before)

    def test_failure_keeps_previous_pages(self):
        self.apply();out=self.root/'pages';out.mkdir();(out/'previous.txt').write_text('preserve')
        self.trust=replace(self.trust,publication=())
        with self.assertRaises(ValueError):runner.compose(ROOT,self.stage,out,self.cfg,monthly_authority=self.authority,at=NOW)
        self.assertEqual((out/'previous.txt').read_text(),'preserve')

    def test_private_assets_and_copy_failure_keep_previous_pages(self):
        code=self.root/'code';shutil.copytree(ROOT/'site',code/'site')
        for n in ('macro_sources.json','operating_policy.json','sources.json','reports_sources.json'):
            shutil.copyfile(ROOT/n,code/n)
        out=self.root/'pages';out.mkdir();(out/'previous.txt').write_text('preserve')
        for name in ('leaked-private.json','manuscript.md'):
            p=code/'site'/name;p.write_text('{}')
            with self.assertRaises(ValueError):runner.compose(code,self.stage,out,self.cfg,at=NOW)
            p.unlink();self.assertEqual((out/'previous.txt').read_text(),'preserve')
        with patch.object(runner.shutil,'copytree',side_effect=OSError('synthetic')):
            with self.assertRaises(OSError):runner.compose(ROOT,self.stage,out,self.cfg,at=NOW)
        self.assertEqual((out/'previous.txt').read_text(),'preserve')

    def test_fresh_authority_rechecked_before_pages_promotion(self):
        self.apply();out=self.root/'pages';out.mkdir();(out/'previous.txt').write_text('preserve')
        calls=[]
        def pins():
            calls.append(1)
            return self.trust if len(calls)==1 else replace(self.trust,publication=())
        authority=r.Authority(pins,lambda *_:[(self.ctx,self.pub)])
        with self.assertRaises(ValueError):runner.compose(ROOT,self.stage,out,self.cfg,monthly_authority=authority,at=NOW)
        self.assertEqual(len(calls),2);self.assertEqual((out/'previous.txt').read_text(),'preserve')

    def test_publication_stage_and_registry_cannot_be_repository(self):
        with self.assertRaises(g.GateError):self.request.apply(ROOT/'some-stage',ROOT,NOW)
        with self.assertRaises(g.GateError):r.directory(ROOT/'trust')

    def test_pages_cannot_replace_code_parent(self):
        with self.assertRaisesRegex(ValueError,'isolated_pages_output_required'):
            runner.compose(ROOT,self.stage,ROOT.parent,self.cfg,at=NOW)

    def test_failed_pages_promotion_restores_previous_directory(self):
        out=self.root/'pages';out.mkdir();(out/'previous.txt').write_text('preserve')
        import os
        original=os.replace
        def fail_candidate(source,target):
            if Path(source).name=='pages' and Path(source).parent.name.startswith('.pages-build-'):
                raise OSError('synthetic promotion failure')
            return original(source,target)
        with patch.object(runner.os,'replace',side_effect=fail_candidate):
            with self.assertRaises(OSError):runner.compose(ROOT,self.stage,out,self.cfg,at=NOW)
        self.assertEqual((out/'previous.txt').read_text(),'preserve')


class ReleasePipelineTests(PipelineHarness):
    def setUp(self):
        super().setUp();self.ctx,self.pub,self.trust,_,_=setup()
        self.authority=r.Authority(lambda:self.trust,lambda *_:[(self.ctx,self.pub)])
        self.request=r.PublicationRequest(self.authority,'market-weather-2026-09:1')

    def run_monthly(self,request=None,collector=lambda *a:True):
        work=self.root/('monthly-'+str(len(list(self.root.glob('monthly-*')))))
        return runner.transact(self.code,str(self.remote),work,self.root/'pages',collector=collector,at=NOW,
                               monthly_request=request,monthly_authority=self.authority)

    def test_local_bare_git_publish_reload_repeat_other_collectors_preserve(self):
        result=self.run_monthly(self.request);self.assertTrue(result['ready'])
        store=self.reader();self.assertEqual(store.tip('main'),self.main)
        self.assertTrue(all(n in store.cfg['public_files'] for n in r.PUBLIC_FILES))
        before=hashes(store.path,r.PUBLIC_FILES);first=store.base
        self.assertFalse(self.run_monthly(self.request)['data_committed']);self.assertEqual(self.reader().base,first)
        self.assertTrue(self.run_monthly(collector=self.change)['ready'])
        self.assertEqual(hashes(self.reader().path,r.PUBLIC_FILES),before)

    def test_missing_publication_never_creates_data_ref_or_pages(self):
        self.pub=None
        with self.assertRaisesRegex(g.GateError,'publication_approval_missing'):self.run_monthly(self.request)
        from src.pipeline.store import git
        self.assertEqual(git(self.code,'ls-remote','origin','refs/heads/data/live').stdout,'')
        self.assertFalse((self.root/'pages').exists())

    def test_revocation_during_precommit_prevents_push_and_preserves_pages(self):
        self.run_monthly(self.request);before=self.reader().base;old=(self.root/'pages/data/market_weather_archive.json').read_bytes()
        from src.pipeline.store import Store
        original=Store.commit
        def revoke(store,*args,**kwargs):
            self.trust=replace(self.trust,publication=());return original(store,*args,**kwargs)
        with patch.object(Store,'commit',revoke):
            with self.assertRaises(ValueError):self.run_monthly()
        self.assertEqual(self.reader().base,before)
        self.assertEqual((self.root/'pages/data/market_weather_archive.json').read_bytes(),old)

    def test_collector_cannot_change_published_catalog(self):
        self.run_monthly(self.request);before=hashes(self.reader().path,r.PUBLIC_FILES)
        def bad(engine,stage,*_):
            p=stage/r.PUBLIC_FILES[0];p.write_text('{}');return True
        # Request an engine explicitly: all prior due slots are already acknowledged.
        work=self.root/'bad-collector'
        result=runner.transact(self.code,str(self.remote),work,self.root/'pages',requested='news',collector=bad,at=NOW,monthly_authority=self.authority)
        self.assertFalse(result['collection_ok']);self.assertEqual(before,hashes(self.reader().path,r.PUBLIC_FILES))

    def guard(self,work):
        import os
        with patch.object(runner,'ROOT',self.code),patch.object(runner,'now_kst',return_value=NOW),patch.object(r,'environment',return_value=self.authority),patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'push'}),patch('sys.argv',['runner','guard','--work',str(work)]):
            return runner.main()

    def test_upload_guard_rechecks_current_revocation(self):
        self.run_monthly(self.request);work=self.root/'monthly-0'
        self.assertEqual(self.guard(work),0)
        self.trust=replace(self.trust,publication=())
        self.assertEqual(self.guard(work),1)

    def test_upload_guard_blocks_tampered_and_extra_artifact(self):
        self.run_monthly(self.request);work=self.root/'monthly-0'
        p=self.root/'pages/data/market_weather_archive.json';original=p.read_bytes()
        p.write_bytes(original+b' ');self.assertEqual(self.guard(work),1)
        p.write_bytes(original);self.assertEqual(self.guard(work),0)
        (self.root/'pages/private.txt').write_text('forbidden')
        self.assertEqual(self.guard(work),1)

    def test_pre_push_recheck_refuses_revocation_after_local_commit(self):
        from src.pipeline import store as store_module
        original=store_module.git
        def intercept(directory,*args,**kwargs):
            result=original(directory,*args,**kwargs)
            if args and args[0]=='commit' and Path(directory).name=='snapshot':
                self.trust=replace(self.trust,publication=())
            return result
        with patch.object(store_module,'git',intercept):
            with self.assertRaises(ValueError):self.run_monthly(self.request)
        self.assertEqual(original(self.code,'ls-remote','origin','refs/heads/data/live').stdout,'')
        self.assertFalse((self.root/'pages').exists())
