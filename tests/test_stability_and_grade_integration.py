"""
稳定性风险模型、质量等级 exe 模型与 agent 路由的集成测试。

覆盖任务：
- 9.1-9.4: API 路由验证（通过 agent 层验证路由正确性）
- 9.5: 综合诊断接口（StabilityRiskAgent + ProblemIdentificationAgent）
- 9.7: CoreEngine.run_thematic_model() 调度三个新模型
- 9.8: 响应字段结构符合统一调用契约
- 10.1: 模型1 离线预计算单元测试
- 10.2: 模型1 在线查询单元测试（正常/未就绪/地块不存在）
- 10.3: exe 调用包装器单元测试（正常/超时/文件缺失/地块无效）
- 10.7: agent 路由和错误处理
- 10.8: 综合诊断整合
- 10.10: 端到端集成测试
"""
from __future__ import annotations

import os
import sys
import subprocess as sp
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import pytest

# 确保可导入项目模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# 检测可选依赖
try:
    from ai_culti_demo.thematic_models import STABILITY_MODEL_AVAILABLE, GRADE_EVAL_MODEL_AVAILABLE
except ImportError:
    STABILITY_MODEL_AVAILABLE = False
    GRADE_EVAL_MODEL_AVAILABLE = False

geopandas_required = pytest.mark.skipif(
    not STABILITY_MODEL_AVAILABLE,
    reason="geopandas 未安装，跳过稳定性模型实际调用测试",
)


# ---------------------------------------------------------------------------
# 10.1 模型1 离线预计算单元测试
# ---------------------------------------------------------------------------
class TestStabilityPrecompute:
    """模型1 离线预计算（九模块输出字段完整性）"""

    @geopandas_required
    def test_run_all_models_returns_nine_modules(self):
        """验证 run_all_models 返回九模块字段（使用 mock 避免实际 geopandas 依赖）"""
        from ai_culti_demo.farmland_stability import model as stability_model

        mock_gdf = MagicMock()
        mock_gdf.copy.return_value = mock_gdf

        with patch.object(stability_model, "calculate_boundary_safety", return_value=mock_gdf) as m1, \
             patch.object(stability_model, "calculate_support_balance", return_value=mock_gdf) as m2, \
             patch.object(stability_model, "calculate_key_criticality", return_value=mock_gdf) as m3, \
             patch.object(stability_model, "calculate_neighbor_consistency", return_value=mock_gdf) as m4, \
             patch.object(stability_model, "calculate_history_trend", return_value=mock_gdf) as m5, \
             patch.object(stability_model, "calculate_drop_risk", return_value=mock_gdf) as m6, \
             patch.object(stability_model, "calculate_factor_degradation", return_value=mock_gdf) as m7, \
             patch.object(stability_model, "calculate_degradation_cluster", return_value=mock_gdf) as m8, \
             patch.object(stability_model, "calculate_persistent_low_quality", return_value=mock_gdf) as m9:

            result = stability_model.run_all_models(
                current_file="fake.shp",
                history_files=["h1.shp", "h2.shp"],
                years=[2021, 2024],
            )

            for m in [m1, m2, m3, m4, m5, m6, m7, m8, m9]:
                m.assert_called_once()
            assert result is mock_gdf


