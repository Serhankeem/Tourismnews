"""Synthetic collection/model boundaries, deliberately separate from real runs."""
import copy
import datetime as dt
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import re
import zipfile
from src.macro import kto
from tools.collect_kto_research import capture, external_new, ROOT
from tools.compare_travel_markets import NODE, composition, verify_live_kto, verify_reference
from tools.replay_model_signal import add
from test_macro import make_xlsx
from test_kto_release_discovery import pages, BOARD, html, NOW

CONFIG = json.loads((ROOT/'macro_sources.json').read_text())
ITEMS = [i for i in CONFIG['indicators'] if i['source_id'] == 'kto_monthly_statistics' and i['enabled']]


def column(n):
    out = ''
    while n:
        n, digit = divmod(n-1, 26)
        out = chr(65+digit)+out
    return out


def collection_fixture():
    sheets = {'입국': {'A1': '［입국］', 'A3': 'Country', 'A4': 'G.TOTAL'},
              '출국': {'A1': '［출국］', 'A3': 'Destination', 'A4': 'G.TOTAL'}}
    values = {}
    for index, item in enumerate(ITEMS):
        row = 4 if not item.get('country') else 10+index
        if item.get('country'):
            sheets['입국']['B'+str(row)] = item['country']
        values[item['id']] = {}
        for n in range(69):
            p = add('2021-01', n)
            c = column(3+n)
            sheets[item['sheet']][c+'3'] = p[:4]+'.'+str(int(p[-2:]))+'월'
            v = (100000 if item['id'] == 'kto_inbound' else 200000 if item['id'] == 'kto_outbound' else 100)+n
            sheets[item['sheet']][c+str(row)] = v
            values[item['id']][p] = v
    check = {'성별 입국(9월)': {'A1': '성별국적별입국 (2026년 9월)', 'C3': '인원(명)'},
             '성별 입국(1~9월)': {'A1': '성별국적별입국 (2026년1~9월)'},
             '성별 출국': {'A1': '성별출국', 'B3': '인원(명)', 'A13': '9월'}}
    for index, item in enumerate(ITEMS):
        vs = values[item['id']]
        if item['sheet'] == '출국':
            check['성별 출국'].update(B13=vs['2026-09'], C13=vs['2025-09'],
                B4=sum(vs[f'2026-{n:02d}'] for n in range(1,10)),
                C4=sum(vs[f'2025-{n:02d}'] for n in range(1,10)))
            continue
        row = 4 if not item.get('country') else 10+index
        for key in ['성별 입국(9월)', '성별 입국(1~9월)']:
            if item.get('country'):
                check[key]['B'+str(row)] = item['country']
        check['성별 입국(9월)'].update({f'C{row}': vs['2026-09'], f'D{row}': vs['2025-09']})
        check['성별 입국(1~9월)'].update({f'C{row}': sum(vs[f'2026-{n:02d}'] for n in range(1,10)),
                                        f'D{row}': sum(vs[f'2025-{n:02d}'] for n in range(1,10))})
    p = pages()
    _, release = kto.latest_release(p[BOARD], NOW)
    p[release] = html('release')
    files, _ = kto.release_files(p[release], release, '2026-09', NOW)
    p[files['series']] = make_xlsx(sheets)
    p[files['crosscheck']] = make_xlsx(check)
    return p, release, files


class CollectionResearchTests(unittest.TestCase):
    def test_full_synthetic_workbooks_never_claim_actual_network_success(self):
        pages_, _, _ = collection_fixture()
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)/'capture'
            r = capture(out, loader=pages_.__getitem__, now=NOW)
            self.assertEqual(r['status'], 'simulation_only')
            self.assertFalse(r['actual_network_collection'])
            self.assertEqual(sum(r['series_months'].values()), 483)
            self.assertTrue((out/'normalized.csv').is_file())
            self.assertEqual(verify_live_kto(out, {})['status'], 'not_live_validated')

    def test_changed_rights_fail_before_any_normalized_result(self):
        p, release, _ = collection_fixture()
        p[release] = p[release].replace(b'img_opentype00', b'img_opentype01')
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)/'capture'
            r = capture(out, loader=p.__getitem__, now=NOW)
            self.assertEqual(r['status'], 'failed')
            self.assertEqual(r['stage'], 'release_rights_and_file_controls')
            self.assertFalse((out/'snapshot.json').exists())

    def test_bad_xlsx_and_provider_exception_are_safe_and_do_not_replace_prior(self):
        p, _, files = collection_fixture()
        p[files['series']] = b'<html>not official XLSX</html>'
        with tempfile.TemporaryDirectory() as t:
            old = Path(t)/'previous'; old.write_bytes(b'VALIDATED_PREVIOUS')
            out = Path(t)/'capture'
            self.assertEqual(capture(out, loader=p.__getitem__, now=NOW)['status'], 'failed')
            def broken(url):
                raise RuntimeError('PRIVATE_SENTINEL_SHOULD_NOT_APPEAR')
            out2 = Path(t)/'failure'
            capture(out2, loader=broken, now=NOW)
            self.assertNotIn('PRIVATE_SENTINEL', (out2/'result.json').read_text())
            self.assertEqual(old.read_bytes(), b'VALIDATED_PREVIOUS')

    def test_existing_or_repository_output_rejected(self):
        with self.assertRaises(ValueError): external_new(ROOT/'site/data/new')
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError): capture(t)

    def test_missing_historical_month_is_not_filled_or_reported_success(self):
        p, _, files = collection_fixture()
        source=zipfile.ZipFile(io.BytesIO(p[files['series']]))
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as target:
            for name in source.namelist():
                raw=source.read(name)
                if name=='xl/worksheets/sheet1.xml':
                    raw=re.sub(rb'<c r="E4"[^>]*>.*?</c>',b'',raw)
                target.writestr(name,raw)
        p[files['series']]=buffer.getvalue()
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'capture';result=capture(out,loader=p.__getitem__,now=NOW)
            self.assertEqual((result['status'],result['stage']),('failed','monthly_continuity'))
            self.assertFalse((out/'normalized.csv').exists())

    def test_hash_tampering_is_detected_before_live_evidence_use(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            (out/'result.json').write_text(json.dumps({'status':'live_public_download_validated','actual_network_collection':True}))
            (out/'requests.json').write_text(json.dumps([{'file':'file.xlsx','sha256':'0'*64}]))
            (out/'file.xlsx').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'hash_mismatch'): verify_live_kto(out, {})


