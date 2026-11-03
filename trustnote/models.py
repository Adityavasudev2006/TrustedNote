from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Label = Literal['Supported', 'Contradicted', 'Unverifiable']
Section = Literal['Subjective', 'Objective', 'Assessment', 'Plan']
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')
class Note(Strict):
    Subjective: list[str]
    Objective: list[str]
    Assessment: list[str]
    Plan: list[str]
    def text(self):
        return '\n\n'.join(k + ':\n' + '\n'.join('- ' + x for x in v) for k,v in self.model_dump().items())
class ExtractedClaim(Strict):
    text: str = Field(min_length=1)
class ClaimList(Strict):
    claims: list[ExtractedClaim] = Field(min_length=1)
class Judgment(Strict):
    label: Label
    evidence_ids: list[str]
    rationale: str
class Claim(Strict):
    id: str
    section: Section
    source_index: int
    source_text: str
    text: str
class Evidence(Strict):
    id: str
    text: str
    start: int
    end: int
    score: float = 0.0
class VerifiedClaim(Strict):
    claim: Claim
    label: Label
    evidence: list[Evidence]
    rationale: str
    scores: dict[str,float] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
