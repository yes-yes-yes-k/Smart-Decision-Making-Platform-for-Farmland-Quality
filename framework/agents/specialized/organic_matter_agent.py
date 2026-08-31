from __future__ import annotations

from typing import Any, Dict
import logging

from ..base import BaseAgent, ProfessionalInputRejected
from ..mock_data import MockDataLoader
from ...domain.data.parcel_data_accessor import ParcelDataAccessor
from ...domain.other_models.model_5 import EXTERNAL_FIELD_MAP, model_5_execution

logger = logging.getLogger(__name__)


# 旧规则仅作为没有任何模型特征时的明确降级路径，不代表真实 RF 结果。
MOCK_INPUTS = {
    "organic_matter": 22.0,
    "total_nitrogen": 1.2,
    "cn_ratio": 11.5,
    "clay_content": 35.0,
}

ORGANIC_RULES = [
    (lambda v: v < 10.0, "极低"),
    (lambda v: 10.0 <= v < 20.0, "低"),
    (lambda v: 20.0 <= v < 30.0, "中"),
    (lambda v: 30.0 <= v < 40.0, "高"),
    (lambda v: v >= 40.0, "极高"),
]

MANURE_DOSAGE_RULES = {
    "极低": 2000.0,
    "低": 1500.0,
    "中": 1000.0,
    "高": 500.0,
    "极高": 0.0,
}

MODEL_FEATURES = {
    "pH", "SOCbe", "SOMbe", "TN", "TP", "TK", "AP", "AK", "Gap",
    "Dose", "Fertilizer type", *EXTERNAL_FIELD_MAP.keys(),
}


