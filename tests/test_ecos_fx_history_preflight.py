"""Synthetic FX values only. Never constructs a real authenticated transport."""
import copy
import datetime as dt
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from src.macro import ecos, ecos_market_preflight as p, ecos_fx_history_preflight as h
from src.macro.model import months
from tools.validate_market_weather_foundation import Replay

NOW=dt.datetime(2026,11,16,tzinfo=dt.timezone.utc)
CONFIG=json.loads((p.ROOT/'macro_sources.json').read_text())
FAKE='SYNTHETIC_SECRET_NEVER_A_REAL_KEY'


def fixture():
    baseline=copy.deepcopy(p.load_baseline());rows=[]
    for n,period in enumerate(months('2021-01','2026-10')):
        row=dict(STAT_CODE='731Y004',UNIT_NAME='원',TIME=period.replace('-',''),DATA_VALUE='1234.'+f'{n:02}')
        for g,(code,name) in enumerate(zip(['0000001','0000100',None,None],['원/미국달러(매매기준율)','평균자료',None,None]),1):
            row[f'ITEM_CODE{g}']=code;row[f'ITEM_NAME{g}']=name
        baseline['series'][h.KEY]['fingerprints'][period]=p.fingerprint(h.KEY,period,row['DATA_VALUE']);rows.append(row)
    class Client(Replay):
        def __init__(self):
            super().__init__({'indicators':[i for i in CONFIG['indicators'] if i['id']==h.KEY]}, {h.KEY:rows})
            self.calls=[];self.mutate=None
        def rows(self,service,table,*args):
            self.calls.append((service,table,args))
            data=super().rows(service,table,*args)
            if service=='StatisticSearch':
                data=[r for r in data if args[1]<=r['TIME']<=args[2]]
                if self.mutate:self.mutate(data,args)
            return data
    return Client(),baseline