# ---------------------------------------------------------------------------
# 10.2 模型1 在线查询单元测试
# ---------------------------------------------------------------------------
class TestStabilityOnlineQuery:
    """模型1 在线查询（正常/未就绪/地块不存在）"""

    @geopandas_required
    def test_normal_query_returns_ok(self):
        """正常查询返回 status=ok 和九模块结果"""
        from ai_culti_demo.thematic_models import run_thematic_model
        from ai_culti_demo.farmland_stability.storage import StabilityStorage

        mock_result = {"parcel_id": "110105001", "grade": 3, "score": 72.5, "module": 1}
        mock_storage = MagicMock()
        mock_storage.is_ready.return_value = True
        mock_storage.get_result.return_value = mock_result

        with patch("ai_culti_demo.thematic_models.StabilityStorage", return_value=mock_storage):
            out = run_thematic_model({
                "model_id": "stability-risk-evaluation",
                "parcel_id": "110105001",
            })

        assert out["status"] == "ok"
        assert out["model"]["model_id"] == "stability-risk-evaluation"
        assert out["reliability"]["level"] == "real_model"
        assert out["stability_detail"]["grade"] == 3

    @geopandas_required
    def test_not_ready_returns_error(self):
        """预计算未就绪返回 STABILITY_NOT_READY"""
        from ai_culti_demo.thematic_models import run_thematic_model

        mock_storage = MagicMock()
        mock_storage.is_ready.return_value = False
        mock_storage.get_result.return_value = None

        with patch("ai_culti_demo.thematic_models.StabilityStorage", return_value=mock_storage):
            out = run_thematic_model({
                "model_id": "stability-risk-evaluation",
                "parcel_id": "110105001",
            })

        assert out["status"] == "error"
        assert out["error"]["code"] == "STABILITY_NOT_READY"

    @geopandas_required
    def test_parcel_not_found_returns_error(self):
        """地块不存在返回 PARCEL_NOT_FOUND"""
        from ai_culti_demo.thematic_models import run_thematic_model

        mock_storage = MagicMock()
        mock_storage.is_ready.return_value = True
        mock_storage.get_result.return_value = None

        with patch("ai_culti_demo.thematic_models.StabilityStorage", return_value=mock_storage):
            out = run_thematic_model({
                "model_id": "stability-risk-evaluation",
                "parcel_id": "nonexistent",
            })

        assert out["status"] == "error"
        assert out["error"]["code"] == "PARCEL_NOT_FOUND"

    def test_missing_parcel_id_falls_back_to_demo(self):
        """缺少 parcel_id 时回退到 demo 结果（不调用实际模型）"""
        from ai_culti_demo.thematic_models import run_thematic_model

        out = run_thematic_model({
            "model_id": "stability-risk-evaluation",
            "area_code": "lechang",
        })

        assert out["status"] == "ok"


# ---------------------------------------------------------------------------
# 10.3 exe 调用包装器单元测试
# ---------------------------------------------------------------------------
class TestGradeRunner:
    """exe 调用包装器（正常/超时/文件缺失/地块无效）"""

    def test_deployment_check_missing_exe(self, tmp_path):
        """exe 文件缺失返回 DEPLOYMENT_ERROR"""
        from ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner

        runner = FarmlandGradeRunner(
            exe_path=str(tmp_path / "nonexistent.exe"),
            dat_path=str(tmp_path / "nonexistent.dat"),
        )
        deployment = runner.check_deployment()
        assert deployment["ready"] is False

    def test_deployment_check_ok(self, tmp_path):
        """exe 和 .dat 均存在时部署校验通过"""
        from ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner

        exe_path = tmp_path / "test.exe"
        dat_path = tmp_path / "test.dat"
        exe_path.write_bytes(b"fake exe")
        dat_path.write_bytes(b"fake dat")

        runner = FarmlandGradeRunner(exe_path=str(exe_path), dat_path=str(dat_path))
        deployment = runner.check_deployment()
        assert deployment["ready"] is True

    def test_run_returns_error_when_deployment_fails(self):
        """部署校验失败时返回 DEPLOYMENT_ERROR"""
        from ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner

        runner = FarmlandGradeRunner(exe_path="nonexistent.exe", dat_path="nonexistent.dat")
        result = runner.run("110105001")
        assert result["status"] == "error"
        assert result["error"]["code"] == "DEPLOYMENT_ERROR"

    def test_run_timeout_returns_timeout_error(self, tmp_path):
        """超时返回 status=error 且 code=TIMEOUT"""
        from ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner

        exe_path = tmp_path / "test.exe"
        dat_path = tmp_path / "test.dat"
        exe_path.write_bytes(b"fake")
        dat_path.write_bytes(b"fake")

        runner = FarmlandGradeRunner(exe_path=str(exe_path), dat_path=str(dat_path), timeout=1)

        # 模拟 Popen 和超时（第一次 communicate 超时，第二次清理调用返回空）
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.side_effect = [
            sp.TimeoutExpired(cmd=str(exe_path), timeout=1),
            (b"", b""),
        ]

        with patch("ai_culti_demo.farmland_grade_eval.runner.subprocess.Popen", return_value=mock_proc):
            result = runner.run("110105001")

        assert result["status"] == "error"
        assert result["error"]["code"] == "TIMEOUT"


