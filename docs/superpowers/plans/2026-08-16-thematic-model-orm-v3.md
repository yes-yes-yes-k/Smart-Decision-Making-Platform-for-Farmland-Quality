---
change: add-thematic-model-orm
design-doc: docs/superpowers/specs/2026-08-16-thematic-model-orm-v3-design.md
base-ref: 58deb465afe4c1587a8d1c854b9f3d2af22420e3
---

# Thematic Model ORM V3.0 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `framework/models/thematic_model.py` 中定义 V3.0 设计的 15 张专题模型表的 SQLAlchemy ORM 模型（英文 snake_case 字段 + 10 个显式 FK + 每列 `comment=` + 按表前缀化索引），经 `__init__.py` 注册后由 `init_db.py` 的 `db.create_all()` 一次性建表并执行 3 个视图 DDL，同时升级 Model-6 元数据。

**Architecture:** 复用 `framework/models/user.py` 中的 Flask-SQLAlchemy `db` 对象（与 `soil_data.py` 同模式）；空间几何列用 `geoalchemy2.Geometry('POLYGON', srid=4326)` + GIST 索引；JSONB 列用 `db.JSON`；视图以原始 SQL 存于 `scripts/v3_views.sql`，在 `db.create_all()` 之后执行。`scripts/thematic_models_v3_ddl.sql` 为权威 DDL 参考，ORM 须生成等价结构。

**Tech Stack:** Python 3.10+、Flask-SQLAlchemy 3.x、SQLAlchemy、GeoAlchemy2 0.14+、PostgreSQL 16 + PostGIS 3.4。

## Global Constraints

- **数据库后端**：PostgreSQL 16 + PostGIS 3.4（MySQL/SQLite 下 Geometry 建表会报错，属预期行为）。
- **字段命名**：V3.0 英文 snake_case；地块唯一编号统一为 `parcel_id`（**禁止** V2.0 拼音 `tybh`/`sjd`/`yjz`/`ytk`/`hex`/`alex`/`gdzldj`/`safe_abs`）。
- **后缀规范**：`_membership`/`_weight`/`_obstacle_degree`/`_obstacle_grade`/`_abs`/`_rel`/`_content`/`_dosage`。
- **类型映射**（来自设计文档）：`SERIAL`/`BIGSERIAL`→`db.BigInteger`（统一）；`VARCHAR(n)`→`db.String(n)`；`TEXT`→`db.Text`；`SMALLINT`→`db.SmallInteger`；`INTEGER`→`db.Integer`；`BOOLEAN`→`db.Boolean`；`DOUBLE PRECISION`/`REAL`→`db.Float`；`TIMESTAMP WITH TIME ZONE`→`db.DateTime(timezone=True)`；`JSONB`→`db.JSON`；`geometry(Polygon,4326)`→`geoalchemy2.Geometry('POLYGON', srid=4326)`。
- **每列**必须带 `comment=` 参数（与 V3.0 §8 `COMMENT ON COLUMN` 一一对应，与 `soil_data.py` 风格一致）。
- **索引名**按表前缀化（PostgreSQL schema 内全局唯一）：`<type>_<table>_<column>[_<suffix>]`；唯一索引用 `db.UniqueConstraint(..., name='uk_...')`，普通索引用 `db.Index('idx_...', col)`，GIST 索引用 `db.Index('idx_...', col, postgresql_using='gist')`。
- **FK 名**：`fk_<table>_<column>`，共 10 个（见设计文档 §2 表）。
- **db 对象来源**：`from .user import db`（与 `soil_data.py` 一致）；`Geometry` 从 `geoalchemy2` 导入。
- **`id` 主键**：所有表 `id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='主键')`。
- **时间戳默认值**：`created_at`/`updated_at`/`uploaded_at`/`logged_at`/`evaluated_at` 用 `server_default=db.func.current_timestamp()`；布尔默认 `server_default="false"`/`"true"`；字符串/整数默认 `server_default="<值>"`。
- **提交节奏**：每个任务结束 commit 一次；commit message 前缀 `feat:`/`chore:`/`test:`。
- **DDL 权威源**：`scripts/thematic_models_v3_ddl.sql` 为字段/类型/注释/索引/FK 的单一事实源；ORM 代码须与之逐列等价。

### Pre-flight：已完成任务（仅校验，无需实现）

tasks.md 中以下任务在编写本计划时**已完成**，实施时只需校验存在性，不得重复创建：

- **1.1** `pyproject.toml` 已含 `geoalchemy2>=0.14.0`（第 15 行）。
- **2.1** `scripts/thematic_models_v3_ddl.sql` 已存在（15 表 + 10 FK + 3 视图 + 全部索引/注释，810 行）。
- **2.2** `scripts/v3_views.sql` 已存在（3 个视图 DDL）。

### 关键代码现状说明（影响 Task 5）

**`framework/agents/capabilities.py` 当前 `PROFESSIONAL_CAPABILITIES` 元组只有 model-1 ~ model-5 五个条目，不存在 Model-6（`placeholder`）条目。** 设计文档/openspec spec/tasks.md 措辞为"将 Model-6 从 `placeholder` 升级为 `comprehensive-fertility-improvement`"，假定已存在占位条目；但真实代码库中并无该条目。因此 **Task 5 采取"新增 Model-6 条目"**（而非修改不存在的条目），这满足设计意图与 spec 验收的端态（`model_id=comprehensive-fertility-improvement`、`name=耕地综合地力改良提升模型`、`domain=fertility`、`runtime_requirement` 标注占位、`question_type=6`），与 tasks.md 5.1 的端态验收完全一致。

---

## File Structure

| 文件 | 操作 | 职责 |
|---|---|---|
| `framework/models/thematic_model.py` | 新建 | 15 个 V3.0 ORM 模型类（字段 + FK + comment + 索引） |
| `framework/models/__init__.py` | 修改 | 导入 15 个模型类触发注册 |
| `framework/agents/capabilities.py` | 修改 | 新增 Model-6 `ProfessionalCapability` 条目 |
| `init_db.py` | 修改 | `db.create_all()` 后执行 `scripts/v3_views.sql`；删视图后再 `drop_all` |
| `scripts/thematic_models_v3_ddl.sql` | 已存在 | V3.0 §8 权威 DDL（已完成，仅校验） |
| `scripts/v3_views.sql` | 已存在 | V3.0 §5 视图 DDL（已完成，仅校验） |
| `pyproject.toml` | 已含依赖 | `geoalchemy2>=0.14.0`（已完成，仅校验） |

---

## Task 1：依赖校验（对应 tasks 1.1 / 1.2）

**Files:**
- 校验（已存在）：`pyproject.toml:15`
- 校验：本地 Python 环境

**Interfaces:**
- Produces：可导入的 `geoalchemy2` 包（供 Task 3 使用）

- [x] **Step 1：校验 `pyproject.toml` 已声明依赖**

Run: `python -c "import tomllib; d=tomllib.loads(open('pyproject.toml','rb').read().decode()); assert 'geoalchemy2>=0.14.0' in d['project']['dependencies'], d['project']['dependencies']; print('OK dep declared')"`
Expected: `OK dep declared`

- [x] **Step 2：校验 geoalchemy2 已安装并可导入**

Run: `python -c "import geoalchemy2; from geoalchemy2 import Geometry; print('geoalchemy2', geoalchemy2.__version__)"`
Expected: `geoalchemy2 <版本号>`（若报 ModuleNotFoundError，执行 `pip install -e .` 或 `pip install "geoalchemy2>=0.14.0"` 后重试）

- [x] **Step 3：Commit（如安装了新包则更新 lockfile/无文件变更则跳过）**

仅当 Step 2 触发了实际安装且产生环境文件变更时提交；否则跳过 commit。

---

## Task 2：DDL / 视图脚本校验（对应 tasks 2.1 / 2.2）

**Files:**
- 校验（已存在）：`scripts/thematic_models_v3_ddl.sql`
- 校验（已存在）：`scripts/v3_views.sql`

**Interfaces:**
- Produces：两个 SQL 脚本就绪，供 Task 6（`init_db.py`）和 Task 7.15（独立 source）使用

- [x] **Step 1：校验 DDL 脚本含 15 张表 + 3 视图**

Run: `python -c "s=open('scripts/thematic_models_v3_ddl.sql',encoding='utf-8').read(); assert s.count('CREATE TABLE ')==15, s.count('CREATE TABLE '); assert s.count('CREATE OR REPLACE VIEW ')==3; assert 'CREATE EXTENSION IF NOT EXISTS postgis' in s; print('OK 15 tables + 3 views')"`
Expected: `OK 15 tables + 3 views`

- [x] **Step 2：校验视图脚本含 3 个视图**

Run: `python -c "s=open('scripts/v3_views.sql',encoding='utf-8').read(); assert s.count('CREATE OR REPLACE VIEW ')==3; assert 'v_model_execution_summary' in s and 'v_parcel_stability_spatial' in s and 'v_confusion_matrix_latest' in s; print('OK 3 views')"`
Expected: `OK 3 views`

- [x] **Step 3：Commit（无文件变更，跳过）**

---

## Task 3.0：创建 thematic_model.py 脚手架（对应 task 3.1）

**Files:**
- Create: `framework/models/thematic_model.py`

