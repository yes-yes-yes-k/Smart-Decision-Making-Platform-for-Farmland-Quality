---
comet_change: add-thematic-model-orm
role: technical-design
canonical_spec: openspec
archived-with: 2026-08-16-add-thematic-model-orm
status: final
---

# Thematic Model ORM V3.0 — Technical Design

## Context

数据库设计文档 V3.0（`专题模型数据库设计文档_V3.docx`，2026-08-15）取代 V2.0，核心变化：
- 字段命名全面取消拼音缩写（SJD/YJZ/YTK/tybh 等），改用英文 snake_case（soil_ph/organic_matter/available_potassium/parcel_id 等）
- 地块唯一编号 `tybh` → `parcel_id`（V3.0 §6.2 明确取消 TYBH/tybh 命名）
- 显式外键约束（V2.0 是弱关联）
- 新增 3 个视图（§5）
- 命名后缀规范：`_membership`/`_weight`/`_obstacle_degree`/`_obstacle_grade`/`_abs`/`_rel`/`_content`/`_dosage`

项目记忆硬约束已同步更新为 V3.0。本变更 `add-thematic-model-orm` 从 V2.0 设计升级到 V3.0；OpenSpec 三件套（proposal/design/tasks）和 delta spec 同步改写。

## Goals / Non-Goals

### Goals

- 在 `framework/models/thematic_model.py` 定义 15 张 V3.0 设计表的 SQLAlchemy ORM 模型，字段名全部英文 snake_case
- ORM 显式定义 V3.0 全部外键约束（7+ 个）
- 每列添加 `comment=` 参数（与 V3.0 COMMENT ON COLUMN 一一对应，与现有 `soil_data.py` 风格一致）
- 在 `__table_args__` 中定义 V3.0 全部 UNIQUE/BTREE/GIST 索引，索引名按表前缀化
- 通过 `framework/models/__init__.py` 导入触发模型注册，`db.create_all()` 一次性创建全部 15 张表
- 在 `scripts/v3_views.sql` 提供 V3.0 §5 的 3 个视图 DDL，由 `init_db.py` 在 `db.create_all()` 之后执行
- 在 `scripts/thematic_models_v3_ddl.sql` 提供 V3.0 §8 的完整 DDL 脚本作为权威参考
- 将 Model-6 元数据升级为"耕地综合地力改良提升模型"，`runtime_requirement` 标注占位状态

### Non-Goals

- 不实现 Model-6 综合地力改良提升的业务逻辑
- 不修改旧的 8 张土壤数据表结构
- 不修改路由判定逻辑或排他规则执行逻辑
- 不实现 V2.0→V3.0 数据迁移脚本（V2.0 表从未落地，无数据需迁移）
- 不实现模型执行日志的写入逻辑（仅定义 ORM 结构）
- 不实现离线导入流程（FK 约束下的导入优化由后续变更处理）

## Technical Approach

### 1. ORM 模型实现（`framework/models/thematic_model.py`）

**复用 Flask-SQLAlchemy `db` 对象**：从 `framework.models.user` 导入 `db`，与 `soil_data.py` 完全一致的模式定义模型类（`db.Model` 基类、`db.Column` 列）。

**15 个 ORM 模型类**（按 V3.0 §3 顺序）：

| 序号 | 类名 | 表名 | 模型归属 |
|---|---|---|---|
| 1 | `ThematicModelRegistry` | `thematic_model_registry` | 注册表 |
| 2 | `ModelExecutionLog` | `model_execution_log` | 执行日志（父表） |
| 3 | `SpatialDataLayer` | `spatial_data_layer` | 空间图层 |
| 4 | `ParcelGeometry` | `parcel_geometry` | 地块几何 |
| 5 | `StabilityRiskResult` | `stability_risk_result` | Model-1 |
| 6 | `QualityGradeResult` | `quality_grade_result` | Model-2 |
| 7 | `ObstacleDiagnosisResult` | `obstacle_diagnosis_result` | Model-3 |
| 8 | `AcidificationRemediationResult` | `acidification_remediation_result` | Model-4 |
| 9 | `OrganicMatterResult` | `organic_matter_result` | Model-5（无 parcel_id） |
| 10 | `ComprehensiveFertilityResult` | `comprehensive_fertility_result` | Model-6（占位） |
| 11 | `RoutingDecisionLog` | `routing_decision_log` | 路由日志 |
| 12 | `ModelEvaluationMetrics` | `model_evaluation_metrics` | 评估指标 |
| 13 | `ExclusiveRuleConfig` | `exclusive_rule_config` | 排他规则 |
| 14 | `ParcelInfo` | `parcel_info` | 地块信息 |
| 15 | `ModelVersionHistory` | `model_version_history` | 版本历史 |

