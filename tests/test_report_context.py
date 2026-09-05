# tests/test_report_context.py
r"""数据驱动报告生成测试（OpenSpec: data-driven-report-generation）。

覆盖任务 7.1-7.7：
- 7.1 normalize_scope：parcel/region/旧 area_code 三种输入
- 7.2 report_type → model 子集映射：UNSUPPORTED / UNKNOWN / 正常
- 7.3 model-4/5 复用"先读库后补算"命中/未命中，含指标缺失降级
- 7.4 区域采样阈值触发与未触发
- 7.5 集成：单地块酸化治理报告，正文含 model-4 用量表与溯源小节
- 7.6 集成：区域有机质提升报告，正文含 region_stats 聚合表
- 7.7 回归：旧请求体 {report_type, area_code} 仍可生成报告

不依赖真实 DB / LLM：
- ParcelInfo / AcidificationRemediationResult / OrganicMatterResult 经 mock 替换
- llm_service.generate 经 mock 替换为确定性 HTML
"""
import sys
import types
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# 测试环境 stub：geoalchemy2 未安装时用 String 代替 Geometry
# ---------------------------------------------------------------------------
if "geoalchemy2" not in sys.modules:
    from sqlalchemy import String

    _geo_stub = types.ModuleType("geoalchemy2")

    class _Geometry:
        def __new__(cls, *args, **kwargs):
            return String()

    _geo_stub.Geometry = _Geometry
    sys.modules["geoalchemy2"] = _geo_stub

# 确保模块加载以便后续 patch 解析属性
import framework.models.thematic_model  # noqa: F401
from src.ai_culti_demo.report_context import (
    ReportContextError,
    UNSUPPORTED_REPORT_TYPES,
    REPORT_TYPE_TO_AGENT,
    normalize_scope,
    resolve_parcel_ids,
    load_indicators,
    compute_model_results,
    compute_region_stats,
    build_report_context,
)
from src.ai_culti_demo.report import generate_report


# ---------------------------------------------------------------------------
# 7.1 normalize_scope
# ---------------------------------------------------------------------------

def test_normalize_scope_parcel():
    """parcel scope 直接归一化。"""
    assert normalize_scope({"type": "parcel", "id": "P001"}) == {"type": "parcel", "id": "P001"}


def test_normalize_scope_region():
    """region scope 直接归一化。"""
    assert normalize_scope({"type": "region", "id": "韶关市"}) == {"type": "region", "id": "韶关市"}


def test_normalize_scope_legacy_area_code():
    """旧 area_code 字符串按 region 范围兼容解析。"""
    assert normalize_scope(None, area_code="韶关市") == {"type": "region", "id": "韶关市"}


def test_normalize_scope_missing_raises():
    """scope 与 area_code 均缺省时抛 MISSING_PARAMS。"""
    with pytest.raises(ReportContextError) as exc_info:
        normalize_scope(None, area_code=None)
    assert exc_info.value.code == "MISSING_PARAMS"


# ---------------------------------------------------------------------------
# 7.2 report_type → model 子集映射
# ---------------------------------------------------------------------------

def test_report_type_mapping_acidification():
    """acidification_treatment → model-4。"""
    assert REPORT_TYPE_TO_AGENT["acidification_treatment"] == "model-4"


def test_report_type_mapping_organic():
    """organic_matter_improvement → model-5。"""
    assert REPORT_TYPE_TO_AGENT["organic_matter_improvement"] == "model-5"


def test_report_type_unsupported_set():
    """方案类模板在 UNSUPPORTED_REPORT_TYPES 中。"""
    assert "farmland_protection_upgrade" in UNSUPPORTED_REPORT_TYPES
    assert "supplementary_farmland" in UNSUPPORTED_REPORT_TYPES


def test_build_context_rejects_unsupported():
    """方案类报告类型在聚合入口被拒绝。"""
    for rt in UNSUPPORTED_REPORT_TYPES:
        with pytest.raises(ReportContextError) as exc_info:
            build_report_context(rt, {"type": "region", "id": "X"})
        assert exc_info.value.code == "UNSUPPORTED_REPORT_TYPE"


