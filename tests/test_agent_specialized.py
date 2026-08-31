"""测试 6 个专业智能体"""
import sys
import os
import types
from unittest.mock import MagicMock
from sqlalchemy import String

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))

# 测试环境可能未安装 geoalchemy2，这里在导入 thematic_model 之前先 stub
# 一个 Geometry 类（返回 String 实例），既满足 SQLAlchemy Column 在类定义
# 阶段调用 Geometry(...) 时所需的 `_set_parent_with_dispatch` 协议，
# 又能保证后续 db.create_all() 渲染 DDL 时 __str__ 返回真实字符串。
if "geoalchemy2" not in sys.modules:
    _geo_stub = types.ModuleType("geoalchemy2")

    class _Geometry:
        """DDL-safe stub：返回 String 类型实例，避免污染后续测试的 DDL 渲染。"""

        def __new__(cls, *args, **kwargs):
            return String()

    _geo_stub.Geometry = _Geometry
    sys.modules["geoalchemy2"] = _geo_stub


def test_stability_risk_agent_execute():
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    agent = StabilityRiskAgent()
    assert agent.model_id == "model-1"
    assert agent.dependencies == []
    result = agent.execute({"area_code": "lechang"})
    assert result["status"] == "ok"
    assert result["metadata"]["simulated"] is True
    counties = result["result"]["counties"]
    assert isinstance(counties, list) and len(counties) >= 1
    first = counties[0]
    assert "name" in first and "quality_grade" in first and "stability" in first
    print("✓ StabilityRiskAgent.execute 返回县区稳定性数据")


def test_stability_risk_agent_answer_question_overall():
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    agent = StabilityRiskAgent()
    out = agent.answer_question("全省耕地质量整体稳定吗？", {})
    assert out["simulated"] is True
    assert "稳定" in out["answer"] or "稳定" in str(out["evidence"])
    assert 0.0 <= out["confidence"] <= 1.0
    assert any("占比" in str(e) or "面积" in str(e) for e in out["evidence"])
    print("✓ StabilityRiskAgent.answer_question 返回稳定性总体评价")


def test_stability_risk_agent_answer_question_risk():
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    agent = StabilityRiskAgent()
    out = agent.answer_question("哪些县区高等级耕地存在退化风险？", {})
    assert out["simulated"] is True
    assert "县" in out["answer"] or len(out["evidence"]) >= 1
    print("✓ StabilityRiskAgent.answer_question 识别退化风险区域")


def test_problem_agent_execute():
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    assert agent.model_id == "model-3"
    assert agent.dependencies == ["model-2"]
    # 缺 parcel_id 时返回统一降级响应（移除 mock 数据）
    result = agent.execute({"area_code": "lechang"})
    assert result["status"] == "degraded"
    assert result["degraded"] is True
    assert result["reason"] == "missing_input"
    assert result["agent_id"] == "model-3"
    assert result["model_id"] == "obstacle-diagnosis"
    print("✓ ProblemIdentificationAgent.execute 缺 parcel_id 返回统一降级响应")


def test_problem_agent_answer_question():
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    # 缺 parcel_id 时返回统一降级响应（移除 mock 数据）
    out = agent.answer_question("耕地在哪些方面有问题？", {})
    assert out["degraded"] is True
    assert out["simulated"] is False
    assert out["reason"] == "missing_input"
    assert out["need_input"] == "parcel_id"
    assert "诊断" in out["answer"]
    print("✓ ProblemIdentificationAgent.answer_question 缺 parcel_id 返回降级响应")


def test_problem_agent_uses_model2_target_ph():
    """model-2 target_ph 消费能力已被真实诊断路径取代；缺 parcel_id 时返回降级响应"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    ctx = {"model-2": {"target_ph": 6.8, "answer": "...", "evidence": [], "confidence": 0.8, "simulated": True}}
    out = agent.answer_question("主要障碍因素是什么？", ctx)
    # 真实诊断路径以 parcel_id 为入口，model-2 target_ph 不再驱动结果
    assert out["degraded"] is True
    assert out["simulated"] is False
    assert out["reason"] == "missing_input"
    assert out["need_input"] == "parcel_id"
    print("✓ ProblemIdentificationAgent 真实路径下缺 parcel_id 时返回降级响应")


def test_problem_agent_consumes_standard_field_names_has_question(monkeypatch):
    """真实诊断分支应读取标准码字段 GDZLDJ/ZALX/ZYZAYS（"有没有问题"分支）"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    fake_real_result = {
        "status": "ok",
        "diagnosis": {
            "ZALX": "酸化障碍",
            "ZYZAYS": "pH偏低；有机质贫瘠；耕层浅薄",
            "CYZAYS": "有效磷不足；速效钾偏低",
        },
        "evaluation": {"GDZLDJ": 7},
    }
    monkeypatch.setattr(agent, "_get_real_diagnosis", lambda context: fake_real_result)

    out = agent.answer_question("我这块地有没有问题？", {})
    assert out["simulated"] is False
    assert "酸化障碍" in out["answer"]
    assert "pH偏低" in out["answer"]
    assert "7级" in out["answer"]
    assert "无明显障碍" not in out["answer"]
    assert "未知" not in out["answer"]
    print("✓ ProblemIdentificationAgent 真实诊断分支消费 GDZLDJ/ZALX/ZYZAYS（有没有问题分支）")


