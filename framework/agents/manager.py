from __future__ import annotations
from typing import Any, Dict, List

from .base import BaseAgent
from .router import RoleRouter


# 肥力相关关键词（与 FertilityMLAgent.FERTILITY_KEYWORDS 保持一致）
FERTILITY_KEYWORDS = [
    "有机碳", "SOC", "soc",
    "施用量", "施肥量", "施肥", "Dose", "dose", "剂量", "施多少肥",
    "肥力", "综合肥力",
    "秸秆", "有机肥", "培肥",
]

# 质量等级相关关键词（与 nodes.QUESTION_TYPE_5_KEYWORDS 保持一致）
# 不从 nodes.py import 以避免循环依赖（nodes.py 已 from manager import agent_manager）
GRADE_KEYWORDS = [
    "质量等级", "等级评价", "综合指数", "指标隶属度", "障碍度排序",
    "耕地质量等级", "质量评价", "等级评定", "指标权重",
]


class _StubAgent(BaseAgent):
    """桩智能体，在专业智能体实现前用于 Manager 单元测试。"""

    def __init__(self, name: str, description: str, model_id: str, domain: str):
        super().__init__(name, description, model_id, domain)

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "ok",
            "result": {"stub": True, "model_id": self.model_id},
            "metadata": {"simulated": True},
        }

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "answer": f"[{self.model_id}] 桩智能体回复：{question}",
            "evidence": [{"source": "stub", "model_id": self.model_id}],
            "confidence": 0.5,
            "simulated": True,
        }


