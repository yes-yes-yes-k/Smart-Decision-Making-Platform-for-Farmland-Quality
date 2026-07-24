---
comet_change: add-stability-risk-and-grade-evaluation
role: technical-design
canonical_spec: openspec
---

# 模型3（耕地质量主要问题精准识别与酸化改良）深度技术设计

## 1. 架构设计

### 1.1 整体架构

模型3采用**模块化集成方案**，将核心代码重构为独立的 Python 包，通过明确的 API 接口与现有系统对接：

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户层 (API)                             │
│            /api/v1/chat/ → AgentManager → 各专业Agent          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    调度层 (CoreEngine)                          │
│              run_thematic_model() → 路由到对应模型               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  模型层 (模块化包)                              │
│  ┌─────────────────────┐  ┌─────────────────────────────┐     │
│  │  farmland_diagnosis  │  │ farmland_acidification      │     │
│  │  (障碍诊断模块)       │  │  (酸化改良模块)              │     │
│  │  - bulk_evaluate()   │  │  - extract_acidification()  │     │
│  │  - diagnose()        │  │  - classify_level()         │     │
│  │  - query_parcel()    │  │  - generate_plan()          │     │
│  └─────────────────────┘  │  - query_parcel()            │     │
│                           └─────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    数据层 (SQLite)                              │
│         farmland_diagnosis.db → 评价结果表/诊断结果表            │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 模块划分

| 模块 | 职责 | 核心函数 |
|------|------|----------|
| `farmland_diagnosis` | 障碍诊断核心逻辑 | `bulk_evaluate()`, `diagnose()`, `query_parcel()` |
| `farmland_acidification` | 酸化改良核心逻辑 | `extract_acidification()`, `classify_level()`, `generate_plan()` |
| `diagnosis_config` | 配置管理 | 区域映射、隶属度系数、权重配置 |
| `diagnosis_storage` | 数据持久化 | SQLite 连接管理、表创建、查询 |

### 1.3 数据流

**批量评价流程**：
1. 用户上传 CSV 文件（含 12 项指标 + 区域信息）
2. `bulk_evaluate()` 读取 CSV，执行隶属度计算、综合权重计算、质量等级划分
3. 将结果写入 SQLite `evaluation_results` 表
4. `diagnose()` 读取评价结果，执行障碍诊断
5. 将诊断结果写入 SQLite `diagnosis_results` 表

**在线查询流程**：
1. 用户请求按地块 ID 查询
2. `query_parcel()` 从 SQLite 读取评价结果和诊断结果
3. 返回结构化 JSON 响应

## 2. 详细设计

### 2.1 模型替换映射

| 占位模型 | 替换为 | Model ID |
|----------|--------|----------|
| `obstacle-factor-identification` | 模型3障碍诊断 | `obstacle-factor-identification`（保留原 ID） |
| `acidification-governance` | 模型3酸化改良 | `acidification-governance`（保留原 ID） |

### 2.2 Question Type 分配

| Question Type | 能力 | 关键词 | Agent |
|---------------|------|--------|-------|
| 2 | 酸化改良 | 酸化程度、酸化治理、调理剂、石灰、pH提升 | AcidificationRemediationAgent |
| 3 | 潜力评估（现有） | 潜力、提升潜力、潜力分布 | PotentialAssessmentAgent |
| **5（新增）** | **障碍诊断** | **障碍诊断、障碍因素、障碍类型、障碍组合、精准识别** | **ObstacleDiagnosisAgent** |

### 2.3 数据库设计

#### 2.3.1 evaluation_results 表（评价结果）

