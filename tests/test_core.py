import csv, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from trustnote.models import Note, ClaimList, Judgment, Claim, Evidence
from trustnote.retrieval import windows, Retriever
from trustnote.verification import LLMVerifier
from trustnote.pipeline import run
from trustnote.dataset import convert, read_rows, check_overlap
from trustnote.evaluation import score_annotations, compare_human_labels, export_annotations
from trustnote.llm import Ollama

class Stub:
    model='TEST DOUBLE - not clinical inference'
    calls=[]
    def ask(self,system,data,schema):
        if schema is ClaimList: return ClaimList(claims=[{'text':data['source_sentence']}])
        if schema is Judgment:
            label={'Dry cough for three days.':'Supported','Patient reports fever.':'Contradicted'}.get(data['claim'],'Unverifiable')
            return Judgment(label=label,evidence_ids=[data['evidence'][0]['id']],rationale='Fixture verdict only.')
        return Note(Subjective=['Dry cough for three days.','Patient reports fever.'],Objective=['Normal X-ray.'],Assessment=[],Plan=[])

class Tests(unittest.TestCase):
    def test_exact_evidence_offsets(self):
        text='Doctor: Fever?\nPatient: No.\nPatient: café\n'+'a word '*400
        for e in windows(text): self.assertEqual(text[e.start:e.end],e.text)
        covered=set()
        for e in windows(text,radius=0): covered.update(range(e.start,e.end))
        self.assertTrue(all(i in covered for i,c in enumerate(text) if not c.isspace()))
    def test_question_answer_context(self):
        result=Retriever('Doctor: Any fever?\nPatient: No.\nDoctor: Thank you.').retrieve('Patient denies fever',1)
        self.assertIn('Patient: No.',result[0].text)
    def test_retrieval_relevant(self):
        result=Retriever('Patient: Knee pain.\nPatient: Taking aspirin.\nDoctor: Temperature 37.',radius=0).retrieve('aspirin',1)
        self.assertIn('aspirin',result[0].text)
    def test_empty_retrieval(self):
        with self.assertRaises(ValueError): Retriever('')
    def test_pipeline_preserves_original(self):
        s=Stub(); result=run('Patient: Dry cough for three days. No fever.',s,LLMVerifier(s))
        self.assertEqual(result['metrics']['total_claims'],3)
        self.assertEqual(result['metrics']['model_estimated_unsupported_claim_rate'],2/3)
        self.assertEqual(result['filtered_note']['Subjective'],['Dry cough for three days.'])
        self.assertEqual(result['filtered_note']['Objective'],[])
        self.assertEqual(len(result['original_note']['Subjective']),2)
    def test_invalid_citation_abstains(self):
        class Bad:
            def ask(self,*args): return Judgment(label='Supported',evidence_ids=['invented'],rationale='wrong')
        c=Claim(id='C1',section='Subjective',source_index=0,source_text='x',text='x')
        r=LLMVerifier(Bad()).verify(c,[Evidence(id='E1',text='x',start=0,end=1)])
        self.assertEqual(r.label,'Unverifiable')
        self.assertEqual(r.evidence,[])
    def test_sentence_guard_catches_extraction_omission(self):
        class Omission(Stub):
            def ask(self,system,data,schema):
                if schema is ClaimList: return ClaimList(claims=[{'text':'Dry cough for three days.'}])
                return super().ask(system,data,schema)
        note=Note(Subjective=['Dry cough for three days and normal X-ray.'],Objective=[],Assessment=[],Plan=[])
        s=Omission();r=run('Patient: Dry cough for three days.',s,LLMVerifier(s),note)
        self.assertEqual(r['claims'][0]['label'],'Supported')
        self.assertEqual(r['filtered_note']['Subjective'],[])
    def test_import_and_overlap(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'x.csv').write_text('dialogue,note\nhello,summary\n',encoding='utf-8')
            convert(p/'x.csv',p/'a.jsonl','train');convert(p/'x.csv',p/'b.jsonl','test')
            self.assertEqual(read_rows(p/'a.jsonl')[0]['transcript'],'hello')
            self.assertEqual(len(check_overlap([p/'a.jsonl',p/'b.jsonl'])),1)
    def test_mts_columns(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'x.csv').write_text('ID,dialogue,section_text\n1,hello,summary\n')
            result=convert(p/'x.csv',p/'a.jsonl','valid')
            self.assertEqual(result['note_column'],'section_text')
    def test_duplicate_dataset_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'x.csv').write_text('dialogue,note\nx,a\nx,b\n')
            with self.assertRaises(ValueError): convert(p/'x.csv',p/'a.jsonl','train')
            self.assertFalse((p/'a.jsonl').exists())
    def test_gold_labels_required(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'labels.csv';p.write_text('gold_label,predicted_label\n,Supported\n')
            with self.assertRaises(ValueError): score_annotations(p)
    def test_metrics_known_matrix(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'labels.csv';p.write_text('gold_label,predicted_label\nSupported,Supported\nContradicted,Unverifiable\nUnverifiable,Unverifiable\n')
            m=score_annotations(p)
            self.assertAlmostEqual(m['accuracy'],2/3)
            self.assertAlmostEqual(m['per_class']['Unverifiable']['precision'],.5)
    def test_context_rejected_before_request(self):
        with patch('urllib.request.urlopen') as request:
            with self.assertRaises(ValueError): Ollama(context=4096).ask('x',{'text':'x'*5000},Note)
            request.assert_not_called()
    def test_human_filtered_empty_undefined(self):
        s=Stub()
        note=Note(Subjective=['Patient reports fever.'],Objective=[],Assessment=[],Plan=[])
        report=run('Patient: No fever.',s,LLMVerifier(s),note)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.csv';export_annotations(report,p)
            with p.open(newline='') as f: rows=list(csv.DictReader(f))
            rows[0]['gold_label']='Contradicted'
            with p.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            result=compare_human_labels(report,p)
            self.assertIsNone(result['filtered_human_unsupported_claim_rate'])
            self.assertEqual(result['baseline_human_unsupported_claim_rate'],1.)
    def test_empty_note_is_not_success(self):
        s=Stub()
        with self.assertRaises(ValueError): run('Patient: hello',s,LLMVerifier(s),Note(Subjective=[],Objective=[],Assessment=[],Plan=[]))
if __name__=='__main__': unittest.main()
