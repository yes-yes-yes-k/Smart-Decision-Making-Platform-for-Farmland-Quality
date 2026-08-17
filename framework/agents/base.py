from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseAgent(ABC):
    """智能体抽象基类，定义统一接口。"""

    def __init__(self, name: str, description: str, model_id: str, domain: str):
        self.name = name
        self.description = description
        self.model_id = model_id
        self.domain = domain
        self.dependencies: List[str] = []
        self._rag_chain = None
        self._llm_service = None

    def _get_rag_chain(self):
        if self._rag_chain is None:
            try:
                from framework.rag.chain import rag_chain
                self._rag_chain = rag_chain
            except ImportError:
                self._rag_chain = None
        return self._rag_chain

    def _get_llm_service(self):
        if self._llm_service is None:
            try:
                from framework.llm.service import llm_service
                self._llm_service = llm_service
            except ImportError:
                self._llm_service = None
        return self._llm_service

    def _retrieve_knowledge(self, question: str, top_k: int = 3) -> Dict[str, Any]:
        rag = self._get_rag_chain()
        if not rag:
            return {"results": [], "count": 0}
        try:
            from framework.vector_store.chroma_store import vector_store
            results = vector_store.search(query=question, n_results=top_k)
            return results
        except Exception:
            return {"results": [], "count": 0}

    def _build_rag_context(self, retrieval_results: Dict[str, Any]) -> str:
        if retrieval_results.get("count", 0) == 0:
            return ""
        context_parts = []
        for i, result in enumerate(retrieval_results.get("results", [])):
            content = result.get("content", "")
            metadata = result.get("metadata", {})
            source = metadata.get("source", "unknown")
            context_parts.append(f"文档{i+1}({source}): {content}")
        return "\n\n".join(context_parts)

    def _generate_with_rag(
        self,
        question: str,
        domain_context: str = "",
        *,
        enable_llm: bool = False,
    ) -> Dict[str, Any]:
        """按需使用 RAG + LLM。

        多智能体路径默认关闭该调用：每个专业智能体先生成可解释的规则结果，
        由编排器在末尾仅调用一次 LLM 进行统一润色，避免串行放大上游时延。
        """
        if not enable_llm:
            return {
                "answer": "",
                "sources": [],
                "success": False,
                "retrieved_count": 0,
                "skipped": True,
            }

        retrieval = self._retrieve_knowledge(question)
        rag_context = self._build_rag_context(retrieval)

        llm = self._get_llm_service()
        if not llm or not llm.is_available():
            return {"answer": "", "sources": [], "success": False}

        try:
            prompt = self._build_domain_prompt(question, rag_context, domain_context)
            llm_result = llm.generate(prompt)
            sources = []
            for result in retrieval.get("results", []):
                metadata = result.get("metadata", {})
                sources.append({
                    "doc_name": metadata.get("source", "unknown"),
                    "content": result.get("content", "")[:200] + "...",
                    "score": 1 - result.get("distance", 0),
                })
            return {
                "answer": llm_result.get("content", ""),
                "sources": sources,
                "success": llm_result.get("success", False),
                "retrieved_count": retrieval.get("count", 0),
            }
        except Exception:
            return {"answer": "", "sources": [], "success": False}

    def _build_domain_prompt(self, question: str, rag_context: str, domain_context: str) -> str:
        domain_desc = f"你是{self.description}专家。"
        context_parts = []
        if rag_context:
            context_parts.append(f"参考文档内容：\n{rag_context}")
        if domain_context:
            context_parts.append(f"领域参考信息：\n{domain_context}")

        context_str = "\n\n".join(context_parts) if context_parts else "无参考文档。"

        return f"""{domain_desc}

基于以下参考信息，回答用户的问题。如果参考信息中有相关内容，请优先使用参考信息回答；如果参考信息中没有相关内容，可以结合你的专业知识回答，但请明确说明。

{context_str}

        用户问题：
{question}

请以自然、专业的语言回答，回答要准确、有条理。"""

    def analyze(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """以统一结构化包络执行专业分析。

        子类可覆盖此方法以暴露更丰富的专业字段；默认实现复用既有
        ``execute`` 结果，确保单模型接口不会再维护独立计算路径。
        """
        execution = self.execute(payload or {})
        raw_status = execution.get("status", "error")
        degraded = execution.get("degraded") is True or raw_status == "degraded"
        result = execution.get("result", {})
        metadata = execution.get("metadata", {})
        simulated = bool(metadata.get("simulated", execution.get("simulated", False)))
        findings = [
            {"title": str(key), "content": str(value)}
            for key, value in result.items()
            if key not in {"indicators", "obstacle_degree"}
        ]
        if result.get("indicators"):
            findings.append({"title": "指标评价", "content": f"共 {len(result['indicators'])} 项指标"})
        if result.get("obstacle_degree"):
            findings.append({"title": "障碍度排序", "content": str(result["obstacle_degree"])})

        capability = getattr(self, "capability", {
            "agent_id": self.model_id,
            "model_id": self.model_id,
            "name": self.name,
            "purpose": self.description,
        })
        fallback_used = raw_status in {"fallback", "rejected"} or simulated or degraded
        if degraded:
            reliability_level = "degraded"
            reliability_message = "真实计算不可用，已返回统一降级响应。"
            fallback_strategy = metadata.get("fallback_reason") or metadata.get("reason") or execution.get("reason") or "真实计算降级"
        elif simulated:
            reliability_level = "demo_stub"
            reliability_message = "结果来自模拟/规则分析。"
            fallback_strategy = metadata.get("fallback_reason") or metadata.get("reason") or "未使用回退"
        else:
            reliability_level = "real_model"
            reliability_message = "结果来自已接入的专业计算。"
            fallback_strategy = metadata.get("fallback_reason") or metadata.get("reason") or "未使用回退"
        return {
            "status": "ok" if raw_status in {"ok", "success", "fallback"} else raw_status,
            "capability": capability,
            "model": capability,
            "summary": f"{capability['name']}已完成结构化分析。",
            "findings": findings,
            "recommendations": [],
            "evidence": result,
            "lineage": {"runtime_dependency": "agent"},
            "reliability": {
                "level": reliability_level,
                "message": reliability_message,
            },
            "fallback": {
                "used": fallback_used,
                "fields": [],
                "strategy": fallback_strategy,
            },
            "analysis": result,
            "degraded": degraded,
        }

    def answer_from_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """将统一结构化分析转换为聊天链路可汇总的专业答复。"""
        findings = analysis.get("findings", [])
        finding_text = "；".join(
            f"{item.get('title', '结果')}：{item.get('content', '')}"
            for item in findings[:4]
            if isinstance(item, dict)
        )
        recommendations = analysis.get("recommendations", [])
        recommendation_text = "；".join(str(item) for item in recommendations[:3])
        answer_parts = [analysis.get("summary", "暂无可用专业分析结果。")]
        if finding_text:
            answer_parts.append(finding_text)
        if recommendation_text:
            answer_parts.append(f"建议：{recommendation_text}")

        raw_evidence = analysis.get("evidence", {})
        if isinstance(raw_evidence, list):
            evidence = raw_evidence
        elif isinstance(raw_evidence, dict):
            evidence = [
                {"metric": str(key), "value": value}
                for key, value in raw_evidence.items()
                if not isinstance(value, (dict, list))
            ]
        else:
            evidence = []

        reliability = analysis.get("reliability", {})
        return {
            "answer": "\n".join(answer_parts),
            "evidence": evidence,
            "confidence": 0.9 if reliability.get("level") == "real_model" else 0.5,
            "simulated": reliability.get("level") == "demo_stub",
            "analysis": analysis,
            "sources": [],
        }

    @abstractmethod
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行模拟计算。
        返回: {"status": "ok"|"error", "result": {...}, "metadata": {"simulated": True}}
        """

    @abstractmethod
    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """回答用户问题。
        返回: {"answer": "...", "evidence": [...], "confidence": 0.8, "simulated": True}
        """