| 字段 | 类型 | 说明 |
|------|------|------|
| `parcel_id` | TEXT | 地块唯一标识（主键） |
| `region_code` | TEXT | 一级农业区代码（HN/CJ） |
| `secondary_region_code` | TEXT | 二级农业区代码 |
| `PH` | REAL | pH 值 |
| `YJ` | REAL | 有机质 |
| `YXP` | REAL | 有效磷 |
| `SXK` | REAL | 速效钾 |
| `RZ` | REAL | 容重 |
| `GZ` | TEXT | 耕层质地 |
| `GG` | TEXT | 灌溉能力 |
| `PS` | TEXT | 排水能力 |
| `DX` | TEXT | 地形部位 |
| `ZD` | TEXT | 质地构型 |
| `YXT` | REAL | 有效土层 |
| `GCH` | REAL | 耕层厚度 |
| `PH_LD` | REAL | pH 隶属度 |
| `YJ_LD` | REAL | 有机质隶属度 |
| `YXP_LD` | REAL | 有效磷隶属度 |
| `SXK_LD` | REAL | 速效钾隶属度 |
| `RZ_LD` | REAL | 容重隶属度 |
| `GZ_LD` | REAL | 耕层质地隶属度 |
| `GG_LD` | REAL | 灌溉能力隶属度 |
| `PS_LD` | REAL | 排水能力隶属度 |
| `DX_LD` | REAL | 地形部位隶属度 |
| `ZD_LD` | REAL | 质地构型隶属度 |
| `YXT_LD` | REAL | 有效土层隶属度 |
| `GCH_LD` | REAL | 耕层厚度隶属度 |
| `composite_weight` | REAL | 综合权重 |
| `grade` | TEXT | 质量等级（1-10） |
| `created_at` | TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | 更新时间 |

#### 2.3.2 diagnosis_results 表（诊断结果）

| 字段 | 类型 | 说明 |
|------|------|------|
| `parcel_id` | TEXT | 地块唯一标识（主键，外键关联 evaluation_results） |
| `obstacle_type` | TEXT | 障碍类型（单一障碍/多障碍/无明显障碍） |
| `main_factors` | TEXT | 主要障碍因素（JSON 数组） |
| `secondary_factors` | TEXT | 次要障碍因素（JSON 数组） |
| `PH_obstacle_level` | TEXT | pH 障碍等级 |
| `YJ_obstacle_level` | TEXT | 有机质障碍等级 |
| `YXP_obstacle_level` | TEXT | 有效磷障碍等级 |
| `SXK_obstacle_level` | TEXT | 速效钾障碍等级 |
| `RZ_obstacle_level` | TEXT | 容重障碍等级 |
| `GZ_obstacle_level` | TEXT | 耕层质地障碍等级 |
| `GG_obstacle_level` | TEXT | 灌溉能力障碍等级 |
| `PS_obstacle_level` | TEXT | 排水能力障碍等级 |
| `DX_obstacle_level` | TEXT | 地形部位障碍等级 |
| `ZD_obstacle_level` | TEXT | 质地构型障碍等级 |
| `YXT_obstacle_level` | TEXT | 有效土层障碍等级 |
| `GCH_obstacle_level` | TEXT | 耕层厚度障碍等级 |
| `PH_obstacle_degree` | REAL | pH 障碍度 |
| `YJ_obstacle_degree` | REAL | 有机质障碍度 |
| `YXP_obstacle_degree` | REAL | 有效磷障碍度 |
| `SXK_obstacle_degree` | REAL | 速效钾障碍度 |
| `RZ_obstacle_degree` | REAL | 容重障碍度 |
| `GZ_obstacle_degree` | REAL | 耕层质地障碍度 |
| `GG_obstacle_degree` | REAL | 灌溉能力障碍度 |
| `PS_obstacle_degree` | REAL | 排水能力障碍度 |
| `DX_obstacle_degree` | REAL | 地形部位障碍度 |
| `ZD_obstacle_degree` | REAL | 质地构型障碍度 |
| `YXT_obstacle_degree` | REAL | 有效土层障碍度 |
| `GCH_obstacle_degree` | REAL | 耕层厚度障碍度 |
| `created_at` | TIMESTAMP | 创建时间 |