**Interfaces:**
- Consumes：`db`（来自 `framework.models.user`）、`geoalchemy2.Geometry`
- Produces：模块文件，后续 Task 3.1–3.15 在此文件追加模型类

- [x] **Step 1：写入模块头部（导入 + 文档字符串）**

写入文件 `framework/models/thematic_model.py`：

```python
"""专题模型数据库 V3.0 SQLAlchemy ORM 模型。

定义 V3.0 设计文档（专题模型数据库设计文档_V3.docx，2026-08-15）§8 的 15 张表：
注册表、执行日志、空间图层、地块几何、Model-1~Model-6 结果表、路由日志、
评估指标、排他规则、地块信息、版本历史。

命名规范（V3.0 §1.1/§6.2）：
- 字段名全面采用英文 snake_case，取消 V2.0 拼音缩写（SJD/YJZ/YTK 等）。
- 地块唯一编号统一为 parcel_id（取消 tybh）。
- 后缀规范：_membership / _weight / _obstacle_degree / _obstacle_grade /
  _abs / _rel / _content / _dosage。
- 索引名按表前缀化（PostgreSQL schema 内全局唯一）。
- 外键约束名：fk_<table>_<column>。

复用 framework.models.user 中的 Flask-SQLAlchemy db 对象，与 soil_data.py 同模式。
权威 DDL 参考：scripts/thematic_models_v3_ddl.sql（ORM db.create_all() 生成等价结构）。
"""
from .user import db
from geoalchemy2 import Geometry
```

- [x] **Step 2：校验模块可导入**

Run: `python -c "import framework.models.thematic_model as m; print('OK', m.__doc__.splitlines()[0])"`
Expected: `OK 专题模型数据库 V3.0 SQLAlchemy ORM 模型。`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): scaffold thematic_model.py module with V3.0 docstring"
```

---

## Task 3.1：ThematicModelRegistry（对应 task 3.2）

**Files:**
- Modify: `framework/models/thematic_model.py`（追加类）

**Interfaces:**
- Consumes：`db`
- Produces：`ThematicModelRegistry`（表 `thematic_model_registry`，无 FK；被 `ModelExecutionLog.agent_id`、`ModelVersionHistory.agent_id` 引用）

- [x] **Step 1：追加 `ThematicModelRegistry` 类**（在脚手架导入语句之后）

```python
class ThematicModelRegistry(db.Model):
    """专题模型注册表（V3.0 §8.1）。"""
    __tablename__ = "thematic_model_registry"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    agent_id = db.Column(db.String(32), nullable=False, comment="智能体标识（model-1 ~ model-6）")
    model_id = db.Column(db.String(64), nullable=False, comment="规范模型标识")
    name = db.Column(db.String(128), nullable=False, comment="模型中文名称")
    description = db.Column(db.Text, comment="模型描述")
    domain = db.Column(db.String(32), nullable=False, comment="领域标识")
    question_type = db.Column(db.SmallInteger, nullable=False, comment="问题类型（1~6）")
    analysis_scale = db.Column(db.String(16), nullable=False, comment="分析尺度（省/县/片区/地块）")
    data_type = db.Column(db.String(16), nullable=False, comment="数据类型（指标数据/评价结果/处方用量）")
    input_format = db.Column(db.String(16), nullable=False, server_default="shp", comment="输入格式（shp/csv/json）")
    output_format = db.Column(db.String(16), nullable=False, server_default="shp", comment="输出格式（shp/csv/json）")
    minimum_inputs = db.Column(db.JSON, comment="最小输入字段列表")
    runtime_requirement = db.Column(db.Text, comment="运行时前置条件")
    version = db.Column(db.String(16), nullable=False, server_default="1.0", comment="当前模型版本")
    status = db.Column(db.String(16), nullable=False, server_default="active", comment="状态")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="更新时间")

    __table_args__ = (
        db.UniqueConstraint("agent_id", name="uk_thematic_model_registry_agent_id"),
        db.UniqueConstraint("model_id", name="uk_thematic_model_registry_model_id"),
        db.Index("idx_thematic_model_registry_question_type", "question_type"),
    )
```

- [x] **Step 2：校验导入与表名/列**

Run: `python -c "from framework.models.thematic_model import ThematicModelRegistry as M; assert M.__tablename__=='thematic_model_registry'; assert 'agent_id' in M.__table__.columns; print('OK', M.__tablename__, len(M.__table__.columns), 'cols')"`
Expected: `OK thematic_model_registry 16 cols`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add ThematicModelRegistry ORM (V3.0 §8.1)"
```

---

## Task 3.2：ModelExecutionLog（对应 task 3.3）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Consumes：`ThematicModelRegistry.agent_id`、`SpatialDataLayer.id`（FK 目标，`SpatialDataLayer` 在 Task 3.3 定义；SQLAlchemy `db.create_all()` 内部按 FK 拓扑排序，类定义顺序不影响建表）
- Produces：`ModelExecutionLog`（表 `model_execution_log`，含 2 个 FK；被 6 个结果表的 `execution_id` 引用）

- [x] **Step 1：追加 `ModelExecutionLog` 类**

```python
class ModelExecutionLog(db.Model):
    """模型执行日志表（V3.0 §8.2，父表，被各结果表通过 execution_id 引用）。"""
    __tablename__ = "model_execution_log"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    trace_id = db.Column(db.String(64), nullable=False, comment="追溯ID（UUID）")
    agent_id = db.Column(db.String(32), db.ForeignKey("thematic_model_registry.agent_id", name="fk_model_execution_log_agent_id"), nullable=False, comment="关联 thematic_model_registry.agent_id")
    question_type = db.Column(db.SmallInteger, nullable=False, comment="问题类型（1~6）")
    user_id = db.Column(db.Integer, comment="用户ID")
    conversation_id = db.Column(db.Integer, comment="会话ID")
    parcel_id = db.Column(db.String(64), comment="地块唯一编号")
    layer_id = db.Column(db.BigInteger, db.ForeignKey("spatial_data_layer.id", name="fk_model_execution_log_layer_id"), comment="关联 spatial_data_layer.id")
    input_params = db.Column(db.JSON, comment="输入参数快照")
    output_result = db.Column(db.JSON, comment="输出结果快照")
    answer_text = db.Column(db.Text, comment="自然语言答复")
    evidence = db.Column(db.JSON, comment="证据列表")
    status = db.Column(db.String(16), nullable=False, comment="执行状态（ok/error/fallback/rejected）")
    routing_mode = db.Column(db.String(16), comment="路由模式（llm/keyword）")
    routing_status = db.Column(db.String(16), comment="路由状态")
    simulated = db.Column(db.Boolean, nullable=False, server_default="false", comment="是否模拟数据")
    confidence = db.Column(db.Float, comment="置信度（0~1）")
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, comment="执行开始时间")
    completed_at = db.Column(db.DateTime(timezone=True), comment="执行完成时间")
    duration_ms = db.Column(db.Float, comment="执行耗时（毫秒）")
    error_message = db.Column(db.Text, comment="错误信息")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="记录创建时间")

    __table_args__ = (
        db.UniqueConstraint("trace_id", name="uk_model_execution_log_trace_id"),
        db.Index("idx_model_execution_log_agent_id", "agent_id"),
        db.Index("idx_model_execution_log_parcel_id", "parcel_id"),
        db.Index("idx_model_execution_log_layer_id", "layer_id"),
        db.Index("idx_model_execution_log_started_at", "started_at"),
    )
```

- [x] **Step 2：校验导入与 FK**

Run: `python -c "from framework.models.thematic_model import ModelExecutionLog as M; assert M.__tablename__=='model_execution_log'; assert len([c for c in M.__table__.foreign_keys])==2; print('OK', M.__tablename__, len(M.__table__.columns), 'cols, 2 FKs')"`
Expected: `OK model_execution_log 22 cols, 2 FKs`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add ModelExecutionLog ORM with 2 FKs (V3.0 §8.2)"
```

---

## Task 3.3：SpatialDataLayer（对应 task 3.4）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Consumes：`Geometry`
- Produces：`SpatialDataLayer`（表 `spatial_data_layer`，无 FK；被 `ModelExecutionLog.layer_id`、`ParcelGeometry.layer_id` 引用）

- [x] **Step 1：追加 `SpatialDataLayer` 类**

```python
class SpatialDataLayer(db.Model):
    """空间数据图层管理表（V3.0 §8.3）。"""
    __tablename__ = "spatial_data_layer"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    layer_name = db.Column(db.String(128), nullable=False, comment="图层名称")
    layer_type = db.Column(db.String(32), nullable=False, comment="图层类型（farmland_boundary/stability_result/diagnosis_result 等）")
    file_path = db.Column(db.Text, nullable=False, comment="Shapefile 文件路径")
    file_hash = db.Column(db.String(64), comment="文件哈希（SHA-256）")
    crs = db.Column(db.String(32), nullable=False, server_default="EPSG:4326", comment="坐标参考系（如 EPSG:4326）")
    feature_count = db.Column(db.Integer, comment="要素数量")
    extent = db.Column(Geometry("POLYGON", srid=4326), comment="图层空间范围（PostGIS 几何）")
    geometry_type = db.Column(db.String(16), comment="几何类型（Point/Polygon/MultiPolygon）")
    attribute_fields = db.Column(db.JSON, comment="属性字段列表 [{name, type}]")
    model_scope = db.Column(db.String(32), comment="适用模型（model-1/model-2/model-3/all）")
    upload_by = db.Column(db.Integer, comment="上传用户ID")
    status = db.Column(db.String(16), nullable=False, server_default="active", comment="状态（active/archived）")
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="上传时间")

    __table_args__ = (
        db.UniqueConstraint("file_hash", name="uk_spatial_data_layer_file_hash"),
        db.Index("idx_spatial_data_layer_layer_type", "layer_type"),
        db.Index("idx_spatial_data_layer_model_scope", "model_scope"),
        db.Index("idx_spatial_data_layer_status", "status"),
        db.Index("idx_spatial_data_layer_extent", "extent", postgresql_using="gist"),
    )