def test_build_context_rejects_unknown():
    """未知报告类型返回 UNKNOWN_REPORT_TYPE。"""
    with pytest.raises(ReportContextError) as exc_info:
        build_report_context("nonexistent_type", {"type": "region", "id": "X"})
    assert exc_info.value.code == "UNKNOWN_REPORT_TYPE"


def test_generate_report_rejects_unsupported():
    """generate_report 对方案类返回 UNSUPPORTED_REPORT_TYPE，不进入聚合。"""
    for rt in UNSUPPORTED_REPORT_TYPES:
        result = generate_report(rt, {"type": "region", "id": "X"})
        assert result["status"] == "error"
        assert result["error"]["code"] == "UNSUPPORTED_REPORT_TYPE"


def test_generate_report_rejects_unknown():
    """generate_report 对未知类型返回 UNKNOWN_REPORT_TYPE。"""
    result = generate_report("nonexistent_type", {"type": "region", "id": "X"})
    assert result["status"] == "error"
    assert result["error"]["code"] == "UNKNOWN_REPORT_TYPE"


# ---------------------------------------------------------------------------
# 辅助：构造 mock 地块记录
# ---------------------------------------------------------------------------

def _make_parcel_record(pid, ph=5.0, som=20.0, land_type="upland", fertilizer_type="urea", target_ph=6.5):
    return {
        "parcel_id": pid,
        "soil_indicators": {"soil_ph": ph, "organic_matter": som},
        "land_type": land_type,
        "fertilizer_type": fertilizer_type,
        "target_ph": target_ph,
        "area_code": "TEST_REGION",
    }


# ---------------------------------------------------------------------------
# 7.3 model-4/5 复用"先读库后补算"命中/未命中，含指标缺失降级
# ---------------------------------------------------------------------------

def test_model4_db_hit_reuses_result(monkeypatch):
    """model-4 读库命中时复用，不触发补算。"""
    parcel_records = [_make_parcel_record("P001")]

    def fake_read_db(pid):
        return {
            "parcel_id": pid, "soil_ph": 4.5, "exchangeable_hydrogen": 1.2,
            "exchangeable_aluminum": 3.0, "target_ph": 6.5,
            "soil_conditioner_dosage": 100.0, "woody_peat_dosage": 200.0,
            "model_version": "v1_db", "source": "db",
        }

    def fake_compute(rec):
        raise AssertionError("读库命中时不应触发补算")

    monkeypatch.setattr("src.ai_culti_demo.report_context._read_model4_from_db", fake_read_db)
    monkeypatch.setattr("src.ai_culti_demo.report_context._compute_model4", fake_compute)

    results, info = compute_model_results("model-4", parcel_records, {"type": "parcel", "id": "P001"})
    m4 = results["model-4"]
    assert len(m4) == 1
    assert m4[0]["source"] == "db"
    assert info["db_hits"] == 1
    assert info["computed"] == 0


def test_model4_db_miss_triggers_compute(monkeypatch):
    """model-4 读库未命中时触发补算，补算不落库。"""
    parcel_records = [_make_parcel_record("P001")]

    monkeypatch.setattr("src.ai_culti_demo.report_context._read_model4_from_db", lambda pid: None)
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context._compute_model4",
        lambda rec: {
            "parcel_id": rec["parcel_id"], "soil_ph": 5.0,
            "lime_dosage": 80.0, "organic_fertilizer_dosage": 150.0,
            "model_version": "process_v2_compute", "source": "computed",
        },
    )

    results, info = compute_model_results("model-4", parcel_records, {"type": "parcel", "id": "P001"})
    m4 = results["model-4"]
    assert len(m4) == 1
    assert m4[0]["source"] == "computed"
    assert info["db_hits"] == 0
    assert info["computed"] == 1


