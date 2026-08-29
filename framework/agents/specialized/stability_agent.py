from __future__ import annotations
from typing import Any, Dict, List
import logging

from ..base import BaseAgent
from ..mock_data import MockDataLoader
from ...domain.data.parcel_data_accessor import ParcelDataAccessor

logger = logging.getLogger(__name__)

# 尝试导入实际模型1实现
try:
    from ai_culti_demo.farmland_stability import StabilityStorage, get_parcel_result
    STABILITY_MODEL_AVAILABLE = True
except ImportError:
    STABILITY_MODEL_AVAILABLE = False


class StabilityRiskAgent(BaseAgent):
    """模型1：耕地质量稳定性与退化风险评价智能体"""

    def __init__(self):
        super().__init__(
            name="StabilityRiskAgent",
            description="评价耕地质量等级稳定性并识别退化风险",
            model_id="stability-risk-evaluation",
            domain="stability",
        )

    def _collect_inputs(self, context: dict) -> dict:
        """DB 优先获取地块指标，未命中时降级到 StabilityStorage。"""
        parcel_id = context.get("parcel_id") or context.get("data", {}).get("parcel_id")

        if parcel_id:
            accessor = ParcelDataAccessor()
            indicators = accessor.get_parcel_indicators(str(parcel_id))
            if indicators is not None:
                inputs = dict(indicators)
                inputs["parcel_id"] = str(parcel_id)
                inputs["data_source"] = "db"
                return inputs

        logger.warning("Parcel %s not in DB, falling back to StabilityStorage", parcel_id)
        inputs = self._collect_inputs_from_legacy(context)
        inputs["data_source"] = "fallback"
        return inputs

    def _collect_inputs_from_legacy(self, context: dict) -> dict:
        """原有数据源：StabilityStorage。"""
        return {
            "parcel_id": context.get("parcel_id") or context.get("data", {}).get("parcel_id"),
            "db_path": context.get("db_path") or context.get("data", {}).get("db_path"),
        }

    def _build_result_record(self, execution_id: int, outputs: dict):
        """构建 StabilityRiskResult ORM 实例。legacy 路径无 parcel_id 时返回 None。"""
        from ...models.thematic_model import StabilityRiskResult

        parcel_id = outputs.get("parcel_id")
        if not parcel_id:
            return None
        return StabilityRiskResult(
            execution_id=execution_id,
            parcel_id=parcel_id,
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
                # DB 路径：调用 calculate_stability
                from framework.domain.calculations.stability_calculation import calculate_stability
                from framework.models.thematic_model import ParcelHistorySnapshot, ParcelInfo
                from framework.models.user import db
                accessor = ParcelDataAccessor()
                mapped = accessor._map_indicators_to_inputs(inputs, "model-1")
                parcel_id = str(inputs.get("parcel_id"))
                # 查询历史快照
                try:
                    history = ParcelHistorySnapshot.query.filter_by(parcel_id=parcel_id).all()
                    history_data = [
                        {
                            "survey_year": h.survey_year,
                            "soil_indicators": h.soil_indicators,
                            "quality_grade": h.quality_grade,
                            "composite_index": h.composite_index,
                        }
                        for h in history
                    ]
                except Exception:
                    db.session.rollback()
                    history_data = []
                # PostGIS 邻域查询
                try:
                    parcel = ParcelInfo.query.filter_by(parcel_id=parcel_id).first()
                except Exception:
                    db.session.rollback()
                    parcel = None
                neighbors = []
                if parcel and parcel.geom:
                    try:
                        from sqlalchemy import text as sa_text
                        # 使用 geography 类型，ST_DWithin 第三参数为米
                        # geometry 类型下 1000 表示 1000 度（覆盖全球）
                        neighbor_rows = db.session.execute(
                            sa_text(
                                "SELECT parcel_id, soil_indicators "
                                "FROM parcel_info "
                                "WHERE parcel_id != :pid "
                                "AND ST_DWithin(geom::geography, "
                                "ST_GeomFromText(:wkt, 4326)::geography, :radius)"
                            ),
                            {
                                "pid": parcel_id,
                                "wkt": db.session.execute(
                                    sa_text("SELECT ST_AsText(geom) FROM parcel_info WHERE parcel_id = :pid"),
                                    {"pid": parcel_id},
                                ).scalar(),
                                "radius": 1000,  # 1000 米 = 1km
                            },
                        ).fetchall()
                        neighbors = [
                            {
                                "parcel_id": r[0],
                                "quality_grade": (r[1] or {}).get("quality_grade") if isinstance(r[1], dict) else None,
                            }
                            for r in neighbor_rows
                        ]
                    except Exception:
                        db.session.rollback()
                        neighbors = []
                # 计算稳定性
                parcel_info = {
                    "indicators": mapped,
                    "quality_index": inputs.get("quality_index", 0.5),
                    "quality_grade": inputs.get("quality_grade", "5"),
                    "area_code": inputs.get("area_code", "440281"),
                }
                stability_result = calculate_stability(parcel_info, history_data, neighbors)
                outputs = {"parcel_id": parcel_id, "stability_modules": stability_result}
                status = "ok"
            elif not STABILITY_MODEL_AVAILABLE:
                return {
                    "status": "degraded",
                    "degraded": True,
                    "reason": "model_unavailable",
                    "agent_id": "model-1",
                    "model_id": "stability-risk-evaluation",
                    "message": "模型1稳定性模块未安装，无法执行真实评价",
                    "data_source": data_source,
                    "persisted": False,
                }
            else:
                # Legacy 路径：StabilityStorage
                parcel_id = inputs.get("parcel_id")
                if not parcel_id:
                    return {
                        "status": "degraded",
                        "degraded": True,
                        "reason": "missing_input",
                        "agent_id": "model-1",
                        "model_id": "stability-risk-evaluation",
                        "message": "缺少 parcel_id，无法查询真实稳定性结果",
                        "data_source": data_source,
                        "persisted": False,
                    }
                db_path = inputs.get("db_path")
                storage = StabilityStorage(db_path)
                result = storage.get_result(parcel_id)
                if not result:
                    return {
                        "status": "degraded",
                        "degraded": True,
                        "reason": "import_failed",
                        "agent_id": "model-1",
                        "model_id": "stability-risk-evaluation",
                        "message": f"地块 {parcel_id} 的稳定性数据未就绪或查询失败",
                        "data_source": data_source,
                        "persisted": False,
                    }
                outputs = result
                status = "degraded"
                data_source = "precomputed"

            persisted = self._persist_result(
                agent_id=self.agent_id,
                parcel_id=data.get("parcel_id") or inputs.get("parcel_id"),
                inputs={**inputs, "data_source": data_source},
                outputs=outputs,
                status=status,
            )

            return {
                "status": status,
                "simulated": False,
                "result": outputs,
                "data_source": data_source,
                "persisted": persisted,
            }
        except Exception as e:
            self._persist_result(
                agent_id=self.agent_id,
                parcel_id=data.get("parcel_id"),
                inputs={**inputs, "data_source": data_source},
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

    def _get_real_stability(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """尝试获取实际稳定性评价结果"""
        if not STABILITY_MODEL_AVAILABLE:
            return {}

        parcel_id = context.get("parcel_id") or context.get("data", {}).get("parcel_id")
        db_path = context.get("db_path") or context.get("data", {}).get("db_path")

        if not parcel_id:
            return {}

        try:
            storage = StabilityStorage(db_path)
            if not storage.is_ready():
                return {}
            result = storage.get_result(parcel_id)
            if result:
                return result
        except Exception:
            pass

        return {}

    @staticmethod
    def _module_metric(
        result: Dict[str, Any], module: int, metric: str, default: float,
    ) -> float:
        """从稳定性结果库的模块分组结构读取数值指标。"""
        value = result.get(f"module_{module}", {}).get(metric, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # 尝试使用实际模型
        real_result = self._get_real_stability(context)

        if real_result:
            stability_score = self._module_metric(
                real_result, 2, '指标支撑均衡度_绝对', 0.0,
            )
            drop_risk = self._module_metric(
                real_result, 6, '掉级风险_绝对', 0.0,
            )
            if drop_risk < 0.2:
                risk_level = "低风险"
            elif drop_risk < 0.5:
                risk_level = "中风险"
            else:
                risk_level = "高风险"

            if "稳定性" in question or "稳不稳" in question:
                answer = (
                    f"您的地块耕地质量稳定性评价结果：稳定性得分 {stability_score:.2f}，"
                    f"稳定性等级：{'稳定' if stability_score > 0.8 else '较稳定'}。"
                )
                evidence = [
                    {"metric": "稳定性得分", "value": stability_score},
                    {"metric": "稳定性等级", "value": "稳定" if stability_score > 0.8 else "较稳定"},
                ]
                confidence = 0.88
            elif "退化风险" in question or "掉级" in question:
                answer = (
                    f"退化风险评价结果：掉级风险得分 {drop_risk:.2f}，风险等级：{risk_level}。"
                    f"九模块评价均已完成，包括等级边界安全度、指标支撑均衡度等。"
                )
                evidence = [
                    {"metric": "掉级风险", "value": drop_risk},
                    {"metric": "风险等级", "value": risk_level},
                ]
                confidence = 0.85
            else:
                answer = (
                    f"稳定性评价结果：稳定性得分 {stability_score:.2f}，"
                    f"风险等级：{risk_level}。"
                    f"九模块评价均已完成。"
                )
                evidence = [
                    {"metric": "稳定性得分", "value": stability_score},
                    {"metric": "风险等级", "value": risk_level},
                ]
                confidence = 0.85

            return {
                "answer": answer,
                "evidence": evidence,
                "confidence": confidence,
                "simulated": False,
                "stability_detail": real_result,
            }

        # 真实稳定性结果不可用时返回统一降级响应
        if not STABILITY_MODEL_AVAILABLE:
            reason = "model_unavailable"
            hint = "模型1稳定性模块未安装"
        else:
            parcel_id = context.get("parcel_id") or context.get("data", {}).get("parcel_id")
            if not parcel_id:
                reason = "missing_input"
                hint = "提供地块 ID（parcel_id）后可获取真实稳定性评价结果"
            else:
                reason = "import_failed"
                hint = f"地块 {parcel_id} 的稳定性数据未就绪"

        return {
            "answer": f"当前无法提供真实稳定性评价结果：{hint}。",
            "evidence": [],
            "confidence": 0.0,
            "simulated": False,
            "degraded": True,
            "reason": reason,
            "need_input": "parcel_id" if reason == "missing_input" else None,
        }