# ---------------------------------------------------------------------------
# 9.7 CoreEngine.run_thematic_model 调度验证
# ---------------------------------------------------------------------------
class TestCoreEngineDispatch:
    """验证 run_thematic_model 能正确调度三个新模型"""

    @geopandas_required
    def test_dispatch_stability_with_parcel_id(self):
        """stability-risk-evaluation + parcel_id 调用实际模型"""
        from ai_culti_demo.thematic_models import run_thematic_model

        mock_storage = MagicMock()
        mock_storage.is_ready.return_value = True
        mock_storage.get_result.return_value = {"parcel_id": "P001", "grade": 4, "score": 80.0}

        with patch("ai_culti_demo.thematic_models.StabilityStorage", return_value=mock_storage):
            out = run_thematic_model({
                "model_id": "stability-risk-evaluation",
                "parcel_id": "P001",
            })

        assert out["status"] == "ok"
        assert out["reliability"]["level"] == "real_model"

    def test_dispatch_grade_with_parcel_code(self):
        """quality-grade-evaluation + parcel_code 调用实际 exe 模型"""
        from ai_culti_demo.thematic_models import run_thematic_model

        mock_exe_result = {
            "status": "ok",
            "quality_grade": "3",
            "composite_index": 78.5,
            "indicators": [{"name": "pH", "raw_value": 6.5, "membership": 0.95, "weight": 0.1}],
            "obstacle_degree": [{"rank": 1, "indicator": "有效磷", "degree": 0.15}],
        }
        with patch("ai_culti_demo.thematic_models.run_grade_evaluation", return_value=mock_exe_result):
            out = run_thematic_model({
                "model_id": "quality-grade-evaluation",
                "parcel_code": "110105001",
            })

        assert out["status"] == "ok"
        assert out["reliability"]["level"] == "real_model"
        assert out["grade_detail"]["quality_grade"] == "3"

    def test_dispatch_grade_missing_parcel_code_falls_back_to_demo(self):
        """quality-grade-evaluation 无 parcel_code 时回退到 demo"""
        from ai_culti_demo.thematic_models import run_thematic_model

        out = run_thematic_model({
            "model_id": "quality-grade-evaluation",
            "area_code": "lechang",
        })

        assert out["status"] == "ok"

    def test_dispatch_invalid_model_id_returns_error(self):
        """无效 model_id 返回 INVALID_MODEL_ID 并列出支持的模型"""
        from ai_culti_demo.thematic_models import run_thematic_model

        out = run_thematic_model({"model_id": "nonexistent-model"})
        assert out["status"] == "error"
        assert out["error"]["code"] == "INVALID_MODEL_ID"
        assert "stability-risk-evaluation" in out["supported_model_ids"]
        assert "quality-grade-evaluation" in out["supported_model_ids"]