def test_problem_agent_consumes_standard_field_names_county_question(monkeypatch):
    """真实诊断分支应读取标准码字段含 CYZAYS（"县/乡镇/方面"分支）"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    fake_real_result = {
        "status": "ok",
        "diagnosis": {
            "ZALX": "酸化障碍",
            "ZYZAYS": "pH偏低；有机质贫瘠",
            "CYZAYS": "有效磷不足；速效钾偏低",
        },
        "evaluation": {"GDZLDJ": 7},
    }
    monkeypatch.setattr(agent, "_get_real_diagnosis", lambda context: fake_real_result)

    out = agent.answer_question("县域耕地在哪些方面有问题？", {})
    assert out["simulated"] is False
    assert "酸化障碍" in out["answer"]
    assert "pH偏低" in out["answer"]
    assert "有效磷不足" in out["answer"]
    assert "7级" in out["answer"]
    print("✓ ProblemIdentificationAgent 真实诊断分支消费 CYZAYS（县域方面分支）")


def test_problem_agent_consumes_standard_field_names_else_branch(monkeypatch):
    """真实诊断分支应读取标准码字段（else 兜底分支）"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    fake_real_result = {
        "status": "ok",
        "diagnosis": {
            "ZALX": "板结障碍",
            "ZYZAYS": "容重偏高；孔隙度偏低",
            "CYZAYS": "耕层浅薄",
        },
        "evaluation": {"GDZLDJ": 8},
    }
    monkeypatch.setattr(agent, "_get_real_diagnosis", lambda context: fake_real_result)

    out = agent.answer_question("主要障碍因素是什么？", {})
    assert out["simulated"] is False
    assert "板结障碍" in out["answer"]
    assert "容重偏高" in out["answer"]
    assert "耕层浅薄" in out["answer"]
    assert "8级" in out["answer"]
    print("✓ ProblemIdentificationAgent 真实诊断分支消费标准字段（else 分支）")


def test_acidification_agent_execute(monkeypatch):
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status": "success", "ytk": 1234.5, "mbnt": 567.8,
            "sub_model": "upland_compound", "land_type": "upland",
            "fertilizer_type": "compound", "model_version": "process_v2_20260801",
            "customized_params": {"FertN": 200.0},
        }
    )
    agent = AcidificationRemediationAgent()
    assert agent.model_id == "model-4"
    result = agent.execute({"SJD":4.31,"JHX":1.56,"JLA":4.08})
    assert result["status"] == "success"
    assert result["result"]["ytk"] == 1234.5
    assert result["result"]["mbnt"] == 567.8
    assert result["metadata"]["model_version"] == "process_v2_20260801"
    print("✓ AcidificationRemediationAgent.execute 返回三层结构含 ytk/mbnt")


def test_acidification_agent_passes_through_params(monkeypatch):
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    captured = {}
    def fake(data, land_type=None, fertilizer_type=None):
        captured["land_type"] = land_type
        captured["fertilizer_type"] = fertilizer_type
        return {"status":"success","ytk":1.0,"mbnt":2.0,"sub_model":"paddy_urea",
                "land_type":land_type,"fertilizer_type":fertilizer_type,
                "model_version":"process_v2_20260801","customized_params":{}}
    monkeypatch.setattr("framework.agents.specialized.acidification_agent.model_4_execution", fake)
    agent = AcidificationRemediationAgent()
    agent.answer_question("如何治理酸化？", {"data":{"SJD":4.31,"JHX":1.56,"JLA":4.08},
                                          "land_type":"paddy","fertilizer_type":"urea"})
    assert captured["land_type"] == "paddy"
    assert captured["fertilizer_type"] == "urea"
    print("✓ AcidificationRemediationAgent 透传 land_type/fertilizer_type 给 model_4_execution")