**列类型映射**：

| V3.0 PostgreSQL 类型 | SQLAlchemy 类型 |
|---|---|
| `SERIAL` / `BIGSERIAL` | `db.BigInteger`（统一用 BigInteger 与 BIGSERIAL 一致） |
| `VARCHAR(n)` | `db.String(n)` |
| `TEXT` | `db.Text` |
| `SMALLINT` | `db.SmallInteger` |
| `INTEGER` | `db.Integer` |
| `BOOLEAN` | `db.Boolean` |
| `DOUBLE PRECISION` | `db.Float` |
| `REAL` | `db.Float` |
| `TIMESTAMP WITH TIME ZONE` | `db.DateTime(timezone=True)` |
| `JSONB` | `db.JSON` |
| `geometry(Polygon,4326)` | `geoalchemy2.Geometry('POLYGON', srid=4326)` |

### 2. 外键约束（用户已确认方案 A，完全跟随 V3.0）

ORM 显式定义 V3.0 DDL 中的全部 FK：

| 子表.列 | 父表.列 | FK 约束名 |
|---|---|---|
| `model_execution_log.agent_id` | `thematic_model_registry.agent_id` | `fk_model_execution_log_agent_id` |
| `model_execution_log.layer_id` | `spatial_data_layer.id` | `fk_model_execution_log_layer_id` |
| `parcel_geometry.layer_id` | `spatial_data_layer.id` | `fk_parcel_geometry_layer_id` |
| `stability_risk_result.execution_id` | `model_execution_log.id` | `fk_stability_risk_result_execution_id` |
| `quality_grade_result.execution_id` | `model_execution_log.id` | `fk_quality_grade_result_execution_id` |
| `obstacle_diagnosis_result.execution_id` | `model_execution_log.id` | `fk_obstacle_diagnosis_result_execution_id` |
| `acidification_remediation_result.execution_id` | `model_execution_log.id` | `fk_acidification_remediation_result_execution_id` |
| `organic_matter_result.execution_id` | `model_execution_log.id` | `fk_organic_matter_result_execution_id` |
| `comprehensive_fertility_result.execution_id` | `model_execution_log.id` | `fk_comprehensive_fertility_result_execution_id` |
| `model_version_history.agent_id` | `thematic_model_registry.agent_id` | `fk_model_version_history_agent_id` |

SQLAlchemy 写法：`db.Column(db.BigInteger, db.ForeignKey('model_execution_log.id', name='fk_stability_risk_result_execution_id'), nullable=False)`。

### 3. COMMENT ON COLUMN 实现

每列通过 `comment=` 参数设置中文注释，与 V3.0 §8 `COMMENT ON COLUMN` 一一对应。示例：

```python
soil_ph = db.Column(db.Float, comment='酸碱度（土壤pH）')
exchangeable_hydrogen = db.Column(db.Float, comment='土壤交换性氢离子')
parcel_id = db.Column(db.String(64), comment='地块唯一编号')
```

### 4. 索引设计（`__table_args__`，按表前缀化命名）

PostgreSQL 索引名在 schema 内全局唯一，V3.0 DDL 中跨表重名（如多个 `uk_parcel_id`、`idx_geom`、`idx_agent_id`）需按表前缀化。

**前缀化规则**：`<type>_<table_name>_<column>[_<suffix>]`，例如 `uk_parcel_geometry_parcel_id`、`idx_stability_risk_result_geom`。

在 `__table_args__` 中使用 `db.Index(name, columns, ...)` 和 `db.UniqueConstraint(..., name=...)`，示例：

