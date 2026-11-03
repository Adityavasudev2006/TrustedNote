import io, json, os, unittest, urllib.error
from unittest.mock import patch
from argparse import Namespace
from trustnote.llm import Gemini, Ollama
from trustnote.models import Judgment
from trustnote.cli import clients

class GeminiTests(unittest.TestCase):
    def client(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':'test-key-not-real'}): return Gemini(interval=0)
    def result(self,finish='STOP',content=None):
        return io.BytesIO(json.dumps({'modelVersion':'test-version','usageMetadata':{'totalTokenCount':10},'candidates':[{'finishReason':finish,'content':{'parts':[{'text':json.dumps(content or {'label':'Supported','evidence_ids':['E1'],'rationale':'fixture'})}]}}]}).encode())
    def test_missing_key(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ValueError): Gemini()
    def test_schema_auth_and_provenance(self):
        client=self.client()
        with patch('urllib.request.urlopen',return_value=self.result()) as http:
            answer=client.ask('verify',{'claim':'test'},Judgment)
            request=http.call_args.args[0]
            self.assertNotIn('test-key-not-real',request.full_url)
            self.assertEqual(request.get_header('X-goog-api-key'),'test-key-not-real')
            payload=json.loads(request.data)
            self.assertIn('responseJsonSchema',payload['generationConfig'])
        self.assertEqual(answer.label,'Supported')
        self.assertEqual(client.calls[0]['model_version'],'test-version')
        self.assertNotIn('test-key-not-real',json.dumps(client.calls))
    def test_truncated_output_rejected(self):
        with patch('urllib.request.urlopen',return_value=self.result(finish='MAX_TOKENS')):
            with self.assertRaisesRegex(RuntimeError,'incomplete'): self.client().ask('verify',{},Judgment)
    def test_missing_candidate_rejected(self):
        with patch('urllib.request.urlopen',return_value=io.BytesIO(b'{"candidates":[]}')):
            with self.assertRaisesRegex(RuntimeError,'no candidate'): self.client().ask('verify',{},Judgment)
    def test_invalid_label_rejected(self):
        with patch('urllib.request.urlopen',return_value=self.result(content={'label':'Probably','evidence_ids':[],'rationale':'x'})):
            with self.assertRaises(ValueError): self.client().ask('verify',{},Judgment)
    def test_quota_error_sanitized_no_retry(self):
        error=urllib.error.HTTPError('https://example',429,'sensitive-provider-detail',{},None)
        with patch('urllib.request.urlopen',side_effect=error) as http:
            with self.assertRaisesRegex(RuntimeError,'Quota') as ctx: self.client().ask('verify',{},Judgment)
            self.assertEqual(http.call_count,1)
            self.assertNotIn('sensitive-provider-detail',str(ctx.exception))
    def test_provider_routing(self):
        args=Namespace(top_k=5,radius=1,context=16384,provider='gemini',model=None,max_output=8192,request_interval=0,verifier='llm',verifier_model=None,url='http://localhost:11434',threshold=.85)
        with patch.dict(os.environ,{'GEMINI_API_KEY':'test-key-not-real'}):
            llm,verifier=clients(args)
        self.assertIsInstance(llm,Gemini);self.assertIs(verifier.llm,llm)
        args.provider='ollama';llm,_=clients(args)
        self.assertIsInstance(llm,Ollama);self.assertEqual(llm.model,'qwen2.5:3b')
if __name__=='__main__': unittest.main()