def test_acidification_agent_answer_no_gb_standard(monkeypatch):
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status":"success","ytk":1234.5,"mbnt":567.8,"sub_model":"upland_compound",
            "land_type":"upland","fertilizer_type":"compound",
            "model_version":"process_v2_20260801","customized_params":{}})
    agent = AcidificationRemediationAgent()
    out = agent.answer_question("如何治理强酸性耕地？施加多少调理剂？", {"data":{"SJD":4.31,"JHX":1.56,"JLA":4.08}})
    assert "GB/T 42817-2023" not in out["answer"]
    assert "亿土康" in out["answer"] or "ytk" in str(out["evidence"]).lower() or "木本泥炭" in out["answer"]
    print("✓ AcidificationRemediationAgent answer 不含 GB/T 42817-2023，含 YTK/MBNT")


def test_organic_matter_agent_execute():
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    agent = OrganicMatterAgent()
    assert agent.model_id == "model-5"
    assert agent.dependencies == []
    result = agent.execute({"area_code": "lechang"})
    assert result["status"] == "degraded"
    assert result["metadata"]["simulated"] is True
    assert "level" in result["result"]
    assert "manure_dosage" in result["result"]
    assert "potential_increase" in result["result"]
    print("✓ OrganicMatterAgent.execute 返回有机质分级与施用量")


def test_organic_matter_agent_answer_question_content():
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    agent = OrganicMatterAgent()
    out = agent.answer_question("全省耕地土壤有机质含量如何？", {})
    assert out["simulated"] is True
    assert "有机质" in out["answer"]
    print("✓ OrganicMatterAgent 返回有机质含量评估")


def test_organic_matter_agent_answer_question_dosage():
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    agent = OrganicMatterAgent()
    out = agent.answer_question("有机肥每亩施用量多少？", {})
    assert out["simulated"] is True
    assert "kg" in out["answer"] or "有机肥" in out["answer"]
    assert any("manure_dosage" in str(e) or "有机肥" in str(e) for e in out["evidence"])
    print("✓ OrganicMatterAgent 返回有机肥施用量建议")


def test_stability_agent_db_path(monkeypatch):
    """DB 命中时 data_source="db"。"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    fake_indicators = {
        "soil_ph": 5.5,
        "organic_matter": 22.0,
        "stability_score": 78.5,
        "quality_grade": 4,
        "risk_index": 0.32,
        "area_mu": 320000,
    }
    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: fake_indicators
    )
    agent = StabilityRiskAgent()
    result = agent.execute({"parcel_id": "P001"})
    assert result["data_source"] == "db"


def test_stability_agent_fallback_path(monkeypatch):
    """DB 未命中时 data_source="fallback"。"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: None
    )
    agent = StabilityRiskAgent()
    result = agent.execute({"parcel_id": "NOT_IN_DB"})
    assert result["data_source"] == "fallback"


def test_stability_agent_persist_success(monkeypatch):
    """持久化成功时 persisted=True。"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "stability_score": 78.5}
    )
    agent = StabilityRiskAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: True)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is True


def test_stability_agent_persist_failure(monkeypatch):
    """持久化失败时 persisted=False，但不阻断结果返回。"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "stability_score": 78.5}
    )
    agent = StabilityRiskAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: False)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is False
    assert result["status"] == "ok"


def test_stability_agent_legacy_no_result_record(monkeypatch):
    """legacy 路径（无 parcel_id）不写入 StabilityRiskResult。"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent

    agent = StabilityRiskAgent()
    # 捕获 _persist_result 的调用，验证 _build_result_record 返回 None
    persist_calls = []

    def fake_persist(agent_id, parcel_id, inputs, outputs, status):
        # 调用 _build_result_record 验证返回值
        result_record = agent._build_result_record(0, outputs)
        persist_calls.append(result_record)
        return True

    monkeypatch.setattr(agent, "_persist_result", fake_persist)
    # 不传 parcel_id，走 legacy 路径
    result = agent.execute({"area_code": "lechang"})
    assert result["data_source"] == "fallback"
    assert persist_calls[0] is None  # legacy 路径不写入结果表


def test_grade_agent_db_path(monkeypatch):
    """DB 命中时 data_source="db"。"""
    from framework.agents.specialized.grade_agent import FarmlandGradeAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    fake_indicators = {
        "soil_ph": 5.5, "organic_matter": 22.0,
        "available_potassium": 120.0, "available_phosphorus": 15.0,
    }
    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: fake_indicators
    )
    agent = FarmlandGradeAgent()
    result = agent.execute({"parcel_id": "P001"})
    assert result["data_source"] == "db"


def test_grade_agent_fallback_path(monkeypatch):
    """DB 未命中时 data_source="fallback"。"""
    from framework.agents.specialized.grade_agent import FarmlandGradeAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: None
    )
    agent = FarmlandGradeAgent()
    result = agent.execute({"parcel_id": "NOT_IN_DB", "parcel_code": "C001"})
    assert result["data_source"] == "fallback"


def test_grade_agent_persist_success(monkeypatch):
    """持久化成功时 persisted=True。"""
    from framework.agents.specialized.grade_agent import FarmlandGradeAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "organic_matter": 22.0}
    )
    agent = FarmlandGradeAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: True)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is True


def test_grade_agent_persist_failure(monkeypatch):
    """持久化失败时 persisted=False，不阻断结果。"""
    from framework.agents.specialized.grade_agent import FarmlandGradeAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "organic_matter": 22.0}
    )
    agent = FarmlandGradeAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: False)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is False


def test_problem_agent_db_path(monkeypatch):
    """DB 命中时 data_source="db"。"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "organic_matter": 22.0}
    )
    agent = ProblemIdentificationAgent()
    result = agent.execute({"parcel_id": "P001"})
    assert result["data_source"] == "db"


