"""Failure-run regressions. Synthetic inputs/HTTP responses; no live approval."""
import base64
import ast
import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
import urllib.error
from unittest.mock import patch
import zlib

from src.macro import weather_dispatch as d,weather_publication as g,weather_release as r
from src.pipeline import diagnostics,runner
from test_weather_dispatch import API,ENV,inputs
from test_weather_publication import NOW


class AuthorizationFailureTests(unittest.TestCase):
    def workflow_contract(self, code, **values):
        workflow=(g.engine.ROOT/'.github/workflows/collect.yml').read_text()
        script=textwrap.dedent(workflow.split("python - <<'PYCODE'\n",1)[1].split('          PYCODE',1)[0])
        guards=[node for node in ast.walk(ast.parse(script)) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='require']
        guard=next(node for node in guards if isinstance(node.args[1],ast.Constant) and node.args[1].value==code)
        return eval(compile(ast.Expression(guard.args[0]),'<workflow-contract>','eval'),{'REPOSITORY':d.REPOSITORY,**values})
    def test_pr_default_token_repository_binding_is_case_insensitive_but_exact(self):
        for name in [d.REPOSITORY,'Serhankeem/Tourismnews','SERHANKEEM/TOURISMNEWS']:
            self.assertTrue(self.workflow_contract('github_dispatch_binding_invalid',run={'repository':{'full_name':name}}))
        for name in ['other/Tourismnews','Serhankeem/other','Serhankeem/Tourismnews-extra']:
            self.assertFalse(self.workflow_contract('github_dispatch_binding_invalid',run={'repository':{'full_name':name}}))
    def test_pr_default_token_actor_and_collaborator_permission_still_required(self):
        for permission,actor_id,expected in [('admin',2,True),('write',2,True),('maintain',2,True),('read',2,False),('admin',3,False)]:
            self.assertEqual(self.workflow_contract('github_publish_permission_required',run={'actor':{'id':2}},role={'permission':permission,'user':{'id':actor_id}}),expected)
    def test_execution_and_actor_permission_contracts_are_both_still_required(self):
        _,_,mh,ch=inputs();api=API(mh,ch)
        self.assertLessEqual(d.authorize(api,ENV,mh,ch,'a'*40,NOW),NOW)
        api.permission={'permission':'read','user':{'id':2}}
        with self.assertRaisesRegex(g.GateError,'github_publish_permission_required'):d.authorize(api,ENV,mh,ch,'a'*40,NOW)
    def test_default_token_client_classifies_http_without_reading_sensitive_body(self):
        expected={401:'monthly_run_api_unauthenticated',403:'monthly_run_api_forbidden',404:'monthly_run_api_not_found',429:'monthly_run_api_rate_limited',503:'monthly_run_api_unavailable'}
        for status,code in expected.items():
            api=d.GitHub('synthetic-token')
            with patch.object(api,'open',side_effect=urllib.error.HTTPError('https://invalid.example/?secret=hidden',status,'sensitive response',{},io.BytesIO(b'private input'))):
                with self.assertRaisesRegex(g.GateError,'^'+code+'$') as caught:api.get('repos/'+d.REPOSITORY+'/actions/runs/123')
            self.assertNotIn('hidden',str(caught.exception));self.assertNotIn('private',str(caught.exception))
    def test_invalid_json_rate_limit_and_missing_token_are_distinct(self):
        with self.assertRaisesRegex(g.GateError,'monthly_token_missing'):d.GitHub('')
        api=d.GitHub('synthetic-token')
        with patch.object(api,'open',side_effect=urllib.error.HTTPError('https://invalid.example',403,'private',{'X-RateLimit-Remaining':'0'},None)),self.assertRaisesRegex(g.GateError,'monthly_run_api_rate_limited'):api.get('repos/'+d.REPOSITORY+'/actions/runs/123')
        with patch.object(api,'open',return_value=io.BytesIO(b'not-json-private')),self.assertRaisesRegex(g.GateError,'monthly_run_api_invalid_response'):api.get('repos/'+d.REPOSITORY+'/actions/runs/123')
    def test_unapproved_other_actor_and_rerun_still_refuse(self):
        _,_,mh,ch=inputs()
        for mutation in [('actor',{'login':'other','id':3}),('run_attempt',2),('event','push')]:
            api=API(mh,ch);api.run[mutation[0]]=mutation[1]
            with self.assertRaises(g.GateError):d.authorize(api,ENV,mh,ch,'a'*40,NOW)
    def test_clipboard_whitespace_preserves_hash_bound_candidate_bytes(self):
        _,raw,mh,ch=inputs();encoded=base64.b64encode(zlib.compress(raw)).decode()
        wrapped='\r\n'+ '\n'.join(encoded[n:n+76] for n in range(0,len(encoded),76))+'\n'
        env={**ENV,'MARKET_WEATHER_CANDIDATE_B64':wrapped,'MARKET_WEATHER_SIGNING_KEY':'ab'*32}
        with patch.dict(os.environ,env,clear=True),patch.object(d,'GitHub',return_value=API(mh,ch)):
            request=d.from_environment(g.engine.ROOT,'a'*40,mh,ch,NOW)
            self.assertEqual(request.raw,raw)
    def test_bad_secret_formats_and_missing_key_are_safe_and_do_not_project(self):
        _,_,mh,ch=inputs()
        for value,code in [('', 'candidate_secret_missing_or_oversized'),('not!base64','monthly_candidate_base64_invalid'),(base64.b64encode(b'not zlib').decode(),'candidate_size_or_encoding_invalid')]:
            with patch.dict(os.environ,{'MARKET_WEATHER_CANDIDATE_B64':value},clear=True),patch.object(g,'_projection') as projection,self.assertRaisesRegex(g.GateError,code):d.from_environment(g.engine.ROOT,'a'*40,mh,ch,NOW)
            projection.assert_not_called()
        with patch.dict(os.environ,{},clear=True),self.assertRaisesRegex(g.GateError,'monthly_signing_key_required'):r.signing_key()
        with patch.dict(os.environ,{'MARKET_WEATHER_SIGNING_KEY':'invalid'},clear=True),self.assertRaisesRegex(g.GateError,'monthly_signing_key_required'):r.signing_key()
    def test_diagnostics_keep_safe_codes_instead_of_the_recorded_generic_error(self):
        for code in ['monthly_run_api_forbidden','monthly_run_api_invalid_response','github_publish_permission_required','candidate_hash_mismatch','manuscript_hash_mismatch','monthly_candidate_base64_invalid','monthly_signing_key_required','statistics_not_currently_eligible']:
            result={'phase':'authorization'};diagnostics.failure(result,g.GateError(code))
            self.assertEqual(result['error_code'],code);self.assertEqual(result['error_kind'],'GateError');self.assertFalse(result['ready'])
        result={'phase':'authorization'};diagnostics.failure(result,g.GateError('private token/body'))
        self.assertNotIn('private',json.dumps(result));self.assertEqual(result['error_code'],'validation_or_execution_failed')
    def test_runner_writes_specific_authorization_failure_without_transaction_or_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)/'work'
            args=['runner','run','--work',str(work),'--output',str(Path(tmp)/'pages'),'--monthly-manuscript-sha256','a'*64,'--monthly-candidate-sha256','b'*64]
            with patch('sys.argv',args),patch.object(runner,'require_main'),patch.object(r,'environment',return_value=None),patch.object(d,'from_environment',side_effect=g.GateError('monthly_run_api_forbidden')),patch.object(runner,'transact') as transact:
                self.assertEqual(runner.main(),1)
            result=json.loads((work/'result.json').read_text());self.assertEqual(result['error_code'],'monthly_run_api_forbidden');self.assertEqual(result['phase'],'authorization');self.assertFalse(result['ready'])
            transact.assert_not_called();self.assertFalse((Path(tmp)/'pages').exists())