```

- [x] **Step 2：校验导入与 GIST 索引**

Run: `python -c "from framework.models.thematic_model import SpatialDataLayer as M; assert M.__tablename__=='spatial_data_layer'; assert 'extent' in M.__table__.columns; print('OK', M.__tablename__, len(M.__table__.columns), 'cols')"`
Expected: `OK spatial_data_layer 14 cols`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add SpatialDataLayer ORM with GIST extent index (V3.0 §8.3)"
```

---

## Task 3.4：ParcelGeometry（对应 task 3.5）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Consumes：`SpatialDataLayer.id`（FK 目标）、`Geometry`
- Produces：`ParcelGeometry`（表 `parcel_geometry`，1 个 FK；`parcel_id` 唯一）

- [x] **Step 1：追加 `ParcelGeometry` 类**

```python
class ParcelGeometry(db.Model):
    """地块空间几何表（V3.0 §8.4，parcel_id 取代 V2.0 tybh）。"""
    __tablename__ = "parcel_geometry"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    parcel_id = db.Column(db.String(64), nullable=False, comment="地块唯一编号")
    geom = db.Column(Geometry("POLYGON", srid=4326), nullable=False, comment="地块几何（PostGIS Polygon）")
    crs = db.Column(db.String(32), nullable=False, server_default="EPSG:4326", comment="坐标参考系")
    area_mu = db.Column(db.Float, comment="面积（亩）")
    area_sqm = db.Column(db.Float, comment="面积（平方米）")
    centroid_lon = db.Column(db.Float, comment="质心经度")
    centroid_lat = db.Column(db.Float, comment="质心纬度")
    layer_id = db.Column(db.BigInteger, db.ForeignKey("spatial_data_layer.id", name="fk_parcel_geometry_layer_id"), comment="关联 spatial_data_layer.id")
    properties = db.Column(db.JSON, comment="其他土壤指标属性快照")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("parcel_id", name="uk_parcel_geometry_parcel_id"),
        db.Index("idx_parcel_geometry_layer_id", "layer_id"),
        db.Index("idx_parcel_geometry_geom", "geom", postgresql_using="gist"),
    )
```

- [x] **Step 2：校验导入与 FK**

Run: `python -c "from framework.models.thematic_model import ParcelGeometry as M; assert M.__tablename__=='parcel_geometry'; assert len([c for c in M.__table__.foreign_keys])==1; print('OK', M.__tablename__, len(M.__table__.columns), 'cols')"`
Expected: `OK parcel_geometry 11 cols`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add ParcelGeometry ORM with parcel_id + GIST (V3.0 §8.4)"
```

---

## Task 3.5：StabilityRiskResult（对应 task 3.6，Model-1）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Consumes：`ModelExecutionLog.id`（FK 目标）
- Produces：`StabilityRiskResult`（表 `stability_risk_result`，1 个 FK，34 列）

- [x] **Step 1：追加 `StabilityRiskResult` 类**

```python
class StabilityRiskResult(db.Model):
    """稳定性风险评价结果表（Model-1，V3.0 §8.5）。"""
    __tablename__ = "stability_risk_result"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    execution_id = db.Column(db.BigInteger, db.ForeignKey("model_execution_log.id", name="fk_stability_risk_result_execution_id"), nullable=False, comment="关联 model_execution_log.id")
    parcel_id = db.Column(db.String(64), nullable=False, comment="地块唯一编号")
    geom = db.Column(Geometry("POLYGON", srid=4326), comment="地块几何（PostGIS，用于空间邻域分析）")
    grade_boundary_safety = db.Column(db.Float, comment="等级边界安全度")
    indicator_balance_abs = db.Column(db.Float, comment="指标支撑均衡度_绝对")
    indicator_balance_rel = db.Column(db.Float, comment="指标支撑均衡度_相对")
    critical_indicator = db.Column(db.Float, comment="关键临界指标")
    critical_indicator_degree_abs = db.Column(db.Float, comment="关键指标临界度_绝对")
    critical_indicator_degree_rel = db.Column(db.Float, comment="关键指标临界度_相对")
    spatial_consistency_abs = db.Column(db.Float, comment="空间邻域一致性_绝对")
    spatial_consistency_rel = db.Column(db.Float, comment="空间邻域一致性_相对")
    neighbor_count = db.Column(db.Integer, comment="邻域地块数")
    historical_slope = db.Column(db.Float, comment="历史年均变化斜率")
    historical_trend_abs = db.Column(db.Float, comment="历史变化趋势_绝对")
    historical_trend_rel = db.Column(db.Float, comment="历史变化趋势_相对")
    historical_trend_type = db.Column(db.String(64), comment="历史变化类型")
    historical_grade_change = db.Column(db.Float, comment="历史等级变化")
    grade_drop_count = db.Column(db.Integer, comment="历史掉级次数")
    grade_drop_risk_abs = db.Column(db.Float, comment="掉级风险_绝对")
    grade_drop_risk_rel = db.Column(db.Float, comment="掉级风险_相对")
    key_degradation_factor = db.Column(db.String(64), comment="关键退化因子")
    key_factor_risk_abs = db.Column(db.Float, comment="关键因子退化风险_绝对")
    key_factor_risk_rel = db.Column(db.Float, comment="关键因子退化风险_相对")
    neighbor_degradation_risk = db.Column(db.Float, comment="邻域平均退化风险")
    degradation_cluster_risk_abs = db.Column(db.Float, comment="退化空间集聚风险_绝对")
    degradation_cluster_risk_rel = db.Column(db.Float, comment="退化空间集聚风险_相对")
    low_quality_year_count = db.Column(db.Integer, comment="低质年份数")
    low_quality_ratio = db.Column(db.Float, comment="持续低质比例")
    persistent_low_risk_abs = db.Column(db.Float, comment="持续低质风险_绝对")
    persistent_low_risk_rel = db.Column(db.Float, comment="持续低质风险_相对")
    input_snapshot = db.Column(db.JSON, comment="输入参数快照（含 terrain_position/topsoil_thickness/soil_ph 等41个标准输入字段）")
    simulated = db.Column(db.Boolean, nullable=False, server_default="false", comment="是否模拟数据")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("execution_id", name="uk_stability_risk_result_execution_id"),
        db.Index("idx_stability_risk_result_parcel_id", "parcel_id"),
        db.Index("idx_stability_risk_result_geom", "geom", postgresql_using="gist"),
    )
```

- [x] **Step 2：校验导入与 FK**

Run: `python -c "from framework.models.thematic_model import StabilityRiskResult as M; assert M.__tablename__=='stability_risk_result'; assert len([c for c in M.__table__.foreign_keys])==1; assert 'grade_drop_risk_abs' in M.__table__.columns; print('OK', M.__tablename__, len(M.__table__.columns), 'cols')"`
Expected: `OK stability_risk_result 34 cols`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add StabilityRiskResult ORM Model-1 (V3.0 §8.5, 34 cols)"
```

---

## Task 3.6：QualityGradeResult（对应 task 3.7，Model-2）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Consumes：`ModelExecutionLog.id`（FK 目标）
- Produces：`QualityGradeResult`（表 `quality_grade_result`，1 个 FK，12 列）

- [x] **Step 1：追加 `QualityGradeResult` 类**

```python
class QualityGradeResult(db.Model):
    """质量等级评价结果表（Model-2，V3.0 §8.6）。"""
    __tablename__ = "quality_grade_result"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    execution_id = db.Column(db.BigInteger, db.ForeignKey("model_execution_log.id", name="fk_quality_grade_result_execution_id"), nullable=False, comment="关联 model_execution_log.id")
    parcel_id = db.Column(db.String(64), comment="地块唯一编号")
    geom = db.Column(Geometry("POLYGON", srid=4326), comment="地块几何（PostGIS）")
    quality_grade = db.Column(db.String(4), nullable=False, comment="耕地质量等级（1~10）")
    composite_index = db.Column(db.Float, nullable=False, comment="综合指数（0~1）")
    composite_weight = db.Column(db.Float, comment="综合权重")
    indicators = db.Column(db.JSON, comment="指标列表 [{name, raw_value, membership, weight}]")
    obstacle_degree = db.Column(db.JSON, comment="障碍度排序 [{rank, indicator, degree}]")
    input_snapshot = db.Column(db.JSON, comment="输入参数快照（含 terrain_position/soil_ph/organic_matter 等标准输入字段）")
    simulated = db.Column(db.Boolean, nullable=False, server_default="false", comment="是否模拟数据")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("execution_id", name="uk_quality_grade_result_execution_id"),
        db.Index("idx_quality_grade_result_parcel_id", "parcel_id"),
        db.Index("idx_quality_grade_result_quality_grade", "quality_grade"),
        db.Index("idx_quality_grade_result_geom", "geom", postgresql_using="gist"),
    )
```