# ---------------------------------------------------------------------------
# 9.8 响应字段结构符合统一调用契约
# ---------------------------------------------------------------------------
class TestResponseContract:
    """验证响应字段结构符合统一调用契约"""

    REQUIRED_FIELDS = {"status", "model", "summary", "findings", "reliability"}

    @geopandas_required
    def test_stability_response_has_required_fields(self):
        """稳定性模型响应包含 status/model/summary/findings/reliability"""
        from ai_culti_demo.thematic_models import run_thematic_model

        mock_storage = MagicMock()
        mock_storage.is_ready.return_value = True
        mock_storage.get_result.return_value = {"grade": 3, "score": 72.0}

        with patch("ai_culti_demo.thematic_models.StabilityStorage", return_value=mock_storage):
            out = run_thematic_model({
                "model_id": "stability-risk-evaluation",
                "parcel_id": "P001",
            })

        missing = self.REQUIRED_FIELDS - set(out.keys())
        assert not missing, f"缺少字段: {missing}"
        assert "stability_detail" in out

    def test_grade_response_has_required_fields(self):
        """质量等级模型响应包含统一字段 + grade_detail"""
        from ai_culti_demo.thematic_models import run_thematic_model

        mock_result = {
            "status": "ok",
            "quality_grade": "3",
            "composite_index": 78.5,
            "indicators": [],
            "obstacle_degree": [],
        }
        with patch("ai_culti_demo.thematic_models.run_grade_evaluation", return_value=mock_result):
            out = run_thematic_model({
                "model_id": "quality-grade-evaluation",
                "parcel_code": "110105001",
            })

        missing = self.REQUIRED_FIELDS - set(out.keys())
        assert not missing, f"缺少字段: {missing}"
        assert "grade_detail" in out

    def test_demo_response_has_required_fields(self):
        """demo 回退响应也包含统一字段 + fallback"""
        from ai_culti_demo.thematic_models import run_thematic_model

        out = run_thematic_model({
            "model_id": "quality-grade-evaluation",
            "area_code": "lechang",
        })

        missing = self.REQUIRED_FIELDS - set(out.keys())
        assert not missing, f"缺少字段: {missing}"
        assert "fallback" in out


# ---------------------------------------------------------------------------
# 9.1-9.4, 10.7 Agent 路由和错误处理
# ---------------------------------------------------------------------------
class TestAgentRouting:
    """验证 agent 能正确路由问题并处理错误"""

    def test_stability_agent_routes_stability_question(self):
        """9.1 StabilityRiskAgent 处理稳定性问题"""
        from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent

        out = StabilityRiskAgent().answer_question("全省耕地质量稳定性如何？", {})
        assert "answer" in out
        assert "稳定" in out["answer"]
        assert out["simulated"] is True

    def test_grade_agent_handles_quality_grade_question(self):
        """9.2 FarmlandGradeAgent 处理质量等级问题"""
        from framework.agents.specialized.grade_agent import FarmlandGradeAgent

        out = FarmlandGradeAgent().answer_question("耕地质量等级评价结果如何？", {})
        assert "answer" in out
        assert "质量等级" in out["answer"]

    def test_problem_agent_handles_diagnosis_question(self):
        """9.3 ProblemIdentificationAgent 处理障碍诊断问题"""
        from framework.agents.specialized.problem_agent import ProblemIdentificationAgent

        out = ProblemIdentificationAgent().answer_question("全省耕地质量存在哪些问题？", {})
        assert "answer" in out
        assert "主要障碍因素" in out["answer"]

    def test_acidification_agent_handles_acidification_question(self):
        """9.4 AcidificationRemediationAgent 处理酸化问题"""
        from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent

        out = AcidificationRemediationAgent().answer_question(
            "查询区域内农用地土壤酸化程度如何？", {})
        assert "answer" in out
        assert "酸化" in out["answer"]

    def test_grade_agent_hint_when_parcel_code_missing(self):
        """10.7 实际模型可用但缺少地块代码时附加提示"""
        from framework.agents.specialized.grade_agent import FarmlandGradeAgent, GRADE_EVAL_AVAILABLE

        if not GRADE_EVAL_AVAILABLE:
            pytest.skip("GRADE_EVAL_AVAILABLE 为 False，跳过提示测试")

        out = FarmlandGradeAgent().answer_question("耕地质量等级评价结果如何？", {})
        assert "hint" in out or "need_input" in out

    def test_problem_agent_hint_when_parcel_id_missing(self):
        """10.7 ProblemIdentificationAgent 缺少 parcel_id 时附加提示"""
        from framework.agents.specialized.problem_agent import (
            ProblemIdentificationAgent, FARMland_DIAGNOSIS_AVAILABLE
        )

        if not FARMland_DIAGNOSIS_AVAILABLE:
            pytest.skip("FARMland_DIAGNOSIS_AVAILABLE 为 False，跳过提示测试")

        out = ProblemIdentificationAgent().answer_question("我这块地有没有问题？", {})
        assert "hint" in out or "need_input" in out

    def test_acidification_agent_hint_when_parcel_id_missing(self):
        """10.7 AcidificationRemediationAgent 缺少 parcel_id 时附加提示"""
        from framework.agents.specialized.acidification_agent import (
            AcidificationRemediationAgent, ACIDIFICATION_MODEL_AVAILABLE
        )

        if not ACIDIFICATION_MODEL_AVAILABLE:
            pytest.skip("ACIDIFICATION_MODEL_AVAILABLE 为 False，跳过提示测试")

        out = AcidificationRemediationAgent().answer_question(
            "我的田酸化了，pH是5.0，要施加多少碱性调理剂？", {})
        assert "hint" in out or "need_input" in out


