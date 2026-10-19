"""Local-only evidence retrieval bound to validated model claims."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from pydantic import Field

from .contracts import EvidenceBundle, EvidenceItem, StrictModel, TaskResult
from .prompt_catalog import RESEARCHER_PROMPT


def canonical_claims_from_results(task_results:dict[str,TaskResult])->list[dict[str,str]]:
    claims=[]
    for result in task_results.values():
        if result.status!="succeeded": continue
        for key,value in result.payload.items():
            if isinstance(value,(str,int,float,bool)) and key!="parcel_id":
                claims.append({"claim_id":f"{result.agent_id}.{key}","agent_id":result.agent_id,"field":key,"value":str(value)})
    return claims


class EvidenceQuery(StrictModel):
    claim_id:str
    query:str=Field(min_length=2,max_length=120)
class EvidenceQueries(StrictModel):
    queries:tuple[EvidenceQuery,...]=Field(max_length=12)
@dataclass(frozen=True)
class EvidenceResearchOutcome:
    bundle:EvidenceBundle
    degradation:str|None
class EvidenceUnavailable(RuntimeError): pass


class EvidenceResearcher:
    def __init__(self,runner,rag): self._runner,self._rag=runner,rag
    def research(self,*,task_results:dict[str,TaskResult],claims:list[dict[str,str]],user_id:int|None=None)->EvidenceBundle:
        allowed={c["claim_id"] for c in claims}
        queries=self._runner.generate(role="researcher",prompt=f"{RESEARCHER_PROMPT.system}\nclaims={claims}",schema=EvidenceQueries)
        items=[]; supported=set()
        for query in queries.queries:
            if query.claim_id not in allowed: continue
            for hit in self._rag.search_documents(query.query,user_id=user_id):
                meta=hit.get("metadata") or {}; source=str(meta.get("source") or "unknown")
                source_id=f"{source}:{meta.get('chunk_index','x')}:{meta.get('page','x')}"
                items.append(EvidenceItem(source_id=source_id,doc_name=str(meta.get("doc_name") or source),chunk_index=meta.get("chunk_index"),page=meta.get("page"),claim_ids=(query.claim_id,),score=hit.get("score")))
                supported.add(query.claim_id)
        return EvidenceBundle(items=tuple(items),unsupported_claims=tuple(sorted(allowed-supported)))
    def research_safe(self,**kwargs)->EvidenceResearchOutcome:
        try: return EvidenceResearchOutcome(self.research(**kwargs),None)
        except Exception: return EvidenceResearchOutcome(EvidenceBundle(items=(),unsupported_claims=tuple(c["claim_id"] for c in kwargs["claims"])),"local_evidence_unavailable")