- [x] **Step 2：校验导入与 FK**

Run: `python -c "from framework.models.thematic_model import QualityGradeResult as M; assert M.__tablename__=='quality_grade_result'; assert len([c for c in M.__table__.foreign_keys])==1; print('OK', M.__tablename__, len(M.__table__.columns), 'cols')"`
Expected: `OK quality_grade_result 12 cols`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add QualityGradeResult ORM Model-2 (V3.0 §8.6)"
```

---

## Task 3.7：ObstacleDiagnosisResult（对应 task 3.8，Model-3，43 数据列）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Consumes：`ModelExecutionLog.id`（FK 目标）
- Produces：`ObstacleDiagnosisResult`（表 `obstacle_diagnosis_result`，1 个 FK，47 列：12 membership + 12 obstacle_degree + 12 obstacle_grade + id/execution_id/parcel_id + 7 汇总 + created_at）

- [x] **Step 1：追加 `ObstacleDiagnosisResult` 类**

```python
class ObstacleDiagnosisResult(db.Model):
    """障碍诊断结果表（Model-3，V3.0 §8.7，含 12 隶属度 + 12 障碍度 + 12 障碍等级）。"""
    __tablename__ = "obstacle_diagnosis_result"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    execution_id = db.Column(db.BigInteger, db.ForeignKey("model_execution_log.id", name="fk_obstacle_diagnosis_result_execution_id"), nullable=False, comment="关联 model_execution_log.id")
    parcel_id = db.Column(db.String(64), comment="地块唯一编号")
    # —— 12 隶属度（_membership）——
    soil_ph_membership = db.Column(db.Float, comment="酸碱度隶属度")
    organic_matter_membership = db.Column(db.Float, comment="有机质隶属度")
    available_p_membership = db.Column(db.Float, comment="有效磷隶属度")
    available_k_membership = db.Column(db.Float, comment="速效钾隶属度")
    soil_bulk_density_membership = db.Column(db.Float, comment="土壤容重隶属度")
    topsoil_texture_membership = db.Column(db.Float, comment="耕层质地隶属度")
    irrigation_capacity_membership = db.Column(db.Float, comment="灌溉能力隶属度")
    drainage_capacity_membership = db.Column(db.Float, comment="排水能力隶属度")
    terrain_position_membership = db.Column(db.Float, comment="地形部位隶属度")
    texture_profile_membership = db.Column(db.Float, comment="质地构型隶属度")
    effective_soil_depth_membership = db.Column(db.Float, comment="有效土层厚度隶属度")
    topsoil_thickness_membership = db.Column(db.Float, comment="耕层厚度隶属度")
    # —— 12 障碍度（_obstacle_degree）——
    ph_obstacle_degree = db.Column(db.Float, comment="pH障碍度")
    organic_matter_obstacle_degree = db.Column(db.Float, comment="有机质障碍度")
    available_p_obstacle_degree = db.Column(db.Float, comment="有效磷障碍度")
    available_k_obstacle_degree = db.Column(db.Float, comment="速效钾障碍度")
    bulk_density_obstacle_degree = db.Column(db.Float, comment="容重障碍度")
    texture_obstacle_degree = db.Column(db.Float, comment="耕层质地障碍度")
    irrigation_obstacle_degree = db.Column(db.Float, comment="灌溉能力障碍度")
    drainage_obstacle_degree = db.Column(db.Float, comment="排水能力障碍度")
    terrain_obstacle_degree = db.Column(db.Float, comment="地形部位障碍度")
    texture_profile_obstacle_degree = db.Column(db.Float, comment="质地构型障碍度")
    soil_depth_obstacle_degree = db.Column(db.Float, comment="有效土层障碍度")
    topsoil_thickness_obstacle_degree = db.Column(db.Float, comment="耕层厚度障碍度")
    # —— 12 障碍等级（_obstacle_grade）——
    ph_obstacle_grade = db.Column(db.Float, comment="pH障碍等级")
    organic_matter_obstacle_grade = db.Column(db.Float, comment="有机质障碍等级")
    available_p_obstacle_grade = db.Column(db.Float, comment="有效磷障碍等级")
    available_k_obstacle_grade = db.Column(db.Float, comment="速效钾障碍等级")
    bulk_density_obstacle_grade = db.Column(db.Float, comment="容重障碍等级")
    texture_obstacle_grade = db.Column(db.Float, comment="耕层质地障碍等级")
    irrigation_obstacle_grade = db.Column(db.Float, comment="灌溉能力障碍等级")
    drainage_obstacle_grade = db.Column(db.Float, comment="排水能力障碍等级")
    terrain_obstacle_grade = db.Column(db.Float, comment="地形部位障碍等级")
    texture_profile_obstacle_grade = db.Column(db.Float, comment="质地构型障碍等级")
    soil_depth_obstacle_grade = db.Column(db.Float, comment="有效土层障碍等级")
    topsoil_thickness_obstacle_grade = db.Column(db.Float, comment="耕层厚度障碍等级")
    # —— 汇总列 ——
    obstacle_type = db.Column(db.String(64), comment="障碍类型")
    primary_obstacle_factor = db.Column(db.String(64), comment="主要障碍因素")
    secondary_obstacle_factor = db.Column(db.String(64), comment="次要障碍因素")
    quality_grade = db.Column(db.String(64), comment="耕地质量等级")
    composite_weight = db.Column(db.Float, comment="综合权重")
    input_snapshot = db.Column(db.JSON, comment="输入参数快照")
    simulated = db.Column(db.Boolean, nullable=False, server_default="false", comment="是否模拟数据")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("execution_id", name="uk_obstacle_diagnosis_result_execution_id"),
        db.Index("idx_obstacle_diagnosis_result_parcel_id", "parcel_id"),
        db.Index("idx_obstacle_diagnosis_result_obstacle_type", "obstacle_type"),
    )
```

- [x] **Step 2：校验导入与 FK**

Run: `python -c "from framework.models.thematic_model import ObstacleDiagnosisResult as M; assert M.__tablename__=='obstacle_diagnosis_result'; assert len([c for c in M.__table__.foreign_keys])==1; assert 'topsoil_thickness_obstacle_grade' in M.__table__.columns; print('OK', M.__tablename__, len(M.__table__.columns), 'cols')"`
Expected: `OK obstacle_diagnosis_result 47 cols`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add ObstacleDiagnosisResult ORM Model-3 (V3.0 §8.7, 47 cols)"
```

---

## Task 3.8：AcidificationRemediationResult（对应 task 3.9，Model-4）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Consumes：`ModelExecutionLog.id`（FK 目标）
- Produces：`AcidificationRemediationResult`（表 `acidification_remediation_result`，1 个 FK，37 列）

- [x] **Step 1：追加 `AcidificationRemediationResult` 类**

```python
class AcidificationRemediationResult(db.Model):
    """酸化改良结果表（Model-4，V3.0 §8.8）。"""
    __tablename__ = "acidification_remediation_result"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    execution_id = db.Column(db.BigInteger, db.ForeignKey("model_execution_log.id", name="fk_acidification_remediation_result_execution_id"), nullable=False, comment="关联 model_execution_log.id")
    parcel_id = db.Column(db.String(64), comment="地块唯一编号")
    soil_ph = db.Column(db.Float, comment="酸碱度（土壤pH）")
    exchangeable_hydrogen = db.Column(db.Float, comment="土壤交换性氢离子")
    exchangeable_aluminum = db.Column(db.Float, comment="土壤交换性铝离子")
    rainfall_ph = db.Column(db.Float, comment="降水pH年均值")
    annual_rainfall = db.Column(db.Float, comment="年降水量")
    grain_yield = db.Column(db.Float, comment="籽粒产量")
    straw_yield = db.Column(db.Float, comment="秸秆产量")
    grain_p_content = db.Column(db.Float, comment="籽粒P含量")
    grain_k_content = db.Column(db.Float, comment="籽粒K含量")
    grain_ca_content = db.Column(db.Float, comment="籽粒Ca含量")
    grain_mg_content = db.Column(db.Float, comment="籽粒Mg含量")
    straw_p_content = db.Column(db.Float, comment="秸秆P含量")
    straw_k_content = db.Column(db.Float, comment="秸秆K含量")
    straw_ca_content = db.Column(db.Float, comment="秸秆Ca含量")
    straw_mg_content = db.Column(db.Float, comment="秸秆Mg含量")
    fertilizer_n = db.Column(db.Float, comment="施肥量以N元素计算")
    nitrogen_deposition = db.Column(db.Float, comment="N沉降")
    target_ph = db.Column(db.Float, comment="目标pH值")
    grain_n_content = db.Column(db.Float, comment="籽粒N含量")
    straw_n_content = db.Column(db.Float, comment="秸秆N含量")
    acid_deposition_input = db.Column(db.Float, comment="酸沉降产酸量")
    crop_uptake_acid = db.Column(db.Float, comment="植株吸收利用产H+量")
    nitrogen_cycle_acid = db.Column(db.Float, comment="氮循环净产酸量")
    agricultural_acid = db.Column(db.Float, comment="农业活动产酸量")
    background_soil_acid = db.Column(db.Float, comment="土壤本底酸量")
    soil_conditioner_dosage = db.Column(db.Float, comment="亿土康施加量")
    woody_peat_dosage = db.Column(db.Float, comment="木本泥炭施加量")
    model_version = db.Column(db.String(32), comment="模型版本（如 process_v2_20260801）")
    status = db.Column(db.String(16), nullable=False, server_default="ok", comment="执行状态（ok/rejected/fallback）")
    warning = db.Column(db.Text, comment="警告信息")
    reason = db.Column(db.Text, comment="拒绝原因")
    out_of_range_features = db.Column(db.JSON, comment="越界特征列表")
    simulated = db.Column(db.Boolean, nullable=False, server_default="false", comment="是否模拟数据")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("execution_id", name="uk_acidification_remediation_result_execution_id"),
        db.Index("idx_acidification_remediation_result_parcel_id", "parcel_id"),
        db.Index("idx_acidification_remediation_result_status", "status"),
    )
```

