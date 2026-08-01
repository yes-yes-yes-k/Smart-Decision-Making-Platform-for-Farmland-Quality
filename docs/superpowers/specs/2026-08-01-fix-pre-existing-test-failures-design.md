---
comet_change: fix-pre-existing-test-failures
role: technical-design
canonical_spec: openspec
archived-with: 2026-08-01-fix-pre-existing-test-failures
status: final
---

# Design Doc: 修复 Pre-existing 测试失败

## 1. 概述

修复项目中 80 failed / 4 collection errors 的 pre-existing 测试失败。失败原因分为三类：代码缺陷（nodes.py 路由逻辑不完整、模块缺失、透传 bug）、测试引用过时（归档后路径未更新）、测试基础设施损坏（fake.shp 缺失、chroma_db 损坏、langchain import 变更）。

## 2. 技术方案

### 2.1 question type 路由修复（framework/agents/nodes.py）

**现状**：
- 定义了 QUESTION_TYPE_1/2/3_KEYWORDS，缺少 TYPE_4/5
- `_identify_question_type_keyword` 只检查 TYPE_1/3，缺少 TYPE_2/4/5
- 缺少 `_is_knowledge_question` 函数
- `identify_question_type` 未在最前端执行知识性问题预检

**修复方案**：

```
identify_question_type(question)
  │
  ├─ 1. 知识性问题预检（新增）
  │   _is_knowledge_question(question) → True 时返回 (0, 1.0) 走 RAG
  │
  ├─ 2. 关键词匹配（补充 TYPE_2/4/5）
  │   _identify_question_type_keyword(question)
  │
  └─ 3. 向量匹配（fallback，不变）
```

**TYPE_4 关键词**（肥力相关）：
```python
QUESTION_TYPE_4_KEYWORDS = [
    "有机质", "有机肥", "秸秆", "肥力", "SOC", "Dose",
    "有机碳", "有机物质", "腐殖质", "有机质含量"
]
```

**TYPE_5 关键词**（质量等级评价相关）：
```python
QUESTION_TYPE_5_KEYWORDS = [
    "质量等级", "综合指数", "障碍度排序", "等级评价",
    "耕地质量", "质量评价", "等级评估"
]
```

**_is_knowledge_question 函数**：
```python
def _is_knowledge_question(question: str) -> bool:
    if not question:
        return False
    # 开头匹配（强信号）
    if question.startswith(("什么是", "何为", "解释")):
        return True
    # 包含匹配（含义类）
    contains_patterns = ["是什么意思", "什么意思", "定义", "概念", "含义"]
    if any(p in question for p in contains_patterns):
        return True
    return False
```

**_identify_question_type_keyword 补充**：
```python
def _identify_question_type_keyword(question: str) -> tuple[int, float]:
    # TYPE_1 检查（现有）
    if any(kw in question for kw in QUESTION_TYPE_1_KEYWORDS):
        return (1, 1.0)
    # TYPE_2 检查（补充）
    if any(kw in question for kw in QUESTION_TYPE_2_KEYWORDS):
        return (2, 1.0)
    # TYPE_3 检查（现有）
    if any(kw in question for kw in QUESTION_TYPE_3_KEYWORDS):
        return (3, 1.0)
    # TYPE_4 检查（新增）
    if any(kw in question for kw in QUESTION_TYPE_4_KEYWORDS):
        return (4, 1.0)
    # TYPE_5 检查（新增）
    if any(kw in question for kw in QUESTION_TYPE_5_KEYWORDS):
        return (5, 1.0)
    return (0, 0.0)
```

**关键词冲突规避**：
- "施加"在 TYPE_2（酸化治理），"有机肥"在 TYPE_4（肥力）— 不冲突
- "酸化"在 TYPE_1/2，"有机质"在 TYPE_4 — 不冲突
- test_type_order_no_cross_collision 测试验证无交叉

### 2.2 parcel_id 透传修复（framework/agents/nodes.py）

**现状**：execute_models 的 context 透传列表为 `("longitude", "latitude", "target_ph", "context", "land_type", "fertilizer_type")`，缺少 parcel_id/parcel_code。

**修复方案**：
```python
for key in ("longitude", "latitude", "target_ph", "context",
            "land_type", "fertilizer_type",
            "parcel_id", "parcel_code"):  # 新增
    if key in state["request"]:
        context[key] = state["request"][key]
```

### 2.3 DataFile 模型（新建 framework/models/data_file.py）