# ---------------------------------------------------------------------------
# 9.5, 10.8 综合诊断整合
# ---------------------------------------------------------------------------
class TestComprehensiveDiagnosis:
    """验证 StabilityRiskAgent + ProblemIdentificationAgent 整合"""

    def test_comprehensive_diagnosis_combines_results(self):
        """综合诊断同时返回稳定性和障碍诊断信息"""
        from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
        from framework.agents.specialized.problem_agent import ProblemIdentificationAgent

        stability_out = StabilityRiskAgent().answer_question("全省耕地质量稳定性如何？", {})
        problem_out = ProblemIdentificationAgent().answer_question("全省耕地质量存在哪些问题？", {})

        combined = {
            "stability": stability_out,
            "diagnosis": problem_out,
        }

        assert "answer" in stability_out
        assert "answer" in problem_out
        assert "稳定" in stability_out["answer"]
        assert "障碍" in problem_out["answer"] or "问题" in problem_out["answer"]
        assert "stability" in combined
        assert "diagnosis" in combined


# ---------------------------------------------------------------------------
# 10.10 端到端集成测试
# ---------------------------------------------------------------------------
class TestEndToEndIntegration:
    """端到端集成测试：run_thematic_model → 响应结构"""

    @geopandas_required
    def test_e2e_stability_full_pipeline(self):
        """端到端：稳定性模型从调度到响应结构"""
        from ai_culti_demo.thematic_models import run_thematic_model

        mock_storage = MagicMock()
        mock_storage.is_ready.return_value = True
        mock_storage.get_result.return_value = {
            "parcel_id": "E2E001", "grade": 3, "score": 75.0, "module": 1,
        }

        with patch("ai_culti_demo.thematic_models.StabilityStorage", return_value=mock_storage):
            out = run_thematic_model({
                "model_id": "stability-risk-evaluation",
                "parcel_id": "E2E001",
            })

        assert out["status"] == "ok"
        assert out["model"]["model_id"] == "stability-risk-evaluation"
        assert out["reliability"]["level"] == "real_model"
        assert out["fallback"]["used"] is False
        assert len(out["findings"]) >= 1
        assert "stability_detail" in out

    def test_e2e_grade_full_pipeline(self):
        """端到端：质量等级模型从调度到响应结构"""
        from ai_culti_demo.thematic_models import run_thematic_model

        mock_exe_result = {
            "status": "ok",
            "quality_grade": "4",
            "composite_index": 82.3,
            "indicators": [
                {"name": "pH", "raw_value": 6.5, "membership": 0.95, "weight": 0.1},
                {"name": "有机质", "raw_value": 25.0, "membership": 0.85, "weight": 0.15},
            ],
            "obstacle_degree": [
                {"rank": 1, "indicator": "有效磷", "degree": 0.15},
            ],
        }
        with patch("ai_culti_demo.thematic_models.run_grade_evaluation", return_value=mock_exe_result):
            out = run_thematic_model({
                "model_id": "quality-grade-evaluation",
                "parcel_code": "E2E002",
            })

        assert out["status"] == "ok"
        assert out["model"]["model_id"] == "quality-grade-evaluation"
        assert out["reliability"]["level"] == "real_model"
        assert out["grade_detail"]["quality_grade"] == "4"
        assert len(out["findings"]) >= 1