#### 2.3.3 acidification_results 表（酸化改良结果）

| 字段 | 类型 | 说明 |
|------|------|------|
| `parcel_id` | TEXT | 地块唯一标识（主键，外键关联 evaluation_results） |
| `acidification_level` | TEXT | 酸化程度（无明显酸化/轻度/中度/重度） |
| `acidification_direction` | TEXT | 酸化方向（酸化/碱化） |
| `target_pH` | REAL | 目标 pH 值 |
| `lime_demand` | REAL | 石灰施用量（kg/亩） |
| `amendment_type` | TEXT | 调理剂类型 |
| `amendment_rate` | REAL | 调理剂施用量（kg/亩） |
| `measures` | TEXT | 改良措施描述（JSON 数组） |
| `expected_effect` | TEXT | 预期效果描述 |
| `created_at` | TIMESTAMP | 创建时间 |

### 2.4 核心模块接口设计

#### 2.4.1 farmland_diagnosis 模块

```python
def bulk_evaluate(input_csv_path: str, output_db_path: str = None) -> dict:
    """
    批量评价入口
    
    Args:
        input_csv_path: 输入 CSV 文件路径
        output_db_path: 输出 SQLite 数据库路径（可选，默认 data/farmland_diagnosis/farmland_diagnosis.db）
    
    Returns:
        {"status": "ok", "processed": int, "errors": []}
    """

def diagnose(db_path: str = None) -> dict:
    """
    执行障碍诊断
    
    Args:
        db_path: SQLite 数据库路径（可选）
    
    Returns:
        {"status": "ok", "diagnosed": int}
    """

def query_parcel(parcel_id: str, db_path: str = None) -> dict:
    """
    查询单个地块的诊断结果
    
    Args:
        parcel_id: 地块 ID
        db_path: SQLite 数据库路径（可选）
    
    Returns:
        {
            "status": "ok",
            "parcel_id": str,
            "evaluation": {...},
            "diagnosis": {...}
        }
        或
        {"status": "not_found"} / {"status": "not_ready"}
    """
```

#### 2.4.2 farmland_acidification 模块

```python
def extract_acidification(evaluation_result: dict) -> dict:
    """
    提取酸化因子
    
    Args:
        evaluation_result: 评价结果字典
    
    Returns:
        {"pH": float, "direction": str, "pH_LD": float}
    """

def classify_level(acidification_factor: dict, diagnosis_result: dict) -> str:
    """
    判定酸化程度
    
    Args:
        acidification_factor: 酸化因子字典
        diagnosis_result: 诊断结果字典
    
    Returns:
        "无明显酸化" | "轻度酸化" | "中度酸化" | "重度酸化"
    """

def generate_plan(parcel_id: str, db_path: str = None) -> dict:
    """
    生成改良方案（混合方式）
    
    Args:
        parcel_id: 地块 ID
        db_path: SQLite 数据库路径（可选）
    
    Returns:
        {
            "status": "ok",
            "acidification_level": str,
            "acidification_direction": str,
            "target_pH": float,
            "lime_demand": float,
            "amendment_type": str,
            "amendment_rate": float,
            "measures": [...],
            "expected_effect": str
        }
    """

def query_parcel(parcel_id: str, db_path: str = None) -> dict:
    """
    查询单个地块的酸化改良方案
    
    Args:
        parcel_id: 地块 ID
        db_path: SQLite 数据库路径（可选）
    
    Returns:
        同 generate_plan 返回格式
    """
```

#### 2.4.3 diagnosis_config 模块

将 `mappings_config.py` 重构为模块化配置：

