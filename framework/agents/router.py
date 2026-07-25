from __future__ import annotations
from typing import Dict, List


class RoleRouter:
    """用户角色路由器，基于关键词匹配识别角色并返回对应智能体组合。"""

    ROLE_KEYWORDS: Dict[str, List[str]] = {
        "province": ["全省", "全市", "全局", "政策", "省市"],
        "county": ["本县", "乡镇", "片区", "任务", "县域"],
        "farmer": ["我的田", "这块地", "施氮肥", "施多少", "农户"],
    }

    ROLE_AGENTS: Dict[str, List[str]] = {
        "province": ["model-1", "model-3"],
        "county": ["model-1", "model-3", "model-2"],
        "farmer": ["model-4", "model-5", "model-6", "model-7"],
    }

    def identify_role(self, question: str) -> str:
        """基于关键词匹配识别用户角色。无匹配时默认返回 'farmer'。"""
        if not question:
            return "farmer"
        for role, keywords in self.ROLE_KEYWORDS.items():
            if any(kw in question for kw in keywords):
                return role
        return "farmer"

    def get_agents_for_role(self, role: str) -> List[str]:
        """返回该角色对应的智能体 ID 列表。未知角色回退到 farmer。"""
        return list(self.ROLE_AGENTS.get(role, self.ROLE_AGENTS["farmer"]))