**参考**：framework/models/document.py 的 Document 模型结构。

```python
from datetime import datetime
from .user import db

class DataFile(db.Model):
    __tablename__ = 'kb_data_file'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='数据文件ID')
    doc_name = db.Column(db.String(255), nullable=False, comment='原始文件名')
    file_path = db.Column(db.String(500), nullable=False, comment='文件存储路径')
    file_type = db.Column(db.String(20), nullable=False, comment='文件类型')
    file_size = db.Column(db.BigInteger, default=0, comment='文件大小(字节)')
    category = db.Column(db.String(30), default='other', comment='文件分类')
    treatment_type = db.Column(db.String(30), nullable=True, comment='治理类型')
    status = db.Column(db.SmallInteger, default=1, comment='状态')
    create_by = db.Column(db.Integer, nullable=False, comment='上传者用户ID')
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp(), comment='上传时间')

    def to_dict(self):
        return {
            'id': self.id,
            'doc_name': self.doc_name,
            'file_path': self.file_path,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'category': self.category,
            'treatment_type': self.treatment_type,
            'status': self.status,
            'create_by': self.create_by,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
        }
```

表由 SQLAlchemy `db.create_all()` 自动创建，无需手动建表。

### 2.4 测试引用过时修复（tests/test_model_specs_sync.py）

将所有 `openspec/changes/sync-model-specs-from-overview/specs/` 路径替换为 `openspec/changes/archive/2026-07-24-sync-model-specs-from-overview/specs/`。

### 2.5 测试基础设施修复

**fake.shp**（tests/test_stability_and_grade_integration.py）：
- 使用 geopandas 创建最小有效 shapefile（1 个空 geometry feature）
- 或在测试 fixture 中 mock geopandas.read_file

**chroma_db 损坏**（tests/test_rag.py）：
- 删除 chroma_db/ 目录重置损坏的元数据
- 索引可通过 reindex_documents.py 重新索引

**langchain Tool import**（tests/test_function_calling.py）：
- langchain 1.3.14 已验证 `from langchain_core.tools import Tool` 可用
- 将 `from langchain.tools import Tool` 改为 `from langchain_core.tools import Tool`

## 3. 数据流

```
用户问题 → identify_question_type
             ├─ _is_knowledge_question → True → TYPE_0 (RAG)
             ├─ _identify_question_type_keyword → TYPE_1/2/3/4/5
             └─ _identify_question_type_vector → fallback

execute_models
  ├─ context = {area_code, data, parcel_id, parcel_code, ...}  ← parcel_id 新增透传
  └─ agent_manager.process(question, context)
       └─ agents 通过 context.get("parcel_id") 获取地块标识符

文件上传 → docs.py
  ├─ DataFile 模型（kb_data_file 表）← 新建
  └─ db.session.add(data_file) → commit
```

## 4. 测试策略

| 测试文件 | 验证内容 | 预期结果 |
|----------|---------|---------|
| test_question_type_keywords.py | TYPE_1-5 关键词路由 | 全部 PASS |
| test_knowledge_question.py | _is_knowledge_question 模式匹配 | 全部 PASS |
| test_execute_models_pipeline.py | parcel_id/parcel_code 透传 | 全部 PASS |
| test_docs_dedup.py | import 链恢复（DataFile 可用） | collection 成功 |
| test_model_specs_sync.py | 归档路径引用 | 全部 PASS |
| test_stability_and_grade_integration.py | fake.shp 可读 | PASS |
| test_rag.py | chroma_db 正常 | PASS |
| test_function_calling.py | langchain import | collection 成功 |
| 全量测试 | 回归对比 | 0 新增失败 |

## 5. 边界条件

- _is_knowledge_question 不匹配具体诊断问题（"我的田耕地质量等级是多少"含"质量等级"但不匹配知识模式）
- parcel_id/parcel_code 未传时维持现有 mock 行为（不报错）
- DataFile 模型的 treatment_type 可为 None
- TYPE_4 关键词"有机质"不应出现在 TYPE_1/2/3 关键词中（无交叉）

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| TYPE_4/5 关键词与现有冲突 | test_type_order_no_cross_collision 验证 |
| chroma_db 重置丢失索引 | reindex_documents.py 可重建 |
| kb_data_file 表不存在 | db.create_all() 自动创建 |
| langchain 其他 import 也变更 | 仅修改测试文件，不影响生产代码 |