class OrganicMatterAgent(BaseAgent):
    """模型5：真实肥力 ML 优先，规则结果仅用于明确降级。"""

    def __init__(self):
        super().__init__(
            name="OrganicMatterAgent",
            description="基于韶关 RF/全局 ETR 的有机质培肥提升与施用量预测",
            model_id="model-5",
            domain="organic_matter",
        )

    def _collect_inputs(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """DB 优先获取地块指标，未命中时降级到用户传入参数。"""
        task = task or {}
        parcel_id = task.get("parcel_id")

        if parcel_id:
            accessor = ParcelDataAccessor()
            indicators = accessor.get_parcel_indicators(str(parcel_id))
            if indicators is not None:
                inputs = dict(indicators)
                inputs["parcel_id"] = str(parcel_id)
                inputs["data_source"] = "db"
                return inputs

        logger.warning("Parcel %s not in DB, falling back to user inputs", parcel_id)
        inputs = self._collect_inputs_from_legacy(task)
        inputs["data_source"] = "fallback"
        return inputs

    @staticmethod
    def _collect_inputs_from_legacy(task: Dict[str, Any] | None) -> Dict[str, Any]:
        """原有数据源：用户传入参数（原 _collect_inputs 逻辑）。"""
        task = task or {}
        inputs: Dict[str, Any] = {}
        if isinstance(task.get("data"), dict):
            inputs.update(task["data"])
            if isinstance(task["data"].get("indicators"), dict):
                inputs.update(task["data"]["indicators"])
        if isinstance(task.get("task"), dict):
            inputs.update(task["task"])
            if isinstance(task["task"].get("indicators"), dict):
                inputs.update(task["task"]["indicators"])
        if isinstance(task.get("indicators"), dict):
            inputs.update(task["indicators"])
        inputs.update({k: v for k, v in task.items() if k not in {"data", "task"}})
        return inputs

    def _build_result_record(self, execution_id: int, outputs: dict):
        """构建 OrganicMatterResult ORM 实例（县级分析，无 parcel_id）。"""
        from ...models.thematic_model import OrganicMatterResult

        result_data = outputs.get("result", outputs)
        return OrganicMatterResult(
            execution_id=execution_id,
            soil_ph=float(outputs.get("soil_ph", 0.0) or 0.0),
            organic_matter=float(result_data.get("organic_matter", 0.0) or 0.0),
            available_potassium=float(outputs.get("available_potassium", 0.0) or 0.0),
            level=result_data.get("level", "未知"),
            potential_increase=float(result_data.get("potential_increase", 0.0) or 0.0),
            simulated=True,
        )

    @staticmethod
    def _has_model_features(inputs: Dict[str, Any]) -> bool:
        return any(str(key).strip() in MODEL_FEATURES and value is not None
                   for key, value in inputs.items())

    @staticmethod
    def _rule_fallback(inputs: Dict[str, Any]) -> Dict[str, Any]:
        data = MockDataLoader.merge_defaults(inputs, MOCK_INPUTS)
        om = float(data["organic_matter"])
        level = MockDataLoader.apply_threshold(om, ORGANIC_RULES)
        manure_dosage = MANURE_DOSAGE_RULES.get(level, 0.0)
        return {
            "organic_matter": om,
            "level": level,
            "manure_dosage": manure_dosage,
            "potential_increase": round(manure_dosage / 1000.0 * 1.5, 2),
            "total_nitrogen": data["total_nitrogen"],
            "cn_ratio": data["cn_ratio"],
            "clay_content": data["clay_content"],
        }

    def _execute_rule_fallback(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "ok",
            "degraded": True,
            "result": self._rule_fallback(inputs),
            "metadata": {
                "simulated": True,
                "fallback": True,
                "fallback_reason": "missing_model_features",
                "need_input": sorted(MODEL_FEATURES - set(inputs)),
            },
        }

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task = task or {}
        chat = task.get("execution_channel") == "chat"
        if chat and (not task.get("guard_passed") or not task.get("parcel_id")):
            raise ProfessionalInputRejected("verified_parcel_required", "有机质聊天计算需要已验证地块")
        inputs = self._collect_inputs(task)
        data_source = inputs.pop("data_source", "unknown")
        if chat and data_source != "db":
            raise ProfessionalInputRejected("verified_parcel_required", "已验证地块未命中权威数据")

        try:
            if not self._has_model_features(inputs) and data_source != "db":
                # Legacy 降级路径：规则 fallback
                outputs = self._rule_fallback(inputs)
                status = "degraded"
                simulated = True
            elif data_source == "db":
                # DB 路径：调用 predict_dose 预测推荐施用量
                from framework.domain.calculations.organic_matter_calculation import predict_dose
                accessor = ParcelDataAccessor()
                mapped = accessor._map_indicators_to_inputs(inputs, "model-5")
                try:
                    from framework.models.thematic_model import ParcelInfo
                    parcel = ParcelInfo.query.filter_by(parcel_id=str(inputs.get("parcel_id"))).first()
                except Exception:
                    parcel = None
                land_type = (parcel.land_type if parcel else None) or inputs.get("land_type") or "upland"
                dose, simulated_flag = predict_dose(mapped, land_type)
                outputs = {
                    "parcel_id": inputs.get("parcel_id"),
                    "dose": dose,
                    "simulated": simulated_flag,
                }
                status = "ok"
                simulated = simulated_flag
            else:
                # Legacy 路径：ML 模型
                result = model_5_execution(
                    inputs,
                    land_type=inputs.get("land_type"),
                )
                outputs = result
                status = result.get("status", "degraded")
                # ML 成功执行时 simulated=False；fallback/rejected 沿用模型自身判定
                simulated = bool(result.get("simulated", status != "success"))

            persisted = self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id") if isinstance(task, dict) else None,
                inputs=inputs,
                outputs=outputs,
                status=status,
                execution_context=task.get("execution_context") if isinstance(task, dict) else None,
            )

            return {
                "status": status,
                "simulated": simulated,
                "result": outputs,
                "metadata": {
                    "simulated": simulated,
                    "data_source": data_source,
                },
                "data_source": data_source,
                "persisted": persisted,
            }
        except Exception as e:
            self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id") if isinstance(task, dict) else None,
                inputs=inputs,
                outputs={"error": str(e)},
                status="error",
                execution_context=task.get("execution_context") if isinstance(task, dict) else None,
            )
            return {
                "status": "error",
                "result": {"error": str(e)},
                "data_source": data_source,
                "persisted": False,
            }

    @staticmethod
    def _answer_from_ml(question: str, result: Dict[str, Any]) -> Dict[str, Any]:
        status = result.get("status")
        if status != "success":
            reason = result.get("reason") or result.get("fallback_reason") or "model_unavailable"
            answer = f"model-5 当前无法完成真实预测（{reason}）。请补充完整土壤特征或检查模型文件。"
            return {
                "answer": answer,
                "evidence": [{"reason": reason}],
                "confidence": result.get("dose_confidence", 0.3),
                "simulated": True,
                "model_id": "model-5",
                "model_version": result.get("model_version"),
                "fallback": True,
                "fallback_reason": reason,
            }

        land_label = {"upland": "旱地", "paddy": "水田"}.get(result.get("land_type"), "非韶关区域")
        answer = (
            f"有机质培肥模型（{land_label}）预测：SOC约 {result['soc_prediction']} g/kg，"
            f"建议施用量约 {result['dose_prediction']} t/ha。"
            f"模型版本：{result.get('model_version', '未知')}。"
        )
        if "原因" in question:
            answer += "预测结果仅用于辅助决策，最终方案需结合土壤和农艺条件复核。"
        evidence = [
            {"metric": "soc_prediction", "value": result.get("soc_prediction"), "unit": "g/kg"},
            {"metric": "dose_prediction", "value": result.get("dose_prediction"), "unit": "t/ha"},
            {"metric": "dose_confidence", "value": result.get("dose_confidence")},
            {"metric": "model_version", "value": result.get("model_version")},
        ]
        if result.get("imputation_applied"):
            evidence.append({"imputed_features": result.get("imputed_features", [])})
        if result.get("dose_warning"):
            evidence.append({"warning": result["dose_warning"]})
        return {
            "answer": answer,
            "evidence": evidence,
            "confidence": result.get("dose_confidence", 0.0),
            "simulated": False,
            "model_id": "model-5",
            "model_version": result.get("model_version"),
            "fertility_detail": result,
        }

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        inputs = self._collect_inputs(context)
        if self._has_model_features(inputs):
            return self._answer_from_ml(question, self.execute(inputs)["result"])

        computed = self._rule_fallback(inputs)
        if "本县" in question or "平均含量" in question:
            answer = (
                f"本县耕地土壤有机质平均含量 {computed['organic_matter']} g/kg，"
                f"等级为{computed['level']}。当前未提供模型特征，以上为规则降级结果。"
            )
            evidence = [{"metric": "organic_matter", "value": computed["organic_matter"], "unit": "g/kg"}]
        elif "原因" in question and ("有机质" in question or "低" in question):
            answer = (
                f"耕地有机质含量低的原因：受土壤类型、气候、地形、耕作制度、"
                f"秸秆还田与施肥管理影响。当前未提供模型特征，暂以规则降级说明。"
            )
            evidence = [{"factors": "土壤类型/气候/地形/耕作制度/秸秆还田/施肥管理"}]
        elif "含量" in question or "分布" in question or "现状" in question:
            answer = (
                f"全省耕地有机质含量平均 {computed['organic_matter']} g/kg，等级为{computed['level']}。"
                "当前未提供模型特征，以上为规则降级结果。"
            )
            evidence = [{"metric": "organic_matter", "value": computed["organic_matter"], "unit": "g/kg"}]
        else:
            answer = (
                f"有机质等级为{computed['level']}，规则降级建议有机肥施用量 "
                f"{computed['manure_dosage']} kg/亩。请提供土壤特征后调用 model-5 真实预测。"
            )
            evidence = [{"metric": "manure_dosage", "value": computed["manure_dosage"], "unit": "kg/亩"}]
        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": 0.5,
            "model_id": "model-5",
            "fallback": True,
            "fallback_reason": "missing_model_features",
            "need_input": sorted(MODEL_FEATURES - set(inputs)),
        })
