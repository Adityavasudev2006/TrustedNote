import csv, json
from pathlib import Path
LABELS=['Supported','Contradicted','Unverifiable']

def export_annotations(report,path):
    fields=['claim_id','claim','source_sentence','predicted_label','gold_label','gold_evidence','notes']
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in report['claims']:
            w.writerow({'claim_id':r['claim']['id'],'claim':r['claim']['text'],'source_sentence':r['claim']['source_text'],
                'predicted_label':r['label'],'gold_label':'','gold_evidence':'','notes':''})

def score_annotations(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    if not rows: raise ValueError('No annotations')
    for r in rows:
        if r.get('gold_label') not in LABELS or r.get('predicted_label') not in LABELS:
            raise ValueError('Every row needs a valid gold_label and predicted_label; blanks are not scored.')
    matrix={a:{b:0 for b in LABELS} for a in LABELS}
    for r in rows: matrix[r['gold_label']][r['predicted_label']]+=1
    metrics={}
    for label in LABELS:
        tp=matrix[label][label]; fp=sum(matrix[x][label] for x in LABELS if x!=label); fn=sum(matrix[label][x] for x in LABELS if x!=label)
        precision=tp/(tp+fp) if tp+fp else 0.; recall=tp/(tp+fn) if tp+fn else 0.
        metrics[label]={'precision':precision,'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0.,'gold_count':tp+fn}
    return {'n':len(rows),'confusion_matrix_rows_gold_columns_predicted':matrix,'per_class':metrics,
        'macro_f1':sum(v['f1'] for v in metrics.values())/3,
        'accuracy':sum(matrix[x][x] for x in LABELS)/len(rows),
        'human_unsupported_claim_rate':sum(r['gold_label']!='Supported' for r in rows)/len(rows)}

def quality(reference,prediction,bertscore=False):
    from rouge_score import rouge_scorer
    score=rouge_scorer.RougeScorer(['rougeL'],use_stemmer=True).score(reference,prediction)['rougeL']
    out={'rougeL_precision':score.precision,'rougeL_recall':score.recall,'rougeL_f1':score.fmeasure}
    if bertscore:
        if not prediction.strip(): out['bertscore_f1']=0.
        else:
            from bert_score import score as bs
            _,_,f,hashcode=bs([prediction],[reference],lang='en',model_type='distilbert-base-uncased',rescale_with_baseline=False,return_hash=True)
            out.update(bertscore_f1=float(f[0]),bertscore_hash=hashcode)
    return out

def compare_human_labels(report,annotation_path):
    with Path(annotation_path).open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    claims={r['claim']['id']:r for r in report['claims']}
    if len(rows)!=len(claims) or len({r['claim_id'] for r in rows})!=len(rows) or set(claims)!={r['claim_id'] for r in rows}:
        raise ValueError('Annotation rows must match all report claims exactly, with no duplicates.')
    retained={cid for d in report['sentence_decisions'] if d['retained'] for cid in d['claim_ids']}
    for r in rows:
        if r['gold_label'] not in LABELS or r['claim']!=claims[r['claim_id']]['claim']['text']:
            raise ValueError('Gold labels are missing or claim text differs from the report.')
    kept=[r for r in rows if r['claim_id'] in retained]
    n_supported=sum(r['gold_label']=='Supported' for r in rows)
    return {'baseline_human_unsupported_claim_rate':sum(r['gold_label']!='Supported' for r in rows)/len(rows) if rows else None,
        'filtered_human_unsupported_claim_rate':sum(r['gold_label']!='Supported' for r in kept)/len(kept) if kept else None,
        'baseline_claims':len(rows),'filtered_claims':len(kept),
        'supported_claim_retention':sum(r['gold_label']=='Supported' for r in kept)/n_supported if n_supported else None,
        'limitation':'Measures extracted claims only. Independently audit extraction coverage and source-sentence meaning.'}

def entity_f1(path):
    """Exact canonical tuple match on independently annotated entities, not an NER model."""
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    fields=('concept','subject','status','time','value','unit')
    def canon(items):
        result=set()
        for item in items:
            if set(item)!=set(fields): raise ValueError('Each entity requires exactly: '+', '.join(fields))
            if not all(isinstance(item[k],str) for k in fields): raise ValueError('Entity fields must be strings')
            result.add(tuple(item[k].strip().lower() for k in fields))
        return result
    gold,pred=canon(data['reference_entities']),canon(data['predicted_entities'])
    tp=len(gold & pred);p=tp/len(pred) if pred else 0.;r=tp/len(gold) if gold else 0.
    return {'metric':'exact canonical clinical entity tuple F1','reference_count':len(gold),'predicted_count':len(pred),
        'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0.,
        'note':'Requires independently supplied canonical entities; this command does not perform clinical entity extraction.'}