def synthetic_database():
    entries = json.loads(subprocess.check_output(['node','-e',
        "process.stdout.write(JSON.stringify(require('./site/market-signal-model.js').CONFIG.indicators))"], cwd=ROOT))
    db = dict(schema_version=1, mode='verified_official_statistics', generated_at='2026-11-24T10:00:00+09:00', indicators=[])
    for n, ident in enumerate(['kto_inbound','kto_tourism_receipts','kto_outbound','kto_tourism_expenditure']):
        base = entries[n%2]; c = base['contract']; item = next(i for i in CONFIG['indicators'] if i['id']==ident)
        url = item['source_url']
        observations = [dict(period=add('2021-01',k),value=1000+(k+1)**2*(n+1),unit=item['unit'],frequency='M',
                            publisher=item['publisher'],source_url=url,verification_status=c['verification'],
                            collection_method=c['method'],finality='not_stated',rights='KOGL-0',file_sha256='0'*64)
                        for k in range(69)]
        latest=copy.deepcopy(observations[-1]);a,b=latest['value'],observations[-13]['value']
        latest['comparisons']=dict(reference_period=latest['period'],yoy_base_period=observations[-13]['period'],yoy_pct=round(100*(a-b)/b,2))
        db['indicators'].append(dict(**item, connected=True, observations=observations, latest=latest))
    return db


class MarketResearchTests(unittest.TestCase):
    def run_node(self, db):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'synthetic.json';p.write_text(json.dumps(db))
            return json.loads(subprocess.check_output(['node','-e',NODE,str(p),'2026-11'],cwd=ROOT,text=True))

    def test_two_separate_markets_future_protection_and_no_missing_input_fallback(self):
        r = self.run_node(synthetic_database())
        for name, result in r['outputs'].items():
            self.assertEqual(result['status'], 'observed')
            self.assertEqual(result['backtest']['scored_months'],31)
            self.assertEqual(r['future_poison_failures'][name],0)
        self.assertEqual(r['outputs']['A_inbound']['source_indicator_ids'],['kto_inbound','kto_tourism_receipts'])
        self.assertEqual(r['outputs']['B_outbound']['source_indicator_ids'],['kto_outbound','kto_tourism_expenditure'])
        self.assertTrue(all(s['status']=='withheld' and s['score'] is None for s in r['missing_stress']))

    def test_wrong_outbound_definition_does_not_pass_or_break_inbound(self):
        db=synthetic_database();db['indicators'][2]['definition']='wrong definition'
        r=self.run_node(db)
        self.assertEqual(r['outputs']['A_inbound']['status'],'observed')
        self.assertEqual(r['outputs']['B_outbound']['status'],'withheld')

    def test_manual_source_is_not_accepted_without_existing_pair_approval(self):
        with self.assertRaisesRegex(ValueError,'approval_or_evidence'):
            verify_reference({'mode':'verified_official_statistics','indicators':[]},{},CONFIG,dt.date(2026,11,24))

    def test_country_groups_are_composition_not_independent_axes(self):
        db={'indicators':[{'id':'kto_inbound','observations':[{'period':'2026-09','value':100}]}]+[
            {'id':'kto_inbound_'+c,'observations':[{'period':'2026-09','value':10}]} for c in ['cn','jp','tw','us','vn']]}
        r=composition(db)[0]
        self.assertEqual(r['selected_five_coverage_pct'],'50.000000')
        self.assertFalse(r['independent_model_weights'])
        db['indicators'][1]['observations'][0]['value']=100
        with self.assertRaisesRegex(ValueError,'inconsistent'):composition(db)


if __name__ == '__main__':
    unittest.main()