- [x] **Step 2：校验导入与 FK**

Run: `python -c "from framework.models.thematic_model import AcidificationRemediationResult as M; assert M.__tablename__=='acidification_remediation_result'; assert len([c for c in M.__table__.foreign_keys])==1; assert 'soil_conditioner_dosage' in M.__table__.columns; print('OK', M.__tablename__, len(M.__table__.columns), 'cols')"`
Expected: `OK acidification_remediation_result 37 cols`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add AcidificationRemediationResult ORM Model-4 (V3.0 §8.8, 37 cols)"
```

---

## Task 3.9：OrganicMatterResult（对应 task 3.10，Model-5，无 parcel_id）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Consumes：`ModelExecutionLog.id`（FK 目标）
- Produces：`OrganicMatterResult`（表 `organic_matter_result`，1 个 FK，15 列，**无 parcel_id**——Model-5 为县级分析）

- [x] **Step 1：追加 `OrganicMatterResult` 类**

```python
class OrganicMatterResult(db.Model):
    """有机质培肥结果表（Model-5，V3.0 §8.9，县级分析，无 parcel_id）。"""
    __tablename__ = "organic_matter_result"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    execution_id = db.Column(db.BigInteger, db.ForeignKey("model_execution_log.id", name="fk_organic_matter_result_execution_id"), nullable=False, comment="关联 model_execution_log.id")
    soil_ph = db.Column(db.Float, comment="酸碱度（土壤pH）")
    available_potassium = db.Column(db.Float, comment="土壤速效钾含量")
    organic_matter = db.Column(db.Float, comment="土壤有机质含量")
    available_phosphorus = db.Column(db.Float, comment="土壤有效磷含量")
    total_phosphorus = db.Column(db.Float, comment="土壤总磷含量")
    total_potassium = db.Column(db.Float, comment="土壤总钾含量")
    total_nitrogen = db.Column(db.Float, comment="土壤总氮含量")
    organic_fertilizer_type = db.Column(db.String(64), comment="土壤有机肥料类型")
    om_improvement_target = db.Column(db.Float, comment="土壤有机质提升值")
    organic_fertilizer_dosage = db.Column(db.Float, comment="有机肥施用量")
    level = db.Column(db.String(8), comment="有机质等级（极低/低/中/高/极高）")
    potential_increase = db.Column(db.Float, comment="预期有机质提升量（g/kg）")
    simulated = db.Column(db.Boolean, nullable=False, server_default="true", comment="是否模拟数据")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("execution_id", name="uk_organic_matter_result_execution_id"),
        db.Index("idx_organic_matter_result_level", "level"),
    )
```

- [x] **Step 2：校验导入、FK 与无 parcel_id**

Run: `python -c "from framework.models.thematic_model import OrganicMatterResult as M; assert M.__tablename__=='organic_matter_result'; assert len([c for c in M.__table__.foreign_keys])==1; assert 'parcel_id' not in M.__table__.columns; print('OK', M.__tablename__, len(M.__table__.columns), 'cols, no parcel_id')"`
Expected: `OK organic_matter_result 15 cols, no parcel_id`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add OrganicMatterResult ORM Model-5 (V3.0 §8.9, no parcel_id)"
```

---

## Task 3.10：ComprehensiveFertilityResult（对应 task 3.11，Model-6 占位）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Consumes：`ModelExecutionLog.id`（FK 目标）
- Produces：`ComprehensiveFertilityResult`（表 `comprehensive_fertility_result`，1 个 FK，9 列，占位表）

- [x] **Step 1：追加 `ComprehensiveFertilityResult` 类**

```python
class ComprehensiveFertilityResult(db.Model):
    """综合地力改良提升结果表（Model-6 占位，V3.0 §8.10；业务逻辑尚未实现）。"""
    __tablename__ = "comprehensive_fertility_result"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    execution_id = db.Column(db.BigInteger, db.ForeignKey("model_execution_log.id", name="fk_comprehensive_fertility_result_execution_id"), nullable=False, comment="关联 model_execution_log.id")
    parcel_id = db.Column(db.String(64), comment="地块唯一编号")
    fertility_score = db.Column(db.Float, comment="综合地力得分")
    fertility_level = db.Column(db.String(8), comment="综合地力等级")
    improvement_plan = db.Column(db.JSON, comment="综合改良方案（整合酸化改良+有机质培肥建议）")
    input_snapshot = db.Column(db.JSON, comment="输入参数快照")
    simulated = db.Column(db.Boolean, nullable=False, server_default="true", comment="是否模拟数据")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("execution_id", name="uk_comprehensive_fertility_result_execution_id"),
        db.Index("idx_comprehensive_fertility_result_parcel_id", "parcel_id"),
    )
```

- [x] **Step 2：校验导入与 FK**

Run: `python -c "from framework.models.thematic_model import ComprehensiveFertilityResult as M; assert M.__tablename__=='comprehensive_fertility_result'; assert len([c for c in M.__table__.foreign_keys])==1; print('OK', M.__tablename__, len(M.__table__.columns), 'cols')"`
Expected: `OK comprehensive_fertility_result 9 cols`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add ComprehensiveFertilityResult ORM Model-6 placeholder (V3.0 §8.10)"
```

---

## Task 3.11：RoutingDecisionLog（对应 task 3.12）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Produces：`RoutingDecisionLog`（表 `routing_decision_log`，无 FK，19 列）

- [x] **Step 1：追加 `RoutingDecisionLog` 类**

```python
class RoutingDecisionLog(db.Model):
    """路由决策日志表（V3.0 §8.11，无 FK）。"""
    __tablename__ = "routing_decision_log"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    trace_id = db.Column(db.String(64), nullable=False, comment="追溯ID（UUID）")
    question = db.Column(db.Text, nullable=False, comment="用户原始问题")
    question_type = db.Column(db.SmallInteger, nullable=False, comment="问题类型（0~6）")
    relevance = db.Column(db.Float, comment="相关性得分（0~1）")
    routing_status = db.Column(db.String(16), nullable=False, server_default="normal", comment="路由状态")
    router_method = db.Column(db.String(16), nullable=False, comment="路由方法（keyword/llm/knowledge/vector）")
    candidate_agents = db.Column(db.JSON, comment="候选智能体列表")
    hit_exclusive_rules = db.Column(db.JSON, comment="命中的排他规则")
    llm_reason = db.Column(db.Text, comment="LLM 路由理由")
    llm_duration_ms = db.Column(db.Float, comment="LLM 路由耗时（毫秒）")
    total_duration_ms = db.Column(db.Float, comment="路由总耗时（毫秒）")
    degradation = db.Column(db.Text, comment="降级说明")
    five_dim_context = db.Column(db.JSON, comment="五维上下文 {scale, data_type, business_task, expected_output}")
    data_version = db.Column(db.String(32), comment="数据版本")
    agent_version = db.Column(db.String(32), comment="智能体版本")
    result_version = db.Column(db.String(16), server_default="v1.2", comment="路由算法版本")
    failure_reason = db.Column(db.Text, comment="失败原因")
    logged_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="日志记录时间")

    __table_args__ = (
        db.UniqueConstraint("trace_id", name="uk_routing_decision_log_trace_id"),
        db.Index("idx_routing_decision_log_question_type", "question_type"),
        db.Index("idx_routing_decision_log_router_method", "router_method"),
        db.Index("idx_routing_decision_log_routing_status", "routing_status"),
        db.Index("idx_routing_decision_log_logged_at", "logged_at"),
    )
```

- [x] **Step 2：校验导入**

Run: `python -c "from framework.models.thematic_model import RoutingDecisionLog as M; assert M.__tablename__=='routing_decision_log'; assert len([c for c in M.__table__.foreign_keys])==0; print('OK', M.__tablename__, len(M.__table__.columns), 'cols')"`
Expected: `OK routing_decision_log 19 cols`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add RoutingDecisionLog ORM (V3.0 §8.11)"
```

---

## Task 3.12：ModelEvaluationMetrics（对应 task 3.13）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Produces：`ModelEvaluationMetrics`（表 `model_evaluation_metrics`，无 FK，13 列；被视图 `v_confusion_matrix_latest` 自连接引用）

- [x] **Step 1：追加 `ModelEvaluationMetrics` 类**

