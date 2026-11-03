from collections import Counter
from datetime import datetime, timezone
import hashlib
from .generation import generate_note, extract_claims
from .retrieval import Retriever
from .models import Claim, Note


def verify_note(note, transcript, llm, verifier, dense=False, top_k=5, radius=1):
    claims=extract_claims(note,llm)
    retriever=Retriever(transcript,dense=dense,radius=radius)
    results=[]; retrieval={}; guards=[]
    for claim in claims:
        evidence=retriever.retrieve(claim.text,top_k)
        retrieval[claim.id]=[e.model_dump() for e in evidence]
        results.append(verifier.verify(claim,evidence))
    kept={k:[] for k in note.model_dump()}
    decisions=[]
    for section,sentences in note.model_dump().items():
        for index,sentence in enumerate(sentences):
            group=[r for r in results if r.claim.section==section and r.claim.source_index==index]
            # Recheck complete source sentence, so an extractor omission alone cannot
            # cause that whole sentence to pass filtering.
            guard=Claim(id=f'S{len(guards)+1:04}',section=section,source_index=index,source_text=sentence,text=sentence)
            evidence=retriever.retrieve(sentence,top_k)
            verdict=verifier.verify(guard,evidence)
            guards.append(verdict)
            retrieval[guard.id]=[e.model_dump() for e in evidence]
            retain=bool(group) and all(r.label=='Supported' for r in group) and verdict.label=='Supported'
            if retain: kept[section].append(sentence)
            decisions.append({'section':section,'source_index':index,'text':sentence,'retained':retain,'claim_ids':[r.claim.id for r in group],'sentence_guard_id':guard.id})
    counts=Counter(r.label for r in results)
    n=len(results)
    return {'original_note':note.model_dump(),'filtered_note':kept,
        'claims':[r.model_dump() for r in results],'sentence_checks':[r.model_dump() for r in guards],
        'retrieved_evidence':retrieval,'sentence_decisions':decisions,
        'metrics':{'total_claims':n,**{k:counts[k] for k in ['Supported','Contradicted','Unverifiable']},
            'model_estimated_unsupported_claim_rate':(counts['Contradicted']+counts['Unverifiable'])/n if n else None,
            'sentence_retention_rate':sum(d['retained'] for d in decisions)/len(decisions) if decisions else None}}

def run(transcript,llm,verifier,note=None,**kwargs):
    original=note or generate_note(transcript,llm)
    result=verify_note(original,transcript,llm,verifier,**kwargs)
    result.update({'schema_version':'1.0','created_at':datetime.now(timezone.utc).isoformat(),
        'transcript':transcript,'transcript_sha256':hashlib.sha256(transcript.encode()).hexdigest(),
        'config':{'provider':type(llm).__name__,'generator_model':getattr(llm,'model','test-double'),'verifier':type(verifier).__name__,
        'verifier_model':getattr(verifier,'MODEL',getattr(getattr(verifier,'llm',None),'model',None)),
        'nli_threshold':getattr(verifier,'threshold',None),'context':getattr(llm,'context',None),'max_output':getattr(llm,'max_output',None),'request_interval':getattr(llm,'interval',None),**kwargs},
        'model_calls':list(getattr(llm,'calls',[])),
        'separate_verifier_calls':list(getattr(getattr(verifier,'llm',None),'calls',[])) if getattr(verifier,'llm',None) is not llm else [],
        'status':'Research draft: model-supported does not mean clinically approved.'})
    return result

def markdown(result):
    lines=['# TrustNote research draft',result['status'],'','## Original SOAP note',Note(**result['original_note']).text(),
        '\n## Filtered SOAP draft',Note(**result['filtered_note']).text(),
        '\n## Claim audit']
    for r in result['claims']:
        lines += [f"\n### {r['claim']['id']} — {r['label']}",r['claim']['text'],r['rationale']]
        for e in r['evidence']:
            lines += [f"Evidence {e['id']} — characters [{e['start']}, {e['end']}):",'```text',e['text'],'```']
    lines += ['\n## Sentence decisions']
    for d in result['sentence_decisions']:
        lines.append(('RETAINED: ' if d['retained'] else 'FLAGGED / REMOVED FROM FILTERED DRAFT: ')+d['text'])
    return '\n\n'.join(lines)
