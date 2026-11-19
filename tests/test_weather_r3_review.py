"""Synthetic manuscripts only. No real editorial/publication approval is issued."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import market_weather_preview as preview
from src.macro import weather_publication as gate
from test_weather_publication import setup,NOW

COVER='\n\n'.join(['한국 관광의 날씨는? / MONTHLY REPORT','2026년 11월 Market Weather',
 '2026년 9월 검증 자료 기반','2026.11 · VOL. 01','발행: 2026년 11월\n통계 기준: 2026년 9월',
 '합성 편집 검토 리드입니다. 종합 판정은 보류합니다.'])


class R3DraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.ctx,self.pub,self.trust,self.config,self.policy=setup()
        article=gate.parse_manuscript(self.ctx.manuscript,self.ctx.diagnostic)
        marker='## '+article['sections'][0]['heading']+'\n\n'
        self.raw=self.ctx.manuscript.decode().replace('# '+article['title'],'# 2026년 11월 관광시장 진단',1).replace(marker,marker+COVER+'\n\n',1).encode()
        (self.root/'draft.md').write_bytes(self.raw);(self.root/'manifest.json').write_bytes(self.ctx.bundle_manifest)
        self.doc=dict(version=1,revision='r3',reference_period='2026-09',issue_month='2026-11',actual_publication_date=None,
                      manuscript_file='draft.md',manuscript_sha256=gate.sha(self.raw),parent_manuscript_sha256=gate.sha(self.ctx.manuscript),
                      source_bundle_manifest_sha256=gate.sha(self.ctx.bundle_manifest),editorial_status='pending',publication_status='not_requested')
        self.path=self.root/'review.json';self.write();self.payload={'state':'private_review','publication_approved':False,'diagnostic':self.ctx.diagnostic}

    def write(self):self.path.write_text(json.dumps(self.doc))

    def load(self):return preview.load_pending(copy.deepcopy(self.payload),self.path,self.root)

    def test_pending_preview_preserves_all_body_and_does_not_approve(self):
        result=self.load();old=gate.parse_manuscript(self.ctx.manuscript,self.ctx.diagnostic)
        article=result['pending_editorial']['article'];self.assertEqual(article['sections'][1:],old['sections'][1:])
        self.assertEqual(article['sections'][0]['markdown'],COVER+'\n\n'+old['sections'][0]['markdown'])
        self.assertFalse(result['publication_approved']);self.assertEqual(result['pending_editorial']['editorial_status'],'pending')
        self.assertIsNone(result['pending_editorial']['actual_publication_date'])
        self.assertNotIn('editorial_private',result)

    def test_r2_editorial_receipt_cannot_approve_changed_r3(self):
        ctx=replace(self.ctx,manuscript=self.raw)
        with patch.object(gate,'_projection') as projection:
            with self.assertRaisesRegex(gate.GateError,'manuscript_hash_mismatch'):
                gate.public_json(ctx,self.pub,self.trust,NOW,self.config,self.policy)
            projection.assert_not_called()

    def test_claimed_approval_or_publication_date_rejected(self):
        for field,value in [('editorial_status','approved'),('publication_status','approved'),('actual_publication_date','2026-11-19')]:
            original=self.doc[field];self.doc[field]=value;self.write()
            with self.assertRaisesRegex(ValueError,'pending_draft_only'):self.load()
            self.doc[field]=original

    def test_manuscript_snapshot_or_period_change_rejected(self):
        for field,value in [('manuscript_sha256','0'*64),('source_bundle_manifest_sha256','0'*64),('reference_period','2026-10')]:
            original=self.doc[field];self.doc[field]=value;self.write()
            with self.assertRaises(ValueError):self.load()
            self.doc[field]=original

    def test_modified_numbers_and_source_links_fail_unchanged_gate_parser(self):
        for old,new in [('합성 현재값은 **100명**','합성 현재값은 **101명**'),('https://datalab.visitkorea.or.kr','https://bad.invalid')]:
            changed=self.raw.replace(old.encode(),new.encode());self.assertNotEqual(changed,self.raw)
            (self.root/'draft.md').write_bytes(changed);self.doc['manuscript_sha256']=gate.sha(changed);self.write()
            with self.assertRaises(ValueError):self.load()

    def test_path_escape_and_unknown_fields_rejected(self):
        self.doc['manuscript_file']='../outside.md';self.write()
        with self.assertRaises(ValueError):self.load()
        self.doc['manuscript_file']='draft.md';self.doc['trust_policy']='fake';self.write()
        with self.assertRaises(ValueError):self.load()

    def test_issue_metadata_must_match_cover_not_only_manifest(self):
        changed=self.raw.replace('2026년 11월 Market Weather'.encode(),'2026년 12월 Market Weather'.encode())
        (self.root/'draft.md').write_bytes(changed);self.doc['manuscript_sha256']=gate.sha(changed);self.write()
        with self.assertRaisesRegex(ValueError,'draft_cover_mismatch'):self.load()

    def test_issue_label_revision_preserves_legacy_draft_and_gate_compatibility(self):
        legacy=self.load()['pending_editorial']['article']
        updated=self.raw.replace('발행: 2026년 11월'.encode(),'발행호: 2026년 11월'.encode())
        (self.root/'draft.md').write_bytes(updated);self.doc['manuscript_sha256']=gate.sha(updated);self.write()
        candidate=self.load()['pending_editorial']['article']
        self.assertEqual(candidate['sections'][1:],legacy['sections'][1:])
        self.assertEqual(candidate['sections'][0]['markdown'].replace('발행호:','발행:',1),legacy['sections'][0]['markdown'])
        self.assertFalse(self.load()['publication_approved']);self.assertIsNone(self.load()['pending_editorial']['actual_publication_date'])