def test_model4_missing_indicators_skipped():
    """指标缺失的地块记入 missing 并跳过 model 计算。"""
    # load_indicators 对无 soil_indicators 的记录返回 missing
    fake_record = MagicMock()
    fake_record.get_parcel_record.return_value = {"parcel_id": "P001", "soil_indicators": None}
    with patch("framework.domain.data.parcel_data_accessor.ParcelDataAccessor") as MockAccessor:
        MockAccessor.return_value = fake_record
        snapshot, missing = load_indicators(["P001"])
    assert snapshot == []
    assert missing == ["P001"]


def test_model5_db_hit_reuses_latest(monkeypatch):
    """model-5 读库命中最新县级结果时复用。"""
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context._read_model5_latest",
        lambda: {
            "organic_fertilizer_dosage": 300.0, "level": "中",
            "source": "db",
        },
    )
    results, info = compute_model_results("model-5", [_make_parcel_record("P001")], {"type": "parcel", "id": "P001"})
    m5 = results["model-5"]
    assert m5 is not None
    assert m5["source"] == "db"
    assert info["db_hits"] == 1


def test_model5_db_miss_computes_for_parcel(monkeypatch):
    """model-5 读库未命中时按 parcel 补算。"""
    monkeypatch.setattr("src.ai_culti_demo.report_context._read_model5_latest", lambda: None)
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context._compute_model5_for_parcel",
        lambda rec: {
            "parcel_id": rec["parcel_id"], "organic_matter": 15.0,
            "organic_fertilizer_dosage": 250.0, "level": "低",
            "source": "computed",
        },
    )
    results, info = compute_model_results("model-5", [_make_parcel_record("P001")], {"type": "parcel", "id": "P001"})
    m5 = results["model-5"]
    assert m5 is not None
    assert m5["source"] == "computed"
    assert info["computed"] == 1


# ---------------------------------------------------------------------------
# 7.4 区域采样阈值触发与未触发
# ---------------------------------------------------------------------------

def test_model4_region_sampling_triggered(monkeypatch):
    """区域范围且需补算数 > 阈值时触发采样，标注采样比例。"""
    monkeypatch.setattr("src.ai_culti_demo.report_context.REGION_SAMPLE_THRESHOLD", 3)
    # 5 个地块，全部读库未命中 → 需补算 5 > 阈值 3 → 采样
    records = [_make_parcel_record(f"P{i}") for i in range(5)]
    monkeypatch.setattr("src.ai_culti_demo.report_context._read_model4_from_db", lambda pid: None)
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context._compute_model4",
        lambda rec: {"parcel_id": rec["parcel_id"], "source": "computed", "model_version": "v"},
    )
    _, info = compute_model_results("model-4", records, {"type": "region", "id": "R"})
    assert info["applied"] is True
    assert info["sampled"] == 3
    assert info["need_compute"] == 5


def test_model4_region_sampling_not_triggered(monkeypatch):
    """区域范围但需补算数 ≤ 阈值时不触发采样。"""
    monkeypatch.setattr("src.ai_culti_demo.report_context.REGION_SAMPLE_THRESHOLD", 10)
    records = [_make_parcel_record(f"P{i}") for i in range(3)]
    monkeypatch.setattr("src.ai_culti_demo.report_context._read_model4_from_db", lambda pid: None)
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context._compute_model4",
        lambda rec: {"parcel_id": rec["parcel_id"], "source": "computed", "model_version": "v"},
    )
    _, info = compute_model_results("model-4", records, {"type": "region", "id": "R"})
    assert info["applied"] is False
    assert info["computed"] == 3


def test_model4_parcel_scope_no_sampling(monkeypatch):
    """parcel 范围不触发采样，即使需补算。"""
    monkeypatch.setattr("src.ai_culti_demo.report_context.REGION_SAMPLE_THRESHOLD", 1)
    records = [_make_parcel_record(f"P{i}") for i in range(3)]
    monkeypatch.setattr("src.ai_culti_demo.report_context._read_model4_from_db", lambda pid: None)
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context._compute_model4",
        lambda rec: {"parcel_id": rec["parcel_id"], "source": "computed", "model_version": "v"},
    )
    _, info = compute_model_results("model-4", records, {"type": "parcel", "id": "P0"})
    assert info["applied"] is False