```python
# 区域映射
REGION_MAP = {...}
SECONDARY_REGION_MAP = {...}

# 隶属度系数（按区域配置）
COEFFICIENTS = {...}

# 权重配置（按二级区域）
WEIGHTS = {...}

# 障碍等级阈值
OBSTACLE_THRESHOLDS = {
    "PH": {"severe": 4.5, "moderate": 5.5, "mild": 6.5},
    "YJ": {"severe": 10, "moderate": 20, "mild": 25},
    ...
}

# 改良方案配置（参考广东省标准）
AMENDMENT_CONFIG = {
    "lime_rate": {"mild": 50, "moderate": 100, "severe": 150},  # kg/亩
    "measures": {
        "mild": ["常规监测", "合理施肥"],
        "moderate": ["施用石灰", "有机肥培肥", "轮作调整"],
        "severe": ["大量施用石灰", "深翻改土", "长期培肥"]
    }
}
```

#### 2.4.4 diagnosis_storage 模块

```python
class DiagnosisStorage:
    def __init__(self, db_path: str = None):
        """初始化数据库连接"""
    
    def create_tables(self) -> None:
        """创建所有必要的表"""
    
    def save_evaluation(self, records: list) -> int:
        """保存评价结果，返回保存数量"""
    
    def save_diagnosis(self, records: list) -> int:
        """保存诊断结果，返回保存数量"""
    
    def save_acidification(self, records: list) -> int:
        """保存酸化改良结果，返回保存数量"""
    
    def get_evaluation(self, parcel_id: str) -> dict:
        """获取单个地块的评价结果"""
    
    def get_diagnosis(self, parcel_id: str) -> dict:
        """获取单个地块的诊断结果"""
    
    def get_acidification(self, parcel_id: str) -> dict:
        """获取单个地块的酸化改良结果"""
    
    def is_ready(self) -> bool:
        """检查数据库是否已就绪（包含评价和诊断数据）"""
```

### 2.5 CoreEngine Adapter 扩展

在 `framework/core_engine/adapter.py` 中扩展 `run_thematic_model()` 的调度逻辑：

```python
def run_thematic_model(self, payload: dict) -> dict:
    """扩展：支持模型3的障碍诊断和酸化改良能力"""
    model_id = payload.get("model_id")
    
    # 模型3障碍诊断
    if model_id == "obstacle-factor-identification":
        return self._run_obstacle_diagnosis(payload)
    
    # 模型3酸化改良
    if model_id == "acidification-governance":
        return self._run_acidification_improvement(payload)
    
    # 原有逻辑
    return self._run_thematic_model(payload)

def _run_obstacle_diagnosis(self, payload: dict) -> dict:
    """执行障碍诊断模型"""
    from src.ai_culti_demo.farmland_diagnosis import query_parcel
    parcel_id = payload.get("parcel_id")
    if not parcel_id:
        return {"status": "error", "error": {"code": "MISSING_PARCEL_ID", "message": "查询障碍诊断需要提供地块 ID"}}
    
    result = query_parcel(parcel_id)
    if result["status"] == "not_ready":
        return {"status": "not_ready", "message": "数据未就绪，请先执行批量评价"}
    if result["status"] == "not_found":
        return {"status": "error", "error": {"code": "PARCEL_NOT_FOUND", "message": "未找到该地块"}}
    
    return {
        "status": "ok",
        "model": {"model_id": "obstacle-factor-identification", "name": "耕地质量主要障碍因素识别模型"},
        "summary": f"地块 {parcel_id} 的障碍诊断结果",
        "findings": [
            {"title": "障碍类型", "content": result["diagnosis"]["obstacle_type"]},
            {"title": "主要障碍因素", "content": "; ".join(result["diagnosis"]["main_factors"])},
            {"title": "次要障碍因素", "content": "; ".join(result["diagnosis"]["secondary_factors"])},
        ],
        "reliability": {"level": "real_model", "message": "基于真实模型计算"},
    }

def _run_acidification_improvement(self, payload: dict) -> dict:
    """执行酸化改良模型"""
    from src.ai_culti_demo.farmland_acidification import query_parcel
    parcel_id = payload.get("parcel_id")
    if not parcel_id:
        return {"status": "error", "error": {"code": "MISSING_PARCEL_ID", "message": "查询酸化改良需要提供地块 ID"}}
    
    result = query_parcel(parcel_id)
    if result["status"] == "not_ready":
        return {"status": "not_ready", "message": "数据未就绪，请先执行批量评价"}
    if result["status"] == "not_found":
        return {"status": "error", "error": {"code": "PARCEL_NOT_FOUND", "message": "未找到该地块"}}
    
    return {
        "status": "ok",
        "model": {"model_id": "acidification-governance", "name": "土壤酸化治理模型"},
        "summary": f"地块 {parcel_id} 的酸化改良方案",
        "findings": [
            {"title": "酸化程度", "content": result["acidification_level"]},
            {"title": "酸化方向", "content": result["acidification_direction"]},
            {"title": "调理剂施用量", "content": f"{result['amendment_rate']} kg/亩"},
            {"title": "改良措施", "content": "; ".join(result["measures"])},
        ],
        "reliability": {"level": "real_model", "message": "基于真实模型计算"},
    }
```

