---
comet_change: multi-agent-model-framework
role: technical-design
canonical_spec: openspec
archived-with: 2026-07-13-multi-agent-model-framework
status: final
---

# 多智能体专业模型框架技术设计文档

## 1. 架构概述

采用方案 A：AgentManager 作为独立模块，在现有 LangGraph 的 `execute_models` 节点中被调用，不替换现有图结构。

```
framework/agents/
├── __init__.py
├── base.py              # BaseAgent 抽象基类
├── manager.py           # AgentManager 中心化编排器
├── router.py            # 用户角色路由
├── mock_data.py         # 模拟数据工具
├── state.py             # 现有 LangGraph 状态定义
├── nodes.py             # 现有 LangGraph 节点（修改）
├── orchestrator.py      # 现有编排器（修改）
└── specialized/         # 6 个专业智能体
    ├── __init__.py
    ├── stability_risk_agent.py       # 模型1
    ├── potential_agent.py            # 模型2
    ├── problem_agent.py              # 模型3
    ├── acidification_agent.py        # 模型4
    ├── organic_matter_agent.py       # 模型5
    └── comprehensive_agent.py        # 模型6
```

## 2. BaseAgent 抽象基类

```python
from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseAgent(ABC):
    """智能体抽象基类，定义统一接口。"""
    
    def __init__(self, name: str, description: str, model_id: str, domain: str):
        self.name = name
        self.description = description
        self.model_id = model_id
        self.domain = domain
        self.dependencies: list[str] = []  # 依赖的前序模型 ID
    
    @abstractmethod
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行模拟计算。
        返回: {"status": "ok"|"error", "result": {...}, "metadata": {"simulated": True}}
        """
    
    @abstractmethod
    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """回答用户问题。
        返回: {"answer": "...", "evidence": [...], "confidence": 0.8}
        """
```

## 3. 模拟数据策略

每个智能体内置三类模拟数据：

### 3.1 模拟输入参数

```python
# 示例：AcidificationRemediationAgent
MOCK_INPUTS = {
    "ph": 5.5,                    # 土壤 pH
    "organic_matter": 25.0,       # 有机质 (g/kg)
    "cec": 8.5,                   # 阳离子交换量
    "clay_content": 35.0,         # 黏粒含量 (%)
    "exchangeable_al": 3.2,       # 交换性铝离子
}
```

### 3.2 阈值规则

```python
# 示例：酸化程度判定规则
ACIDIFICATION_THRESHOLDS = {
    "ph < 4.5": "强酸性",
    "4.5 <= ph < 5.5": "酸性",
    "5.5 <= ph < 6.5": "弱酸性",
    "ph >= 6.5": "正常",
}

# 示例：石灰施用量计算
LIME_DOSAGE_RULES = {
    "强酸性": 150.0,   # kg/亩
    "酸性": 100.0,
    "弱酸性": 50.0,
    "正常": 0.0,
}
```

### 3.3 模拟输出结果

所有输出结果包含 `simulated: True` 标记，明确标注为模拟数据。

## 4. AgentManager 中心化编排器

```python
class AgentManager:
    """中心化智能体编排器。"""
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.router = RoleRouter()
        self._register_agents()
    
    def _register_agents(self):
        """注册所有 6 个专业智能体。"""
        # 按模型 ID 注册，记录依赖关系
        self.agents["model-1"] = StabilityRiskAgent()
        self.agents["model-2"] = PotentialAssessmentAgent()
        self.agents["model-3"] = ProblemIdentificationAgent()
        self.agents["model-4"] = AcidificationRemediationAgent()
        self.agents["model-5"] = OrganicMatterAgent()
        self.agents["model-6"] = ComprehensiveImprovementAgent()
    
    def process(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理用户问题，返回综合结果。"""
        # 1. 识别用户角色
        role = self.router.identify_role(question)
        
        # 2. 获取智能体组合
        agent_ids = self.router.get_agents_for_role(role)
        
        # 3. 按依赖顺序执行
        results = self._execute_with_dependencies(agent_ids, question, context)
        
        # 4. 汇总结果
        return self._summarize(role, agent_ids, results)
    
    def _execute_with_dependencies(self, agent_ids, question, context):
        """按依赖关系顺序执行智能体。"""
        ordered = self._topological_sort(agent_ids)
        accumulated_context = dict(context)
        results = {}
        
        for agent_id in ordered:
            agent = self.agents[agent_id]
            result = agent.answer_question(question, accumulated_context)
            results[agent_id] = result
            accumulated_context[agent_id] = result
        
        return results
```

