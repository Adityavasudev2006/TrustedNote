import argparse, json, sys
from pathlib import Path
from .dataset import read_rows, convert, check_overlap, prepare_corpus
from .evaluation import export_annotations, score_annotations, quality, compare_human_labels, entity_f1
from .llm import Ollama, Gemini, Groq
from .models import Note
from .pipeline import run, markdown
from .verification import LLMVerifier, NLIVerifier

def write_json(path,obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')
def save_report(result,out):
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    write_json(out/'report.json',result)
    (out/'report.md').write_text(markdown(result),encoding='utf-8')
    export_annotations(result,out/'annotations.csv')
def add_model(p):
    p.add_argument('--provider',choices=['ollama','gemini','groq'],default='ollama')
    p.add_argument('--model',help='Defaults: qwen2.5:3b (Ollama), gemini-2.5-flash (Gemini), openai/gpt-oss-20b (Groq)')
    p.add_argument('--request-interval',type=float,default=5,help='Minimum seconds between cloud API request starts')
    p.add_argument('--max-output',type=int,default=8192,help='Cloud API output-token limit')
    p.add_argument('--verifier-model',help='Separate model on selected provider for LLM verification; defaults to generator model')
    p.add_argument('--url',default='http://localhost:11434')
    p.add_argument('--context',type=int,default=16384)
    p.add_argument('--verifier',choices=['llm','nli'],default='llm')
    p.add_argument('--dense',action='store_true')
    p.add_argument('--top-k',type=int,default=5)
    p.add_argument('--radius',type=int,default=1)
    p.add_argument('--threshold',type=float,default=.85)

def clients(a):
    if a.top_k<1 or a.radius<0 or a.context<4096: raise ValueError('Require top-k >= 1, radius >= 0, context >= 4096')
    def make(model):
        if a.provider=='groq': return Groq(model or 'openai/gpt-oss-20b',a.max_output,a.request_interval)
        if a.provider=='gemini': return Gemini(model or 'gemini-2.5-flash',a.max_output,a.request_interval)
        return Ollama(model or 'qwen2.5:3b',a.url,a.context)
    llm=make(a.model)
    verifier=NLIVerifier(a.threshold) if a.verifier=='nli' else LLMVerifier(make(a.verifier_model) if a.verifier_model else llm)
    return llm,verifier

def main():
    p=argparse.ArgumentParser(description='TrustNote text-only research pipeline')
    sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('inspect');q.add_argument('file')
    q=sub.add_parser('prepare-corpus');q.add_argument('folder');q.add_argument('--out',default='data/prepared')
    q=sub.add_parser('prepare');q.add_argument('file');q.add_argument('--out',required=True);q.add_argument('--split',required=True,choices=['train','valid','test','test1','test2','test3']);q.add_argument('--transcript-column');q.add_argument('--note-column')
    q=sub.add_parser('check-splits');q.add_argument('files',nargs='+')
    q=sub.add_parser('run');q.add_argument('--transcript',required=True);q.add_argument('--note',help='Existing structured SOAP JSON; skips generation');q.add_argument('--out',required=True);add_model(q)
    q=sub.add_parser('batch');q.add_argument('--data',required=True);q.add_argument('--out',required=True);q.add_argument('--limit',type=int,default=3);q.add_argument('--quality',action='store_true');q.add_argument('--bertscore',action='store_true');add_model(q)
    q=sub.add_parser('score');q.add_argument('annotations');q.add_argument('--out',required=True);q.add_argument('--report')
    q=sub.add_parser('score-entities');q.add_argument('entities');q.add_argument('--out',required=True)
    a=p.parse_args()
    try:
        if a.command=='prepare-corpus':
            print(json.dumps(prepare_corpus(a.folder,a.out),indent=2));return
        if a.command=='inspect':
            rows=read_rows(a.file)
            print(json.dumps({'rows':len(rows),'columns':list(rows[0]) if rows else [],'first_row_lengths':{k:len(str(v)) for k,v in rows[0].items()} if rows else {}},indent=2)); return
        if a.command=='prepare':
            print(json.dumps(convert(a.file,a.out,a.split,a.transcript_column,a.note_column),indent=2));return
        if a.command=='check-splits':
            collisions=check_overlap(a.files);print(json.dumps({'exact_transcript_overlaps':collisions},indent=2));
            if collisions: sys.exit(1)
            return
        if a.command=='score':
            result=score_annotations(a.annotations)
            if a.report: result['paired_filter_comparison']=compare_human_labels(json.loads(Path(a.report).read_text(encoding='utf-8')),a.annotations)
            write_json(a.out,result);print(json.dumps(result,indent=2));return
        if a.command=='score-entities':
            result=entity_f1(a.entities);write_json(a.out,result);print(json.dumps(result,indent=2));return
        llm,verifier=clients(a)
        opts={'dense':a.dense,'top_k':a.top_k,'radius':a.radius}
        if a.command=='run':
            transcript=Path(a.transcript).read_text(encoding='utf-8-sig')
            note=Note.model_validate_json(Path(a.note).read_text(encoding='utf-8')) if a.note else None
            result=run(transcript,llm,verifier,note=note,**opts);save_report(result,a.out)
            print(json.dumps(result['metrics'],indent=2));print('Report:',str(Path(a.out)/'report.md'));return
        if a.limit<1: raise ValueError('limit must be positive')
        rows=read_rows(a.data)[:a.limit]
        if not rows: raise ValueError('Dataset empty')
        summary=[]
        for index,row in enumerate(rows,1):
            print(f'Running {index}/{len(rows)}: {row["id"]}',flush=True)
            llm.calls=[]
            if hasattr(verifier,'llm') and verifier.llm is not llm: verifier.llm.calls=[]
            result=run(row['transcript'],llm,verifier,**opts)
            result['dataset_record']={k:v for k,v in row.items() if k not in ['transcript','reference_note']}
            entry={'id':row['id'],**result['metrics']}
            if a.quality or a.bertscore:
                # Missing reference is an explicit error; never substitute transcript.
                reference=row['reference_note']
                for arm,key in [('baseline','original_note'),('filtered','filtered_note')]:
                    prediction='\n'.join(x for v in result[key].values() for x in v)
                    entry[arm]=quality(reference,prediction,a.bertscore)
            save_report(result,Path(a.out)/f'case-{index:04}')
            summary.append(entry);write_json(Path(a.out)/'summary.json',summary)
        print('Saved case reports and summary.json. Estimated labels are not gold evaluation.')
    except (ValueError,RuntimeError,KeyError,OSError,ImportError) as e:
        p.exit(2,f'Error: {e}\n')
if __name__=='__main__': main()
