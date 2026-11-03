import io,json,os,unittest,urllib.error
from unittest.mock import patch
from trustnote.llm import Groq
from trustnote.models import Judgment
class GroqTests(unittest.TestCase):
 def make(self):
  with patch.dict(os.environ,{'GROQ_API_KEY':'fixture-secret'}): return Groq(interval=0, max_retries=0)
 def response(self,finish='stop'):
  return io.BytesIO(json.dumps({'choices':[{'finish_reason':finish,'message':{'content':json.dumps({'label':'Supported','evidence_ids':['E1'],'rationale':'fixture'})}}],'usage':{'total_tokens':20}}).encode())
 def test_request_and_parse(self):
  c=self.make()
  with patch('urllib.request.urlopen',return_value=self.response()) as http:
   self.assertEqual(c.ask('test',{},Judgment).label,'Supported')
   req=http.call_args.args[0];self.assertEqual(req.get_header('Authorization'),'Bearer fixture-secret')
   self.assertTrue(json.loads(req.data)['response_format']['json_schema']['strict'])
  self.assertNotIn('fixture-secret',json.dumps(c.calls))
 def test_length_rejected(self):
  with patch('urllib.request.urlopen',return_value=self.response('length')):
   with self.assertRaises(RuntimeError):self.make().ask('test',{},Judgment)
 def test_error_redacts_secret(self):
  e=urllib.error.HTTPError('https://api.groq.com',429,'error',{},io.BytesIO(b'{"error":{"message":"quota fixture-secret"}}'))
  with patch('urllib.request.urlopen',side_effect=e):
   with self.assertRaises(RuntimeError) as ctx:self.make().ask('test',{},Judgment)
  self.assertNotIn('fixture-secret',str(ctx.exception));self.assertIn('quota',str(ctx.exception))
 def test_missing_key(self):
  with patch.dict(os.environ,{},clear=True):
   with self.assertRaises(ValueError):Groq()
