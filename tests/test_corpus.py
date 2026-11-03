import csv, tempfile, unittest
from pathlib import Path
from trustnote.dataset import prepare_corpus, CORPUS_FILES

class CorpusTests(unittest.TestCase):
    def make_corpus(self,base,duplicate=False):
        folder=base/'aci-bench-corpus'/'challenge_data';folder.mkdir(parents=True)
        for i,(split,names) in enumerate(CORPUS_FILES.items()):
            with (folder/names[0]).open('w',newline='',encoding='utf-8') as f:
                w=csv.DictWriter(f,fieldnames=['dataset','encounter_id','dialogue','note']);w.writeheader()
                w.writerow({'dataset':'fixture','encounter_id':'same' if duplicate else f'E{i}', 'dialogue':f'Patient: fixture {i}', 'note':f'Fixture note {i}'})
        (folder/'train_metadata.csv').write_text('bad metadata intentionally ignored')
        return folder.parent
    def test_five_splits_metadata_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);src=self.make_corpus(p);result=prepare_corpus(src,p/'prepared')
            self.assertEqual(result['total_rows'],5)
            self.assertEqual(len(list((p/'prepared').glob('*.jsonl'))),5)
            self.assertEqual(len(result['warnings']),5)
    def test_duplicate_encounter_no_partial_import(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);src=self.make_corpus(p,duplicate=True)
            with self.assertRaisesRegex(ValueError,'Repeated encounter'): prepare_corpus(src,p/'prepared')
            self.assertFalse((p/'prepared').exists())
    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);src=self.make_corpus(p);out=p/'prepared';out.mkdir();(out/'keep.txt').write_text('original')
            with self.assertRaisesRegex(ValueError,'not empty'): prepare_corpus(src,out)
            self.assertEqual((out/'keep.txt').read_text(),'original')
