"""Incident regression: synthetic limit/hook, local bare Git; no production writes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from src import collector as c
from src.pipeline import runner,store
from src.pipeline.layout import read,hashes,files
from test_pipeline import PipelineHarness
from src import discovery_storage
from src.pipeline import diagnostics,report


class RecoveryTransactions(PipelineHarness):
    def test_near_blob_limit_lossless_compaction_recovers_push(self):
        self.run_pipeline()
        baseline=self.reader();original=read(baseline.path/'collector_state/discovery.json')
        size=(baseline.path/'collector_state/discovery.json').stat().st_size
        compact=len((json.dumps(original,ensure_ascii=False,separators=(',',':'))+'\n').encode())
        limit=(size+compact)//2
        hook=self.remote/'hooks/pre-receive'
        hook.write_text('#!/usr/bin/env python3\nimport sys,subprocess\nfor row in sys.stdin:\n old,new,ref=row.split()\n raw=subprocess.check_output(["git","show",new+":collector_state/discovery.json"])\n if len(raw)>'+str(limit)+':\n  print("remote: GH001: Large files detected. exceeds GitHub file size limit",file=sys.stderr)\n  sys.exit(1)\n')
        hook.chmod(0o755)
        # Small test threshold models the actual 100 MiB GitHub boundary.
        with patch.object(store,'COMPACT_AT_BYTES',1,create=True):
            result=self.run_pipeline(self.change,requested='news')
        self.assertTrue(result['ready']);saved=self.reader()
        self.assertEqual(read(saved.path/'collector_state/discovery.json'),original)
        self.assertLess((saved.path/'collector_state/discovery.json').stat().st_size,limit)
        self.assertEqual(saved.tip('main'),self.main)

    def test_failed_push_retains_collection_and_zero_saved_counts(self):
        self.run_pipeline();baseline=self.reader().base
        hook=self.remote/'hooks/pre-receive';hook.write_text('#!/bin/sh\necho "remote: GH001: Large files detected" >&2\nexit 1\n');hook.chmod(0o755)
        result={}
        with self.assertRaises(store.StoreError):
            runner.transact(self.code,str(self.remote),self.root/'failed',self.root/'pages',requested='news',collector=self.change,at=self.at,result=result)
        self.assertEqual(result['phase'],'persist');self.assertTrue(result['collection_ok'])
        self.assertFalse(result['data_committed']);self.assertEqual(result['data_commit'],baseline)
        self.assertEqual(result['new_records']['news'],0)
        self.assertEqual(self.reader().base,baseline)

    def test_unknown_remote_outcome_never_claims_zero_saved_or_success(self):
        self.run_pipeline();result={};original=store.git;interrupted=[]
        def unavailable(directory,*args,**kwargs):
            if args[0]=='push':
                interrupted.append(True)
                import subprocess
                return subprocess.CompletedProcess(args,1,'','transport token=PRIVATE')
            if interrupted and args[0]=='ls-remote':raise store.StoreError('git_operation_failed:ls-remote')
            return original(directory,*args,**kwargs)
        with patch.object(store,'git',unavailable):
            with self.assertRaises(store.StoreError):
                runner.transact(self.code,str(self.remote),self.root/'unknown',self.root/'pages',requested='news',collector=self.change,at=self.at,result=result)
        self.assertEqual(result['storage_status'],'unverified');self.assertIsNone(result['data_committed'])
        self.assertIsNone(result['new_records']['news']);self.assertEqual(result['operator_action'],'confirm_remote_head')

    def test_saved_snapshot_survives_assembly_failure(self):
        result={}
        with patch.object(runner,'compose',side_effect=OSError('private endpoint')):
            with self.assertRaises(OSError):runner.transact(self.code,str(self.remote),self.root/'assembly',self.root/'pages',collector=self.change,at=self.at,result=result)
        self.assertTrue(result['data_committed']);self.assertEqual(result['storage_status'],'committed')
        self.assertEqual(self.reader().base,result['data_commit']);self.assertEqual(result['phase'],'assemble')
        finished=report.finalize(result,'skipped');self.assertEqual(finished['operator_action'],'review_saved_snapshot_before_redeploy')


class StorageCodecTests(unittest.TestCase):
    def test_roundtrip_unicode_unknown_fields_and_determinism(self):
        doc={'schema_version':3,'candidates':{'a':{'title':None,'title_sha256':'x','unknown':['한글',1,None],
              'publication_policy':{'status':'review'},'first_discovered_at':'2026-11-18','source_ids':['a','b']}}}
        packed=discovery_storage.encode(doc)
        self.assertEqual(discovery_storage.decode(packed),doc);self.assertEqual(discovery_storage.encode(doc),packed)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'discovery.json';c.write_atomic(p,packed)
            self.assertEqual(read(p),doc);self.assertEqual(c.read_json(p,{}),doc)
            packed['payload_sha256']='0'*64;c.write_atomic(p,packed)
            with self.assertRaises(ValueError):c.read_json(p,{})
            with self.assertRaises(ValueError):read(p)

    def test_plain_existing_json_is_backward_compatible(self):
        doc={'schema_version':3,'candidates':{}};self.assertIs(discovery_storage.decode(doc),doc)

    def test_corrupt_truncated_or_oversized_envelope_fails_closed(self):
        original=discovery_storage.encode({'schema_version':3,'candidates':{}})
        changes=[{'payload_base64':'!!!'},{'payload_sha256':'0'*64},{'uncompressed_bytes':1},
                 {'uncompressed_bytes':discovery_storage.MAX_UNCOMPRESSED+1},{'storage_format':'unknown'},
                 {'uncompressed_bytes':True},{'private_extra':'forbidden'}]
        for change in changes:
            with self.subTest(change=list(change)):
                with self.assertRaises(ValueError):discovery_storage.decode({**original,**change})
        with patch.object(discovery_storage,'MAX_UNCOMPRESSED',4):
            with self.assertRaises(ValueError):discovery_storage.encode({'large':'payload'})

    def test_oversized_non_discovery_file_is_blocked_before_git_add(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'collector_state').mkdir()
            c.write_atomic(root/'collector_state/discovery.json',{'schema_version':3,'candidates':{}})
            (root/'control.json').write_text('{}');(root/'large.json').write_text('x'*100)
            cfg={'public_files':['large.json'],'private_files':['collector_state/discovery.json']}
            with patch.object(store,'MAX_BLOB_BYTES',80):
                with self.assertRaisesRegex(store.StoreError,'git_blob_size_limit_preflight'):store.prepare_storage(root,cfg)

    def test_remote_errors_are_allowlisted_without_raw_details(self):
        for message,expected in [('remote GH001: Large files detected https://PRIVATE.invalid','git_remote_blob_limit'),
                                 ('Permission denied token=PRIVATE','git_permission_denied'),
                                 ('GH013 repository rule https://PRIVATE','git_remote_policy_rejected'),
                                 ('Connection reset SECRET','git_transport_failure'),('unrecognized SECRET','git_push_rejected_unknown')]:
            self.assertEqual(store.push_reason(message),expected)


class ProviderRecoveryTests(unittest.TestCase):
    def run_sources(self,root,mode):
        from test_discovery_v03 import source
        from test_collector import AT,feed
        from src.engine import execute
        sources=[source(id='good',url='https://example.org/good'),source(id='bad',url='https://example.org/bad')]
        def load(url):
            if mode=='all_failed' or (mode=='partial' and url.endswith('/bad')):raise OSError('https://PRIVATE.invalid?token=SECRET')
            if mode=='empty':return b'<rss><channel></channel></rss>'
            return feed('국제선 항공노선 확대',link='https://example.org/'+url.rsplit('/',1)[-1])
        result=execute(sources,root/'site',root/'state',at=AT,loader=load,providers=[])
        from src.pipeline.collect import collect
        with patch('src.engine.execute',return_value=result):ok=collect('news',root,False,90)
        return result,ok

    def test_partial_healthy_empty_and_all_failure_preserve_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            partial,ok=self.run_sources(root,'partial');self.assertTrue(ok);self.assertEqual(partial['discovery_status'],'partial')
            self.assertEqual(partial['new_newsroom_items'],1)
            diagnostic=diagnostics.sources({'discovery':partial},{'good','bad'})
            self.assertEqual(diagnostic['successful_sources'],1);self.assertEqual(diagnostic['failed_source_ids'],['bad'])
            self.assertNotIn('PRIVATE',json.dumps(diagnostic));self.assertNotIn('SECRET',json.dumps(diagnostic))
            archive=read(root/'state/archive.json')['articles']
            public=read(root/'site/news.json')['articles']
            failed,ok=self.run_sources(root,'all_failed');self.assertFalse(ok);self.assertEqual(failed['discovery_status'],'failed')
            self.assertEqual(read(root/'state/archive.json')['articles'],archive)
            self.assertEqual(read(root/'site/news.json')['articles'],public)
            # Subsequent real engine reads the new on-disk envelope, then writes
            # its normal logical ledger. No candidate, date or permission resets.
            prior=read(root/'state/discovery.json')
            c.write_atomic(root/'state/discovery.json',discovery_storage.encode(prior))
            empty,ok=self.run_sources(root,'empty');self.assertTrue(ok);self.assertEqual(empty['new_newsroom_items'],0)
            self.assertEqual(read(root/'state/discovery.json'),prior)
            healthy,ok=self.run_sources(root,'healthy');self.assertTrue(ok)
            duplicate,ok=self.run_sources(root,'healthy');self.assertTrue(ok);self.assertEqual(duplicate['new_newsroom_items'],0)
            self.assertEqual(len({a['id'] for a in read(root/'state/archive.json')['articles']}),len(read(root/'state/archive.json')['articles']))

    def test_briefing_or_publication_gate_failure_is_not_success(self):
        from src.pipeline.collect import collect
        for key in ('briefing','publication_visibility'):
            data={'publication_result':'ok','discovery_status':'ok',key:{'status':'failed'}}
            with patch('src.engine.execute',return_value=data):self.assertFalse(collect('news',Path('/isolated'),False,90))


class DiagnosticTests(unittest.TestCase):
    def test_summary_never_echoes_errors_urls_or_unknown_counts(self):
        result={'phase':'https://PRIVATE','requested':'SECRET','error':'https://PRIVATE?key=SECRET',
                'error_code':'SECRET','data_commit':'https://PRIVATE','counts':{'secret':'PRIVATE'},
                'engines':{'news':{'status':'failed','error':'https://PRIVATE','error_kind':'SECRET'}}}
        rendered=report.render(result,'skipped');self.assertNotIn('PRIVATE',rendered);self.assertNotIn('SECRET',rendered)

    def test_storage_and_deployment_statuses_remain_independent(self):
        data={'phase':'ready_for_pages','ready':True,'data_committed':True,'storage_status':'committed',
              'data_commit':'a'*40,'collection_ok':True,'engines':{'news':{'status':'partial'}}}
        for deployment in ('success','failure','skipped'):
            done=report.finalize(data,deployment);self.assertTrue(done['data_committed']);self.assertEqual(done['deployment_status'],deployment)
        self.assertIsNone(report.finalize(data,'failure')['previous_public_preserved'])

    def test_failure_classification_rejects_sensitive_exception_text(self):
        result={'phase':'validate','engines':{}};diagnostics.failure(result,ValueError('https://SECRET.invalid?token=PRIVATE'))
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertNotIn('SECRET',json.dumps(result))


if __name__=='__main__':unittest.main()
