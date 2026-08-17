from __future__ import annotations
from typing import Any, Dict, List
import logging

from ..base import BaseAgent
from ..mock_data import MockDataLoader
from ...domain.data.parcel_data_accessor import ParcelDataAccessor
from ...models.thematic_model import QualityGradeResult

logger = logging.getLogger(__name__)

# 尝试导入实际 Python 模型实现
try:
    from ai_culti_demo.farmland_grade_eval import run_grade_evaluation
    GRADE_EVAL_AVAILABLE = True
except ImportError:
    GRADE_EVAL_AVAILABLE = False


class FarmlandGradeAgent(BaseAgent):
    """耕地质量等级评价智能体（Python 模型实现）"""

    def __init__(self):
        super().__init__(
            name="FarmlandGradeAgent",
            description="通过 Python 模型进行耕地质量等级评价",
            model_id="quality-grade-evaluation",
            domain="grade",
        )

    def _collect_inputs(self, context: dict) -> dict:
        """DB 优先获取地块指标，未命中时降级到 CSV run_grade_evaluation。"""
        parcel_id = context.get("parcel_id") or context.get("parcel_code")

        if parcel_id:
            accessor = ParcelDataAccessor()
            indicators = accessor.get_parcel_indicators(str(parcel_id))
            if indicators is not None:
                inputs = self._map_indicators_to_inputs(indicators)
                inputs["parcel_id"] = str(parcel_id)
                inputs["data_source"] = "db"
                return inputs

        logger.warning("Parcel %s not in DB, falling back to CSV source", parcel_id)
        inputs = self._collect_inputs_from_legacy(context)
        inputs["data_source"] = "fallback"
        return inputs

    def _collect_inputs_from_legacy(self, context: dict) -> dict:
        """原有数据源：CSV run_grade_evaluation。"""
        return {
            "parcel_code": context.get("parcel_code"),
            "exe_path": context.get("exe_path"),
            "dat_path": context.get("dat_path"),
        }

    def _map_indicators_to_inputs(self, indicators: dict) -> dict:
        """将 soil_indicators JSON 映射为质量等级评价输入字段。"""
        return {
            "soil_ph": indicators.get("soil_ph"),
            "organic_matter": indicators.get("organic_matter"),
            "available_potassium": indicators.get("available_potassium"),
            "available_phosphorus": indicators.get("available_phosphorus"),
            "soil_bulk_density": indicators.get("soil_bulk_density"),
            "topsoil_texture": indicators.get("topsoil_texture"),
            "irrigation_capacity": indicators.get("irrigation_capacity"),
            "drainage_capacity": indicators.get("drainage_capacity"),
            "terrain_position": indicators.get("terrain_position"),
            "topsoil_thickness": indicators.get("topsoil_thickness"),
        }

    def _build_result_record(self, execution_id: int, outputs: dict):
        """构建 QualityGradeResult ORM 实例。legacy 路径无 parcel_id 时返回 None。"""
        parcel_id = outputs.get("parcel_id")
        if not parcel_id:
            return None
        return QualityGradeResult(
            execution_id=execution_id,
            parcel_id=parcel_id,
            quality_grade=str(outputs.get("quality_grade", "0")),
            composite_index=float(outputs.get("composite_index", 0.0)),
            input_snapshot=outputs,
            simulated=True,
        )

    def execute(self, data: Dict[str, Any] = None) -> Dict[str, Any]:
        if not data:
            data = {}

        inputs = self._collect_inputs(data)
        data_source = inputs.pop("data_source", "unknown")

        try:
            if data_source == "db":
                # DB 路径：直接使用 soil_indicators 作为评价结果快照
                outputs = {
                    "parcel_id": inputs.get("parcel_id"),
                    "quality_grade": inputs.get("quality_grade", "0"),
                    "composite_index": inputs.get("composite_index", 0.0),
                    "indicators": inputs,
                }
                status = "ok"
            elif not GRADE_EVAL_AVAILABLE:
                return {
                    "status": "degraded",
                    "degraded": True,
                    "reason": "model_unavailable",
                    "agent_id": "model-2",
                    "model_id": "quality-grade-evaluation",
                    "message": "模型2质量等级评价模块未安装，无法执行真实评价",
                    "data_source": data_source,
                    "persisted": False,
                }
            else:
                # Legacy 路径：CSV run_grade_evaluation
                parcel_code = inputs.get("parcel_code")
                if not parcel_code:
                    return {
                        "status": "degraded",
                        "degraded": True,
                        "reason": "missing_input",
                        "agent_id": "model-2",
                        "model_id": "quality-grade-evaluation",
                        "message": "缺少 parcel_code，无法查询真实质量等级结果",
                        "data_source": data_source,
                        "persisted": False,
                    }
                exe_path = inputs.get("exe_path")
                dat_path = inputs.get("dat_path")
                result = run_grade_evaluation(parcel_code, exe_path, dat_path)
                if result.get("status") != "ok":
                    return {
                        "status": "degraded",
                        "degraded": True,
                        "reason": "import_failed",
                        "agent_id": "model-2",
                        "model_id": "quality-grade-evaluation",
                        "message": f"地块 {parcel_code} 的质量等级数据未就绪或查询失败",
                        "data_source": data_source,
                        "persisted": False,
                    }
                outputs = result
                status = "degraded"

            persisted = self._persist_result(
                agent_id=self.agent_id,
                parcel_id=data.get("parcel_id") or data.get("parcel_code"),
                inputs=inputs,
                outputs=outputs,
                status=status,
            )

            return {
                "status": "ok",
                "simulated": data_source != "db",
                "result": outputs,
                "data_source": data_source,
                "persisted": persisted,
            }
        except Exception as e:
            self._persist_result(
                agent_id=self.agent_id,
                parcel_id=data.get("parcel_id"),
                inputs=inputs,
                outputs={"error": str(e)},
                status="error",
            )
            return {
                "status": "degraded",
                "degraded": True,
                "reason": "exception",
                "message": str(e),
                "data_source": data_source,
                "persisted": False,
            }

    def _get_real_grade(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """尝试获取实际质量等级评价结果"""
        if not GRADE_EVAL_AVAILABLE:
            return {}

        parcel_code = context.get("parcel_code") or context.get("data", {}).get("parcel_code")
        exe_path = context.get("exe_path") or context.get("data", {}).get("exe_path")
        dat_path = context.get("dat_path") or context.get("data", {}).get("dat_path")

        if not parcel_code:
            return {}

        try:
            result = run_grade_evaluation(parcel_code, exe_path, dat_path)
            if result.get("status") == "ok":
                return result
        except Exception:
            pass

        return {}

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # 检测实际模型可用但缺少地块代码的情况（用于附加提示）
        need_parcel_hint = False
        if GRADE_EVAL_AVAILABLE:
            parcel_code = context.get("parcel_code") or context.get("data", {}).get("parcel_code")
            if not parcel_code:
                need_parcel_hint = True

        # 尝试使用实际模型
        real_result = self._get_real_grade(context)

        if real_result:
            grade = real_result.get("quality_grade", "未知")
            composite_index = real_result.get("composite_index", 0)
            indicators = real_result.get("indicators", [])
            obstacle_degree = real_result.get("obstacle_degree", [])

            if "质量等级" in question or "等级评价" in question:
                answer = (
                    f"耕地质量等级评价结果：质量等级为{grade}级，"
                    f"综合指数：{composite_index}。"
                    f"共{len(indicators)}个指标参与评价。"
                )
                evidence = [
                    {"metric": "质量等级", "value": grade},
                    {"metric": "综合指数", "value": composite_index},
                ]
                confidence = 0.90
            elif "障碍度" in question or "障碍" in question:
                obstacle_str = "; ".join([f"{o['indicator']}({o['degree']})" for o in obstacle_degree]) or "无明显障碍"
                answer = (
                    f"障碍度排序结果：{obstacle_str}。"
                    f"质量等级为{grade}级。"
                )
                evidence = [
                    {"metric": "质量等级", "value": grade},
                    {"metric": "障碍度排序", "value": obstacle_str},
                ]
                confidence = 0.88
            elif "综合指数" in question:
                answer = (
                    f"综合指数评价结果：{composite_index}，"
                    f"对应质量等级为{grade}级。"
                )
                evidence = [
                    {"metric": "综合指数", "value": composite_index},
                    {"metric": "质量等级", "value": grade},
                ]
                confidence = 0.90
            else:
                answer = (
                    f"耕地质量等级评价结果：质量等级为{grade}级，"
                    f"综合指数：{composite_index}。"
                )
                evidence = [
                    {"metric": "质量等级", "value": grade},
                    {"metric": "综合指数", "value": composite_index},
                ]
                confidence = 0.88

            return {
                "answer": answer,
                "evidence": evidence,
                "confidence": confidence,
                "simulated": False,
                "grade_detail": real_result,
            }

        # 真实质量等级结果不可用时返回统一降级响应
        if not GRADE_EVAL_AVAILABLE:
            reason = "model_unavailable"
            hint = "模型2质量等级评价模块未安装"
        else:
            parcel_code = context.get("parcel_code") or context.get("data", {}).get("parcel_code")
            if not parcel_code:
                reason = "missing_input"
                hint = "提供地块代码（parcel_code）后可获取真实质量等级评价结果"
            else:
                reason = "import_failed"
                hint = f"地块 {parcel_code} 的质量等级数据未就绪"

        return {
            "answer": f"当前无法提供真实质量等级评价结果：{hint}。",
            "evidence": [],
            "confidence": 0.0,
            "simulated": False,
            "degraded": True,
            "reason": reason,
            "need_input": "parcel_code" if reason == "missing_input" else None,
        }