### 2.6 Agent 实现

#### 2.6.1 ObstacleDiagnosisAgent（新增）

```python
class ObstacleDiagnosisAgent(BaseAgent):
    """模型3：耕地质量主要问题精准识别模型（障碍诊断）"""
    
    def __init__(self):
        super().__init__(
            name="ObstacleDiagnosisAgent",
            description="识别耕地质量主要障碍因素并判定障碍组合类型",
            model_id="model-5",  # 新增 question_type=5
            domain="obstacle",
        )
    
    def execute(self, task: dict) -> dict:
        """执行障碍诊断任务"""
    
    def answer_question(self, question: str, context: dict) -> dict:
        """回答障碍诊断相关问题"""
        parcel_id = context.get("parcel_id")
        
        # 检查数据是否就绪
        storage = DiagnosisStorage()
        if not storage.is_ready():
            return {
                "answer": "模型3数据未就绪，请先执行批量评价",
                "evidence": [],
                "confidence": 0.3,
            }
        
        # 查询诊断结果
        result = query_parcel(parcel_id)
        
        # 根据问题类型返回不同格式的回答
        if "障碍类型" in question or "障碍组合" in question:
            answer = f"障碍类型：{result['diagnosis']['obstacle_type']}"
            if result['diagnosis']['main_factors']:
                answer += f"；主要障碍因素：{'; '.join(result['diagnosis']['main_factors'])}"
            if result['diagnosis']['secondary_factors']:
                answer += f"；次要障碍因素：{'; '.join(result['diagnosis']['secondary_factors'])}"
        
        # 构建证据列表
        evidence = [...]
        
        return {
            "answer": answer,
            "evidence": evidence,
            "confidence": 0.85,
        }
```

#### 2.6.2 AcidificationRemediationAgent（修改）

```python
class AcidificationRemediationAgent(BaseAgent):
    """模型3：耕地土壤酸化改良模型（修改为使用真实模型）"""
    
    def __init__(self):
        super().__init__(
            name="AcidificationRemediationAgent",
            description="评估土壤酸化程度并生成改良方案",
            model_id="model-4",
            domain="acidification",
        )
    
    def answer_question(self, question: str, context: dict) -> dict:
        """回答酸化改良相关问题（使用模型3真实数据）"""
        parcel_id = context.get("parcel_id")
        
        # 查询改良方案
        result = generate_plan(parcel_id)
        
        # 返回真实改良方案
        answer = f"酸化程度：{result['acidification_level']}；"
        answer += f"酸化方向：{result['acidification_direction']；"
        answer += f"建议施用量：{result['amendment_rate']} kg/亩；"
        answer += f"改良措施：{'; '.join(result['measures'])}"
        
        return {
            "answer": answer,
            "evidence": [...],
            "confidence": 0.85,
        }
```

#### 2.6.3 AgentManager 综合诊断扩展