```python
__table_args__ = (
    db.UniqueConstraint('parcel_id', name='uk_parcel_geometry_parcel_id'),
    db.Index('idx_parcel_geometry_layer_id', 'layer_id'),
    db.Index('idx_parcel_geometry_geom', 'geom', postgresql_using='gist'),
)
```

### 5. 视图实现（`scripts/v3_views.sql`）

V3.0 §5 的 3 个视图作为原始 SQL DDL 存放在 `scripts/v3_views.sql`，由 `init_db.py` 在 `db.create_all()` 之后通过 `db.session.execute(text(open('scripts/v3_views.sql').read()))` 执行。

视图列表：
1. `v_model_execution_summary` — 模型执行汇总（`thematic_model_registry` LEFT JOIN `model_execution_log`）
2. `v_parcel_stability_spatial` — 地块稳定性空间（`parcel_geometry` JOIN `stability_risk_result`）
3. `v_confusion_matrix_latest` — 最新混淆矩阵（`model_evaluation_metrics` 自连接取最新 `evaluated_at`）

**注意**：ORM 不为视图定义模型类（视图是查询辅助，非数据存储）；如未来需要 ORM 查询视图，可单独定义只读模型类，不属于本变更范围。

### 6. DDL 脚本（`scripts/thematic_models_v3_ddl.sql`）

V3.0 §8 的完整 DDL 脚本作为权威参考，包含：
- `CREATE EXTENSION IF NOT EXISTS postgis;`
- 15 张表的 `CREATE TABLE`（V3.0 字段名 + FK 约束）
- 每列的 `COMMENT ON COLUMN`（与 ORM `comment=` 一致）
- 全部索引（按表前缀化命名）
- 3 个视图的 `CREATE OR REPLACE VIEW`

此脚本是 V3.0 docx 的 SQL 落地版，可独立执行于全新 PostgreSQL+PostGIS 数据库；ORM `db.create_all()` 应生成等价结构。

**执行顺序与 ORM 定义顺序的差异**：
- DDL 脚本按 FK 依赖拓扑排序（父表先于子表），而非 V3.0 §8 章节顺序。具体来说，§8.3 `spatial_data_layer` 被移至 §8.2 `model_execution_log` 之前，因为后者有 FK 引用前者的 `id`。PostgreSQL 要求被引用表在 FK 约束创建时已存在。
- ORM 模型类定义顺序不受此限制——SQLAlchemy 的 `db.create_all()` 会在内部对表按 FK 依赖拓扑排序后再发出 `CREATE TABLE`，因此 `thematic_model.py` 中模型类的定义顺序可以跟随 V3.0 §8 章节顺序。
- DDL 脚本中的注释保留了 V3.0 §8.x 章节号（如 `-- §8.3  spatial_data_layer`）用于与 docx 交叉引用，但实际执行顺序由依赖关系决定。

### 7. 模型注册（`framework/models/__init__.py`）

修改 `framework/models/__init__.py`，从 `.thematic_model` 导入全部 15 个模型类，使 `db.create_all()` 能发现新表。

### 8. Model-6 元数据升级（`framework/agents/capabilities.py`）

修改 `framework/agents/capabilities.py` 中 Model-6 的 `ProfessionalCapability`：
- `model_id`: `placeholder` → `comprehensive-fertility-improvement`
- `name`: `占位模型` → `耕地综合地力改良提升模型`
- `description`: 更新为综合地力评价与改良提升描述
- `domain`: `placeholder` → `fertility`
- `runtime_requirement`: 标注为占位状态（业务逻辑尚未实现）
- `question_type`: 保持 6 不变

### 9. 依赖更新（`pyproject.toml`）

新增 `geoalchemy2>=0.14.0` 运行时依赖（与现有 `geopandas` 兼容）。

## Data Flow

