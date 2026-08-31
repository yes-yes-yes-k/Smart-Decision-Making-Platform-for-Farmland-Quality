from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ProfessionalInputRejected(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


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
                # 普通执行日志只保存规范公共快照；完整输入仍作为审计输入保留，
                # 不把 execute() 的旧展示包络写入 output_result。
                from .output_contract import normalize_execution, public_full, sanitize_json
                execution = dict(outputs or {}) if isinstance(outputs, dict) else {"result": outputs}
                persisted_outputs = dict(outputs or {}) if isinstance(outputs, dict) else {"result": outputs}
                persisted_outputs.setdefault("model_version", "unknown")
                persisted_outputs.setdefault("data_as_of", None)
                persisted_outputs.setdefault("data_version", None)
                persisted_outputs.setdefault("actual_inputs", dict(inputs or {}))
                execution["status"] = status
                if "result" not in execution:
                    execution["result"] = outputs
                execution.setdefault("data_source", inputs.get("data_source", "unknown"))
                execution.setdefault("simulated", bool(inputs.get("simulated", False)))
                normalized = normalize_execution(self, inputs, execution)
                audit_inputs = sanitize_json(dict(inputs or {}))
                meta = normalized.get("meta", {})
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
                    input_params=audit_inputs,
                    output_result=public_full(normalized),
                    evidence=normalized.get("issues", []),
                    status=normalized.get("status", status),
                    simulated=bool(normalized.get("meta", {}).get("simulated", False)),
                    error_message=(normalized.get("issues") or [{}])[0].get("message") if normalized.get("status") in {"error", "rejected", "unavailable"} else None,
                    model_version=meta.get("model_version") or "unknown",
                    data_as_of=meta.get("data_as_of"),
                    data_version=meta.get("data_version"),
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
        """执行一次模型并返回统一的模型结果信封。

        ``execute`` 仍由各专业 Agent 负责，所有公共入口只消费这里生成的
        ``model_id/status/subject/result/meta/issues``，避免在 API、聊天和工具
        调用层分别复制旧的展示型字段。
        """
        from .output_contract import normalize_execution

        try:
            execution = self.execute(payload or {})
        except Exception as exc:
            execution = {
                "status": "error",
                "error": str(exc),
                "result": None,
                "data_source": "unknown",
            }
        return normalize_execution(self, payload or {}, execution)

    def answer_from_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """从规范结果生成聊天答复兼容对象。

        该对象只在 AgentManager 的内部兼容路径使用，公共聊天响应由投影函数
        生成，不再将此对象直接序列化给客户端。
        """
        from .output_contract import deterministic_answer

        answer = deterministic_answer(analysis)
        result = analysis.get("result") if isinstance(analysis, dict) else {}
        evidence = []
        if isinstance(result, dict):
            evidence = [
                {"metric": key, "value": value}
                for key, value in result.items()
                if not isinstance(value, (dict, list)) and value is not None
            ]
        return {
            "answer": answer,
            "evidence": evidence,
            "sources": [],
            "model_result": analysis,
            "status": analysis.get("status", "error"),
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
