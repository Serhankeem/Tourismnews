"""Synthetic shadow snapshots only. Actual operating replay is kept outside Git."""
import copy
import hashlib
import tempfile
from pathlib import Path
import unittest

from src.macro import weather_diagnostic as engine, weather_shadow as shadow
from test_weather_diagnostic import fixture, NOW


class ShadowTests(unittest.TestCase):
    def setUp(self):
        self.config, self.archive, self.policy = fixture()

    def diagnose(self, target='2026-09'):
        return engine.diagnose(self.config,self.archive,self.policy,target,NOW,NOW)

    def save(self, path, previous=None):
        return shadow.save_bundle(path,self.config,self.archive,self.policy,self.diagnose(),{}, {},previous)

    def test_subdisplay_positive_and_negative_direction(self):
        obs = self.archive['indicators']['kto_inbound']['observations']
        obs['2025-09']['value'] = 10**12
        for delta, expected in ((1,'increase'),(-1,'decrease'),(0,'unchanged')):
            obs['2026-09']['value'] = 10**12+delta
            result = self.diagnose()
            evidence = next(e for e in result['evidence'] if e['indicator']=='kto_inbound')
            self.assertEqual(evidence['direction'],expected)
            text = shadow.briefing(result)['evidence'][0]['text']
            self.assertNotIn('-0.00%',text)
            if delta:self.assertIn('원값의 변화 방향',text)

    def test_half_up_display_boundary(self):
        self.assertEqual(shadow.display_rate('1.005000'),'1.01%')
        self.assertEqual(shadow.display_rate('-1.005000'),'-1.01%')
        self.assertEqual(shadow.display_rate(None),'비교 불가')

    def test_retrospective_69_months_uses_current_cutoff(self):
        report = shadow.retrospective(self.config,self.archive,self.policy,'2021-01','2026-09',NOW,NOW)
        self.assertEqual(report['ready_months'],69)
        self.assertEqual(report['verified_nonnull_comparisons'],250)
        self.assertFalse(report['historic_as_of_verified'])
        self.assertTrue(all(r['mode']=='retrospective_current_vintage' for r in report['results']))

    def test_retrospective_approval_boundary_is_withheld(self):
        report = shadow.retrospective(self.config,self.archive,self.policy,'2026-09','2026-10',NOW,NOW)
        self.assertEqual(report['ready_months'],1)
        self.assertFalse(report['results'][-1]['target_ready'])

    def test_scenarios_are_labeled_copies_and_preserve_input(self):
        before = copy.deepcopy(self.archive)
        result = shadow.sensitivity(self.config,self.archive,self.policy,'2026-09',NOW,NOW)
        self.assertEqual(len(result['cases']),7)
        self.assertTrue(all(c['passed'] and c['scenario_kind']=='counterfactual_copy' for c in result['cases']))
        self.assertEqual(self.archive,before)

    def test_revised_comparison_baseline_is_flagged(self):
        self.archive['indicators']['kto_inbound']['observations']['2025-09']['revision_status']='revised'
        self.assertIn('revised_comparison_baseline',self.diagnose()['axes']['kto_inbound']['warnings'])

    def test_briefing_is_private_two_evidence_and_traceable(self):
        draft = shadow.briefing(self.diagnose())
        self.assertEqual(len(draft['evidence']),2)
        self.assertEqual(draft['overall_status'],'withheld')
        self.assertFalse(draft['publication_approved'])
        self.assertEqual(draft['editorial_review']['status'],'pending')
        for row in draft['evidence']:
            self.assertIn('2025-09',row['text']);self.assertIn('2026-08',row['text'])
            self.assertNotIn('. 2025-09',row['text'])
            self.assertTrue(row['source']['file_sha256'])
        self.assertIn('산업 활동',shadow.markdown(draft))

    def test_unready_or_public_result_cannot_generate_briefing(self):
        with self.assertRaises(ValueError):shadow.briefing(self.diagnose('2026-10'))
        result=self.diagnose();result['publication_approved']=True
        with self.assertRaises(ValueError):shadow.briefing(result)

    def test_bundle_hashes_permissions_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'issue';self.save(path)
            self.assertFalse(shadow.verify_bundle(path)['publication_approved'])
            self.assertEqual(path.stat().st_mode & 0o777,0o700)
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in path.rglob('*') if p.is_file()))
            original=(path/'manifest.json').read_bytes()
            with self.assertRaises(FileExistsError):self.save(path)
            self.assertEqual(original,(path/'manifest.json').read_bytes())

    def test_tamper_or_extra_file_rejected(self):
        for kind in ('tamper','extra'):
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'issue';self.save(path)
                (path/('briefing-private.md' if kind=='tamper' else 'unexpected')).write_text('changed')
                with self.assertRaises(ValueError):shadow.verify_bundle(path)

    def test_revision_links_previous_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            before=Path(tmp)/'v1';after=Path(tmp)/'v2';self.save(before)
            previous_bytes=(before/'manifest.json').read_bytes()
            obs=self.archive['indicators']['kto_inbound']['observations']['2026-09']
            obs['value']+=1;obs['revision_status']='revised'
            manifest=self.save(after,before)
            self.assertEqual(manifest['revision_history'][0]['previous_manifest_sha256'],hashlib.sha256(previous_bytes).hexdigest())
            self.assertEqual(previous_bytes,(before/'manifest.json').read_bytes())
            self.assertNotEqual(manifest['input_hashes'],shadow.verify_bundle(before)['input_hashes'])

    def test_mismatched_snapshot_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=self.diagnose();result['input_hashes']['archive']='0'*64
            path=Path(tmp)/'bad'
            with self.assertRaises(ValueError):shadow.save_bundle(path,self.config,self.archive,self.policy,result,{}, {})
            self.assertFalse(path.exists())

    def test_repository_output_is_forbidden(self):
        with self.assertRaises(ValueError):self.save(engine.ROOT/'forbidden-step13')

    def test_invalid_calendar_order(self):
        with self.assertRaises(ValueError):list(shadow.months('2026-10','2021-01'))

    def test_historical_scenarios_skip_unavailable_prior_year(self):
        report=shadow.retrospective(self.config,self.archive,self.policy,'2021-12','2022-02',NOW,NOW)
        result=shadow.historical_sensitivity(self.config,self.archive,self.policy,report,NOW,NOW)
        self.assertEqual(result['tested_months'],2)
        self.assertEqual(result['scenario_count'],14)
        self.assertEqual(result['skipped'][0]['period'],'2021-12')

    def test_revision_cannot_write_inside_previous_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            before=Path(tmp)/'v1';self.save(before)
            with self.assertRaises(ValueError):self.save(before/'nested',before)
            shadow.verify_bundle(before)


if __name__ == '__main__':unittest.main()