class FXHistoryTests(unittest.TestCase):
    def test_fixed_three_then_67_no_other_series_or_new_months(self):
        c,b=fixture();r=h.probe(CONFIG,b,c,NOW)
        self.assertEqual(r['status'],'simulation_only');self.assertEqual(r['authentication'],'not_verified')
        self.assertEqual(r['matched_count'],70);self.assertEqual(r['unqueried_count'],0)
        searches=[x for x in c.calls if x[0]=='StatisticSearch']
        self.assertEqual([x[2][1:3] for x in searches],[('202608','202610'),('202101','202607')])
        self.assertTrue(all(x[1]=='731Y004' for x in c.calls))
        self.assertIn('70 months',h.render(r))

    def test_gate_correction_prevents_history_expansion(self):
        c,b=fixture();c.mutate=lambda rows,args:rows[0].update(DATA_VALUE='1')
        r=h.probe(CONFIG,b,c,NOW)
        self.assertEqual(r['phase'],'gate_3');self.assertEqual(r['error'],'corrections_require_review')
        self.assertEqual(r['unqueried_count'],67)
        self.assertEqual(len([x for x in c.calls if x[0]=='StatisticSearch']),1)

    def test_history_correction_retains_baseline_and_reports_only_month(self):
        c,b=fixture();before=copy.deepcopy(b)
        def mutate(rows,args):
            if args[1]=='202101':rows[0]['DATA_VALUE']='1'
        c.mutate=mutate;r=h.probe(CONFIG,b,c,NOW)
        self.assertEqual(r['status'],'failed');self.assertEqual(r['correction_periods'],['2021-01'])
        self.assertEqual(r['response_count'],70);self.assertEqual(b,before)
        self.assertNotIn('DATA_VALUE',h.render(r))

    def test_invalid_rows_stop_and_never_count_unvalidated_history(self):
        for mode in ('missing','duplicate','selector','unit','float','future'):
            c,b=fixture()
            def mutate(rows,args):
                if args[1]!='202101':return
                if mode=='missing':rows.pop()
                elif mode=='duplicate':rows.append(copy.deepcopy(rows[0]))
                elif mode=='selector':rows[0]['ITEM_CODE2']='0000200'
                elif mode=='unit':rows[0]['UNIT_NAME']='USD'
                elif mode=='float':rows[0]['DATA_VALUE']=1.1
                else:rows[0]['TIME']='202611'
            c.mutate=mutate;r=h.probe(CONFIG,b,c,NOW)
            with self.subTest(mode=mode):
                self.assertEqual(r['status'],'failed');self.assertEqual(r['response_count'],3)
                self.assertEqual(r['unqueried_count'],67);h.render(r)

    def test_disabled_registry_and_pinned_baseline_required(self):
        c,b=fixture();cfg=copy.deepcopy(CONFIG)
        next(i for i in cfg['indicators'] if i['id']==h.KEY)['enabled']=True
        r=h.probe(cfg,b,c,NOW);self.assertEqual(r['error'],'configuration_invalid');self.assertFalse(c.calls)
        b['series'][h.KEY]['fingerprints'].pop('2021-01')
        self.assertEqual(h.probe(CONFIG,b,c,NOW)['error'],'baseline_invalid')

    def test_missing_invalid_rate_limited_and_sensitive_exceptions(self):
        for code,expected in [('ecos_auth_required','credential_missing'),('ecos_auth_invalid','authentication_rejected'),
                              ('ecos_rate_limited','rate_limited'),(FAKE,'unexpected_failure')]:
            c,b=fixture()
            with patch.object(c,'rows',side_effect=ecos.EcosError(code)):
                r=h.probe(CONFIG,b,c,NOW)
            self.assertEqual(r['error'],expected);self.assertNotIn(FAKE,h.render(r))

    def test_renderer_refuses_untrusted_text_or_counts(self):
        c,b=fixture();r=h.probe(CONFIG,b,c,NOW)
        for key,value in [('error',FAKE),('phase',FAKE),('response_count',71),('correction_periods',[FAKE]),('extra',FAKE)]:
            changed=copy.deepcopy(r);changed[key]=value
            with self.subTest(key=key),self.assertRaises(p.ProbeError):h.render(changed)

    def test_main_guard_precedes_client_and_summary(self):
        with patch.dict(os.environ,{},clear=True),patch.object(ecos,'Client') as client,context_stdout():
            self.assertEqual(h.main(),1);client.assert_not_called()

    def test_cli_simulation_safe_summary_and_no_extra_files(self):
        c,b=fixture()
        with tempfile.TemporaryDirectory() as d:
            summary=Path(d)/'summary';summary.touch()
            env=dict(GITHUB_ACTIONS='true',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/main',
                     RUNNER_TEMP=d,GITHUB_STEP_SUMMARY=str(summary),ECOS_API_KEY=FAKE)
            with patch.dict(os.environ,env,clear=True),patch.object(p,'load_baseline',return_value=b),patch.object(h,'probe',return_value=h.probe(CONFIG,b,c,NOW)):
                self.assertEqual(h.main(),1)
            self.assertIn('simulation_only',summary.read_text());self.assertNotIn(FAKE,summary.read_text())
            self.assertEqual([p.name for p in Path(d).iterdir()],['summary'])

    def test_workflow_manual_read_only_no_artifact_or_collector(self):
        text=(p.ROOT/'.github/workflows/ecos-fx-history-preflight.yml').read_text()
        self.assertIn('workflow_dispatch:',text);self.assertIn('contents: read',text)
        self.assertNotIn('schedule:',text);self.assertNotIn('upload-artifact',text)
        self.assertNotIn('pipeline.yml',text);self.assertNotIn('contents: write',text)
        self.assertIn('secrets.ECOS_API_KEY',text);self.assertIn("github.ref == 'refs/heads/main'",text)


def context_stdout():
    from contextlib import redirect_stdout
    return redirect_stdout(io.StringIO())


if __name__=='__main__':unittest.main()
