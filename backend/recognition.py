"""Candidate-only native/OCR interface. No silent character substitution."""
import re, unicodedata
from typing import Protocol

CODE=re.compile(r'^\d{3}-[A-Z]+$')
def normalize_code(raw):
    value=unicodedata.normalize('NFKC',raw).upper().strip()
    value=re.sub('[\u00ad‐‑‒–—−]','-',value)
    return re.sub(r'\s*-\s*','-',value)
def classify(raw):
    normalized=normalize_code(raw)
    return {'raw':raw,'normalized':normalized,'kind':'piece_candidate' if CODE.fullmatch(normalized) else 'annotation',
            'hypotheses':[], 'approved':False}
class OCREngine(Protocol):
    name:str
    def read(self,image_path:str,orientation:int=0)->list[dict]: ...
def deduplicate(observations,tolerance=2):
    result=[]
    for obs in sorted(observations,key=lambda o:o.get('confidence',0),reverse=True):
        x,y=obs['polygon'][0]
        if not any(obs['normalized']==p['normalized'] and abs(x-p['polygon'][0][0])<=tolerance and abs(y-p['polygon'][0][1])<=tolerance for p in result): result.append(obs)
    return result
def propose_identity(code,contexts,catalog):
    """Separate evidence axes. Only a human decision can publish a link."""
    candidates=[]
    for candidate in contexts:
        if candidate['code']!=code: continue
        fields=['rack','axes','level','side']
        known=[f for f in fields if candidate.get(f) and catalog.get(f)]
        conflict=[f for f in known if candidate[f]!=catalog[f]]
        candidates.append({'instance_id':candidate['id'],'reading_score':catalog.get('reading_confidence'),
            'geometry_score':None,'identity_score':len(known)/4 if not conflict else 0,
            'blocking':['localização conflitante'] if conflict else ['identidade exige revisão'],
            'evidence':{'compatible_fields':[f for f in known if f not in conflict],'conflicts':conflict}})
    return {'state':'AMBÍGUA' if len(candidates)>1 else 'NÃO ASSOCIADA','candidates':candidates,'algorithm':'context-candidate-1','auto_approval':False}
