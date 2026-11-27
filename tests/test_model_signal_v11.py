"""Private research/preview boundaries, no live downloads or publication."""
from fractions import Fraction as F
import http.client
import json
from pathlib import Path
import threading
import unittest

from tools import compare_model_signal_v11 as c, model_signal_v11_preview as preview


class ModelSignalV11Tests(unittest.TestCase):
    def test_exact_transforms_and_midrank_exclude_target_and_future(self):
        series={c.add('2021-01', n): F((n//12+1)*1000) for n in range(75)}
        self.assertEqual(c.position(series,'2026-09','smooth24'),F(25,2))
        for method in c.METHODS:
            original=c.position(series,'2026-09',method)
            prefix={p:v for p,v in series.items() if p<='2026-09'}
            self.assertEqual(c.position(prefix,'2026-09',method),original)
            changed={p:v if p<='2026-09' else v*10000 for p,v in series.items()}
            self.assertEqual(c.position(changed,'2026-09',method),original)
    def test_insufficient_window_and_constant_distribution_do_not_fabricate(self):
        for method in c.METHODS:
            with self.assertRaises(KeyError): c.position({'2026-09':F(1)},'2026-09',method)
            series={c.add('2021-01', n):F(1000) for n in range(69)}
            with self.assertRaisesRegex(ValueError,'degenerate_reference'): c.position(series,'2026-09',method)
    def test_zero_denominator_does_not_create_score(self):
        series={c.add('2021-01',n):F(0) for n in range(69)}
        with self.assertRaises(ValueError): c.position(series,'2026-09','rolling12_yoy24')
    def test_preview_data_requires_loopback_host_cookie_and_same_origin(self):
        result={'status':'withheld','reason':'snapshot_hash_mismatch','publication_approved':False}
        server=preview.server(result);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
        try:
            conn.request('GET','/result.json');r=conn.getresponse();self.assertEqual(r.status,403);r.read()
            conn.request('GET','/',headers={'Host':'untrusted.example'});r=conn.getresponse();self.assertEqual(r.status,403);r.read()
            conn.request('GET','/');r=conn.getresponse();self.assertEqual(r.status,200);cookie=r.getheader('Set-Cookie');r.read()
            self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
            conn.request('GET','/result.json',headers={'Cookie':cookie,'Origin':'https://untrusted.example'});r=conn.getresponse();self.assertEqual(r.status,403);r.read()
            conn.request('GET','/result.json',headers={'Cookie':cookie});r=conn.getresponse();self.assertEqual(r.status,200);self.assertEqual(r.getheader('Cache-Control'),'no-store');self.assertEqual(json.loads(r.read()),result)
            conn.request('GET','/../site/data/macro.json',headers={'Cookie':cookie});r=conn.getresponse();self.assertEqual(r.status,404);r.read()
        finally:conn.close();server.shutdown();server.server_close();thread.join()
    def test_preview_assets_are_not_in_operating_pages_allowlist(self):
        root=Path(__file__).resolve().parents[1]
        config=json.loads((root/'pipeline.json').read_text())
        self.assertFalse(any('v11' in p for p in config['static_public_files']))
        self.assertNotIn('v11',(root/'site/index.html').read_text())