```python
class ModelEvaluationMetrics(db.Model):
    """模型评估指标表（V3.0 §8.12，无 FK）。"""
    __tablename__ = "model_evaluation_metrics"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    model_pair = db.Column(db.String(32), nullable=False, comment="易混淆模型对标识")
    positive_label = db.Column(db.String(32), nullable=False, comment="正类标签")
    tp = db.Column(db.Integer, nullable=False, server_default="0", comment="真阳性")
    fp = db.Column(db.Integer, nullable=False, server_default="0", comment="假阳性")
    fn = db.Column(db.Integer, nullable=False, server_default="0", comment="假阴性")
    tn = db.Column(db.Integer, nullable=False, server_default="0", comment="真阴性")
    total = db.Column(db.Integer, nullable=False, server_default="0", comment="样本总数")
    accuracy = db.Column(db.Float, nullable=False, server_default="0", comment="正确率")
    confusion_rate = db.Column(db.Float, nullable=False, server_default="0", comment="混淆率")
    evaluation_mode = db.Column(db.String(16), nullable=False, comment="评估模式（keyword/llm）")
    sample_count = db.Column(db.Integer, comment="评估样本数")
    evaluated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="评估时间")

    __table_args__ = (
        db.Index("idx_model_evaluation_metrics_model_pair", "model_pair"),
        db.Index("idx_model_evaluation_metrics_evaluation_mode", "evaluation_mode"),
    )
```

- [x] **Step 2：校验导入**

Run: `python -c "from framework.models.thematic_model import ModelEvaluationMetrics as M; assert M.__tablename__=='model_evaluation_metrics'; print('OK', M.__tablename__, len(M.__table__.columns), 'cols')"`
Expected: `OK model_evaluation_metrics 13 cols`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add ModelEvaluationMetrics ORM (V3.0 §8.12)"
```

---

## Task 3.13：ExclusiveRuleConfig（对应 task 3.14）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Produces：`ExclusiveRuleConfig`（表 `exclusive_rule_config`，无 FK，10 列，`id` 为 SERIAL/BigInteger）

- [x] **Step 1：追加 `ExclusiveRuleConfig` 类**

```python
class ExclusiveRuleConfig(db.Model):
    """排他规则配置表（V3.0 §8.13，无 FK）。"""
    __tablename__ = "exclusive_rule_config"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    rule_name = db.Column(db.String(64), nullable=False, comment="规则名称")
    rule_pair = db.Column(db.JSON, nullable=False, comment="易混淆模型对")
    discriminator = db.Column(db.String(128), nullable=False, comment="判别维度描述")
    condition = db.Column(db.String(64), comment="关键词条件名")
    target = db.Column(db.String(32), nullable=False, comment="目标模型ID")
    dimension_conditions = db.Column(db.JSON, comment="维度条件")
    enabled = db.Column(db.Boolean, nullable=False, server_default="true", comment="是否启用")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="更新时间")

    __table_args__ = (
        db.UniqueConstraint("rule_name", name="uk_exclusive_rule_config_rule_name"),
        db.Index("idx_exclusive_rule_config_target", "target"),
        db.Index("idx_exclusive_rule_config_enabled", "enabled"),
    )
```

- [x] **Step 2：校验导入**

Run: `python -c "from framework.models.thematic_model import ExclusiveRuleConfig as M; assert M.__tablename__=='exclusive_rule_config'; print('OK', M.__tablename__, len(M.__table__.columns), 'cols')"`
Expected: `OK exclusive_rule_config 10 cols`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add ExclusiveRuleConfig ORM (V3.0 §8.13)"
```

---

## Task 3.14：ParcelInfo（对应 task 3.15）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Produces：`ParcelInfo`（表 `parcel_info`，无 FK，12 列，`geom` GIST 索引）

- [x] **Step 1：追加 `ParcelInfo` 类**

```python
class ParcelInfo(db.Model):
    """地块信息表（V3.0 §8.14，无 FK）。"""
    __tablename__ = "parcel_info"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    parcel_id = db.Column(db.String(64), nullable=False, comment="地块唯一编号")
    geom = db.Column(Geometry("POLYGON", srid=4326), comment="地块几何（PostGIS）")
    area_code = db.Column(db.String(32), comment="区域编码")
    centroid_lon = db.Column(db.Float, comment="质心经度")
    centroid_lat = db.Column(db.Float, comment="质心纬度")
    land_type = db.Column(db.String(16), comment="土地利用类型（upland/paddy）")
    fertilizer_type = db.Column(db.String(32), comment="肥料类型")
    target_ph = db.Column(db.Float, comment="目标pH值")
    soil_indicators = db.Column(db.JSON, comment="结构化土壤指标快照（terrain_position/topsoil_thickness/soil_ph 等）")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="更新时间")

    __table_args__ = (
        db.UniqueConstraint("parcel_id", name="uk_parcel_info_parcel_id"),
        db.Index("idx_parcel_info_area_code", "area_code"),
        db.Index("idx_parcel_info_geom", "geom", postgresql_using="gist"),
    )
```

- [x] **Step 2：校验导入**

Run: `python -c "from framework.models.thematic_model import ParcelInfo as M; assert M.__tablename__=='parcel_info'; assert 'soil_indicators' in M.__table__.columns; print('OK', M.__tablename__, len(M.__table__.columns), 'cols')"`
Expected: `OK parcel_info 12 cols`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add ParcelInfo ORM with GIST (V3.0 §8.14)"
```

---

## Task 3.15：ModelVersionHistory（对应 task 3.16）

**Files:**
- Modify: `framework/models/thematic_model.py`

**Interfaces:**
- Consumes：`ThematicModelRegistry.agent_id`（FK 目标）
- Produces：`ModelVersionHistory`（表 `model_version_history`，1 个 FK，7 列；至此 15 个模型全部完成）

- [x] **Step 1：追加 `ModelVersionHistory` 类**

```python
class ModelVersionHistory(db.Model):
    """模型版本历史表（V3.0 §8.15，FK → thematic_model_registry.agent_id）。"""
    __tablename__ = "model_version_history"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    agent_id = db.Column(db.String(32), db.ForeignKey("thematic_model_registry.agent_id", name="fk_model_version_history_agent_id"), nullable=False, comment="关联 thematic_model_registry.agent_id")
    version = db.Column(db.String(16), nullable=False, comment="版本号")
    change_description = db.Column(db.Text, comment="变更描述")
    parameters = db.Column(db.JSON, comment="版本参数快照")
    status = db.Column(db.String(16), nullable=False, server_default="active", comment="状态")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.Index("idx_model_version_history_agent_id", "agent_id"),
        db.Index("idx_model_version_history_version", "version"),
    )
```

- [x] **Step 2：校验全部 15 个模型可导入 + FK 总数为 10**

Run: `python -c "import framework.models.thematic_model as m; names=['ThematicModelRegistry','ModelExecutionLog','SpatialDataLayer','ParcelGeometry','StabilityRiskResult','QualityGradeResult','ObstacleDiagnosisResult','AcidificationRemediationResult','OrganicMatterResult','ComprehensiveFertilityResult','RoutingDecisionLog','ModelEvaluationMetrics','ExclusiveRuleConfig','ParcelInfo','ModelVersionHistory']; cls=[getattr(m,n) for n in names]; assert len(cls)==15; fk=sum(len([c for c in C.__table__.foreign_keys]) for C in cls); assert fk==10, fk; print('OK 15 models, 10 FKs total')"`
Expected: `OK 15 models, 10 FKs total`

- [x] **Step 3：Commit**

```bash
git add framework/models/thematic_model.py
git commit -m "feat(thematic-model): add ModelVersionHistory ORM, complete 15 V3.0 models (V3.0 §8.15)"
```

---

## Task 4：模型注册（对应 task 4.1）

**Files:**
- Modify: `framework/models/__init__.py`

**Interfaces:**
- Consumes：Task 3.1–3.15 产出的 15 个模型类
- Produces：`framework.models` 包导入时触发 15 个模型注册，`db.create_all()` 可发现新表

- [x] **Step 1：在 `framework/models/__init__.py` 末尾追加 15 个模型导入**

在现有 `from .soil_data import (...)` 块之后追加：

```python
from .thematic_model import (
    ThematicModelRegistry,
    ModelExecutionLog,
    SpatialDataLayer,
    ParcelGeometry,
    StabilityRiskResult,
    QualityGradeResult,
    ObstacleDiagnosisResult,
    AcidificationRemediationResult,
    OrganicMatterResult,
    ComprehensiveFertilityResult,
    RoutingDecisionLog,
    ModelEvaluationMetrics,
    ExclusiveRuleConfig,
    ParcelInfo,
    ModelVersionHistory,
)
```

- [x] **Step 2：校验包导入触发注册（15 个表注册到 db.metadata）**

Run: `python -c "import framework.models; from framework.models.user import db; tables=sorted(db.metadata.tables.keys()); new=[t for t in tables if t in {'thematic_model_registry','model_execution_log','spatial_data_layer','parcel_geometry','stability_risk_result','quality_grade_result','obstacle_diagnosis_result','acidification_remediation_result','organic_matter_result','comprehensive_fertility_result','routing_decision_log','model_evaluation_metrics','exclusive_rule_config','parcel_info','model_version_history'}]; assert len(new)==15, (len(new), new); print('OK 15 new tables registered')"`
Expected: `OK 15 new tables registered`

- [x] **Step 3：Commit**

```bash
git add framework/models/__init__.py
git commit -m "feat(thematic-model): register 15 V3.0 models in framework.models.__init__"
```

---

## Task 5：Model-6 元数据升级（对应 task 5.1）

> **注意（与 tasks.md 措辞的偏差）**：tasks.md 5.1 措辞为"将 Model-6 从 `placeholder` 更新为 `comprehensive-fertility-improvement`"，假定 `capabilities.py` 已存在 Model-6 占位条目。但实际代码库中 `PROFESSIONAL_CAPABILITIES` 元组只有 model-1~model-5 五个条目，**不存在 Model-6 条目**。因此本任务**新增**一个 Model-6 `ProfessionalCapability` 条目，端态值与设计文档/openspec spec 验收场景完全一致（`model_id=comprehensive-fertility-improvement`、`name=耕地综合地力改良提升模型`、`domain=fertility`、`runtime_requirement` 标注占位、`question_type=6`）。

**Files:**
- Modify: `framework/agents/capabilities.py`（在 `PROFESSIONAL_CAPABILITIES` 元组末尾、`model-5` 条目之后追加 `model-6` 条目）

**Interfaces:**
- Produces：`CAPABILITY_BY_QUESTION_TYPE[6]`、`CAPABILITY_BY_AGENT_ID['model-6']`、`CAPABILITY_BY_MODEL_ID['comprehensive-fertility-improvement']` 可用

- [x] **Step 1：在 `PROFESSIONAL_CAPABILITIES` 元组中 `model-5` 条目之后追加 `model-6` 条目**

定位 `framework/agents/capabilities.py` 中 `model-5` 的 `ProfessionalCapability(...)` 结束的 `),`（约第 61 行），在其后追加：

```python
    ProfessionalCapability(
        "model-6", "comprehensive-fertility-improvement", "耕地综合地力改良提升模型",
        "综合耕地地力评价与改良提升（整合酸化改良与有机质培肥建议）。", "fertility", 6,
        ("parcel_id",), "占位状态：综合地力改良提升业务逻辑尚未实现，本能力暂不可执行；数据库结构（comprehensive_fertility_result 表）已就绪。",
        "地块", "评价结果",   # model-6 综合地力：地块级评价结果（占位）
    ),
