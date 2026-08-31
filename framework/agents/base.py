from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


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

    @property
    def agent_id(self) -> str:
        """从能力注册表查找 agent_id（如 model-1）；查找失败时回退到 model_id。"""
        try:
            from framework.agents.capabilities import CAPABILITY_BY_MODEL_ID
            cap = CAPABILITY_BY_MODEL_ID.get(self.model_id)
            if cap:
                return cap.agent_id
        except Exception:
            pass
        return self.model_id

    def _get_question_type(self) -> int:
        """从能力注册表查找 question_type；查找失败时返回 0。"""
        try:
            from framework.agents.capabilities import CAPABILITY_BY_MODEL_ID
            cap = CAPABILITY_BY_MODEL_ID.get(self.model_id)
            if cap:
                return cap.question_type
        except Exception:
            pass
        return 0

    def _persist_result(
        self,
        agent_id: str,
        parcel_id: Optional[str],
        inputs: dict,
        outputs: dict,
        status: str,
        *,
        execution_context: dict | None = None,
    ) -> bool:
        """同步持久化执行日志和结果表。

        Args:
            agent_id: Agent 标识（如 "model-1"）
            parcel_id: 地块 ID（Model-5 县级分析时为 None）
            inputs: 输入快照
            outputs: 输出快照
            status: "ok" | "degraded" | "error"

        Returns:
            True: 持久化成功
            False: 持久化失败（已记录 ERROR 日志，不抛异常）
        """
        try:
            from framework.models.user import db
            from framework.models.thematic_model import ModelExecutionLog

            # 确保在 Flask 应用上下文中执行数据库操作
            app_ctx = None
            try:
                from framework.api.app import create_app
                _app = create_app("default")
                app_ctx = _app.app_context()
                app_ctx.push()
            except Exception:
                pass

            try:
                now = datetime.now(timezone.utc)
                execution_context = execution_context or {}
                snapshot = execution_context.get("analysis_context")
                obj = (snapshot or {}).get("object") or {}
                persisted_outputs = dict(outputs)
                persisted_outputs.setdefault("model_version", "unknown")
                persisted_outputs.setdefault("data_as_of", None)
                persisted_outputs.setdefault("data_version", None)
                persisted_outputs.setdefault("actual_inputs", dict(inputs))
                log = ModelExecutionLog(
                    trace_id=execution_context.get("trace_id") or uuid.uuid4().hex,
                    agent_id=agent_id,
                    question_type=self._get_question_type(),
                    user_id=execution_context.get("user_id"),
                    conversation_id=execution_context.get("conversation_id"),
                    parcel_id=parcel_id,
                    analysis_object_type=obj.get("type"),
                    analysis_object_id=obj.get("id"),
                    area_code=obj.get("area_code"),
                    context_version=(snapshot or {}).get("version"),
                    analysis_context_snapshot=snapshot,
                    input_params=inputs,
                    output_result=persisted_outputs,
                    model_version=persisted_outputs.get("model_version") or "unknown",
                    data_as_of=persisted_outputs.get("data_as_of"),
                    data_version=persisted_outputs.get("data_version"),
                    status=status,
                    started_at=now,
                    completed_at=now,
                )
                db.session.add(log)
                db.session.flush()

                result_record = self._build_result_record(log.id, persisted_outputs)
                if result_record is not None:
                    db.session.add(result_record)

                db.session.commit()
                return True
            finally:
                if app_ctx:
                    app_ctx.pop()
        except Exception as e:
            logger.error(
                "持久化失败 (agent_id=%s, parcel_id=%s): %s", agent_id, parcel_id, e
            )
            try:
                from framework.models.user import db as _db
                _db.session.rollback()
            except Exception:
                pass
            return False

    def _build_result_record(self, execution_id: int, outputs: dict):
        """构建结果表 ORM 实例。子类 override 返回对应结果表记录。

        Args:
            execution_id: model_execution_log.id
            outputs: 模型输出

        Returns:
            ORM 实例（如 StabilityRiskResult(...)）或 None（无结果表时）
        """
        return None

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
            "data_source": execution.get("data_source", "unknown"),
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
            "model_version": result.get("model_version") or metadata.get("model_version") or "unknown",
            "data_as_of": result.get("data_as_of") or metadata.get("data_as_of"),
            "data_version": result.get("data_version") or metadata.get("data_version"),
            "actual_inputs": result.get("actual_inputs") or dict(payload or {}),
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
            "model_version": analysis.get("model_version") or "unknown",
            "data_as_of": analysis.get("data_as_of"),
            "data_version": analysis.get("data_version"),
            "actual_inputs": analysis.get("actual_inputs") or {},
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