# ---------------------------------------------------------------------------
# 7.5 集成：单地块酸化治理报告生成
# ---------------------------------------------------------------------------

def test_integration_acidification_parcel_report(monkeypatch):
    """单地块酸化治理报告：正文含 model-4 用量表 + 溯源小节。"""
    # Mock scope 解析：parcel 范围返回单地块
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.resolve_parcel_ids",
        lambda scope: [scope["id"]],
    )
    # Mock 指标加载
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.load_indicators",
        lambda pids: ([_make_parcel_record(pids[0])], []),
    )
    # Mock model-4 计算（读库命中）
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context._read_model4_from_db",
        lambda pid: {
            "parcel_id": pid, "soil_ph": 4.5, "exchangeable_hydrogen": 1.2,
            "exchangeable_aluminum": 3.0, "target_ph": 6.5,
            "soil_conditioner_dosage": 100.0, "woody_peat_dosage": 200.0,
            "model_version": "v1_db", "source": "db",
        },
    )
    # Mock LLM 返回确定性 HTML
    monkeypatch.setattr(
        "src.ai_culti_demo.report.llm_service.generate",
        lambda prompt, **kwargs: {"success": True, "content": f"<p>LLM 内容：{prompt[:20]}...</p>"},
    )

    result = generate_report("acidification_treatment", {"type": "parcel", "id": "P001"})

    assert result["status"] == "ok"
    content = result["content"]
    # 正文含 model-4 用量表（data 章节 data_renderer 直接产 HTML）
    assert "<table>" in content
    assert "P001" in content
    # 溯源小节
    assert "数据来源与计算依据" in content
    assert "parcel_info" in content


# ---------------------------------------------------------------------------
# 7.6 集成：区域有机质提升报告生成
# ---------------------------------------------------------------------------

def test_integration_organic_matter_region_report(monkeypatch):
    """区域有机质提升报告：正文含 region_stats 聚合表。"""
    # Mock scope 解析：region 范围返回多个地块
    parcel_ids = ["P001", "P002", "P003"]
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.resolve_parcel_ids",
        lambda scope: parcel_ids,
    )
    # Mock 指标加载：3 个地块
    records = [_make_parcel_record(pid, som=15.0 + i) for i, pid in enumerate(parcel_ids)]
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.load_indicators",
        lambda pids: (records, []),
    )
    # Mock model-5 读库命中（县级结果）
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context._read_model5_latest",
        lambda: {
            "organic_fertilizer_dosage": 300.0, "level": "中",
            "organic_matter": 16.0, "potential_increase": 5.0,
            "source": "db",
        },
    )
    # Mock LLM
    monkeypatch.setattr(
        "src.ai_culti_demo.report.llm_service.generate",
        lambda prompt, **kwargs: {"success": True, "content": "<p>区域分析内容</p>"},
    )

    result = generate_report("organic_matter_improvement", {"type": "region", "id": "韶关市"})

    assert result["status"] == "ok"
    content = result["content"]
    # region 范围应有聚合统计
    # 注意：model-5 县级结果为单值，region_stats 仍会记录
    assert "数据来源与计算依据" in content
    assert "韶关市" in content


# ---------------------------------------------------------------------------
# 7.7 回归：旧请求体 {report_type, area_code} 仍可生成报告
# ---------------------------------------------------------------------------

