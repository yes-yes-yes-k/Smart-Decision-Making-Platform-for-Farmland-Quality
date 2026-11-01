"""Archive source-read AI spot checks; block release without rewriting labels."""
from collections import Counter
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,readlines,lines,dump,budget_snapshot
from framework.knowledge_graph.benchmark_rebuild import sha256_file

CASES={
 'rebuild-v2:118:54:d1e49ea009a1':('test','fail',[
    ('entity_boundary_and_type','vesasanindicator','The selected letters are part of serves as an indicator, not a soil obstacle.'),
    ('entity_boundary','POM-poredistanceser','The selection includes the beginning of serves; literal source membership does not certify a complete entity.'),
    ('unsupported_relation','POM-poredistanceservesasanindicator','The assertion describes a proxy for POM occlusion, not an obstacle named vesasanindicator.')]),
 'rebuild-v2:163:72:d56cbb16b92e':('test','fail',[
    ('unit_as_indicator','lomc(','Rotated/OCR chart unit characters are not a named soil-quality property.'),
    ('boundary','macroaggregate,','A trailing list comma is included in the entity; the offset gate cannot detect boundary semantics.')]),
 'rebuild-v2:100:72:846326ed7e9f':('test','fail',[
    ('entity_boundary','mpaction','The source contains compaction, but the selected entity omits co.'),
    ('insufficient_evidence_window','limiting the number of passes can protect the soil structure from s','This selected assertion ends mid-word and does not include the obstacle.')]),
 'rebuild-v2:314:36:c74c6296d698':('test','fail',[
    ('entity_boundary','envalues','The source contains nitrogenvalues, but this is a word fragment.'),
    ('relation_target_drift','Nuseefficiency','The later maize statement names N uptake and N recovery efficiency; its relation to the earlier Nuseefficiency label requires adjudication, not automatic equivalence.')]),
 'rebuild-v2:615:4:bd2f0f09bf20':('calibration','fail',[
    ('laboratory_method_as_agronomic_measure','利用氟化锭一盐酸溶液浸','The paragraph is laboratory soil phosphorus extraction, not an agricultural intervention; the selected action also ends before 提.')]),
 'rebuild-v2:746:5:61cd65dc06df':('calibration','no_defect_confirmed_in_spot_check',[]),
 'rebuild-v2:824:13:4bb35750b0fb':('calibration','requires_adjudication',[
    ('predicate_scope','根据 GB/T 33469确定的耕地质量等级','A standard used to determine quality grade does not by itself establish that the standard includes that concept as an indicator; audit the predicate against the frozen definition.')]),
 'rebuild-v2:148:92:5db023058f7b':('calibration','fail',[
    ('entity_boundary','oilcarboninc','This is part of Soilcarbonincreased, not a complete indicator.'),
    ('entity_boundary','chara','This is an internal fragment of biocharamendment.'),
    ('bibliography_and_column_join','reapplicationofbiocharon','The chunk interleaves separate bibliography columns; endpoints alone do not support a causal relationship across them.')]),
 'rebuild-v2:582:2:da2e64843750':('calibration','no_defect_confirmed_in_spot_check',[]),
 'rebuild-v2:482:3:0033ef15f31d':('calibration','requires_adjudication',[
    ('possible_missing_entity','有效土层厚度','The reference has no soil-property entity while the source discusses effective soil depth. Determine entity scope independently; do not convert missing labels into a negative automatically.')]),
 'rebuild-v2:61:70:936975187cc4':('calibration','requires_adjudication',[
    ('generic_property_scope','soil properties','The title contains a generic property category, not a specific measured property; verify against the handbook exclusion scope.')]),
 'rebuild-v2:136:66:129f535e790d':('calibration','no_defect_confirmed_in_spot_check',[]),
}


def main():
    dest=OUT/'semantic-quality-audit-v1'
    if (dest/'manifest.json').exists():
        for f in json.loads((dest/'manifest.json').read_text(encoding='utf-8'))['files']:
            if sha256_file(ROOT/f['path'])!=f['sha256']:raise ValueError('semantic_audit_archive_changed')
        print('frozen_semantic_failure_audit_verified');return
    frames={part:readlines(OUT/path) for part,path in [
        ('calibration','calibration-silver-v1/references.jsonl'),('test','reference-release-v1/test/references.jsonl')]}
    byid={r['sample_id']:r for frame in frames.values() for r in frame}
    items=[];snapshots=[]
    for sid,(part,judgment,findings) in CASES.items():
        ref=byid[sid];blocks={b['block_id']:b['text'] for b in ref['visible_input']['blocks']}
        bound=[]
        for kind,quote,reason in findings:
            hits=[dict(block_id=block,start=text.index(quote),end=text.index(quote)+len(quote),text=quote)
                for block,text in blocks.items() if quote in text]
            if not hits:raise ValueError('finding_not_bound_to_source:'+sid+':'+quote)
            bound.append(dict(category=kind,source_spans=hits,reason=reason))
        items.append(dict(sample_id=sid,partition=part,judgment=judgment,findings=bound,
            reviewer='Codex_AI_source_read_spot_audit',expert_certified=False,labels_modified=False))
        snapshots.append(ref)
    lines(dest/'items.jsonl',items);lines(dest/'reviewed-reference-snapshots.jsonl',snapshots)
    frame=dict(selection='deterministic_hash_order_of_available_reference_ids_then_relation_positive_filter',
        test_seed='literal-evidence-audit-v1:',test_take_relation_positive=4,
        calibration_seed='calibration-semantic-audit-v1:',calibration_take_per_relation_presence=4,
        sample_ids_by_partition={part:[r['sample_id'] for r in rows] for part,rows in frames.items()},
        not_a_representative_accuracy_sample=True)
    dump(dest/'selection-frame.json',frame)
    report=dict(status='fail',release_hold=True,samples_reviewed=len(items),
        judgments_by_partition={part:dict(Counter(i['judgment'] for i in items if i['partition']==part)) for part in frames},
        freeze_or_formal_acceptance_allowed=False,existing_calibration_hashes_preserved=True,
        frozen_calibration_current_use='development_diagnostic_only_pending_versioned_semantic_resolution',
        final_references_current_use='unfinished_drafts_not_acceptance_reference',
        pure_literal_span_and_title_assertion_gates_are_necessary_not_sufficient=True,
        failures_require_source_adjudication_not_automatic_deletion=True,
        population_error_rate_estimated=False,all_500_semantically_reviewed=False,
        reviewer_is_AI_not_expert=True,shared_budget=budget_snapshot(),
        next_steps=['audit all available calibration and final drafts using source-bound defect categories',
            'pilot a versioned selector contract that cross-checks verbatim surface against selected coordinates',
            'judge semantics on materialized fragments and complete assertion windows, not numeric indices alone',
            'validate fresh controls and historical failed sources before any further batch calls',
            'retain frozen membership, original labels and budget history; no automatic total-cap increase'])
    dump(dest/'report.json',report)
    files=[Path(__file__),dest/'items.jsonl',dest/'reviewed-reference-snapshots.jsonl',dest/'selection-frame.json',dest/'report.json']
    dump(dest/'manifest.json',dict(status='frozen_failure_evidence_not_reference_labels',
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in files]))
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
