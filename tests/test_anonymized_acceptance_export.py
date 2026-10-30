import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_anonymized_rag_acceptance_set.py"
_SPEC = importlib.util.spec_from_file_location("acceptance_export", _SCRIPT)
exporter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(exporter)


def _graph():
    return {
        "entities": [
            {"id": "obstacle:acidification", "type": "obstacle", "name": "土壤酸化", "aliases": ["酸化"]},
            {"id": "measure:liming", "type": "measure", "name": "施用石灰", "aliases": ["石灰"]},
        ],
        "relations": [{
            "id": "rel:1", "type": "addresses",
            "source": "measure:liming", "target": "obstacle:acidification",
            "supporting_document_count": 1,
            "evidence": [{
                "document_id": 1, "document_title": "材料", "page": 2,
                "chunk_index": 3, "quote": "施用石灰可改良土壤酸化。",
            }],
        }],
    }


def test_anonymize_removes_direct_identifiers():
    value, counts = exporter.anonymize(
        "联系人：张三，手机号13812345678，邮箱a@example.com，"
        "地块编号ABC_12345，土壤酸化怎么改良？"
    )

    assert "张三" not in value
    assert "13812345678" not in value
    assert "a@example.com" not in value
    assert "ABC_12345" not in value
    assert sum(counts.values()) >= 4


def test_build_set_excludes_gold_overlap_and_model_calculation():
    records, audit = exporter.build_set(
        ["土壤酸化怎么改良？", "试算土壤酸化改良用量"],
        _graph(), ["土壤酸化怎么改良？"], max_items=50,
    )

    assert records == []
    assert audit["counts"]["gold_overlap"] == 1
    assert audit["counts"]["non_qa"] == 1


def test_definition_question_is_frozen_as_vector_fallback():
    records, _ = exporter.build_set(
        ["什么是土壤酸化"], _graph(), [], max_items=50,
    )

    assert records[0]["expected"]["retrieval_mode"] == "vector_fallback"
    assert records[0]["expected"]["top_relation_ids"] == []