```python
class AgentManager:
    def process(self, question: str, context: dict) -> dict:
        """扩展：支持综合诊断"""
        role = self.router.identify_role(question)
        
        # 综合诊断场景：同时涉及稳定性和障碍诊断
        if "综合诊断" in question or ("稳定" in question and "障碍" in question):
            agent_ids = ["model-1", "model-5"]  # 模型1 + 模型3障碍诊断
            results = self._execute_with_dependencies(agent_ids, question, context)
            return {
                "status": "ok",
                "data": self._summarize_comprehensive(role, agent_ids, results),
            }
        
        # 原有逻辑
        ...
    
    def _summarize_comprehensive(self, role, agent_ids, results):
        """综合诊断结果汇总"""
        stability_result = results.get("model-1", {})
        diagnosis_result = results.get("model-5", {})
        
        summary = "综合诊断报告：\n"
        summary += f"- 稳定性评价：{stability_result.get('answer', '')}\n"
        summary += f"- 障碍诊断：{diagnosis_result.get('answer', '')}\n"
        
        # 整合建议
        recommendations = [...]
        
        return {
            "role": "comprehensive",
            "agents_invoked": agent_ids,
            "summary": summary,
            "details": {
                "stability": stability_result,
                "diagnosis": diagnosis_result,
            },
            "recommendations": recommendations,
        }
```

### 2.7 路由扩展

在 `framework/agents/nodes.py` 中扩展路由规则：

```python
# 新增 QUESTION_TYPE_5_KEYWORDS
QUESTION_TYPE_5_KEYWORDS = [
    "障碍诊断", "障碍因素", "障碍类型", "障碍组合", "精准识别",
    "主要问题", "障碍等级", "障碍程度",
]

# 扩展 QUESTION_TYPE_TO_MODEL_ID
QUESTION_TYPE_TO_MODEL_ID = {
    1: "model-1",
    2: "model-4",
    3: "model-2,model-3",
    4: "model-5,model-6",
    5: "model-5",  # 新增：障碍诊断
}

def _identify_question_type_keyword(question: str) -> tuple[int, float]:
    """扩展：支持 question_type=5"""
    relevance = _check_relevance_keyword(question)
    if relevance < 0.3:
        return 0, relevance
    if any(keyword in question for keyword in QUESTION_TYPE_1_KEYWORDS):
        return 1, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_2_KEYWORDS):
        return 2, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_3_KEYWORDS):
        return 3, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_4_KEYWORDS):
        return 4, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_5_KEYWORDS):
        return 5, relevance  # 新增
    else:
        return 0, relevance
```

## 3. 技术风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| CSV 文件编码问题 | 读取 CSV 时可能出现中文乱码 | 支持 UTF-8 和 GBK 两种编码自动检测 |
| SQLite 并发访问 | 多个请求同时查询可能导致锁冲突 | 使用 WAL 模式，设置合理的连接池 |
| 批量评价耗时 | 大量数据时批量评价可能耗时较长 | 采用异步任务队列，支持进度查询 |
| 数据未就绪 | 在线查询时数据可能尚未完成评价 | 返回 `status: "not_ready"` 状态，提示用户先执行批量评价 |
| 区域配置缺失 | 未配置的区域会导致评价失败 | 在配置加载时校验所有区域，提供默认配置 |

## 4. 测试策略

### 4.1 单元测试

| 模块 | 测试场景 |
|------|----------|
| `farmland_diagnosis` | 正常批量评价、CSV 字段缺失、区域无效、单个地块查询、数据未就绪 |
| `farmland_acidification` | 酸化因子提取、酸化程度判定（轻/中/重）、改良方案生成、轻度酸化提示 |
| `diagnosis_config` | 区域映射正确性、隶属度系数配置、权重配置、障碍阈值配置 |
| `diagnosis_storage` | 表创建、数据插入、数据查询、并发访问 |

### 4.2 集成测试