def test_problem_agent_fallback_path(monkeypatch):
    """DB 未命中时 data_source="fallback"。"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: None
    )
    agent = ProblemIdentificationAgent()
    result = agent.execute({"parcel_id": "NOT_IN_DB"})
    assert result["data_source"] == "fallback"


def test_problem_agent_persist_success(monkeypatch):
    """持久化成功时 persisted=True。"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "organic_matter": 22.0}
    )
    agent = ProblemIdentificationAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: True)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is True


def test_problem_agent_persist_failure(monkeypatch):
    """持久化失败时 persisted=False，不阻断结果。"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "organic_matter": 22.0}
    )
    agent = ProblemIdentificationAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: False)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is False


def test_acidification_agent_db_path(monkeypatch):
    """DB 命中时 data_source="db"。"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 4.31, "exchangeable_hydrogen": 1.56,
                           "exchangeable_aluminum": 4.08}
    )
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status": "success", "ytk": 1234.5, "mbnt": 567.8,
            "sub_model": "upland_compound", "model_version": "process_v2_20260801",
            "customized_params": {},
        }
    )
    agent = AcidificationRemediationAgent()
    result = agent.execute({"parcel_id": "P001"})
    assert result["data_source"] == "db"


def test_acidification_agent_fallback_path(monkeypatch):
    """DB 未命中时 data_source="fallback"。"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: None
    )
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status": "success", "ytk": 1234.5, "mbnt": 567.8,
            "sub_model": "upland_compound", "model_version": "process_v2_20260801",
            "customized_params": {},
        }
    )
    agent = AcidificationRemediationAgent()
    result = agent.execute({"parcel_id": "NOT_IN_DB"})
    assert result["data_source"] == "fallback"


def test_acidification_agent_persist_success(monkeypatch):
    """持久化成功时 persisted=True。"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 4.31, "exchangeable_hydrogen": 1.56}
    )
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status": "success", "ytk": 1234.5, "mbnt": 567.8,
            "sub_model": "upland_compound", "model_version": "process_v2_20260801",
            "customized_params": {},
        }
    )
    agent = AcidificationRemediationAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: True)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is True


def test_acidification_agent_persist_failure(monkeypatch):
    """持久化失败时 persisted=False，不阻断结果。"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 4.31, "exchangeable_hydrogen": 1.56}
    )
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status": "success", "ytk": 1234.5, "mbnt": 567.8,
            "sub_model": "upland_compound", "model_version": "process_v2_20260801",
            "customized_params": {},
        }
    )
    agent = AcidificationRemediationAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: False)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is False


def test_acidification_agent_build_result_record_db_path():
    """_build_result_record 在有 parcel_id 时应返回 AcidificationRemediationResult 实例。

    验证构造函数参数与 ORM 模型一致（AcidificationRemediationResult 无 input_snapshot 列）。
    """
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    from framework.models.thematic_model import AcidificationRemediationResult

    agent = AcidificationRemediationAgent()
    outputs = {
        "parcel_id": "P001",
        "soil_ph": 4.31,
        "result": {
            "ytk": 1234.5,
            "mbnt": 567.8,
            "sub_model": "upland_compound",
            "model_version": "process_v2_20260801",
            "customized_params": {},
        },
    }
    record = agent._build_result_record(execution_id=1, outputs=outputs)
    assert isinstance(record, AcidificationRemediationResult)
    assert record.execution_id == 1
    assert record.parcel_id == "P001"
    assert record.soil_ph == 4.31
    assert record.soil_conditioner_dosage == 1234.5
    assert record.woody_peat_dosage == 567.8
    assert record.model_version == "process_v2_20260801"
    assert record.status == "upland_compound"
    assert record.simulated is True
    print("✓ AcidificationRemediationAgent._build_result_record 返回有效 ORM 实例")


def test_acidification_agent_build_result_record_legacy_none():
    """_build_result_record 在无 parcel_id（legacy 路径）时返回 None，避免污染结果表。"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent

    agent = AcidificationRemediationAgent()
    # legacy 路径：outputs 无 parcel_id
    record = agent._build_result_record(
        execution_id=1,
        outputs={"soil_ph": 5.5, "result": {"ytk": 100.0, "mbnt": 50.0}},
    )
    assert record is None
    print("✓ AcidificationRemediationAgent._build_result_record legacy 路径返回 None")