## 5. 角色路由

```python
class RoleRouter:
    """用户角色路由器。"""
    
    ROLE_KEYWORDS = {
        "province": ["全省", "全市", "全局", "政策", "省市"],
        "county": ["本县", "乡镇", "片区", "任务", "县域"],
        "farmer": ["我的田", "这块地", "施氮肥", "施多少", "农户"],
    }
    
    ROLE_AGENTS = {
        "province": ["model-1", "model-3"],
        "county": ["model-1", "model-3", "model-2"],
        "farmer": ["model-4", "model-5", "model-6"],
    }
    
    def identify_role(self, question: str) -> str:
        """基于关键词匹配识别用户角色。"""
        for role, keywords in self.ROLE_KEYWORDS.items():
            if any(kw in question for kw in keywords):
                return role
        return "farmer"  # 默认农户角色
```

## 6. 6 个专业智能体设计

### 6.1 StabilityRiskAgent（模型1）

- **模拟数据**: 10 个县区的质量等级、稳定性评分、退化风险指数
- **计算逻辑**: 基于等级边界安全度和关键指标临界度判定稳定性
- **输出**: 稳定性评价（稳定/一般/较弱）、面积占比、风险区域排序

### 6.2 PotentialAssessmentAgent（模型2）

- **模拟数据**: 11 个评价指标的当前值和潜在值
- **计算逻辑**: 计算各指标障碍度值（0-100）和提升潜力等级
- **输出**: 障碍度值表、提升潜力等级、目标 pH

### 6.3 ProblemIdentificationAgent（模型3）

- **模拟数据**: 11 个指标的障碍等级频数分布
- **计算逻辑**: 统计主要/次要障碍因素，识别障碍组合
- **输出**: 障碍因素排序、障碍组合、指标等级统计表

### 6.4 AcidificationRemediationAgent（模型4）

- **模拟数据**: pH 值、交换性铝、有机质等
- **计算逻辑**: pH 阈值判定酸化程度，计算石灰施用量
- **输出**: 酸化程度级别、碱性材料施用量、pH 提升预测值

### 6.5 OrganicMatterAgent（模型5）

- **模拟数据**: 有机质含量、全氮、碳氮比等
- **计算逻辑**: 有机质分级，计算有机肥施用量
- **输出**: 有机质等级、有机肥施用量、潜在有机质提升值

### 6.6 ComprehensiveImprovementAgent（模型6）

- **模拟数据**: 综合提升措施库
- **计算逻辑**: 汇总模型1-5结果，匹配提升措施
- **输出**: 综合诊断、分区提升建议、措施优先级排序

## 7. 与现有 LangGraph 集成

修改 `nodes.py` 中的 `execute_models` 函数：

```python
def execute_models(state: MultiAgentState) -> MultiAgentState:
    """调用 AgentManager 执行多智能体协作。"""
    from framework.agents.manager import agent_manager
    
    question = state["request"].get("question", "")
    context = {
        "area_code": state["request"].get("area_code", "lechang"),
        "data": state.get("data", {}),
    }
    
    result = agent_manager.process(question, context)
    
    state["model_results"] = result
    state["status"] = "model_completed"
    return state
```

## 8. API 响应格式

```json
{
  "status": "ok",
  "data": {
    "role": "farmer",
    "agents_invoked": ["model-4", "model-5", "model-6"],
    "summary": "您的地块存在中度酸化问题...",
    "details": {
      "model-4": {
        "answer": "土壤酸化程度为中度，建议施石灰 75 kg/亩",
        "evidence": ["pH=5.5", "交换性铝=3.2 cmol/kg"],
        "confidence": 0.85,
        "simulated": true
      },
      "model-5": { ... },
      "model-6": { ... }
    },
    "recommendations": [
      "施用石灰调理酸度",
      "增施有机肥提升有机质"
    ]
  }
}
```

## 9. 测试策略

| 测试类型 | 范围 | 方法 |
|---------|------|------|
| 智能体单元测试 | 每个智能体的 execute 和 answer_question | 验证模拟计算输出和问题回答格式 |
| Manager 测试 | 依赖调度、结果汇总 | 验证拓扑排序和汇总格式 |
| Router 测试 | 角色识别 | 验证关键词匹配和默认角色 |
| API 集成测试 | 端到端 | 验证 `/api/v1/chat/` 返回结构化结果 |

