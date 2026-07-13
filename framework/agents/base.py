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