class AgentManager:
    """中心化智能体编排器。"""

    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.router = RoleRouter()
        self._register_agents()

    def _register_agents(self) -> None:
        """注册所有 7 个专业智能体；若专业实现尚未就绪，回退到桩智能体。"""
        specs = [
            ("model-1", "StabilityRiskAgent", "耕地质量等级稳定性与退化风险识别", "stability"),
            ("model-2", "PotentialAssessmentAgent", "耕地质量提升潜力评估", "potential"),
            ("model-3", "ProblemIdentificationAgent", "耕地质量主要问题精准识别", "problem"),
            ("model-4", "AcidificationRemediationAgent", "耕地土壤酸化改良", "acidification"),
            ("model-5", "OrganicMatterAgent", "耕地土壤有机质培肥提升", "organic_matter"),
            ("model-6", "FertilityMLAgent", "耕地肥力 SOC/Dose ML 预测", "fertility_ml"),
            ("model-7", "FarmlandGradeAgent", "耕地质量等级评价（Fortran exe）", "grade"),
        ]

        real_agents = self._load_real_agents()
        for model_id, class_name, description, domain in specs:
            if model_id in real_agents:
                self.agents[model_id] = real_agents[model_id]
            else:
                self.agents[model_id] = _StubAgent(class_name, description, model_id, domain)

        # 显式声明依赖关系
        self.agents["model-1"].dependencies = []
        self.agents["model-2"].dependencies = []
        self.agents["model-3"].dependencies = ["model-2"]
        self.agents["model-4"].dependencies = []
        self.agents["model-5"].dependencies = []
        self.agents["model-6"].dependencies = []
        self.agents["model-7"].dependencies = []

    def _load_real_agents(self) -> Dict[str, BaseAgent]:
        """尝试加载专业智能体实现，失败时返回空字典。"""
        real: Dict[str, BaseAgent] = {}
        # model-1: 优先加载带真实模型集成的新版 stability_agent，
        # 回退到旧版 stability_risk_agent（纯 mock）
        try:
            from .specialized.stability_agent import StabilityRiskAgent
            real["model-1"] = StabilityRiskAgent()
        except ImportError:
            try:
                from .specialized.stability_risk_agent import StabilityRiskAgent
                real["model-1"] = StabilityRiskAgent()
            except ImportError:
                pass
        try:
            from .specialized.potential_agent import PotentialAssessmentAgent
            real["model-2"] = PotentialAssessmentAgent()
        except ImportError:
            pass
        try:
            from .specialized.problem_agent import ProblemIdentificationAgent
            real["model-3"] = ProblemIdentificationAgent()
        except ImportError:
            pass
        try:
            from .specialized.acidification_agent import AcidificationRemediationAgent
            real["model-4"] = AcidificationRemediationAgent()
        except ImportError:
            pass
        try:
            from .specialized.organic_matter_agent import OrganicMatterAgent
            real["model-5"] = OrganicMatterAgent()
        except ImportError:
            pass
        try:
            from .specialized.fertility_ml_agent import FertilityMLAgent
            real["model-6"] = FertilityMLAgent()
        except ImportError:
            pass
        try:
            from .specialized.grade_agent import FarmlandGradeAgent
            real["model-7"] = FarmlandGradeAgent()
        except ImportError:
            pass
        return real

    def process(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理用户问题，返回综合结果。"""
        role = self.router.identify_role(question)
        agent_ids = self.router.get_agents_for_role(role)
        results = self._execute_with_dependencies(agent_ids, question, context)
        return {
            "status": "ok",
            "data": self._summarize(role, agent_ids, results),
        }

    def _execute_with_dependencies(
        self, agent_ids: List[str], question: str, context: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """按依赖关系顺序执行智能体，前序输出累积到 context。"""
        ordered = self._topological_sort(agent_ids)
        accumulated = dict(context)
        results: Dict[str, Dict[str, Any]] = {}

        for agent_id in ordered:
            # 按需过滤：非肥力问题跳过 model-6
            if not self._should_execute_agent(agent_id, question):
                results[agent_id] = {
                    "status": "skipped",
                    "reason": "question_not_related",
                    "answer": "",
                    "evidence": [],
                    "confidence": 0.0,
                    "simulated": True,
                }
                accumulated[agent_id] = results[agent_id]
                continue

            agent = self.agents[agent_id]
            try:
                result = agent.answer_question(question, accumulated)
            except Exception as exc:
                result = {
                    "answer": f"智能体执行失败: {exc}",
                    "evidence": [],
                    "confidence": 0.0,
                    "simulated": True,
                    "error": str(exc),
                }
            results[agent_id] = result
            accumulated[agent_id] = result

        return results

    def _topological_sort(self, agent_ids: List[str]) -> List[str]:
        """对给定的智能体子集进行拓扑排序。
        仅考虑位于 agent_ids 集合内的依赖；集合外的依赖被忽略。"""
        id_set = set(agent_ids)
        visited: set = set()
        order: List[str] = []

        def visit(node: str) -> None:
            if node in visited or node not in id_set:
                return
            visited.add(node)
            for dep in self.agents[node].dependencies:
                if dep in id_set:
                    visit(dep)
            order.append(node)

        for agent_id in agent_ids:
            visit(agent_id)

        return order

    def _should_execute_agent(self, agent_id: str, question: str) -> bool:
        """问题感知过滤：model-6 仅肥力问题执行，model-7 仅质量等级问题执行。"""
        if agent_id == "model-6":
            q_lower = (question or "").lower()
            return any(kw.lower() in q_lower for kw in FERTILITY_KEYWORDS)
        if agent_id == "model-7":
            return any(kw in (question or "") for kw in GRADE_KEYWORDS)
        return True

    def _synthesize_comprehensive_result(self, results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """综合模型1（退化风险）和模型3（障碍诊断）的结果。"""
        model1_result = results.get("model-1", {})
        model3_result = results.get("model-3", {})

        synthesis = {
            "type": "comprehensive",
            "model1": model1_result,
            "model3": model3_result,
        }

        if model1_result.get("status") == "ok" and model3_result.get("status") == "ok":
            risk_info = model1_result.get("result", {})
            diagnosis_info = model3_result.get("result", {})

            synthesis["summary"] = "综合诊断结果："
            if risk_info.get("risk_level"):
                synthesis["summary"] += f"退化风险等级为{risk_info['risk_level']}；"
            if diagnosis_info.get("obstacle_type"):
                synthesis["summary"] += f"障碍类型为{diagnosis_info['obstacle_type']}。"

        return synthesis

    def _summarize(
        self,
        role: str,
        agent_ids: List[str],
        results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """汇总各智能体结果为 API 响应结构。"""
        ordered_invoked = self._topological_sort(agent_ids)
        details = {aid: results[aid] for aid in ordered_invoked if aid in results}

        # 摘要：拼接各智能体的 answer
        answer_parts = [
            f"[{aid}] {results[aid].get('answer', '')}"
            for aid in ordered_invoked
            if aid in results
        ]
        summary = "\n".join(answer_parts) if answer_parts else "暂无可用结果"

        # 推荐建议：从各智能体的 evidence 中收集去重条目
        recommendations: List[str] = []
        seen = set()
        for aid in ordered_invoked:
            payload = results.get(aid, {})
            for ev in payload.get("evidence", []):
                if isinstance(ev, dict):
                    text = ev.get("recommendation") or ev.get("source")
                else:
                    text = str(ev)
                if text and text not in seen:
                    seen.add(text)
                    recommendations.append(text)

        return {
            "role": role,
            "agents_invoked": ordered_invoked,
            "summary": summary,
            "details": details,
            "recommendations": recommendations,
        }


# 模块级单例
agent_manager = AgentManager()