```
init_db.py 执行流程
    │
    ├──> db.create_all()
    │       ├──> 创建 8 张旧土壤数据表（soil_data.py 中的模型，未修改）
    │       └──> 创建 15 张 V3.0 新表（thematic_model.py 中的模型）
    │               ├──> 含全部 FK 约束（PostgreSQL 自动校验）
    │               ├──> 含全部 UNIQUE/BTREE/GIST 索引
    │               └──> 每列 COMMENT 自动持久化
    │
    └──> 执行 scripts/v3_views.sql
            └──> 创建 3 个视图（依赖 15 张新表已就绪）
```

应用层 CRUD 通过 ORM 模型访问 15 张表；视图通过 `db.session.execute(text('SELECT * FROM v_model_execution_summary'))` 查询。

## Technical Risks

1. **[风险] FK 约束阻碍离线导入**
   - 场景：批量导入 shapefile 时若父表数据未先就绪，FK 违反导致插入失败。
   - 缓解：本变更仅定义 ORM 结构，不实现离线导入逻辑；如未来需要，可：(a) 按依赖顺序导入（父表先于子表）；(b) 使用 `SET session_replication_role='replica'` 临时禁用触发器；(c) 重新设计为 `DEFERRABLE INITIALLY DEFERRED`。
   - 接受：本变更不在 scope 内解决导入问题。

2. **[风险] PostgreSQL 索引名全局唯一**
   - 场景：V3.0 DDL 中多个表共用 `uk_parcel_id`、`idx_geom`、`idx_agent_id` 等索引名，PostgreSQL 会拒绝重名。
   - 缓解：所有索引名按表前缀化（如 `uk_parcel_geometry_parcel_id`、`uk_parcel_info_parcel_id`），DDL 脚本与 ORM `__table_args__` 同步前缀化。

3. **[风险] 视图依赖表已存在**
   - 场景：在 `db.create_all()` 之前执行 `v3_views.sql` 会因表不存在而失败。
   - 缓解：`init_db.py` 固定调用顺序为 `db.create_all()` → 执行 `v3_views.sql`；脚本使用 `CREATE OR REPLACE VIEW` 容错。

4. **[风险] GeoAlchemy2 依赖 PostgreSQL/PostGIS 后端**
   - 场景：在 MySQL/SQLite 环境下 `db.create_all()` 对 Geometry 列会报错。
   - 缓解：项目硬约束要求 PostgreSQL 16 + PostGIS 3.4，MySQL 报错是预期行为；本变更与 `migrate-to-postgresql-postgis` 变更协同。

5. **[权衡] `obstacle_diagnosis_result` 字段众多（43 列）**
   - 12 membership + 12 obstacle_degree + 12 obstacle_grade + 7 汇总 = 43 列。
   - 模型类较长但结构清晰；按 V3.0 §8.7 完整定义，分组添加 comment。

6. **[权衡] `organic_matter_result` 无 `parcel_id`**
   - V3.0 §8.9 该表无 `parcel_id`（Model-5 是县级分析），与项目记忆"Model-5 是县级分析"一致。

7. **[权衡] Spec 大幅重写**
   - V3.0 要求改写 `specs/thematic-model-orm/spec.md` 全部 Requirement（8 个 Requirement 块的字段名），属于大幅重写。
   - 已标记为设计发现，用户已通过方案 A 确认。

## Test Strategy

### 单元 / 集成测试

- 运行 `python init_db.py`，验证 `db.create_all()` 成功创建全部 15 张新表
- 验证 15 张表名与 V3.0 §3 列表完全一致
- 验证每张表的字段名、类型、`comment` 与 V3.0 §8 DDL 完全一致（英文 snake_case + parcel_id）

### 约束 / 索引验证

- 验证 FK 约束存在：
  ```sql
  SELECT constraint_name, table_name, referenced_table_name
  FROM information_schema.referential_constraints
  ORDER BY table_name;
  ```
- 验证 UNIQUE 索引（`uk_*` 前缀化后）存在：`\di` 或 `pg_indexes`
- 验证 GIST 索引在所有 `geom` 和 `extent` 列上：
  ```sql
  SELECT indexname, tablename FROM pg_indexes
  WHERE indexdef LIKE '%USING gist%';
  ```

### 视图验证

- 验证 3 个视图创建成功：`\dv` 或 `SELECT * FROM pg_views WHERE schemaname='public'`
- 验证视图可查询：`SELECT * FROM v_model_execution_summary LIMIT 1;`

