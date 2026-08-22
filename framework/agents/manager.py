from __future__ import annotations
from typing import Any, Dict, List

from .base import BaseAgent
from .capabilities import PROFESSIONAL_CAPABILITIES, public_capability_descriptor
from .router import QuestionTypeRouter


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
        self.router = QuestionTypeRouter()
        self._register_agents()

    def _register_agents(self) -> None:
        """注册所有 5 个专业智能体；若专业实现尚未就绪，回退到桩智能体。"""
        real_agents = self._load_real_agents()
        for capability in PROFESSIONAL_CAPABILITIES:
            if capability.agent_id in real_agents:
                agent = real_agents[capability.agent_id]
            else:
                agent = _StubAgent(
                    f"{capability.agent_id}Stub",
                    capability.description,
                    capability.agent_id,
                    capability.domain,
                )
            agent.capability = public_capability_descriptor(capability)
            self.agents[capability.agent_id] = agent

        # 显式声明依赖关系
        self.agents["model-1"].dependencies = []
        self.agents["model-2"].dependencies = []
        self.agents["model-3"].dependencies = []
        self.agents["model-4"].dependencies = []
        self.agents["model-5"].dependencies = []

    def _load_real_agents(self) -> Dict[str, BaseAgent]:
        """尝试加载专业智能体实现，失败时返回空字典。"""
        real: Dict[str, BaseAgent] = {}
        # model-1: 稳定性风险，优先加载带真实模型集成的新版 stability_agent，
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
        # model-2: 质量等级评价
        try:
            from .specialized.grade_agent import FarmlandGradeAgent
            real["model-2"] = FarmlandGradeAgent()
        except ImportError:
            pass
        # model-3: 障碍诊断
        try:
            from .specialized.problem_agent import ProblemIdentificationAgent
            real["model-3"] = ProblemIdentificationAgent()
        except ImportError:
            pass
        # model-4: 酸化改良
        try:
            from .specialized.acidification_agent import AcidificationRemediationAgent
            real["model-4"] = AcidificationRemediationAgent()
        except ImportError:
            pass
        # model-5: 有机质提升
        try:
            from .specialized.organic_matter_agent import OrganicMatterAgent
            real["model-5"] = OrganicMatterAgent()
        except ImportError:
            pass
        return real

    def _refresh_stub_agents(self) -> None:
        """在循环导入结束后，将初始化阶段的临时桩替换为真实 Agent。"""
        if not isinstance(self.agents.get("model-5"), _StubAgent):
            return
        real_agents = self._load_real_agents()
        for capability in PROFESSIONAL_CAPABILITIES:
            agent = real_agents.get(capability.agent_id)
            if agent is None or not isinstance(self.agents.get(capability.agent_id), _StubAgent):
                continue
            agent.capability = public_capability_descriptor(capability)
            agent.dependencies = []
            self.agents[capability.agent_id] = agent

    def process(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理用户问题，返回综合结果。"""
        # src.ai_culti_demo 初始化可能与 framework.agents 形成循环导入；
        # 首次请求时再刷新一次，避免 model-5 永久停留在占位桩。
        self._refresh_stub_agents()
        question_type = context.get("question_type")
        agent_ids = self.router.get_agents_for_type(question_type)

        if not agent_ids:
            # 防御性：question_type 为 None/0/未知时返回 no_routing
            return {
                "status": "no_routing",
                "data": {
                    "question_type": question_type,
                    "agents_invoked": [],
                    "summary": "未识别问题类型",
                    "details": {},
                    "recommendations": [],
                },
            }

        results = self._execute_with_dependencies(agent_ids, question, context)
        return {
            "status": "ok",
            "data": self._summarize(question_type, agent_ids, results),
        }

    def _execute_with_dependencies(
        self, agent_ids: List[str], question: str, context: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """按依赖关系顺序执行智能体，前序输出累积到 context。"""
        ordered = self._topological_sort(agent_ids)
        accumulated = dict(context)
        results: Dict[str, Dict[str, Any]] = {}

        for agent_id in ordered:
            agent = self.agents[agent_id]
            try:
                payload = self._analysis_payload(accumulated)
                analysis = agent.analyze(payload)
                result = agent.answer_from_analysis(analysis)
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

    @staticmethod
    def _analysis_payload(context: Dict[str, Any]) -> Dict[str, Any]:
        """将聊天上下文转换为可供结构化专业分析复用的输入。"""
        payload: Dict[str, Any] = {}
        if isinstance(context.get("data"), dict):
            payload.update(context["data"])
            payload["indicators"] = context["data"]
        for key, value in context.items():
            if key not in {"data", "question_type"} and not key.startswith("model-"):
                payload[key] = value
        parcel_id = payload.get("parcel_id", "")
        parcel_code = payload.get("parcel_code", "")
        print(f"[AgentManager] _analysis_payload: parcel_id={parcel_id}, parcel_code={parcel_code}, "
              f"keys={list(payload.keys())}")
        return payload

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

    def _synthesize_comprehensive_result(self, results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """综合模型1（退化风险）和模型3（障碍诊断）的结果。"""
        stability_result = results.get("model-1", {})
        diagnosis_result = results.get("model-3", {})

        synthesis = {
            "type": "comprehensive",
            "stability": stability_result,
            "diagnosis": diagnosis_result,
        }

        if stability_result.get("status") == "ok" and diagnosis_result.get("status") == "ok":
            risk_info = stability_result.get("result", {})
            diagnosis_info = diagnosis_result.get("result", {})

            synthesis["summary"] = "综合诊断结果："
            if risk_info.get("risk_level"):
                synthesis["summary"] += f"退化风险等级为{risk_info['risk_level']}；"
            if diagnosis_info.get("obstacle_type"):
                synthesis["summary"] += f"障碍类型为{diagnosis_info['obstacle_type']}。"

        return synthesis

    def _summarize(
        self,
        question_type: int,
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
            "question_type": question_type,
            "agents_invoked": ordered_invoked,
            "summary": summary,
            "details": details,
            "recommendations": recommendations,
        }


# 模块级单例
agent_manager = AgentManager()
