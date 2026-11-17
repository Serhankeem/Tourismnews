"""All positive publication approvals and figures here are SYNTHETIC, in memory.

No real approval is issued, no public file is written, and no network is used.
"""
import copy
from dataclasses import replace
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.macro import weather_publication as g,weather_diagnostic as e
from test_weather_diagnostic import fixture

NOW=dt.datetime(2026,11,17,6,tzinfo=dt.timezone.utc)


def encoded(doc):return (json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode()


def pin(raw,role):
    doc=g.decode(raw);row=doc[role]
    return g.Anchor(g.sha(raw),row['approver_github_login'],row['approved_at'])


def setup():
    config,archive,policy=fixture()
    analysis_time=NOW-dt.timedelta(hours=2)
    diag=e.diagnose(config,archive,policy,'2026-09',analysis_time,analysis_time)
    sections=['## 합성 부분 모니터\n\n합성 자료의 두 지표만 비교합니다.\n\n계절성을 제거하지 않은 비교입니다.']
    urls=[]
    for n,key in enumerate(e.CORE,1):
        row=diag['axes'][key];c=row['comparisons'];unit='명' if n==1 else '달러'
        word=lambda raw:'증가' if float(raw)>0 else '감소' if float(raw)<0 else '동일'
        display=lambda raw:format(abs(g.Decimal(raw)).quantize(g.Decimal('.01'),rounding=g.ROUND_HALF_UP),'.2f')
        sections.append(f"## {n:02}. 합성 지표\n\n합성 현재값은 **{row['value']:,}{unit}**입니다.\n\n2025년 9월의 {row['comparison_observations']['2025-09']['value']:,}{unit} 대비 {display(c['yoy_pct'])}% {word(c['yoy_pct'])}; 2026년 8월의 {row['comparison_observations']['2026-08']['value']:,}{unit} 대비 {display(c['mom_pct'])}% {word(c['mom_pct'])}.\n\n합성 통계의 정의와 모집단은 구분합니다.")
        urls.append(row['provenance']['source_url'])
    sections += ['## 합성 해석 범위\n\n종합 판정은 보류합니다. 산업 활동이 없습니다.',
                 '## 합성 출처\n\n'+ '\n'.join(f'- [합성 자료 제공처]({u})' for u in urls)+'\n\nretrospective_current_vintage. 확정성과 공표일은 미확인입니다.\n\n*합성 테스트 초안*']
    manuscript=('# 합성 월간 원고\n\n**합성 부분 모니터**\n\n자료 기준월: 2026년 9월\n발행 상태: 편집 검토 중 · 미발행\n\n'+'\n\n'.join(sections)+'\n').encode()
    bundle=encoded({'files':{'diagnostic-private.json':g.sha(encoded(diag))}})
    editorial=encoded(dict(record_type='user_confirmed_editorial_approval_with_identity_and_basis_time',
                          content_id='market-weather-2026-09',reference_period='2026-09',editorial_revision='r2',manuscript_sha256=g.sha(manuscript),
                          editorial=dict(status='approved',approver_github_login='synthetic_editor',approved_at=(NOW-dt.timedelta(hours=1)).isoformat(),approved_content_sha256=g.sha(manuscript),scope='exact_manuscript_only'),
                          input_snapshot=dict(reference_period='2026-09',source_bundle_manifest_sha256=g.sha(bundle),canonical_json_input_hashes=diag['input_hashes'],methodology_version=e.VERSION,input_cutoff=diag['input_cutoff'],original_analysis_at=diag['analysis_at'])))
    ctx=g.Context(manuscript,editorial,bundle,diag,config,archive,policy)
    publication=encoded(dict(record_type='publication_approval',content_id='market-weather-2026-09',reference_period='2026-09',editorial_revision='r2',manuscript_sha256=g.sha(manuscript),
                            publication=dict(status='approved',approver_github_login='synthetic_publisher',approved_at=(NOW-dt.timedelta(minutes=10)).isoformat(),scope='website_content',public_revision=1,
                                             editorial_record_sha256=g.sha(editorial),archive_sha256=diag['input_hashes']['archive'],contract_sha256=g.sha(g.SCHEMA.read_bytes()),implementation_sha256=g.sha(Path(g.__file__).read_bytes()),
                                             valid_from=(NOW-dt.timedelta(minutes=10)).isoformat(),valid_until=(NOW+dt.timedelta(days=1)).isoformat(),release_at=NOW.isoformat())))
    trust=g.Trust((pin(editorial,'editorial'),),(pin(publication,'publication'),))
    return ctx,publication,trust,config,policy


class PublicationGateTests(unittest.TestCase):
    def setUp(self):self.ctx,self.pub,self.trust,self.config,self.policy=setup()

    def audit(self,pub=None,trust=None,ctx=None,now=NOW):
        return g.audit(ctx or self.ctx,pub,self.trust if trust is None else trust,now,self.config,self.policy)

    def export(self,pub=None,trust=None,ctx=None,now=NOW):
        return g.public_json(ctx or self.ctx,pub,self.trust if trust is None else trust,now,self.config,self.policy)

    def alter_publication(self,change):
        doc=g.decode(self.pub);change(doc);raw=encoded(doc)
        return raw,replace(self.trust,publication=(pin(raw,'publication'),))

    def test_no_publication_no_projection_or_serialization(self):
        report=self.audit();self.assertTrue(report['editorial_verified']);self.assertTrue(report['manuscript_compatible'])
        self.assertEqual(report['reason'],'publication_approval_missing')
        with patch.object(g,'_projection') as projection:
            with self.assertRaisesRegex(g.GateError,'publication_approval_missing'):self.export()
            projection.assert_not_called()

    def test_both_independent_synthetic_approvals_allow_only_memory_payload(self):
        output=g.decode(self.export(self.pub));self.assertEqual(output['schema_version'],2)
        self.assertEqual(set(output['metrics']),set(e.CORE));self.assertEqual(output['overall_state'],'withheld')
        self.assertEqual(len(output['article']['sections']),5);self.assertEqual(output['editorial_revision'],'r2')
        self.assertEqual(output['revision'],1);self.assertIsNone(output['correction'])
        self.assertNotIn('input_hashes',output);self.assertNotIn('editorial',output);self.assertNotIn('publication_approved',output)

    def test_unpinned_approved_strings_do_not_authorize(self):
        self.assertEqual(self.audit(self.pub,g.Trust())['reason'],'editorial_approval_untrusted')
        self.assertEqual(self.audit(self.pub,replace(self.trust,publication=()))['reason'],'publication_approval_untrusted')

    def test_editorial_cannot_be_reused_as_publication(self):
        with self.assertRaises(g.GateError):self.export(self.ctx.editorial_record)

    def test_revoked_editorial_and_publication(self):
        for role in ('editorial','publication'):
            trust=replace(self.trust,**{role:(replace(getattr(self.trust,role)[0],revoked=True),)})
            with self.assertRaisesRegex(g.GateError,role+'_approval_revoked'):self.export(self.pub,trust)

    def test_wrong_anchor_identity_or_time(self):
        trust=replace(self.trust,editorial=(replace(self.trust.editorial[0],approver='other'),))
        self.assertEqual(self.audit(self.pub,trust)['reason'],'editorial_identity_or_time_mismatch')

    def test_changed_manuscript_invalidates_approval(self):
        with self.assertRaisesRegex(g.GateError,'manuscript_hash_mismatch'):self.export(self.pub,ctx=replace(self.ctx,manuscript=self.ctx.manuscript+b'changed'))

    def test_current_policy_collection_or_publication_revocation(self):
        for action in ('collection','publication'):
            config=copy.deepcopy(self.config)
            next(s for s in config['sources'] if s['id']=='tourgo_tourism_balance')['approval'][action]['approved']=False
            r=g.audit(self.ctx,self.pub,self.trust,NOW,config,self.policy)
            self.assertEqual(r['reason'],'statistics_not_currently_eligible')

    def test_period_outside_existing_tourgo_scope(self):
        config=copy.deepcopy(self.config)
        next(s for s in config['sources'] if s['id']=='tourgo_tourism_balance')['approval']['publication']['period_through']='2026-08'
        self.assertEqual(g.audit(self.ctx,self.pub,self.trust,NOW,config,self.policy)['reason'],'statistics_not_currently_eligible')

    def test_current_terms_conditions_still_required(self):
        config=copy.deepcopy(self.config)
        next(s for s in config['sources'] if s['id']=='tourgo_tourism_balance')['activation_conditions']['attribution']=False
        self.assertEqual(g.audit(self.ctx,self.pub,self.trust,NOW,config,self.policy)['reason'],'statistics_not_currently_eligible')

    def test_changed_statistics_and_diagnostic_are_rejected(self):
        changed=copy.deepcopy(self.ctx.archive);changed['indicators']['kto_inbound']['observations']['2026-09']['value']+=1
        self.assertEqual(self.audit(self.pub,ctx=replace(self.ctx,archive=changed))['reason'],'snapshot_input_mismatch')
        diag=copy.deepcopy(self.ctx.diagnostic);diag['axes']['kto_inbound']['value']+=1
        self.assertEqual(self.audit(self.pub,ctx=replace(self.ctx,diagnostic=diag))['reason'],'diagnostic_hash_mismatch')

    def test_publication_cannot_authorize_another_month_or_revision(self):
        for field,value in (('reference_period','2026-10'),('editorial_revision','r3'),('manuscript_sha256','a'*64)):
            raw,trust=self.alter_publication(lambda d:d.update({field:value}))
            self.assertEqual(self.audit(raw,trust)['reason'],'publication_scope_mismatch')

    def test_separate_editorial_receipt_binding_required(self):
        raw,trust=self.alter_publication(lambda d:d['publication'].update(editorial_record_sha256='a'*64))
        self.assertEqual(self.audit(raw,trust)['reason'],'editorial_receipt_binding_mismatch')

    def test_archive_binding_required(self):
        raw,trust=self.alter_publication(lambda d:d['publication'].update(archive_sha256='a'*64))
        self.assertEqual(self.audit(raw,trust)['reason'],'publication_snapshot_mismatch')

    def test_contract_and_implementation_binding_required(self):
        for key in ('contract_sha256','implementation_sha256'):
            raw,trust=self.alter_publication(lambda d:d['publication'].update({key:'a'*64}))
            self.assertEqual(self.audit(raw,trust)['reason'],'projection_contract_mismatch')

    def test_publication_expired_or_not_yet_valid(self):
        for field,stamp in (('valid_until',NOW-dt.timedelta(seconds=1)),('valid_from',NOW+dt.timedelta(days=1))):
            raw,trust=self.alter_publication(lambda d:d['publication'].update({field:stamp.isoformat()}))
            self.assertEqual(self.audit(raw,trust)['reason'],'publication_expired_or_not_yet_valid')

    def test_future_approval_rejected(self):
        raw,trust=self.alter_publication(lambda d:d['publication'].update(approved_at=(NOW+dt.timedelta(days=1)).isoformat()))
        self.assertEqual(self.audit(raw,trust)['reason'],'publication_approval_in_future')

    def test_missing_timezone_not_accepted(self):
        raw,trust=self.alter_publication(lambda d:d['publication'].update(valid_until='2026-11-18T00:00:00'))
        self.assertFalse(self.audit(raw,trust)['publication_verified'])

    def test_no_new_public_revision_or_generic_scope(self):
        for key,value in (('public_revision',2),('scope','all_content')):
            raw,trust=self.alter_publication(lambda d:d['publication'].update({key:value}))
            self.assertEqual(self.audit(raw,trust)['reason'],'publication_release_scope_invalid')

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):g.decode(b'{"approved":true,"approved":false}')

    def test_safe_report_does_not_contain_article_or_exception_details(self):
        report=self.audit(self.pub);self.assertTrue(report['publication_verified'])
        self.assertNotIn('합성',json.dumps(report,ensure_ascii=False));self.assertFalse(report['public_json_generated'])

    def test_no_mutation_of_input(self):
        before=copy.deepcopy(self.ctx);self.export(self.pub);self.assertEqual(self.ctx,before)

    def test_trust_file_must_be_readonly_and_role_separated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'trust.json';doc={'version':1,'editorial':[self.trust.editorial[0].__dict__],'publication':[]}
            path.write_bytes(encoded(doc))
            with self.assertRaisesRegex(g.GateError,'readonly_trust_required'):g.trust_file(path)
            path.chmod(0o400);trust=g.trust_file(path)
            self.assertEqual(len(trust.editorial),1);self.assertEqual(trust.publication,())

    def test_trust_revocation_checked_at_each_call(self):
        self.export(self.pub)
        with self.assertRaises(g.GateError):self.export(self.pub,replace(self.trust,publication=()))

    def test_scope_expansion_is_not_implicitly_accepted(self):
        config=copy.deepcopy(self.config)
        next(s for s in config['sources'] if s['id']=='tourgo_tourism_balance')['approval']['publication']['period_through']='2026-10'
        self.assertEqual(g.audit(self.ctx,self.pub,self.trust,NOW,config,self.policy)['reason'],'tourgo_scope_expansion_forbidden')

    def test_flag_only_editorial_metadata_cannot_grant_publication(self):
        record=g.decode(self.ctx.editorial_record);record['publication']={'status':'approved'}
        raw=encoded(record);ctx=replace(self.ctx,editorial_record=raw)
        trust=replace(self.trust,editorial=(pin(raw,'editorial'),))
        self.assertEqual(self.audit(None,trust,ctx)['reason'],'publication_approval_missing')

    def test_context_is_snapshotted_before_projection(self):
        original=g._projection;before=self.ctx.diagnostic['axes']['kto_inbound']['value']
        def change_outer(*args):
            self.ctx.diagnostic['axes']['kto_inbound']['value']=before+999
            return original(*args)
        with patch.object(g,'_projection',side_effect=change_outer):output=g.decode(self.export(self.pub))
        self.assertEqual(output['metrics']['kto_inbound']['value'],before)

    def test_no_silent_article_section_loss_or_html(self):
        for raw in (self.ctx.manuscript.replace(b'## 02.',b'02.'),self.ctx.manuscript+b'<script>bad</script>'):
            with self.assertRaises(g.GateError):g.parse_manuscript(raw,self.ctx.diagnostic)

    def test_publication_must_follow_editorial_approval(self):
        raw,trust=self.alter_publication(lambda d:d['publication'].update(approved_at=(NOW-dt.timedelta(hours=2)).isoformat()))
        self.assertEqual(self.audit(raw,trust)['reason'],'publication_precedes_editorial')

    def test_full_approved_prose_is_preserved(self):
        article=g.parse_manuscript(self.ctx.manuscript,self.ctx.diagnostic)
        output=g.decode(self.export(self.pub))
        self.assertEqual(output['article'],{'subtitle':article['subtitle'],'sections':article['sections']})
        self.assertEqual(output['summary'],article['sections'][0]['markdown'])
        self.assertEqual(output['evidence'][0]['text'],article['sections'][1]['markdown'])
        self.assertNotIn('발행 상태: 편집 검토 중',json.dumps(output,ensure_ascii=False))

    def test_monetization_change_blocks_existing_editorial_approval(self):
        policy=copy.deepcopy(self.policy);policy['ads_enabled']=True
        self.assertEqual(g.audit(self.ctx,self.pub,self.trust,NOW,self.config,policy)['reason'],'statistics_not_currently_eligible')

    def test_untrusted_receipt_does_not_follow_embedded_file_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'receipt.json';p.write_bytes(self.ctx.editorial_record)
            with patch.object(g.shadow,'verify_bundle') as verify:
                with self.assertRaisesRegex(g.GateError,'editorial_approval_untrusted'):g.load_context(p,g.Trust(),NOW)
                verify.assert_not_called()

    def test_public_timestamp_must_conform_to_contract(self):
        raw,trust=self.alter_publication(lambda d:d['publication'].update(release_at=NOW.isoformat().replace('T',' ')))
        self.assertEqual(self.audit(raw,trust)['reason'],'public_timestamp_format_invalid')


if __name__=='__main__':unittest.main()
