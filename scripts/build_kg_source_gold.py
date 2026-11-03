"""Version reviewed labels with literal source spans, without model predictions."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_kg_gold_sources import locate_quote

# Source-only review decisions. Each pair selects an inclusive literal span.
SPANS = {
    5: ('改善灌溉条件', '防止农作物产生渍害'),
    11: ('坡耕地土壤养分障碍主要由全磷', '主要分布于江西省、广东省和广西省。'),
    18: ('部分是因为平原地区地势低洼', '耕地内涝。'),
    20: ('区域补充性指标包括耕层厚度', '各区域耕地质量划分指标见附录'),
    21: ('区域补充性指标包括耕层厚度', '各区域耕地质量划分指标见附录'),
    23: ('通过深翻改土和引入客土等手段', '从而实质性增加有效土层厚度'),
    39: ('采用障碍度诊断模型进一步分析发现', '时土壤存在障碍问题'),
    74: ('可采用深松与深耕的耕作技术打破犁底层', '以及增加耕层厚度'),
    84: ('对于土壤有机质含量较低的问题', '有效提升土壤有机质含量。'),
    93: ('采用测土配方施肥方法平衡施肥', '避免养分过剩或匮乏'),
}
for _row in (24, 28, 56, 59, 75, 85):
    SPANS[_row] = ('基础性指标包括地形部位', '区域补充性指标包括')
for _row in (42, 44, 54):
    SPANS[_row] = ('地形部位、有效土层厚度', '依据实地踏勘情况赋值。')
DEFERRED = {4, 10, 29, 30, 43, 81}
PARENT_SHA256 = '16af6ee0743856f1a851f841e09b6cfbb6af79c1df83a70b4d7751845e3f29dd'


def reviewed_span(content, start_marker, end_marker):
    offsets = [i for i, c in enumerate(content) if not c.isspace()]
    folded = ''.join(content[i] for i in offsets)
    start_marker = ''.join(start_marker.split())
    end_marker = ''.join(end_marker.split())
    start = folded.find(start_marker)
    end = folded.find(end_marker, start + len(start_marker)) if start >= 0 else -1
    if end < 0:
        return None
    return offsets[start], offsets[end + len(end_marker) - 1] + 1


def build(gold, snapshots):
    chunks = [chunk for request in snapshots['requests'] for chunk in request['chunks']]
    rows, decisions = [], []
    for index, original in enumerate(gold):
        entry = dict(original_row=index, relation_id=original['relation']['id'])
        if index in DEFERRED:
            entry.update(action='deferred', reason='laboratory-test sentence crosses pages 44/45; not a complete single-chunk evidence unit')
            decisions.append(entry)
            continue
        evidence = original['evidence']
        options = []
        for chunk in chunks:
            if (chunk['document_id'], chunk['page']) != (evidence['document_id'], evidence['page']):
                continue
            if index in SPANS:
                span = reviewed_span(chunk['content'], *SPANS[index])
                match = dict(span_start=span[0], span_end=span[1], quote=chunk['content'][span[0]:span[1]], kind='source_reviewed_replacement') if span else None
            else:
                match = locate_quote(chunk['content'], evidence['quote'])
            if match:
                options.append((chunk, match))
        if not options:
            raise ValueError(f'No reviewed literal source for row {index}')
        # Stable source-based choice; never based on extraction predictions.
        options.sort(key=lambda x: (x[0]['chunk_index'] != evidence.get('chunk_index'), x[0]['chunk_index']))
        chunk, match = options[0]
        row = deepcopy(original)
        row['gold_version'] = 'cultivated-land-extraction-gold-v2-source-verified'
        row['evidence'].update(chunk_index=chunk['chunk_index'], quote=match['quote'],
            quote_sha256=hashlib.sha256(match['quote'].encode()).hexdigest(),
            span_start=match['span_start'], span_end=match['span_end'],
            source_chunk_sha256=hashlib.sha256(chunk['content'].encode()).hexdigest())
        row['source_revision'] = dict(original_row=index, method=match['kind'],
            review_actor='codex-source-review', independent_human_review=False,
            relation_labels_changed=False)
        rows.append(row)
        entry.update(action='included', method=match['kind'], original_evidence=evidence,
            revised_evidence=row['evidence'], relation_labels_changed=False)
        decisions.append(entry)
    return rows, decisions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gold', type=Path, default=ROOT/'artifacts/minimal_kg/extraction_gold_v1.jsonl')
    parser.add_argument('--snapshots', type=Path, default=ROOT/'.tools/kg-gold-evaluation/v1/input-manifest.json')
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/minimal_kg/extraction_gold_v2.jsonl')
    args = parser.parse_args()
    if args.output.resolve() == args.gold.resolve():
        parser.error('new gold must not overwrite its parent')
    gold_bytes = args.gold.read_bytes()
    if hashlib.sha256(gold_bytes).hexdigest() != PARENT_SHA256:
        parser.error('source-review decisions require the exact reviewed v1 parent')
    rows, decisions = build([json.loads(line) for line in gold_bytes.decode().splitlines() if line.strip()],
        json.loads(args.snapshots.read_text(encoding='utf-8')))
    output = ''.join(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n' for row in rows)
    args.output.write_text(output,encoding='utf-8')
    manifest = dict(gold_version='cultivated-land-extraction-gold-v2-source-verified',
        parent_sha256=hashlib.sha256(gold_bytes).hexdigest(), output_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
        snapshot_sha256=hashlib.sha256(args.snapshots.read_bytes()).hexdigest(),
        evidence_count=len(rows), original_evidence_count=len(gold_bytes.decode().splitlines()),
        deferred_count=len(DEFERRED), review_actor='codex-source-review', independent_human_review=False,
        predictions_used=False, relation_labels_changed=False, decisions=decisions)
    args.output.with_suffix('.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:val for key,val in manifest.items() if key!='decisions'}))


if __name__ == '__main__':
    main()