def test_regression_legacy_area_code(monkeypatch):
    """旧请求体 {report_type, area_code}（无 scope）仍可生成报告。"""
    # Mock scope 解析
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.resolve_parcel_ids",
        lambda scope: ["P001"],
    )
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.load_indicators",
        lambda pids: ([_make_parcel_record(pids[0])], []),
    )
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context._read_model4_from_db",
        lambda pid: {
            "parcel_id": pid, "soil_ph": 4.5, "exchangeable_hydrogen": 1.2,
            "exchangeable_aluminum": 3.0, "target_ph": 6.5,
            "soil_conditioner_dosage": 100.0, "woody_peat_dosage": 200.0,
            "model_version": "v1_db", "source": "db",
        },
    )
    monkeypatch.setattr(
        "src.ai_culti_demo.report.llm_service.generate",
        lambda prompt, **kwargs: {"success": True, "content": "<p>内容</p>"},
    )

    # 旧式调用：area_code 作为字符串（scope=None）
    result = generate_report("acidification_treatment", None, area_code="韶关市")

    assert result["status"] == "ok"
    # region 范围的 area_code 应回写
    assert result["area_code"] == "韶关市"
    assert result["scope"] == {"type": "region", "id": "韶关市"}


def test_regression_scope_overrides_area_code(monkeypatch):
    """scope 优先于 area_code。"""
    # Mock 全链路
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.resolve_parcel_ids",
        lambda scope: [scope["id"]],
    )
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.load_indicators",
        lambda pids: ([_make_parcel_record(pids[0])], []),
    )
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context._read_model4_from_db",
        lambda pid: {
            "parcel_id": pid, "soil_ph": 4.5, "exchangeable_hydrogen": 1.2,
            "exchangeable_aluminum": 3.0, "target_ph": 6.5,
            "soil_conditioner_dosage": 100.0, "woody_peat_dosage": 200.0,
            "model_version": "v1_db", "source": "db",
        },
    )
    monkeypatch.setattr(
        "src.ai_culti_demo.report.llm_service.generate",
        lambda prompt, **kwargs: {"success": True, "content": "<p>内容</p>"},
    )

    # 同时传 scope 和 area_code：scope 优先
    result = generate_report(
        "acidification_treatment",
        {"type": "parcel", "id": "P001"},
        area_code="韶关市",
    )
    assert result["status"] == "ok"
    assert result["scope"] == {"type": "parcel", "id": "P001"}
    # parcel 范围 area_code 为空字符串
    assert result["area_code"] == ""


# ---------------------------------------------------------------------------
# region_stats 聚合测试
# ---------------------------------------------------------------------------

def test_region_stats_parcel_scope_returns_none():
    """parcel 范围 region_stats 为 None。"""
    stats = compute_region_stats(
        {"type": "parcel", "id": "P001"},
        [_make_parcel_record("P001")],
        {},
    )
    assert stats is None


def test_region_stats_region_scope_aggregates():
    """region 范围对连续指标算均值/最小/最大。"""
    records = [
        _make_parcel_record("P1", ph=5.0, som=15.0),
        _make_parcel_record("P2", ph=6.0, som=25.0),
    ]
    stats = compute_region_stats({"type": "region", "id": "R"}, records, {})
    assert stats is not None
    assert "soil_ph" in stats
    assert stats["soil_ph"]["mean"] == 5.5
    assert stats["soil_ph"]["min"] == 5.0
    assert stats["soil_ph"]["max"] == 6.0
    assert stats["soil_ph"]["count"] == 2
    assert "organic_matter" in stats


# ---------------------------------------------------------------------------
# fix-organic-matter-report：model-5 空记录识别与补算降级
# ---------------------------------------------------------------------------

from src.ai_culti_demo.report_context import _read_model5_latest, _compute_model5_for_parcel
from src.ai_culti_demo.report_templates import (
    render_parcel_indicators_table,
    render_organic_matter_dosage_table,
    _organic_data_brief,
    organic_fertilizer_prompt,
)