```

字段对照（与现有 model-1~model-5 同顺序位置参数）：
`agent_id="model-6"`, `model_id="comprehensive-fertility-improvement"`, `name="耕地综合地力改良提升模型"`, `description="综合耕地地力评价与改良提升（整合酸化改良与有机质培肥建议）。"`, `domain="fertility"`, `question_type=6`, `minimum_inputs=("parcel_id",)`, `runtime_requirement="占位状态：..."`, `analysis_scale="地块"`, `data_type="评价结果"`。

- [x] **Step 2：校验 Model-6 元数据端态**

Run: `python -c "from framework.agents.capabilities import CAPABILITY_BY_QUESTION_TYPE as m; c=m[6]; assert c.agent_id=='model-6'; assert c.model_id=='comprehensive-fertility-improvement', c.model_id; assert c.name=='耕地综合地力改良提升模型', c.name; assert c.domain=='fertility'; assert c.question_type==6; assert '占位' in c.runtime_requirement and '尚未实现' in c.runtime_requirement, c.runtime_requirement; assert c.analysis_scale=='地块'; assert c.data_type=='评价结果'; print('OK', c.agent_id, c.model_id, c.question_type)"`
Expected: `OK model-6 comprehensive-fertility-improvement 6`

- [x] **Step 3：校验原有 model-1~model-5 未受影响**

Run: `python -c "from framework.agents.capabilities import CAPABILITY_BY_QUESTION_TYPE as m; assert set(m.keys())=={1,2,3,4,5,6}; assert m[1].agent_id=='model-1' and m[5].agent_id=='model-5'; print('OK 6 capabilities, model-1..5 unchanged')"`
Expected: `OK 6 capabilities, model-1..5 unchanged`

- [x] **Step 4：Commit**

```bash
git add framework/agents/capabilities.py
git commit -m "feat(capabilities): add Model-6 comprehensive-fertility-improvement capability (placeholder runtime)"
```

---

## Task 6：init_db.py 执行视图脚本（对应 task 6.1）

**Files:**
- Modify: `init_db.py`

**Interfaces:**
- Consumes：`scripts/v3_views.sql`（Task 2 校验就绪）、15 张新表（Task 3+4 注册后 `db.create_all()` 创建）
- Produces：`python init_db.py` 一次性创建 15 表 + 3 视图，且可重复执行（幂等）

**说明**：`init_db.py` 现有 `db.drop_all()`（第 35 行）不会删除视图，而 PostgreSQL 不允许 DROP 被视图引用的表。因此须在 `db.drop_all()` 之前先 `DROP VIEW IF EXISTS ... CASCADE`，否则第二次运行会因视图依赖而失败。

- [x] **Step 1：在 PostGIS 扩展块之后、`db.drop_all()` 之前，插入"删视图"代码**

在 `init_db.py` 的 `db.drop_all()` 行（约第 35 行）**之前**插入：

```python
    # 先删除 V3.0 视图（若存在），避免 db.drop_all() 因视图依赖表而失败
    if db_uri.startswith('postgresql'):
        db.session.execute(text(
            "DROP VIEW IF EXISTS v_model_execution_summary, "
            "v_parcel_stability_spatial, v_confusion_matrix_latest CASCADE"
        ))
        db.session.commit()
```

- [x] **Step 2：在 `db.create_all()` 之后、admin 用户创建之前，插入"执行视图脚本"代码**

在 `db.create_all()` 行（约第 36 行）**之后**、`admin = User(...)` 行（约第 38 行）**之前**插入：

```python
    # 执行 V3.0 视图脚本（依赖 15 张新表已通过 db.create_all() 创建）
    if db_uri.startswith('postgresql'):
        views_path = PROJECT_ROOT / "scripts" / "v3_views.sql"
        if views_path.exists():
            with open(views_path, encoding="utf-8") as f:
                db.session.execute(text(f.read()))
            db.session.commit()
            print("[初始化] V3.0 视图创建完成（v_model_execution_summary / v_parcel_stability_spatial / v_confusion_matrix_latest）")
        else:
            print(f"[警告] 视图脚本不存在：{views_path}", file=sys.stderr)
```

> `text` 与 `PROJECT_ROOT` 在 `init_db.py` 顶部已导入/定义（`from sqlalchemy import text`、`PROJECT_ROOT = Path(__file__).resolve().parent`），无需新增导入。

- [x] **Step 3：校验语法（不连库）**

Run: `python -c "import ast; ast.parse(open('init_db.py',encoding='utf-8').read()); print('OK init_db.py syntax')"`
Expected: `OK init_db.py syntax`

- [x] **Step 4：Commit（实际建库验证留待 Task 7）**

```bash
git add init_db.py
git commit -m "feat(init_db): execute v3_views.sql after create_all and drop views before drop_all"
```

---

## Task 7：Build 阶段集成自验证（对应 tasks 7.1–7.15）

> 本任务为 Build 阶段自验证（Comet Verify 阶段会独立复核）。前置条件：本地已就绪 PostgreSQL 16 + PostGIS 3.4 实例，且 `.env`/配置中 `SQLALCHEMY_DATABASE_URI` 指向该实例。命令中的 `<dbname>` 替换为实际数据库名（DDL 注释示例为 `agent_culti_demo`）；也可通过应用自身连接执行等价 SQL。

**Files:**
- 校验：`init_db.py`、`scripts/thematic_models_v3_ddl.sql`、`scripts/v3_views.sql`、`framework/agents/capabilities.py`、15 张新表

- [x] **Step 1（7.1）：运行 `init_db.py`，验证 `db.create_all()` 成功**

Run: `python init_db.py`
Expected: stdout 含 `[初始化] PostGIS 扩展已就绪`、`[初始化] 数据库表结构创建完成`、`[初始化] V3.0 视图创建完成（...）`、`[初始化] 管理员用户已创建: admin / admin123`，无 traceback。

- [x] **Step 2（7.2）：验证 15 张表名与 V3.0 §3 列表完全一致**

Run: `psql -d <dbname> -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('thematic_model_registry','model_execution_log','spatial_data_layer','parcel_geometry','stability_risk_result','quality_grade_result','obstacle_diagnosis_result','acidification_remediation_result','organic_matter_result','comprehensive_fertility_result','routing_decision_log','model_evaluation_metrics','exclusive_rule_config','parcel_info','model_version_history') ORDER BY tablename;"`
Expected: 返回 15 行（按字母序），与上述列表逐一对应。

- [x] **Step 3（7.3）：验证字段命名使用 V3.0 英文 snake_case，无 V2.0 拼音**

