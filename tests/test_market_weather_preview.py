"""No private fixture values: loopback isolation and empty-preview transport."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from tools import market_weather_preview as preview


class PreviewServerTests(unittest.TestCase):
    def setUp(self):
        self.server=preview.create_server(port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.port=self.server.server_port

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path='/',headers=None,method='GET'):
        connection=http.client.HTTPConnection('127.0.0.1',self.port)
        connection.request(method,path,headers=headers or {})
        response=connection.getresponse();body=response.read();info=dict(response.getheaders());status=response.status
        connection.close();return status,info,body

    def test_loopback_binding_and_no_statistical_html(self):
        self.assertEqual(self.server.server_address[0],'127.0.0.1')
        status,headers,body=self.request()
        self.assertEqual(status,200);self.assertNotIn(b'kto_inbound',body)
        self.assertIn('no-store',headers['Cache-Control'])
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
        self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])

    def test_private_endpoint_requires_local_session(self):
        self.assertEqual(self.request('/api/preview')[0],403)
        cookie=self.request()[1]['Set-Cookie'].split(';')[0]
        status,headers,body=self.request('/api/preview',{'Cookie':cookie})
        self.assertEqual(status,200);self.assertEqual(json.loads(body),{'state':'no_data','publication_approved':False})
        self.assertNotIn('Access-Control-Allow-Origin',headers)

    def test_foreign_host_origin_and_fetch_site_are_denied(self):
        cookie=self.request()[1]['Set-Cookie'].split(';')[0]
        for extra in ({'Host':'public.example.org'},{'Origin':'https://public.example.org'},{'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.request('/api/preview',{'Cookie':cookie,**extra})[0],403)

    def test_no_arbitrary_files_or_write_route(self):
        for path in ('/manifest.json','/inputs/archive.json','/../macro_sources.json','/api/preview?export=1'):
            self.assertEqual(self.request(path)[0],404)
        self.assertEqual(self.request('/api/preview',method='POST')[0],501)

    def test_external_bundle_validation_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):preview.load_preview(Path(tmp))
        with self.assertRaises(ValueError):preview.load_preview(preview.engine.ROOT/'site')

    def test_preview_assets_are_outside_public_site(self):
        self.assertFalse((preview.engine.ROOT/'site/preview').exists())
        self.assertFalse(any(p.name in ('monthly.js','monthly.css','diagnostic-private.json','briefing-private.json') for p in (preview.engine.ROOT/'site').rglob('*')))


if __name__=='__main__':unittest.main()
