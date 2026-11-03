from .models import Note, ClaimList, Claim

GENERATION = '''Convert the supplied doctor-patient transcript into a concise SOAP note.
Include only explicitly stated clinical information. Preserve speaker, patient versus
family history, negation, uncertainty, timing, drug dose, units, route, and frequency.
A question is not a positive finding. A differential is not a confirmed diagnosis.
Do not infer normal examinations, negative symptoms, vitals, medications, or treatment.
Use empty arrays for sections without information. Each array item is one note sentence.
Subjective = reported history; Objective = measured/exam findings; Assessment = stated
clinical assessment; Plan = stated future actions. Do not add advice or headings as items.'''
EXTRACTION = '''Decompose this single clinical note sentence into atomic clinical claims.
Every clinical fact in the sentence must be covered, including negative findings.
Resolve pronouns using the note context. Preserve subject, negation, time, uncertainty,
values/units and medication details. Do not add facts or consult outside knowledge.
Each claim must stand alone. Split independent symptoms/findings, but keep a medication
and its dose/route/frequency together. Extract claims from the source sentence only;
other note sentences are context. Never silently omit a difficult claim.'''

def generate_note(transcript, llm):
    if not transcript.strip(): raise ValueError('Transcript is empty.')
    return llm.ask(GENERATION, {'transcript':transcript}, Note)

def extract_claims(note, llm):
    claims = []
    for section, sentences in note.model_dump().items():
        for index, sentence in enumerate(sentences):
            if not sentence.strip(): raise ValueError('Empty note sentence.')
            out = llm.ask(EXTRACTION, {'source_sentence':sentence, 'section':section, 'note_context':note.model_dump()}, ClaimList)
            for x in out.claims:
                claims.append(Claim(id=f'C{len(claims)+1:04}',section=section,source_index=index,source_text=sentence,text=x.text))
    if not claims: raise ValueError('No clinical claims were generated; this is not a successful note.')
    return claims
