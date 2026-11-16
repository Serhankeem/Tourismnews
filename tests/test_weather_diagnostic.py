"""Synthetic values in copies of registered provenance contracts; no network."""
import copy
import datetime as dt
import json
import unittest
from pathlib import Path
from src.macro import weather_diagnostic as w,tourgo
from test_tourgo_readiness import synthetic69

NOW=dt.datetime(2026,11,16,tzinfo=dt.timezone.utc)

def fixture():
 c=w.read(w.ROOT/'macro_sources.json');a=w.read(w.ROOT/'collector_state/macro_archive.json');policy=w.read(w.ROOT/'operating_policy.json')
 source=next(s for s in c['sources'] if s['id']==tourgo.SOURCE);items=[i for i in c['indicators'] if i['id'] in tourgo.IDS]
 snap=tourgo.fetch(source,items,synthetic69(),NOW)
 for i in items:a['indicators'][i['id']]=dict(unit=i['unit'],definition=i['definition'],observations=snap['records'][i['id']],revisions=[])
 for key,s in a['indicators'].items():
  if key.startswith('kto_inbound') or key=='kto_outbound':
   for o in s['observations'].values():o['value']=100;o['file_sha256']='a'*64
 return c,a,policy

class DiagnosticTests(unittest.TestCase):
 def setUp(self):self.c,self.a,self.p=fixture()
 def runit(self,target='2026-09',cutoff=NOW):return w.diagnose(self.c,self.a,self.p,target,cutoff,NOW)
 def test_normal_private_partial_and_exact_comparisons(self):
  r=self.runit();self.assertEqual(r['status'],'partial_monitor');self.assertFalse(r['publication_approved']);self.assertEqual(r['overall_status'],'withheld');self.assertEqual(r['axes']['kto_inbound']['comparisons']['yoy_pct'],'0.000000');self.assertLessEqual(len(r['evidence']),3)
 def test_no_mutation_and_no_new_inputs(self):
  for i in self.c['indicators']:
   if i['id'].startswith('market_'):i['enabled']=True
  before=copy.deepcopy(self.a);r=self.runit();self.assertEqual(before,self.a);self.assertEqual(set(r['axes']),set(w.CORE));self.assertFalse(any(k.startswith('market_') for k in r['supporting']))
 def test_target_outside_approval_delays_not_fill(self):
  r=self.runit('2026-10');self.assertFalse(r['target_ready']);self.assertEqual(r['aligned_period'],'2026-09');self.assertEqual(r['status'],'withheld')
 def test_missing_prior_and_zero_baseline(self):
  obs=self.a['indicators']['kto_inbound']['observations'];obs.pop('2025-09');r=self.runit();self.assertIsNone(r['axes']['kto_inbound']['comparisons']['yoy_pct'])
  obs['2025-09']=copy.deepcopy(obs['2025-08']);obs['2025-09']['value']=0;self.assertIsNone(self.runit()['axes']['kto_inbound']['comparisons']['yoy_pct'])
 def test_period_mismatch_aligns_but_not_target_ready(self):
  for k in tourgo.IDS:self.a['indicators'][k]['observations'].pop('2026-09')
  r=self.runit();self.assertEqual(r['aligned_period'],'2026-08');self.assertFalse(r['target_ready'])
 def test_unit_definition_and_provenance_fail_closed(self):
  for field,value in [('unit','천명'),('definition','changed')]:
   c,a,p=fixture();a['indicators']['kto_inbound'][field]=value;r=w.diagnose(c,a,p,'2026-09',NOW,NOW);self.assertEqual(r['status'],'withheld')
 def test_expired_or_revoked_collection_or_publication(self):
  for action in ('collection','publication'):
   c,a,p=fixture();next(s for s in c['sources'] if s['id']==tourgo.SOURCE)['approval'][action]['approved']=False
   self.assertEqual(w.diagnose(c,a,p,'2026-09',NOW,NOW)['status'],'withheld')
 def test_future_vintage_is_not_backfilled_as_asof(self):
  r=self.runit(cutoff=dt.datetime(2025,1,1,tzinfo=dt.timezone.utc));self.assertEqual(r['status'],'withheld');self.assertEqual(r['mode'],'retrospective_current_vintage')
 def test_revisions_and_pandemic_context(self):
  o=self.a['indicators']['kto_inbound']['observations']['2026-09'];o['revision_status']='revised';o['value']=100000000
  r=self.runit();self.assertIn('revised_observation',r['axes']['kto_inbound']['warnings']);self.assertNotIn('score',r)
  self.assertIn('pandemic_baseline_context_required',self.runit('2022-09')['axes']['kto_inbound']['warnings'])
 def test_duplicate_json_and_bad_shapes(self):
  with self.assertRaises(ValueError):json.loads('{"x":1,"x":2}',object_pairs_hook=w.unique)
  self.a['indicators']['kto_inbound']['observations']=[];self.assertEqual(self.runit()['status'],'withheld')
 def test_definition_drift_in_config_and_archive_cannot_bypass_contract(self):
  next(i for i in self.c['indicators'] if i['id']=='kto_inbound')['definition']='new';self.a['indicators']['kto_inbound']['definition']='new';self.assertEqual(self.runit()['status'],'withheld')
 def test_conflicting_directions_remain_partial_not_overall_judgment(self):
  obs=self.a['indicators']['kto_inbound']['observations'];obs['2026-09']['value']=1
  r=self.runit();self.assertEqual(r['flow_relation'],'mixed');self.assertEqual(r['overall_status'],'withheld');self.assertFalse(r['publication_approved'])
 def test_revision_preserves_previous_result_and_archive(self):
  before=self.runit();old=copy.deepcopy(self.a);obs=self.a['indicators']['kto_inbound']['observations'];obs['2026-09']['value']=200;obs['2026-09']['revision_status']='revised';obs['2026-09']['file_sha256']='b'*64
  after=self.runit();self.assertEqual(before['axes']['kto_inbound']['value'],100);self.assertEqual(after['axes']['kto_inbound']['value'],200);self.assertNotEqual(before['input_hashes']['archive'],after['input_hashes']['archive']);self.assertEqual(old['indicators']['kto_inbound']['observations']['2026-09']['value'],100)
 def test_future_publication_and_unofficial_provenance_are_excluded(self):
  self.a['indicators']['kto_inbound']['observations']['2026-09']['release_published_at']='2026-11-17T00:00:00+00:00'
  self.assertFalse(self.runit()['target_ready'])
  self.a['indicators']['kto_inbound']['observations']['2026-08']['source_url']='https://example.org/unofficial'
  self.assertEqual(self.runit()['status'],'withheld')
 def test_future_analysis_cutoff_is_rejected(self):
  with self.assertRaises(ValueError):self.runit(cutoff=NOW+dt.timedelta(days=1))

if __name__=='__main__':unittest.main()
