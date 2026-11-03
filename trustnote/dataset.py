import csv, json, hashlib
from pathlib import Path

def read_rows(path):
    path=Path(path)
    if path.suffix.lower()=='.csv':
        with path.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
    if path.suffix.lower()=='.jsonl':
        return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data,list): raise ValueError('JSON must be a list of records; use CSV or JSONL otherwise.')
    return data

def convert(path,output,split,transcript_column=None,note_column=None):
    rows=read_rows(path)
    if not rows: raise ValueError('Dataset is empty')
    keys={k.lower():k for k in rows[0]}
    def choose(explicit,aliases):
        if explicit:
            if explicit not in rows[0]: raise ValueError(f'Unknown column {explicit}. Available: {list(rows[0])}')
            return explicit
        for name in aliases:
            if name in keys: return keys[name]
        raise ValueError(f'Cannot map dataset columns. Available: {list(rows[0])}. Supply explicit column flags.')
    tc=choose(transcript_column,['dialogue','transcript','conversation','src'])
    nc=choose(note_column,['note','section_text','summary','tgt','reference_note'])
    records=[]; seen=set()
    for i,row in enumerate(rows):
        transcript,reference=row.get(tc),row.get(nc)
        if not isinstance(transcript,str) or not transcript.strip() or not isinstance(reference,str) or not reference.strip():
            raise ValueError(f'Row {i+1} has an empty/non-text transcript or reference; nothing imported.')
        digest=hashlib.sha256(transcript.strip().encode()).hexdigest()
        if digest in seen: raise ValueError(f'Duplicate transcript in row {i+1}; inspect dataset variants before importing.')
        seen.add(digest)
        records.append({'id':f'{split}-{i+1:04}','source_id':str(row.get('encounter_id',row.get('ID',row.get('id',i+1)))),
            'split':split,'transcript':transcript,'reference_note':reference,'source_file':Path(path).name,
            'transcript_sha256':digest})
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in records)+'\n',encoding='utf-8')
    return {'rows':len(records),'transcript_column':tc,'note_column':nc,'split':split}

def check_overlap(paths):
    seen={}; collisions=[]
    for path in paths:
        for row in read_rows(path):
            digest=hashlib.sha256(row['transcript'].strip().encode()).hexdigest()
            if digest in seen: collisions.append({'first':seen[digest],'second':{'file':str(path),'id':row['id']}})
            else: seen[digest]={'file':str(path),'id':row['id']}
    return collisions

CORPUS_FILES={
    'train':('train.csv',),
    'valid':('valid.csv',),
    'test1':('clinicalnlp_taskB_test1.csv','clinicalnlptaskB_test1.csv'),
    'test2':('clinicalnlp_taskC_test2.csv',),
    'test3':('clef_taskC_test3.csv',),
}

def prepare_corpus(corpus,output):
    """Import the five official challenge splits without mixing ASR variants."""
    import tempfile, shutil
    corpus=Path(corpus)
    challenge=corpus if corpus.name=='challenge_data' else corpus/'challenge_data'
    if not challenge.is_dir(): raise ValueError('Expected aci-bench-corpus/challenge_data containing the five main CSV files.')
    files={p.name.lower():p for p in challenge.iterdir() if p.is_file()}
    selected={}
    for split,names in CORPUS_FILES.items():
        matches=[files[n.lower()] for n in names if n.lower() in files]
        if len(matches)!=1: raise ValueError(f'Expected exactly one file for {split}: {names}; found {len(matches)}')
        selected[split]=matches[0]
    output=Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output folder is not empty. Choose a fresh --out folder to preserve previous imports.')
    with tempfile.TemporaryDirectory() as temp:
        stage=Path(temp); summary={}; seen_ids={}
        for split,path in selected.items():
            summary[split]=convert(path,stage/f'{split}.jsonl',split)
            summary[split]['source_file']=path.name
            summary[split]['file_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            raw=read_rows(path)
            for row in raw:
                lower={k.lower():v for k,v in row.items()}
                encounter=lower.get('encounter_id') or lower.get('id')
                if encounter:
                    key=(lower.get('dataset',''),str(encounter).strip())
                    if key in seen_ids: raise ValueError(f'Repeated encounter {key} in {seen_ids[key]} and {split}; inspect split overlap.')
                    seen_ids[key]=split
        collisions=check_overlap([stage/f'{s}.jsonl' for s in selected])
        if collisions: raise ValueError('Exact transcript overlap across splits; inspect data before proceeding.')
        expected={'train':67,'valid':20,'test1':40,'test2':40,'test3':40}
        warnings=[f'{s}: expected {expected[s]} rows, found {v["rows"]}; confirm dataset version.' for s,v in summary.items() if v['rows']!=expected[s]]
        manifest={'source':'ACI-Bench challenge_data','official_url':'https://github.com/wyim/aci-bench',
            'splits':summary,'total_rows':sum(v['rows'] for v in summary.values()),'warnings':warnings,
            'excluded':'Metadata CSVs and src_experiment_data variants are not imported.'}
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        output.mkdir(parents=True,exist_ok=True)
        for p in stage.iterdir(): shutil.copy2(p,output/p.name)
    return manifest
