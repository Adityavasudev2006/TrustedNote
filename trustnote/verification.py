from .models import Judgment, VerifiedClaim

VERIFY = '''Judge whether a clinical claim is grounded in the supplied transcript windows.
Supported: ALL details are explicitly stated or unambiguously entailed.
Contradicted: explicit conflicting evidence concerns the SAME person, time, and clinical
attribute. Unverifiable: absent, ambiguous, partly supported, or evidence is insufficient.
Do not use general medical knowledge to supply missing patient facts. Preserve negation,
uncertainty, temporality, family versus patient, hypothetical versus actual, medication
status, dosage, units, and speaker. A question alone is not evidence of its premise.
Return exact evidence window IDs and a short rationale. Cite opposing evidence as well
as supporting evidence. Unresolved conflicting statements mean Unverifiable.
Evidence IDs must come only from the supplied list; never invent quotations.'''

class LLMVerifier:
    def __init__(self,llm): self.llm=llm
    def verify(self,claim,evidence):
        result=self.llm.ask(VERIFY,{'claim':claim.text,'evidence':[{'id':e.id,'text':e.text} for e in evidence]},Judgment)
        valid={e.id:e for e in evidence}
        flags=[]
        if any(i not in valid for i in result.evidence_ids) or (result.label!='Unverifiable' and not result.evidence_ids):
            flags.append('invalid_or_missing_citation')
            result=Judgment(label='Unverifiable',evidence_ids=[],rationale='Verifier failed evidence citation validation.')
        # Include all retrieved windows separately in report; selected evidence is linked here.
        return VerifiedClaim(claim=claim,label=result.label,evidence=[valid[i] for i in dict.fromkeys(result.evidence_ids)],rationale=result.rationale,flags=flags)

class NLIVerifier:
    MODEL='cross-encoder/nli-deberta-v3-small'
    def __init__(self,threshold=.85,margin=.15):
        if not .5 < threshold <= 1: raise ValueError('NLI threshold must be > .5 and <= 1')
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        self.torch=torch
        self.tokenizer=AutoTokenizer.from_pretrained(self.MODEL)
        self.model=AutoModelForSequenceClassification.from_pretrained(self.MODEL).eval()
        self.threshold,self.margin=threshold,margin
        # Fixed model's published label order: contradiction, entailment, neutral.
        self.labels=['contradiction','entailment','neutral']
    def verify(self,claim,evidence):
        scored=[]; flags=[]
        for e in evidence:
            inputs=self.tokenizer(e.text,claim.text,return_tensors='pt',truncation=False)
            limit=min(self.tokenizer.model_max_length,512)
            if inputs['input_ids'].shape[1] > limit:
                flags.append('nli_window_too_long:'+e.id); continue
            with self.torch.inference_mode():
                probs=self.model(**inputs).logits.softmax(-1)[0].tolist()
            scored.append((e,dict(zip(self.labels,probs))))
        support=[e for e,s in scored if s['entailment']>=self.threshold and s['entailment']-max(s['contradiction'],s['neutral'])>=self.margin]
        conflict=[e for e,s in scored if s['contradiction']>=self.threshold and s['contradiction']-max(s['entailment'],s['neutral'])>=self.margin]
        label='Unverifiable'
        if support and not conflict: label='Supported'
        if conflict and not support: label='Contradicted'
        if support and conflict: flags.append('conflicting_windows')
        # Any skipped window could contain a conflict; abstain instead of asserting support.
        if any(x.startswith('nli_window_too_long') for x in flags): label='Unverifiable'
        maximum={k:max((s[k] for _,s in scored),default=0.) for k in self.labels}
        return VerifiedClaim(claim=claim,label=label,evidence=list({e.id:e for e in support+conflict}.values()),
            rationale='NLI window scores with threshold and margin; scores are not calibrated clinical confidence.',scores=maximum,flags=flags)
