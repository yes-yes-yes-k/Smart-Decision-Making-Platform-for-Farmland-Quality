"""Exhaustive selected-block shingle audit against selected and exposed sources."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_kg_acceptance_v1 import OUT,verify_freeze
from scripts.experiment_kg_recall import read,write,jsonl,sha
from framework.knowledge_graph.acceptance_data import normalized,assert_isolation

def shingles(s):
    s=normalized(s)
    return {s[i:i+5] for i in range(max(0,len(s)-4))} if len(s)>=80 else set()

def audit():
    verify_freeze();rows=read(OUT/'pool/selection.jsonl');assert_isolation(rows)
    old=read(ROOT/'artifacts/knowledge_platform/gold-v4/visible-inputs.jsonl')
    hist=[(r['sample_id'],shingles(b['text'])) for r in old for b in r['blocks'] if b['block_id']=='chunk']
    current=[shingles(r['text']) for r in rows];conflicts=[];checked=0
    for i,(a,aa) in enumerate(zip(rows,current)):
        if not aa:continue
        for j in range(i):
            b=rows[j];bb=current[j]
            if not bb or a['isolation_group']==b['isolation_group']:continue
            checked+=1
            if min(len(aa),len(bb))/max(len(aa),len(bb))<.85:continue
            score=len(aa&bb)/len(aa|bb)
            if score>=.85:conflicts.append(dict(a=a['sample_id'],b=b['sample_id'],kind='selected_duplicate_group_unresolved',jaccard=score))
        for oldid,bb in hist:
            if not bb:continue
            checked+=1
            if min(len(aa),len(bb))/max(len(aa),len(bb))<.85:continue
            score=len(aa&bb)/len(aa|bb)
            if score>=.85:conflicts.append(dict(a=a['sample_id'],b=oldid,kind='historical_exposure_near_duplicate',jaccard=score))
    jsonl(OUT/'pool/selected-duplicate-conflicts.jsonl',conflicts)
    report=dict(status='fail' if conflicts else 'pass',samples=len(rows),checked_pairs=checked,conflicts=len(conflicts),
        threshold=.85,method='exhaustive normalized character 5-shingle Jaccard on selected-vs-selected and selected-vs-1000 historical blocks',
        selection_sha256=sha(OUT/'pool/selection.jsonl'),semantic_independence_certified=False,
        remaining_limits=['only available historical chunk snapshots audited','short blocks under 80 normalized chars are not semantic-deduplicated','full-corpus semantic duplication cannot be proven absent'])
    write(OUT/'pool/isolation-audit.json',report);print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':audit()