def test_model5_latest_empty_record_returns_none():
    """4.1: _read_model5_latest() 关键字段全空时返回 None。"""
    fake_row = MagicMock()
    fake_row.organic_fertilizer_type = None
    fake_row.organic_fertilizer_dosage = None
    fake_row.level = None
    fake_row.potential_increase = None
    fake_row.om_improvement_target = None

    fake_model = MagicMock()
    fake_model.query.order_by.return_value.first.return_value = fake_row

    with patch("framework.models.thematic_model.OrganicMatterResult", fake_model):
        with patch("src.ai_culti_demo.report_context._app_ctx", lambda: _NullCtx()):
            assert _read_model5_latest() is None


def test_model5_latest_partial_fields_returns_record():
    """4.2: _read_model5_latest() 部分字段有值时仍返回记录。"""
    fake_row = MagicMock()
    fake_row.organic_fertilizer_type = "urea"
    fake_row.organic_fertilizer_dosage = 300.0
    fake_row.level = None
    fake_row.potential_increase = None
    fake_row.om_improvement_target = None

    fake_model = MagicMock()
    fake_model.query.order_by.return_value.first.return_value = fake_row

    with patch("framework.models.thematic_model.OrganicMatterResult", fake_model):
        with patch("src.ai_culti_demo.report_context._app_ctx", lambda: _NullCtx()):
            result = _read_model5_latest()
            assert result is not None
            assert result["organic_fertilizer_dosage"] == 300.0
            assert result["source"] == "db"


def test_model5_compute_includes_soil_ph():
    """4.3: _compute_model5_for_parcel() 补算结果含 soil_ph。"""
    record = _make_parcel_record("P001", ph=5.5, som=18.0)

    fake_accessor = MagicMock()
    fake_accessor._map_indicators_to_inputs.return_value = {"pH": 5.5, "SOMbe": 18.0}

    with patch("framework.domain.data.parcel_data_accessor.ParcelDataAccessor", return_value=fake_accessor):
        with patch("framework.domain.calculations.organic_matter_calculation.predict_dose",
                   return_value=(250.0, False)):
            result = _compute_model5_for_parcel(record)
            assert result is not None
            assert result["source"] == "computed"
            assert result["soil_ph"] == 5.5
            assert result["organic_fertilizer_dosage"] == 250.0


def test_render_parcel_indicators_table_parcel():
    """4.4: 单地块渲染指标表。"""
    ctx = {
        "scope": {"type": "parcel", "id": "P001"},
        "indicators_snapshot": [
            {
                "parcel_id": "P001",
                "soil_indicators": {
                    "soil_ph": 5.5,
                    "organic_matter": 18.0,
                    "available_potassium": 120.0,
                    "available_phosphorus": 15.0,
                    "total_nitrogen": 1.2,
                },
            }
        ],
    }
    html = render_parcel_indicators_table(ctx)
    assert "<table>" in html
    assert "土壤 pH" in html
    assert "5.50" in html
    assert "有机质" in html
    assert "18.00" in html


def test_render_parcel_indicators_table_empty():
    """4.5: 指标全空显示降级提示。"""
    ctx = {
        "scope": {"type": "parcel", "id": "P001"},
        "indicators_snapshot": [
            {"parcel_id": "P001", "soil_indicators": {}}
        ],
    }
    html = render_parcel_indicators_table(ctx)
    assert "数据缺失" in html
    assert "建议补充检测" in html


def test_render_parcel_indicators_table_no_snapshot():
    """4.5b: indicators_snapshot 为空时显示降级提示。"""
    ctx = {
        "scope": {"type": "parcel", "id": "P001"},
        "indicators_snapshot": [],
    }
    html = render_parcel_indicators_table(ctx)
    assert "数据缺失" in html


def test_render_parcel_indicators_table_region():
    """4.5c: 区域范围渲染聚合统计表。"""
    ctx = {
        "scope": {"type": "region", "id": "韶关市"},
        "region_stats": {
            "soil_ph": {"mean": 5.5, "min": 4.5, "max": 6.5, "count": 10},
            "organic_matter": {"mean": 20.0, "min": 15.0, "max": 25.0, "count": 10},
        },
    }
    html = render_parcel_indicators_table(ctx)
    assert "<table>" in html
    assert "均值" in html
    assert "最小" in html
    assert "最大" in html
    assert "样本数" in html
    assert "5.50" in html