### Model-6 元数据验证

- `model_id=comprehensive-fertility-improvement`
- `name=耕地综合地力改良提升模型`
- `domain=fertility`
- `runtime_requirement` 标注占位状态
- `question_type=6` 不变

### 兼容性验证

- 旧的 8 张土壤数据表未被修改
- `db.create_all()` 同时创建旧表与新表
- 应用层通过 ORM 可正常查询新表（SELECT）

## Spec Patch

### 改写 `openspec/changes/add-thematic-model-orm/specs/thematic-model-orm/spec.md`

将全部 Requirement 的字段名从 V2.0 拼音改为 V3.0 英文 snake_case；新增 FK、COMMENT、索引、视图相关验收场景；将 `tybh` 全部替换为 `parcel_id`；新增索引前缀化命名场景。

### 改写 `openspec/changes/add-thematic-model-orm/proposal.md`

- 移除 V2.0 拼音引用，改用 V3.0 英文 snake_case + parcel_id
- 新增 V3.0 FK、视图、COMMENT、索引条目
- 引用 V3.0 §1.1/§6.2 命名规范

### 改写 `openspec/changes/add-thematic-model-orm/design.md`

- 决策 4（拼音缩写）→ V3.0 英文 snake_case + parcel_id
- 决策 7（弱关联）→ V3.0 显式 FK 约束
- 新增决策 8：视图实现（原始 SQL DDL + init_db.py 执行）
- 新增决策 9：COMMENT 通过 `comment=` 参数
- 新增决策 10：索引按表前缀化命名
- 新增决策 11：V2.0→V3.0 数据迁移不在本变更 scope

### 改写 `openspec/changes/add-thematic-model-orm/tasks.md`

- 字段名全部更新为 V3.0 英文 snake_case
- 新增 FK、COMMENT、索引、视图、索引前缀化任务
- 新增 DDL 脚本和视图脚本交付任务

## Migration Plan

1. 在 `pyproject.toml` 新增 `geoalchemy2>=0.14.0` 依赖并安装
2. 创建 `framework/models/thematic_model.py`，定义全部 15 个 ORM 模型类（V3.0 字段名 + FK + COMMENT + 索引）
3. 修改 `framework/models/__init__.py`，导入 `thematic_model` 模块中的全部模型类
4. 创建 `scripts/thematic_models_v3_ddl.sql`（V3.0 §8 完整 DDL，索引名前缀化）
5. 创建 `scripts/v3_views.sql`（V3.0 §5 的 3 个视图 DDL）
6. 修改 `framework/agents/capabilities.py`，升级 Model-6 的 `ProfessionalCapability` 元数据
7. 修改 `init_db.py`，在 `db.create_all()` 之后执行 `scripts/v3_views.sql`
8. 在 PostgreSQL 16 + PostGIS 3.4 环境运行 `python init_db.py` 验证全部 15 张表 + 3 个视图创建成功
9. **回滚策略**：删除 `thematic_model.py`、还原 `__init__.py` 和 `capabilities.py`、删除两个 SQL 脚本、移除 `init_db.py` 中视图执行、移除 `geoalchemy2` 依赖即可完全回滚（新表为新增，不影响旧表）。

## Open Questions

无。所有设计决策已通过 brainstorming 与用户两轮确认锁定。

## References

- V3.0 数据库设计文档：`专题模型数据库设计文档_V3.docx`（2026-08-15，47331 字符）
- 现有 ORM 风格参考：`framework/models/soil_data.py`
- V3.0 DDL 落地脚本：`scripts/thematic_models_v3_ddl.sql`（本变更新增）
- V3.0 视图脚本：`scripts/v3_views.sql`（本变更新增）
- OpenSpec delta spec：`openspec/changes/add-thematic-model-orm/specs/thematic-model-orm/spec.md`（本变更改写为 V3.0）
- 项目记忆硬约束：`c:\Users\17417\.trae-cn\memory\projects\-d-17417-Documents-agent-culti-demo--p2-a01d85c5f497e31385de\project_memory.md`（已更新为 V3.0）
