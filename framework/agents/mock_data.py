from __future__ import annotations
from typing import Any, Callable, Dict, List, Tuple


class MockDataLoader:
    """模拟数据加载与阈值规则计算工具。"""

    @staticmethod
    def merge_defaults(input_data: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
        """合并用户输入与默认值，用户输入优先。"""
        merged = dict(defaults)
        merged.update(input_data or {})
        return merged

    @staticmethod
    def mark_simulated(payload: Dict[str, Any]) -> Dict[str, Any]:
        """返回 payload 的副本并添加 simulated: True 标记。"""
        out = dict(payload)
        out["simulated"] = True
        return out

    @staticmethod
    def apply_threshold(value: float, rules: List[Tuple[Callable[[float], bool], str]]) -> str:
        """按顺序匹配阈值规则，返回首个满足条件的标签。
        rules: [(predicate, label), ...]
        """
        for predicate, label in rules:
            try:
                if predicate(value):
                    return label
            except Exception:
                continue
        return "未知"