| 测试场景 | 验证内容 |
|----------|----------|
| `run_thematic_model()` 调度 | 模型3的两个能力能正确路由并返回结构化结果 |
| Agent 路由 | 关键词路由到正确的 Agent |
| 综合诊断 | AgentManager 能同时调用模型1和模型3并整合结果 |
| API 端到端 | `/api/v1/chat/` 接口能正确返回模型3的诊断结果 |

### 4.3 回归测试

确保整合后不影响现有功能：
- 其他占位模型（spatial-structure-analysis, soil-indicator-analysis 等）不受影响
- 模型1的稳定性风险识别功能正常
- RAG 路由和其他 question_type 路由正常

## 5. 边界条件处理

| 边界条件 | 处理方式 |
|----------|----------|
| CSV 文件缺失必需字段 | 返回明确错误信息，列出缺失字段 |
| 区域名称无效 | 返回错误信息，列出无效区域和行号 |
| 地块 ID 不存在 | 返回 `status: "not_found"` |
| 批量评价未执行 | 返回 `status: "not_ready"` |
| 轻度或无酸化 | 返回"无需特殊改良"提示 |
| 所有指标无障碍 | 返回"无明显障碍" |

## 6. Spec Patch

以下变更需要回写到 OpenSpec delta spec：

### 6.1 role-based-routing/spec.md

新增 `QUESTION_TYPE_5_KEYWORDS` 路由规则，包含障碍诊断相关关键词。

### 6.2 professional-model-agents/spec.md

明确 `ObstacleDiagnosisAgent` 的 question_type 为 5，`AcidificationRemediationAgent` 使用真实模型数据。

### 6.3 farmland-obstacle-diagnosis-model/spec.md

补充 SQL 表结构设计说明，明确持久化格式为 SQLite。

### 6.4 farmland-acidification-improvement-model/spec.md

补充改良方案生成的混合方式说明（基于障碍等级 + 指标数值计算）。

## 7. Implementation Divergence

### 7.1 模型3 数据导入接口（本期不实施）

**偏差说明**：`farmland-obstacle-diagnosis-model/spec.md` 中定义了「模型3 数据导入接口」Requirement，要求支持上传新 CSV 数据并触发重新评价和诊断。本期 change 未实施该接口，tasks.md 9.6 已明确标注「本期不实施」。

**原因**：本期 change 聚焦三个核心模型的集成（模型1 稳定性风险、耕地质量等级 exe、模型3 障碍诊断与酸化改良），优先保证核心评价和诊断能力的可用性。数据导入接口属于运营增强功能，可在核心模型稳定运行后再行实施。

**影响范围**：
- 用户当前需通过手动部署 CSV 文件到 `data/farmland_diagnosis/` 目录并运行批量评价脚本更新诊断结果
- 不影响核心的障碍诊断查询、酸化改良方案生成和综合诊断能力

**后续实施计划**：

将在单独的 OpenSpec change 中实施「数据导入接口」，计划包含：

1. **API 端点设计**：新增 `POST /api/v1/data/import` 接口，支持上传 CSV 文件
2. **字段校验**：上传时校验 CSV 必需字段（一级农业区、二级农业区、12 项指标），缺失字段时拒绝导入并返回缺失字段列表
3. **文件部署**：校验通过后将文件部署到 `data/farmland_diagnosis/` 目录
4. **触发重新评价**：导入成功后提示用户触发批量评价（`evaluate_acidification` 或 CLI 命令）以更新诊断结果
5. **shapefile 导入扩展**：同步支持模型1 的 shapefile 导入，触发离线预计算
6. **.dat 数据库更新**：支持耕地质量等级 exe 的 .dat 数据库替换

**建议 change 名称**：`add-data-import-interface`
**建议优先级**：P2（核心模型稳定运行后实施）
**预计影响 spec**：`farmland-obstacle-diagnosis-model`（已定义 Requirement）、`farmland-stability-risk-model`（新增 shapefile 导入 Requirement）