Run: `python -c "import framework.models.thematic_model as m,re; bad=['sjd','yjz','ytk','tybh','hex','alex','gdzldj','safe_abs']; cls=[getattr(m,n) for n in ['ThematicModelRegistry','ModelExecutionLog','SpatialDataLayer','ParcelGeometry','StabilityRiskResult','QualityGradeResult','ObstacleDiagnosisResult','AcidificationRemediationResult','OrganicMatterResult','ComprehensiveFertilityResult','RoutingDecisionLog','ModelEvaluationMetrics','ExclusiveRuleConfig','ParcelInfo','ModelVersionHistory']]; cols=[c.name for C in cls for c in C.__table__.columns]; hit=[c for c in cols if any(b in c.lower() for b in bad)]; assert not hit, hit; good=['soil_ph','organic_matter','available_potassium','exchangeable_hydrogen','parcel_id']; assert all(g in cols for g in good), good; print('OK no pinyin, V3.0 names present')"`
Expected: `OK no pinyin, V3.0 names present`

- [x] **Step 4（7.4）：验证 V3.0 后缀规范**

Run: `python -c "import framework.models.thematic_model as m; suf=['_membership','_weight','_obstacle_degree','_obstacle_grade','_abs','_rel','_content','_dosage']; cls=[getattr(m,n) for n in ['ObstacleDiagnosisResult','StabilityRiskResult','QualityGradeResult','AcidificationRemediationResult','OrganicMatterResult']]; cols=[c.name for C in cls for c in C.__table__.columns]; found={s:any(c.endswith(s) for c in cols) for s in suf}; assert all(found.values()), found; print('OK suffixes', found)"`
Expected: `OK suffixes {'_membership': True, '_weight': True, '_obstacle_degree': True, '_obstacle_grade': True, '_abs': True, '_rel': True, '_content': True, '_dosage': True}`

- [x] **Step 5（7.5）：验证空间几何列使用 Geometry 且 GIST 索引存在**

Run: `psql -d <dbname> -c "SELECT indexname, tablename FROM pg_indexes WHERE schemaname='public' AND indexdef LIKE '%USING gist%' ORDER BY tablename;"`
Expected: 至少包含 `idx_spatial_data_layer_extent`、`idx_parcel_geometry_geom`、`idx_stability_risk_result_geom`、`idx_quality_grade_result_geom`、`idx_parcel_info_geom`（5 个 GIST 索引）。

- [x] **Step 6（7.6）：验证 JSONB 列使用 JSON 类型**

Run: `python -c "import framework.models.thematic_model as m; from sqlalchemy import JSON; json_cols={'input_params','output_result','evidence','minimum_inputs','indicators','obstacle_degree','input_snapshot','improvement_plan','candidate_agents','hit_exclusive_rules','five_dim_context','rule_pair','dimension_conditions','soil_indicators','parameters','out_of_range_features','attribute_fields','properties'}; cls=[getattr(m,n) for n in dir(m) if isinstance(getattr(m,n,None),type) and getattr(getattr(m,n),'__table__',None) is not None]; found={c.name for C in cls for c in C.__table__.columns if isinstance(c.type,JSON)}; missing=json_cols-found; assert not missing, missing; print('OK all JSONB cols use JSON:', len(found))"`
Expected: `OK all JSONB cols use JSON: <N>`（N ≥ 18，无 missing）

- [x] **Step 7（7.7）：验证全部 10 个外键约束存在**

Run: `psql -d <dbname> -c "SELECT constraint_name, table_name, referenced_table_name FROM information_schema.referential_constraints WHERE constraint_schema='public' ORDER BY table_name;"`
Expected: 返回 10 行，约束名含 `fk_model_execution_log_agent_id`、`fk_model_execution_log_layer_id`、`fk_parcel_geometry_layer_id`、`fk_stability_risk_result_execution_id`、`fk_quality_grade_result_execution_id`、`fk_obstacle_diagnosis_result_execution_id`、`fk_acidification_remediation_result_execution_id`、`fk_organic_matter_result_execution_id`、`fk_comprehensive_fertility_result_execution_id`、`fk_model_version_history_agent_id`。

- [x] **Step 8（7.8）：验证每列 comment 与 V3.0 §8 COMMENT ON COLUMN 一致**

Run: `psql -d <dbname> -c "SELECT table_name, column_name, col_description((table_schema||'.'||table_name)::regclass, ordinal_position) AS comment FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('thematic_model_registry','parcel_geometry','organic_matter_result','comprehensive_fertility_result') ORDER BY table_name, ordinal_position;"`
Expected: 每行 `comment` 非空，且与 `scripts/thematic_models_v3_ddl.sql` 中对应 `COMMENT ON COLUMN` 文本一致（如 `parcel_geometry.parcel_id` → `地块唯一编号`、`organic_matter_result.soil_ph` → `酸碱度（土壤pH）`）。

- [x] **Step 9（7.9）：验证索引名按表前缀化、无跨表重名**

Run: `psql -d <dbname> -c "SELECT indexname, tablename FROM pg_indexes WHERE schemaname='public' AND indexname LIKE 'uk_%' OR indexname LIKE 'idx_%' ORDER BY indexname;"`
Expected: 所有 `uk_`/`idx_` 索引名均含表名片段（如 `uk_parcel_geometry_parcel_id`、`uk_parcel_info_parcel_id` 不重名）；`SELECT indexname, COUNT(*) FROM pg_indexes WHERE schemaname='public' GROUP BY indexname HAVING COUNT(*)>1;` 返回 0 行。

- [x] **Step 10（7.10）：验证 GIST 索引覆盖所有 geom/extent 列**

Run: `psql -d <dbname> -c "SELECT indexname, tablename FROM pg_indexes WHERE schemaname='public' AND indexdef LIKE '%USING gist%';"`
Expected: 同 Step 5，覆盖 `extent`（spatial_data_layer）与所有 `geom` 列（parcel_geometry、stability_risk_result、quality_grade_result、parcel_info）。

- [x] **Step 11（7.11）：验证 3 个视图创建成功**

Run: `psql -d <dbname> -c "SELECT viewname FROM pg_views WHERE schemaname='public' AND viewname IN ('v_model_execution_summary','v_parcel_stability_spatial','v_confusion_matrix_latest') ORDER BY viewname;"`
Expected: 返回 3 行，与列表一致。

- [x] **Step 12（7.12）：验证视图可查询**

Run: `psql -d <dbname> -c "SELECT * FROM v_model_execution_summary LIMIT 1; SELECT * FROM v_parcel_stability_spatial LIMIT 1; SELECT * FROM v_confusion_matrix_latest LIMIT 1;"`
Expected: 三条查询均无错误返回（空结果集也可，只要不报 "relation does not exist"）。

- [x] **Step 13（7.13）：验证 Model-6 元数据升级**

Run: `python -c "from framework.agents.capabilities import CAPABILITY_BY_QUESTION_TYPE as m; c=m[6]; assert c.model_id=='comprehensive-fertility-improvement'; assert c.name=='耕地综合地力改良提升模型'; assert c.domain=='fertility'; assert '占位' in c.runtime_requirement and '尚未实现' in c.runtime_requirement; assert c.question_type==6; print('OK Model-6 metadata', c.model_id, c.domain, c.question_type)"`
Expected: `OK Model-6 metadata comprehensive-fertility-improvement fertility 6`

- [x] **Step 14（7.14）：验证旧 8 张土壤数据表未被修改，`db.create_all()` 同时创建旧表与新表**

Run: `psql -d <dbname> -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('third_survey_topsoils','third_survey_profiles','third_survey_site_conditions','third_survey_bulk_densities','second_survey_points','formula_fertilizations','agri_chemicalizations','grain_yields') ORDER BY tablename;"`
Expected: 返回 8 行（旧表全部存在，结构未变）。
补充校验旧表列未变：`python -c "import framework.models.soil_data as s; assert [c.name for c in s.ThirdSurveyTopsoil.__table__.columns][:3]==['id','sample_id','lon']; print('OK old soil tables unchanged')"`
Expected: `OK old soil tables unchanged`

- [x] **Step 15（7.15）：验证 DDL 脚本可独立 source 执行创建完整 V3.0 schema**

> 此步需在**全新空数据库**上执行（避免与 ORM 已建表冲突），或在 ORM 建表后用 `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` 重置后执行。

Run: `psql -d <fresh_dbname> -f scripts/thematic_models_v3_ddl.sql`
Expected: 无错误退出；随后 `psql -d <fresh_dbname> -c "SELECT count(*) FROM pg_tables WHERE schemaname='public';"` 返回 15；`psql -d <fresh_dbname> -c "SELECT count(*) FROM pg_views WHERE schemaname='public' AND viewname LIKE 'v_%';"` 返回 3；`psql -d <fresh_dbname> -c "SELECT count(*) FROM information_schema.referential_constraints WHERE constraint_schema='public';"` 返回 10。

- [x] **Step 16：Commit（验证无代码变更，跳过；如有验证脚本产出则不纳入）**

---

## 回滚策略

如需完全回滚（设计文档 Migration Plan 第 9 条）：
1. 删除 `framework/models/thematic_model.py`
2. 还原 `framework/models/__init__.py`（移除 15 个 thematic_model 导入）
3. 还原 `framework/agents/capabilities.py`（移除 model-6 条目）
4. 还原 `init_db.py`（移除删视图 + 执行视图脚本两段）
5. 删除 `scripts/thematic_models_v3_ddl.sql` 与 `scripts/v3_views.sql`
6. 移除 `pyproject.toml` 中 `geoalchemy2>=0.14.0` 依赖（如其他变更未依赖）

新表为新增，不影响旧 8 张土壤数据表；回滚后 `db.create_all()` 仅创建旧表。