def test_organic_matter_agent_db_path(monkeypatch):
    """DB 命中时 data_source="db"。"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {
            "soil_ph": 5.5, "organic_matter": 22.0,
            "available_potassium": 120.0, "SOCbe": 15.0,
        }
    )
    agent = OrganicMatterAgent()
    result = agent.execute({"parcel_id": "P001"})
    assert result["data_source"] == "db"


def test_organic_matter_agent_fallback_path(monkeypatch):
    """DB 未命中时 data_source="fallback"。"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: None
    )
    agent = OrganicMatterAgent()
    result = agent.execute({"parcel_id": "NOT_IN_DB"})
    assert result["data_source"] == "fallback"


def test_organic_matter_agent_no_parcel_id_uses_fallback():
    """无 parcel_id 时直接走 fallback（县级分析）。"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    agent = OrganicMatterAgent()
    result = agent.execute({"area_code": "lechang"})
    assert result["data_source"] == "fallback"


def test_organic_matter_agent_persist_success(monkeypatch):
    """持久化成功时 persisted=True。"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "organic_matter": 22.0}
    )
    agent = OrganicMatterAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: True)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is True


def test_organic_matter_agent_persist_failure(monkeypatch):
    """持久化失败时 persisted=False，不阻断结果返回（补 Model-5 缺口）。"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "organic_matter": 22.0}
    )
    agent = OrganicMatterAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: False)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is False
    assert result["status"] == "ok"


def test_organic_matter_agent_degraded_logs_status(monkeypatch):
    """降级路径执行日志 status="degraded"，且返回 data_source="fallback"（补 B3 场景断言）。"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    # DB 未命中 + 无模型特征 → legacy 降级路径
    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: None
    )
    agent = OrganicMatterAgent()
    persist_calls = []

    def capture_persist(agent_id, parcel_id, inputs, outputs, status, **_kwargs):
        persist_calls.append({"status": status, "inputs": inputs, "outputs": outputs})
        return True

    monkeypatch.setattr(agent, "_persist_result", capture_persist)
    result = agent.execute({"parcel_id": "NOT_IN_DB"})
    assert result["status"] == "degraded"
    assert result["data_source"] == "fallback"
    assert len(persist_calls) == 1
    assert persist_calls[0]["status"] == "degraded"


def test_organic_matter_agent_error_logs_status(monkeypatch):
    """计算失败时执行日志 status="error"，返回 persisted=False（补 B4 场景）。"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent

    def boom(*a, **kw):
        raise RuntimeError("model crashed")

    monkeypatch.setattr(
        "framework.agents.specialized.organic_matter_agent.model_5_execution", boom
    )
    agent = OrganicMatterAgent()
    persist_calls = []

    def capture_persist(agent_id, parcel_id, inputs, outputs, status, **_kwargs):
        persist_calls.append({"status": status, "outputs": outputs})
        return True

    monkeypatch.setattr(agent, "_persist_result", capture_persist)
    # 传入模型特征（SOCbe/pH）但不传 parcel_id，走 ML 路径触发异常
    result = agent.execute({"SOCbe": 15.0, "pH": 5.5})
    assert result["status"] == "error"
    assert result["persisted"] is False
    assert len(persist_calls) == 1
    assert persist_calls[0]["status"] == "error"


if __name__ == "__main__":
    test_stability_risk_agent_execute()
    test_stability_risk_agent_answer_question_overall()
    test_stability_risk_agent_answer_question_risk()
    test_problem_agent_execute()
    test_problem_agent_answer_question()
    test_problem_agent_uses_model2_target_ph()
    test_organic_matter_agent_execute()
    test_organic_matter_agent_answer_question_content()
    test_organic_matter_agent_answer_question_dosage()
    print("\n所有专业智能体测试通过！")
