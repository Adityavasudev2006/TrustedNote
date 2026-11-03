"""BM25 plus optional dense retrieval, fused by reciprocal rank (RRF)."""
import re, math
from collections import Counter
from .models import Evidence

def tokens(s): return re.findall(r"\w+(?:[.-]\w+)*", s.lower())

def windows(transcript, radius=1, max_chars=1100):
    # Preserve exact original offsets. Split long lines at word boundaries, never drop text.
    spans=[]
    for line in re.finditer(r'[^\n]+', transcript):
        start=line.start()
        while start < line.end():
            end=min(start+max_chars, line.end())
            if end < line.end():
                boundary=transcript.rfind(' ',start,end)
                if boundary > start: end=boundary+1
            spans.append((start,end)); start=end
    result=[]
    for i in range(len(spans)):
        lo, hi=max(0,i-radius),min(len(spans),i+radius+1)
        start,end=spans[lo][0],spans[hi-1][1]
        if not result or (start,end)!=(result[-1].start,result[-1].end):
            result.append(Evidence(id=f'E{len(result)+1:04}',text=transcript[start:end],start=start,end=end))
    return result

class Retriever:
    def __init__(self, transcript, dense=False, radius=1):
        self.docs=windows(transcript,radius)
        if not self.docs: raise ValueError('Transcript has no evidence.')
        self.counts=[Counter(tokens(x.text)) for x in self.docs]
        self.avg=sum(sum(c.values()) for c in self.counts)/len(self.counts) or 1
        self.df=Counter(t for c in self.counts for t in c)
        self.encoder=None
        if dense:
            from sentence_transformers import SentenceTransformer
            self.encoder=SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
            self.vectors=self.encoder.encode([x.text for x in self.docs],normalize_embeddings=True)
    def retrieve(self, claim, k=5):
        if k < 1: raise ValueError('top-k must be positive')
        scores=[]
        for c in self.counts:
            dl=sum(c.values())
            score=sum(math.log(1+(len(self.docs)-self.df[t]+.5)/(self.df[t]+.5))*c[t]*2.5/(c[t]+1.5*(.25+.75*dl/self.avg)) for t in set(tokens(claim)) if c[t])
            scores.append(score)
        order=sorted(range(len(scores)),key=lambda i:scores[i],reverse=True)
        if self.encoder is not None:
            q=self.encoder.encode([claim],normalize_embeddings=True)[0]
            dense_order=sorted(range(len(scores)),key=lambda i:float(self.vectors[i]@q),reverse=True)
            fused=Counter()
            for ranked in [order,dense_order]:
                for rank,i in enumerate(ranked,1): fused[i]+=1/(60+rank)
            scores=[fused[i] for i in range(len(scores))]
            order=sorted(range(len(scores)),key=lambda i:scores[i],reverse=True)
        return [self.docs[i].model_copy(update={'score':scores[i]}) for i in order[:k]]