def test_integration_organic_parcel_has_indicators(monkeypatch):
    """4.6: 单地块有机质报告含地块指标概览章节与真实 pH/有机质值。"""
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.resolve_parcel_ids",
        lambda scope: [scope["id"]],
    )
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.load_indicators",
        lambda pids: ([_make_parcel_record(pids[0], ph=5.5, som=18.0)], []),
    )
    # model-5 空记录 → 返回 None 触发补算
    monkeypatch.setattr("src.ai_culti_demo.report_context._read_model5_latest", lambda: None)
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context._compute_model5_for_parcel",
        lambda rec: {
            "parcel_id": rec["parcel_id"],
            "organic_matter": 18.0,
            "soil_ph": 5.5,
            "organic_fertilizer_dosage": 250.0,
            "level": "低",
            "source": "computed",
        },
    )
    monkeypatch.setattr(
        "src.ai_culti_demo.report.llm_service.generate",
        lambda prompt, **kwargs: {"success": True, "content": "<p>LLM 内容</p>"},
    )

    result = generate_report("organic_matter_improvement", {"type": "parcel", "id": "P001"})
    assert result["status"] == "ok"
    content = result["content"]
    # 含地块指标概览章节
    assert "地块土壤指标概览" in content
    # 含真实 pH 与有机质值
    assert "5.50" in content
    assert "18.00" in content
    # 含 model-5 补算用量
    assert "250.00" in content
    assert "现场补算" in content


def test_regression_model5_valid_db_hit_reuses(monkeypatch):
    """4.7a: model-5 有落库有效结果时仍复用。"""
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.resolve_parcel_ids",
        lambda scope: [scope["id"]],
    )
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.load_indicators",
        lambda pids: ([_make_parcel_record(pids[0])], []),
    )
    # 有效落库结果（关键字段非空）
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context._read_model5_latest",
        lambda: {
            "organic_fertilizer_dosage": 300.0,
            "level": "中",
            "potential_increase": 5.0,
            "source": "db",
        },
    )
    # 补算不应被调用
    def fail_compute(rec):
        raise AssertionError("有效落库结果不应触发补算")

    monkeypatch.setattr("src.ai_culti_demo.report_context._compute_model5_for_parcel", fail_compute)
    monkeypatch.setattr(
        "src.ai_culti_demo.report.llm_service.generate",
        lambda prompt, **kwargs: {"success": True, "content": "<p>内容</p>"},
    )

    result = generate_report("organic_matter_improvement", {"type": "parcel", "id": "P001"})
    assert result["status"] == "ok"
    assert "300.00" in result["content"]


def test_regression_acidification_unaffected(monkeypatch):
    """4.7b: 酸化治理模板不受有机质修复影响。"""
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.resolve_parcel_ids",
        lambda scope: [scope["id"]],
    )
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context.load_indicators",
        lambda pids: ([_make_parcel_record(pids[0])], []),
    )
    monkeypatch.setattr(
        "src.ai_culti_demo.report_context._read_model4_from_db",
        lambda pid: {
            "parcel_id": pid, "soil_ph": 4.5,
            "soil_conditioner_dosage": 100.0, "woody_peat_dosage": 200.0,
            "model_version": "v1_db", "source": "db",
        },
    )
    monkeypatch.setattr(
        "src.ai_culti_demo.report.llm_service.generate",
        lambda prompt, **kwargs: {"success": True, "content": "<p>酸化治理内容</p>"},
    )

    result = generate_report("acidification_treatment", {"type": "parcel", "id": "P001"})
    assert result["status"] == "ok"
    assert "100.00" in result["content"]
    assert "200.00" in result["content"]


class _NullCtx:
    """mock _app_ctx 返回的空 context manager。"""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
