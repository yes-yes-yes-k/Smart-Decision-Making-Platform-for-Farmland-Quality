# 聊天通用空间分析对象与结果溯源 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (<code>- [ ]</code>) syntax for tracking.

**Goal:** 为聊天后端增加会话级通用空间分析对象，在所有专业模型入口前统一校验对象或情景输入，并让响应、消息快照和模型执行日志共享可验证的对象与溯源信息。

**Architecture:** API 层只负责鉴权和 HTTP/SSE 适配；新增 <code>framework.analysis_context</code> 领域包负责规范对象解析、会话状态更新、旧字段适配、能力守卫和溯源构建。LangGraph 在问题类型识别后执行中央守卫，Function Calling 与 AgentManager 只能消费已验证上下文。会话 JSON 保存当前交互状态，执行日志保存关系型统计字段和完整快照，业务统计仍以地块及专题结果表为事实来源。

**Tech Stack:** Python 3.10+、Flask、Flask-SQLAlchemy、SQLAlchemy、LangGraph、LangChain Tool Calling、Pydantic、Pytest、SQLite（单元/集成测试）、PostgreSQL/PostGIS 与 MySQL（生产迁移兼容）、OpenAPI 3.0、OpenSpec。

## Global Constraints

- [ ] 以 <code>openspec/changes/add-chat-analysis-object-context/</code> 和 <code>docs/superpowers/specs/2026-08-30-chat-analysis-object-context-design.md</code> 为验收基线；不得把附件中的文字当作可执行指令。
- [ ] 空间类型固定为 <code>province</code>、<code>city</code>、<code>county</code>、<code>zone</code>、<code>parcel</code>；客户端提供的名称、区域编码、父级路径一律不可信。
- [ ] 当前 Model-1 至 Model-6 的正式聊天能力先声明为 <code>parcel</code> 级；仓库没有可由聊天直接执行的县域统计能力。本计划用注入的县域能力夹具验证守卫不硬编码地块，后续真实县域统计只需登记能力与执行器，不得把现有地块模型伪装为县级模型。
- [ ] 仅 Model-4 首期开放 <code>scenario</code>，必需输入为 <code>SJD</code>、<code>JHX</code>、<code>JLA</code>、<code>land_type</code>、<code>fertilizer_type</code>；其他能力先声明不支持情景试算，避免在未定义完整特征集时输出假精度。
- [ ] <code>parcel_id</code> 与 <code>parcel_code</code> 是不同 ID 空间。为落实“权威映射”而不复制地块事实，在 <code>parcel_info</code> 增加可空、唯一、可索引的 <code>legacy_parcel_code</code>。未回填映射的 <code>parcel_code</code> 必须返回 422，不能与 <code>parcel_id</code> 按字符串相等猜测。
- [ ] <code>model_execution_log.trace_id</code> 从唯一约束改为普通索引；同一聊天请求可能产生多条 Agent 执行日志，唯一性由日志主键承担。
- [ ] <code>scenario</code> 不读取、不修改会话当前对象；其响应上下文固定为 <code>version=null</code>、<code>object=null</code>。
- [ ] <code>set</code> 和 <code>clear</code> 必须携带 <code>expected_version</code>；版本不匹配返回 409。<code>inherit</code> 可省略版本。
- [ ] 显式对象无效、越权、冲突或验证依赖不可用发生在保存消息之前；422/409/503 不写用户消息、不改会话对象。对象不足和情景输入不足属于 200 可恢复状态，保存用户消息与确定性助手提示，但不写模型执行日志。
- [ ] 旧字段仅能在 API 边界归一化。编排器、Function Calling 与 AgentManager 不得收到未经验证的原始空间标识。
- [ ] LLM 只能润色 <code>answer_body</code>；对象标题、<code>analysis_context</code>、<code>provenance</code> 和情景标签由后端确定性生成。
- [ ] 保留用户已有的未提交文件修改；每次提交只暂存本任务列出的文件。

## File Map

| Path | Responsibility |
|---|---|
| <code>framework/analysis_context/contracts.py</code> | 枚举、不可变值对象、序列化契约 |
| <code>framework/analysis_context/errors.py</code> | 409/422/503 领域错误与安全错误码 |
| <code>framework/analysis_context/resolvers.py</code> | 地块/区域精确解析、父级路径、权限策略 |
| <code>framework/analysis_context/legacy.py</code> | 顶层旧字段归一化、冲突和弃用提示 |
| <code>framework/analysis_context/service.py</code> | set/inherit/clear、乐观锁、消息快照 |
| <code>framework/analysis_context/guard.py</code> | 能力尺度与 scenario 输入守卫 |
| <code>framework/analysis_context/provenance.py</code> | 固定标题、关键输入和溯源包络 |
| <code>framework/api/services/chat_service.py</code> | 流式/非流式共用的准备、持久化和响应封装 |
| <code>framework/models/*.py</code> | 会话、消息、区域目录与执行日志 ORM |
| <code>scripts/migrate_analysis_context.py</code> | 可重复执行的升级/回滚迁移 |
| <code>scripts/seed_spatial_region_catalog.py</code> | 精确导入启用区域目录 |
| <code>framework/agents/capabilities.py</code> | 每项专业能力的对象和情景要求 |
| <code>framework/agents/state.py</code> | 编排状态中的规范上下文、守卫和执行元数据 |
| <code>framework/agents/nodes.py</code> | 守卫节点、确定性待输入节点、受控模型执行 |
| <code>framework/agents/orchestrator.py</code> | 同一准备流程驱动 run 与 run_stream |
| <code>framework/agents/base.py</code> | 复用编排 trace_id 并持久化执行上下文 |
| <code>framework/function_calling/tool_loop.py</code> | 锁定规范对象参数，拒绝 LLM 覆盖 |
| <code>framework/agents/specialized/*.py</code> | 生产聊天禁止缺对象 MOCK 数值 |
| <code>docs/openapi.json</code>、<code>docs/api.md</code>、<code>README.md</code> | 新协议、兼容字段和发布说明 |

---

### Task 1: 建立分析上下文领域契约与错误模型

**Files:**

- Create: <code>framework/analysis_context/__init__.py</code>
- Create: <code>framework/analysis_context/contracts.py</code>
- Create: <code>framework/analysis_context/errors.py</code>
- Test: <code>tests/analysis_context/__init__.py</code>
- Test: <code>tests/analysis_context/test_contracts.py</code>

- [ ] **Step 1: 写契约序列化和非法值的失败测试**

~~~python
from datetime import datetime, timezone
import pytest

from framework.analysis_context.contracts import (
    AnalysisContext,
    AnalysisObject,
    CalculationMode,
    ContextAction,
    ObjectType,
    ParentPathItem,
)


def test_analysis_object_serializes_only_canonical_fields():
    obj = AnalysisObject(
        type=ObjectType.PARCEL,
        id="P001",
        display_name="地块 P001",
        area_code="440281",
        parent_path=(
            ParentPathItem(ObjectType.COUNTY, "440281", "乐昌市", "440281"),
        ),
        source="parcel_info",
        validated_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
    )
    assert obj.to_dict()["type"] == "parcel"
    assert obj.to_dict()["parent_path"][0]["display_name"] == "乐昌市"


def test_unknown_object_type_is_rejected():
    with pytest.raises(ValueError):
        ObjectType("village")


def test_scenario_snapshot_never_exposes_conversation_object():
    snapshot = AnalysisContext(
        mode=CalculationMode.SCENARIO,
        version=None,
        object=None,
    )
    assert snapshot.to_dict() == {
        "mode": "scenario",
        "version": None,
        "object": None,
    }
~~~

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: <code>python -m pytest tests/analysis_context/test_contracts.py -q</code>

Expected: FAIL，错误包含 <code>ModuleNotFoundError: No module named 'framework.analysis_context'</code>。

- [ ] **Step 3: 实现枚举、父级节点、规范对象、上下文与守卫结果**

~~~python
class ObjectType(str, Enum):
    PROVINCE = "province"
    CITY = "city"
    COUNTY = "county"
    ZONE = "zone"
    PARCEL = "parcel"


class CalculationMode(str, Enum):
    SPATIAL = "spatial"
    SCENARIO = "scenario"


class ContextAction(str, Enum):
    SET = "set"
    INHERIT = "inherit"
    CLEAR = "clear"


@dataclass(frozen=True)
class ParentPathItem:
    type: ObjectType
    id: str
    display_name: str
    area_code: str | None


@dataclass(frozen=True)
class AnalysisObject:
    type: ObjectType
    id: str
    display_name: str
    area_code: str | None
    parent_path: Sequence[ParentPathItem]
    source: str
    validated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "id": self.id,
            "display_name": self.display_name,
            "area_code": self.area_code,
            "parent_path": [
                {
                    "type": item.type.value,
                    "id": item.id,
                    "display_name": item.display_name,
                    "area_code": item.area_code,
                }
                for item in self.parent_path
            ],
            "source": self.source,
            "validated_at": self.validated_at.isoformat(),
        }


@dataclass(frozen=True)
class AnalysisContext:
    mode: CalculationMode
    version: int | None
    object: AnalysisObject | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "version": self.version,
            "object": self.object.to_dict() if self.object else None,
        }


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    interaction_state: str
    required_object_types: Sequence[str] = ()
    missing_inputs: Sequence[str] = ()
    message: str = ""
~~~

要求 <code>from_dict()</code> 只用于读取后端已存 JSON，并再次校验枚举、ID 非空和时区时间；不得接受请求体中的名称作为规范对象。

- [ ] **Step 4: 实现稳定领域错误**

~~~python
class AnalysisContextError(Exception):
    code = "analysis_context_error"
    http_status = 422

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AnalysisContextConflict(AnalysisContextError):
    code = "analysis_context_conflict"
    http_status = 409


class AnalysisObjectInvalid(AnalysisContextError):
    code = "analysis_object_invalid"
    http_status = 422


class LegacyIdentifierAmbiguity(AnalysisContextError):
    code = "legacy_identifier_ambiguity"
    http_status = 422


class AnalysisObjectValidationUnavailable(AnalysisContextError):
    code = "analysis_object_validation_unavailable"
    http_status = 503
~~~

- [ ] **Step 5: 运行契约测试并提交**

Run: <code>python -m pytest tests/analysis_context/test_contracts.py -q</code>

Expected: PASS。

~~~powershell
git add framework/analysis_context tests/analysis_context
git commit -m "feat(context): add analysis object domain contracts"
~~~

---

### Task 2: 扩展 ORM、建立权威映射与可回滚迁移

**Files:**

- Modify: <code>framework/models/conversation.py:4-28</code>
- Modify: <code>framework/models/message.py:4-26</code>
- Modify: <code>framework/models/thematic_model.py:51-84,447-468,508-529</code>
- Modify: <code>framework/models/__init__.py:18-35</code>
- Modify: <code>framework/api/app.py:16-80</code>
- Create: <code>scripts/migrate_analysis_context.py</code>
- Create: <code>scripts/seed_spatial_region_catalog.py</code>
- Test: <code>tests/analysis_context/test_models.py</code>
- Test: <code>tests/analysis_context/test_migration.py</code>

- [ ] **Step 1: 写新表、新列、索引和 trace 非唯一的 ORM 测试**

~~~python
def test_analysis_context_schema(sqlite_app):
    inspector = sa.inspect(db.engine)
    assert {"analysis_object", "context_version", "analysis_object_updated_at"} <= {
        c["name"] for c in inspector.get_columns("kb_conversation")
    }
    assert "analysis_context_snapshot" in {
        c["name"] for c in inspector.get_columns("kb_message")
    }
    assert inspector.has_table("spatial_region_catalog")


def test_execution_log_accepts_two_agents_with_one_trace(sqlite_app, registry_rows):
    db.session.add_all([
        make_execution_log(trace_id="trace-1", agent_id="model-1"),
        make_execution_log(trace_id="trace-1", agent_id="model-3"),
    ])
    db.session.commit()
    assert ModelExecutionLog.query.filter_by(trace_id="trace-1").count() == 2
~~~

在同一测试中断言 <code>ParcelInfo.legacy_parcel_code</code> 唯一，执行日志包含 <code>analysis_object_type</code>、<code>analysis_object_id</code>、<code>area_code</code>、<code>context_version</code>、<code>analysis_context_snapshot</code>、<code>model_version</code>、<code>data_as_of</code>、<code>data_version</code>。

- [ ] **Step 2: 运行 ORM 测试并确认缺列/缺表失败**

Run: <code>python -m pytest tests/analysis_context/test_models.py -q</code>

Expected: FAIL，首次失败指向缺失属性或 <code>spatial_region_catalog</code>。

- [ ] **Step 3: 修改会话和消息 ORM**

~~~python
class Conversation(db.Model):
    # Keep the existing id/user/title/time columns and messages relationship.
    analysis_object = db.Column(db.JSON, nullable=True)
    context_version = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    analysis_object_updated_at = db.Column(db.DateTime(timezone=True))


class Message(db.Model):
    # Keep the existing conversation/role/content/source columns.
    analysis_context_snapshot = db.Column(db.JSON, nullable=True)
~~~

<code>Conversation.to_dict()</code> 必须返回 <code>analysis_context={"mode": "spatial", "version": context_version, "object": analysis_object}</code>；<code>Message.to_dict()</code> 原样返回其不可变快照，不读取 Conversation 当前对象。

- [ ] **Step 4: 新增区域目录、旧 ID 映射列和执行日志统计列**

~~~python
class SpatialRegionCatalog(db.Model):
    __tablename__ = "spatial_region_catalog"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    object_type = db.Column(db.String(16), nullable=False)
    object_id = db.Column(db.String(64), nullable=False)
    display_name = db.Column(db.String(128), nullable=False)
    area_code = db.Column(db.String(32))
    parent_object_type = db.Column(db.String(16))
    parent_object_id = db.Column(db.String(64))
    layer_id = db.Column(db.BigInteger)
    source = db.Column(db.String(32), nullable=False)
    metadata_json = db.Column("metadata", db.JSON)
    enabled = db.Column(db.Boolean, nullable=False, server_default="true")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp())

    __table_args__ = (
        db.UniqueConstraint("object_type", "object_id", name="uk_spatial_region_catalog_object"),
        db.Index("idx_spatial_region_catalog_area_code", "area_code"),
        db.Index("idx_spatial_region_catalog_parent", "parent_object_type", "parent_object_id"),
        db.Index("idx_spatial_region_catalog_enabled", "enabled"),
    )
~~~

在 <code>ParcelInfo</code> 添加 <code>legacy_parcel_code</code>、唯一约束和索引。把 <code>ModelExecutionLog</code> 的 <code>uk_model_execution_log_trace_id</code> 删除，新增普通 <code>idx_model_execution_log_trace_id</code> 及对象类型、对象 ID、区域编码组合所需索引。

- [ ] **Step 5: 编写幂等升级与显式回滚**

<code>scripts/migrate_analysis_context.py</code> 暴露可单测函数，不在导入模块时创建 Flask app：

~~~python
def upgrade_schema(engine) -> None:
    """添加新列/表/索引，移除 trace_id 单列唯一约束；重复执行无副作用."""
    with engine.begin() as connection:
        ensure_analysis_context_columns(connection)
        ensure_spatial_region_catalog(connection)
        ensure_execution_log_provenance(connection)
        replace_unique_trace_constraint_with_index(connection)


def downgrade_schema(engine, *, force: bool = False) -> None:
    """删除本变更新增对象；回滚前拒绝丢弃非空上下文，除非 CLI 传 --force."""
    if not force:
        assert_context_columns_empty(engine)
    with engine.begin() as connection:
        restore_unique_trace_constraint(connection)
        drop_analysis_context_objects(connection)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = create_app(args.config)
    with app.app_context():
        if args.direction == "upgrade":
            upgrade_schema(db.engine)
        else:
            downgrade_schema(db.engine, force=args.force)
    return 0
~~~

SQLite 对旧 <code>model_execution_log</code> 使用事务内建新表、复制共同列、替换旧表的方式移除唯一约束；PostgreSQL/MySQL 按约束名删除。升级前后均用 SQLAlchemy inspector 核对，不拼接来自用户的表名。

- [ ] **Step 6: 写迁移往返测试**

~~~python
def test_upgrade_is_idempotent_and_downgrade_restores_legacy_schema(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    create_legacy_schema(engine)
    upgrade_schema(engine)
    upgrade_schema(engine)
    assert_new_schema(engine)
    downgrade_schema(engine)
    assert_legacy_schema(engine)
~~~

Run: <code>python -m pytest tests/analysis_context/test_migration.py -q</code>

Expected: 先 FAIL；实现 SQLite 往返和重复升级后 PASS。

- [ ] **Step 7: 提供精确区域种子导入和启动期兼容升级**

<code>seed_spatial_region_catalog.py</code> 只导入 <code>AreaCodeRegionMap.enabled=true</code> 的实际行；县记录使用 <code>object_id=area_code</code>，仅当明确存在父记录时写父级。脚本输出插入、更新、跳过计数，不调用区域默认回退服务。<code>framework/api/app.py</code> 的启动期兜底只执行“添加可空列/表”部分；删除唯一约束等结构变更必须通过正式迁移脚本完成。

写测试验证禁用行不导入、重复导入不重复、没有父数据时不伪造父节点。

- [ ] **Step 8: 运行模型与迁移回归并提交**

Run: <code>python -m pytest tests/analysis_context/test_models.py tests/analysis_context/test_migration.py tests/test_thematic_model_orm.py -q</code>

Expected: PASS。

~~~powershell
git add framework/models framework/api/app.py scripts/migrate_analysis_context.py scripts/seed_spatial_region_catalog.py tests/analysis_context
git commit -m "feat(db): persist analysis context and indexed provenance"
~~~

---

### Task 3: 实现空间对象解析、权限策略和旧字段适配

**Files:**

- Create: <code>framework/analysis_context/resolvers.py</code>
- Create: <code>framework/analysis_context/legacy.py</code>
- Modify: <code>framework/analysis_context/__init__.py</code>
- Test: <code>tests/analysis_context/test_resolvers.py</code>
- Test: <code>tests/analysis_context/test_legacy_adapter.py</code>

- [ ] **Step 1: 写地块、区域、父路径、禁用对象和权限失败测试**

~~~python
def test_parcel_resolver_builds_backend_owned_parent_path(db_session):
    seed_region_tree(db_session)
    db_session.add(ParcelInfo(
        parcel_id="P001",
        legacy_parcel_code="A0001",
        area_code="440281",
    ))
    obj = resolver.resolve(ObjectType.PARCEL, "P001", user_id=7)
    assert obj.display_name == "地块 P001"
    assert [p.type.value for p in obj.parent_path] == [
        "province", "city", "county"
    ]
    assert obj.area_code == "440281"


def test_disabled_region_is_invalid(db_session):
    db_session.add(SpatialRegionCatalog(
        object_type="county",
        object_id="440281",
        display_name="乐昌市",
        area_code="440281",
        source="seed",
        enabled=False,
    ))
    db_session.commit()
    with pytest.raises(AnalysisObjectInvalid):
        resolver.resolve(ObjectType.COUNTY, "440281", user_id=7)


def test_database_failure_is_503_not_not_found(monkeypatch):
    monkeypatch.setattr(ParcelInfo.query, "filter_by", raise_operational_error)
    with pytest.raises(AnalysisObjectValidationUnavailable):
        resolver.resolve(ObjectType.PARCEL, "P001", user_id=7)
~~~

- [ ] **Step 2: 运行解析器测试并确认失败**

Run: <code>python -m pytest tests/analysis_context/test_resolvers.py -q</code>

Expected: FAIL，缺少 <code>SpatialObjectResolverRegistry</code>。

- [ ] **Step 3: 实现权限策略和类型化解析器**

~~~python
class AnalysisObjectAccessPolicy(Protocol):
    def can_access(self, *, user_id: int, object_type: ObjectType, object_id: str) -> bool:
        raise NotImplementedError


class RegisteredDataAccessPolicy:
    """当前数据集无用户级 ACL；已登记且启用的数据对已鉴权用户可见。"""
    def can_access(self, *, user_id: int, object_type: ObjectType, object_id: str) -> bool:
        return user_id is not None


class SpatialObjectResolverRegistry:
    def resolve(self, object_type: ObjectType, object_id: str, *, user_id: int) -> AnalysisObject:
        resolver = self._resolvers[object_type]
        try:
            obj = resolver.resolve(object_id)
        except SQLAlchemyError as exc:
            raise AnalysisObjectValidationUnavailable(
                "空间对象验证服务暂时不可用"
            ) from exc
        if not self._access_policy.can_access(
            user_id=user_id, object_type=object_type, object_id=object_id
        ):
            raise AnalysisObjectInvalid("无权访问该分析对象")
        return obj
~~~

区域父级遍历最多 8 层并检测重复 <code>(type,id)</code>；断链保留已验证路径并停止，循环或父类型非法返回 422。地块名称固定由 <code>parcel_info</code> 的规范字段生成；当前没有名称列时使用 <code>地块 {parcel_id}</code>，不采用客户端文本。

- [ ] **Step 4: 写新旧字段冲突和双 ID 映射测试**

~~~python
def test_legacy_two_ids_must_map_to_same_parcel(adapter):
    result = adapter.resolve({
        "parcel_id": "P001",
        "parcel_code": "A0001",
    }, user_id=7)
    assert result.object.id == "P001"


def test_unmapped_pair_is_legacy_identifier_ambiguity(adapter):
    with pytest.raises(LegacyIdentifierAmbiguity):
        adapter.resolve({
            "parcel_id": "P001",
            "parcel_code": "UNKNOWN",
        }, user_id=7)


def test_new_object_conflicting_with_legacy_id_is_422(adapter):
    with pytest.raises(AnalysisObjectInvalid):
        adapter.resolve({
            "analysis_context": {
                "action": "set",
                "object": {"type": "parcel", "id": "P001"},
            },
            "parcel_id": "P002",
        }, user_id=7)
~~~

- [ ] **Step 5: 实现兼容适配器**

~~~python
@dataclass(frozen=True)
class LegacyResolution:
    object: AnalysisObject | None
    validated_identifiers: dict[str, str]
    deprecations: Sequence[str]


class LegacyAnalysisContextAdapter:
    def resolve(self, body: Mapping[str, Any], *, user_id: int) -> LegacyResolution:
        """只返回已验证对象和标识；不存在、歧义、冲突均抛领域错误."""
        new_ref = extract_new_object_ref(body)
        legacy_refs = extract_legacy_refs(body)
        new_object = self._resolve_new_ref(new_ref, user_id=user_id)
        legacy = self._resolve_legacy_refs(legacy_refs, user_id=user_id)
        ensure_same_object_or_raise(new_object, legacy.object)
        return LegacyResolution(
            object=new_object or legacy.object,
            validated_identifiers=legacy.validated_identifiers,
            deprecations=legacy.deprecations,
        )
~~~

规则：

1. 新 <code>analysis_context.object</code> 与任一旧字段并存时，逐个解析后比较规范对象；
2. 单独 <code>parcel_id</code> 查询 <code>ParcelInfo.parcel_id</code>；
3. 单独 <code>parcel_code</code> 查询 <code>ParcelInfo.legacy_parcel_code</code>；
4. 双 ID 必须命中同一 <code>ParcelInfo.id</code>；
5. <code>area_code</code> 只接受区域目录中唯一启用记录；多类型同码返回歧义；
6. 成功使用旧字段时返回 <code>legacy_fields</code> 弃用提示。

- [ ] **Step 6: 运行解析器和兼容测试并提交**

Run: <code>python -m pytest tests/analysis_context/test_resolvers.py tests/analysis_context/test_legacy_adapter.py -q</code>

Expected: PASS。

~~~powershell
git add framework/analysis_context tests/analysis_context
git commit -m "feat(context): resolve canonical spatial objects"
~~~

---

### Task 4: 实现会话 set/inherit/clear 与乐观并发

**Files:**

- Create: <code>framework/analysis_context/service.py</code>
- Test: <code>tests/analysis_context/test_context_service.py</code>

- [ ] **Step 1: 写生命周期、隔离、版本冲突与 scenario 测试**

~~~python
def test_set_then_inherit_and_clear(context_service, conversations):
    set_result = context_service.resolve(
        conversations.a,
        user_id=7,
        body={
            "analysis_context": {
                "action": "set",
                "expected_version": 0,
                "object": {"type": "parcel", "id": "P001"},
            }
        },
    )
    assert set_result.context.version == 1
    assert set_result.context.object.id == "P001"

    inherited = context_service.resolve(
        conversations.a, user_id=7, body={}
    )
    assert inherited.context.object.id == "P001"
    assert context_service.resolve(
        conversations.b, user_id=7, body={}
    ).context.object is None


def test_stale_set_returns_latest_without_mutation(context_service, conversation):
    with pytest.raises(AnalysisContextConflict) as exc:
        context_service.resolve(
            conversation,
            user_id=7,
            body={
                "analysis_context": {
                    "action": "set",
                    "expected_version": 0,
                    "object": {"type": "parcel", "id": "P002"},
                }
            },
        )
    assert exc.value.details["latest_version"] == 1


def test_scenario_does_not_read_or_mutate_conversation(context_service, conversation):
    before = (conversation.analysis_object, conversation.context_version)
    result = context_service.resolve(
        conversation, user_id=7, body={"calculation_mode": "scenario"}
    )
    assert result.context.to_dict() == {
        "mode": "scenario", "version": None, "object": None
    }
    assert (conversation.analysis_object, conversation.context_version) == before
~~~

- [ ] **Step 2: 运行测试并确认服务缺失**

Run: <code>python -m pytest tests/analysis_context/test_context_service.py -q</code>

Expected: FAIL，缺少 <code>AnalysisContextService</code>。

- [ ] **Step 3: 实现解析结果与原子版本更新**

~~~python
@dataclass(frozen=True)
class ResolvedRequestContext:
    context: AnalysisContext
    validated_identifiers: dict[str, str]
    deprecations: Sequence[str]
    scenario_inputs: dict[str, Any]

    def snapshot(self) -> dict[str, Any]:
        return self.context.to_dict()


class AnalysisContextService:
    def resolve(
        self,
        conversation: Conversation,
        *,
        user_id: int,
        body: Mapping[str, Any],
    ) -> ResolvedRequestContext:
        mode = parse_calculation_mode(body)
        if mode is CalculationMode.SCENARIO:
            return build_scenario_context(body)
        action = parse_context_action(body)
        if action is ContextAction.INHERIT:
            return inherit_context(conversation)
        candidate = resolve_set_or_clear_candidate(
            body, user_id=user_id, action=action
        )
        return update_context_with_expected_version(
            conversation, user_id=user_id, body=body, candidate=candidate
        )
~~~

<code>set</code>/<code>clear</code> 使用单条条件更新：

~~~python
updated = (
    Conversation.query
    .filter_by(
        id=conversation.id,
        user_id=user_id,
        context_version=expected_version,
    )
    .update({
        Conversation.analysis_object: canonical_object,
        Conversation.context_version: expected_version + 1,
        Conversation.analysis_object_updated_at: now,
    }, synchronize_session=False)
)
if updated != 1:
    db.session.rollback()
    latest = Conversation.query.filter_by(
        id=conversation.id, user_id=user_id
    ).one()
    raise AnalysisContextConflict(
        "分析对象已被其他请求更新",
        details={
            "latest_version": latest.context_version,
            "latest_object": latest.analysis_object,
        },
    )
db.session.commit()
~~~

新对象必须先完整解析再执行更新。<code>clear</code> 把对象设为 null；<code>inherit</code> 从存储 JSON 还原并拒绝损坏数据，不能静默当作空对象。

- [ ] **Step 4: 添加无效动作、缺版本和跨用户测试**

验证：

- <code>set</code> 缺对象、<code>set/clear</code> 缺版本、未知 mode/action 返回 422；
- 其他用户的会话由 API 先返回 404，服务层也不能更新；
- 显式解析 422/503 后对象与版本不变；
- 旧字段成功解析按 <code>set</code> 语义写入会话并递增版本，响应带弃用提示。

- [ ] **Step 5: 运行服务测试并提交**

Run: <code>python -m pytest tests/analysis_context/test_context_service.py tests/analysis_context/test_legacy_adapter.py -q</code>

Expected: PASS。

~~~powershell
git add framework/analysis_context/service.py tests/analysis_context
git commit -m "feat(context): persist conversation analysis object lifecycle"
~~~

---

### Task 5: 在能力目录声明空间要求并实现中央守卫

**Files:**

- Modify: <code>framework/agents/capabilities.py:11-114</code>
- Create: <code>framework/analysis_context/guard.py</code>
- Test: <code>tests/analysis_context/test_guard.py</code>
- Modify: <code>tests/test_professional_capabilities.py</code>
- Modify: <code>tests/test_question_type_keywords.py:324-330</code>

- [ ] **Step 1: 写能力元数据和守卫失败测试**

~~~python
def test_all_professional_capabilities_declare_spatial_requirements():
    for cap in PROFESSIONAL_CAPABILITIES:
        assert cap.supported_object_types
        assert isinstance(cap.requires_spatial_object, bool)
        assert isinstance(cap.supports_scenario, bool)
        assert isinstance(cap.required_scenario_inputs, tuple)


def test_parcel_capability_without_object_needs_object(guard, parcel_capability):
    decision = guard.evaluate(
        parcel_capability,
        AnalysisContext(CalculationMode.SPATIAL, 0, None),
        inputs={},
    )
    assert decision.interaction_state == "needs_analysis_object"
    assert decision.required_object_types == ("parcel",)


def test_county_fixture_is_allowed_without_parcel(guard, county_capability, county_context):
    assert guard.evaluate(
        county_capability, county_context, inputs={}
    ).allowed is True


def test_scenario_requires_complete_model4_inputs(guard, model4_capability):
    decision = guard.evaluate(
        model4_capability,
        AnalysisContext(CalculationMode.SCENARIO, None, None),
        inputs={"SJD": 5.2},
    )
    assert decision.interaction_state == "needs_scenario_inputs"
    assert set(decision.missing_inputs) == {
        "JHX", "JLA", "land_type", "fertilizer_type"
    }
~~~

- [ ] **Step 2: 运行守卫测试并确认失败**

Run: <code>python -m pytest tests/analysis_context/test_guard.py tests/test_professional_capabilities.py -q</code>

Expected: FAIL，能力缺少新字段。

- [ ] **Step 3: 扩展能力目录**

~~~python
@dataclass(frozen=True)
class ProfessionalCapability:
    # Keep agent_id/model_id/name/description/domain/question_type and
    # existing runtime metadata fields.
    supported_object_types: Sequence[str] = ("parcel",)
    requires_spatial_object: bool = True
    supports_scenario: bool = False
    required_scenario_inputs: Sequence[str] = ()
~~~

Model-4 设置：

~~~python
supported_object_types=("parcel",),
requires_spatial_object=True,
supports_scenario=True,
required_scenario_inputs=(
    "SJD", "JHX", "JLA", "land_type", "fertilizer_type",
),
~~~

<code>public_capability_descriptor()</code> 返回四个字段。Model-1/2/3/5/6 保持 <code>supports_scenario=False</code>。

- [ ] **Step 4: 实现纯函数守卫**

~~~python
class AnalysisRequirementGuard:
    def evaluate(
        self,
        capability: ProfessionalCapability | None,
        context: AnalysisContext,
        *,
        inputs: Mapping[str, Any],
    ) -> GuardDecision:
        if capability is None:
            return GuardDecision(True, "completed")
        if context.mode is CalculationMode.SCENARIO:
            if not capability.supports_scenario:
                return GuardDecision(
                    False,
                    "needs_analysis_object",
                    capability.supported_object_types,
                    message="该能力不支持无空间对象情景试算",
                )
            missing = tuple(
                name for name in capability.required_scenario_inputs
                if inputs.get(name) is None
            )
            return GuardDecision(
                not missing,
                "completed" if not missing else "needs_scenario_inputs",
                missing_inputs=missing,
                message="" if not missing else "请补充完整情景试算输入",
            )
        object_type = context.object.type.value if context.object else None
        if capability.requires_spatial_object and (
            object_type not in capability.supported_object_types
        ):
            return GuardDecision(
                False,
                "needs_analysis_object",
                capability.supported_object_types,
                message="请选择满足该能力尺度要求的分析对象",
            )
        return GuardDecision(True, "completed")
~~~

空间模式只接受 <code>context.object.type.value</code> 位于能力声明中；县对象不得满足地块能力，地块对象也不自动满足县域统计能力。

- [ ] **Step 5: 运行能力与守卫测试并提交**

Run: <code>python -m pytest tests/analysis_context/test_guard.py tests/test_professional_capabilities.py tests/test_question_type_keywords.py -q</code>

Expected: PASS。

~~~powershell
git add framework/agents/capabilities.py framework/analysis_context/guard.py tests/analysis_context tests/test_professional_capabilities.py tests/test_question_type_keywords.py
git commit -m "feat(orchestrator): declare and guard spatial requirements"
~~~

---

### Task 6: 将中央守卫接入 LangGraph，并统一流式/非流式准备流程

**Files:**

- Modify: <code>framework/agents/state.py:1-16</code>
- Modify: <code>framework/agents/nodes.py:69-152,187-352,372-459</code>
- Modify: <code>framework/agents/orchestrator.py:18-203</code>
- Modify: <code>tests/test_execute_models_pipeline.py</code>
- Modify: <code>tests/test_agent_integration.py:46-193,242-404</code>
- Create: <code>tests/analysis_context/test_orchestrator_guard.py</code>
- Create: <code>tests/analysis_context/test_stream_parity.py</code>

- [ ] **Step 1: 写“零模型调用”红灯测试**

~~~python
def test_missing_parcel_short_circuits_all_execution(
    monkeypatch, orchestrator, empty_spatial_request
):
    calls = {"fc": 0, "manager": 0, "llm": 0}
    monkeypatch.setattr(nodes, "_execute_via_function_calling", count(calls, "fc"))
    monkeypatch.setattr(agent_manager, "process", count(calls, "manager"))
    monkeypatch.setattr(nodes.llm_service, "generate", count(calls, "llm"))

    result = orchestrator.run(empty_spatial_request)

    assert result["interaction_state"] == "needs_analysis_object"
    assert result["required_object_types"] == ["parcel"]
    assert calls == {"fc": 0, "manager": 0, "llm": 0}
    assert not contains_professional_number(result)
~~~

再写完整 Model-4 scenario 允许执行、scenario 缺输入零调用、知识问答 type 0 不受守卫影响的测试。

- [ ] **Step 2: 运行测试并确认当前会进入 AgentManager**

Run: <code>python -m pytest tests/analysis_context/test_orchestrator_guard.py -q</code>

Expected: FAIL；计数显示 manager 或 function calling 被调用。

- [ ] **Step 3: 扩展编排状态**

~~~python
class MultiAgentState(TypedDict):
    request: dict[str, Any]
    data: dict[str, Any]
    model_results: dict[str, Any]
    llm_response: dict[str, Any]
    rag_response: dict[str, Any]
    conversation_history: list[dict]
    status: str
    error: Optional[str]
    question_type: Optional[int]
    relevance: Optional[float]
    routing_status: Optional[str]
    trace_id: Optional[str]
    analysis_context: dict[str, Any]
    calculation_mode: str
    guard_decision: dict[str, Any]
    validated_identifiers: dict[str, str]
    scenario_inputs: dict[str, Any]
    user_id: int | None
    conversation_id: int | None
~~~

<code>initialize_state()</code> 只初始化缺省值，不覆盖 API 已注入的上述字段。<code>identify_question_node()</code> 继续生成单个 <code>trace_id</code>。

- [ ] **Step 4: 新增守卫节点和确定性待输入节点**

~~~python
def analysis_requirement_node(state: MultiAgentState) -> MultiAgentState:
    capability = get_capability_by_question_type(state.get("question_type"))
    context = AnalysisContext.from_dict(state["analysis_context"])
    decision = analysis_requirement_guard.evaluate(
        capability,
        context,
        inputs=state.get("scenario_inputs", {}),
    )
    return {**state, "guard_decision": decision.to_dict()}


def route_after_requirement(state: MultiAgentState) -> str:
    if state.get("routing_status") == ROUTING_STATUS_BOUNDARY_PENDING:
        return "boundary_pending"
    if state.get("question_type") == 0:
        return "rag_chat"
    if not state["guard_decision"]["allowed"]:
        return "needs_input"
    return "execute_models"


def needs_input_node(state: MultiAgentState) -> MultiAgentState:
    decision = state["guard_decision"]
    return {
        **state,
        "model_results": {
            "status": decision["interaction_state"],
            "data": {
                "agents_invoked": [],
                "details": {},
                "recommendations": [],
                "summary": decision["message"],
            },
        },
        "status": "model_completed",
    }
~~~

图边改为 <code>identify_question → analysis_requirement → route_after_requirement</code>。待输入节点直接聚合，不经过 <code>llm_generate</code>。

- [ ] **Step 5: 只从规范上下文构造模型输入**

新增 <code>_build_verified_execution_context(state)</code>：

- spatial parcel：<code>parcel_id=analysis_context.object.id</code>；
- Model-2 仅在 <code>validated_identifiers</code> 含权威 <code>parcel_code</code> 时传入；
- scenario：只传 <code>scenario_inputs</code>；
- 总是传 <code>execution_channel="chat"</code>、<code>guard_passed=True</code>、<code>execution_context</code>；
- 不再扫描 request 中的原始 <code>parcel_id/parcel_code/area_code</code>。

更新 <code>tests/test_execute_models_pipeline.py</code>：删除“原始双 ID 直接透传”期望，改为“规范对象产生 parcel_id、未验证旧字段不可达”。更新旧集成测试中同时传 <code>parcel_id</code>/<code>parcel_code</code> 却无映射的用例，使其显式创建 <code>ParcelInfo</code> 映射或断言 422。

- [ ] **Step 6: 抽取 run/run_stream 共用准备函数**

~~~python
def prepare_routed_state(
    request: dict[str, Any],
    conversation_history: list[dict] | None,
) -> tuple[MultiAgentState, str]:
    state = initialize_state(_new_initial_state(request, conversation_history))
    state = identify_question_node(state)
    state = analysis_requirement_node(state)
    return state, route_after_requirement(state)
~~~

<code>run_stream()</code> 必须调用该函数；<code>run()</code> 的图节点必须调用相同的 node 函数。流式待输入路径只发送一个 <code>meta</code> 和一个 <code>done</code>，不发送专业数值 token。

- [ ] **Step 7: 写流式/非流式语义一致测试**

~~~python
def test_missing_object_has_same_semantics_in_run_and_stream(orchestrator, request):
    normal = orchestrator.run(request)
    done = next(
        item["data"] for item in orchestrator.run_stream(request)
        if item["type"] == "done"
    )
    for key in (
        "interaction_state",
        "analysis_context",
        "required_object_types",
        "trace_id",
    ):
        assert done[key] == normal[key]
~~~

因为每次请求的 <code>trace_id</code> 本应不同，该测试应把 UUID 生成器固定为同一值后比较；不要在生产代码复用跨请求 trace。

- [ ] **Step 8: 运行编排回归并提交**

Run: <code>python -m pytest tests/analysis_context/test_orchestrator_guard.py tests/analysis_context/test_stream_parity.py tests/test_execute_models_pipeline.py tests/test_multi_agent.py -q</code>

Expected: PASS。

~~~powershell
git add framework/agents tests/analysis_context tests/test_execute_models_pipeline.py tests/test_agent_integration.py
git commit -m "feat(orchestrator): gate every professional execution path"
~~~

---

### Task 7: 复用 trace_id 持久化执行上下文并构建确定性溯源

**Files:**

- Create: <code>framework/analysis_context/provenance.py</code>
- Modify: <code>framework/agents/base.py:155-224</code>
- Modify: <code>framework/agents/manager.py:115-183</code>
- Modify: <code>framework/agents/nodes.py:282-457</code>
- Modify: <code>framework/agents/specialized/stability_agent.py</code>
- Modify: <code>framework/agents/specialized/grade_agent.py</code>
- Modify: <code>framework/agents/specialized/problem_agent.py</code>
- Modify: <code>framework/agents/specialized/acidification_agent.py</code>
- Modify: <code>framework/agents/specialized/organic_matter_agent.py</code>
- Test: <code>tests/analysis_context/test_provenance.py</code>
- Modify: <code>tests/test_base_agent_persist.py</code>

- [ ] **Step 1: 写 trace、对象版本和 unknown 版本的持久化测试**

~~~python
def test_persist_result_reuses_request_trace_and_context(
    agent, execution_context, db_session
):
    assert agent._persist_result(
        agent_id="model-4",
        parcel_id="P001",
        inputs={"SJD": 5.1},
        outputs={"model_version": "acid-v2", "data_as_of": "2024"},
        status="ok",
        execution_context=execution_context,
    )
    log = ModelExecutionLog.query.one()
    assert log.trace_id == execution_context["trace_id"]
    assert log.user_id == 7
    assert log.conversation_id == 12
    assert log.analysis_object_type == "parcel"
    assert log.analysis_object_id == "P001"
    assert log.context_version == 3
~~~

再写两个 Agent 同 trace 可保存、模型版本缺失输出 <code>unknown</code> 而不是能力目录版本、对象不足零日志的测试。

- [ ] **Step 2: 运行持久化测试并确认随机 UUID 导致失败**

Run: <code>python -m pytest tests/test_base_agent_persist.py -q</code>

Expected: FAIL，日志 trace 与请求 trace 不一致或新字段为空。

- [ ] **Step 3: 给 BaseAgent 传递执行上下文**

~~~python
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
    execution_context = execution_context or {}
    trace_id = execution_context.get("trace_id") or uuid.uuid4().hex
    snapshot = execution_context.get("analysis_context")
    obj = (snapshot or {}).get("object") or {}
    log = ModelExecutionLog(
        trace_id=trace_id,
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
        output_result=outputs,
        model_version=outputs.get("model_version", "unknown"),
        data_as_of=outputs.get("data_as_of"),
        data_version=outputs.get("data_version"),
        status=status,
        started_at=now,
        completed_at=now,
    )
~~~

AgentManager 的 payload 必须保留 <code>execution_context</code>，各专业 Agent 调用 <code>_persist_result()</code> 时原样传入。不要在 Agent 内重新解析会话或对象。

- [ ] **Step 4: 写溯源构建器红灯测试**

~~~python
def test_provenance_is_backend_owned_and_uses_actual_inputs():
    result = builder.build(
        trace_id="trace-1",
        analysis_context=parcel_context,
        capability=model4_capability,
        agent_result={
            "model_version": "acid-v2",
            "data_as_of": "2024",
            "data_version": "soil-survey-3",
            "actual_inputs": {"SJD": 5.1, "JHX": 1.2, "JLA": 3.4},
        },
        calculated_at=fixed_now,
    )
    assert result["model_version"] == "acid-v2"
    assert result["key_inputs"]["SJD"] == 5.1
    assert result["spatial_object"]["id"] == "P001"
    assert result["object_title"] == "分析对象：地块 P001"
~~~

- [ ] **Step 5: 实现 ResultProvenanceBuilder**

~~~python
class ResultProvenanceBuilder:
    def build(
        self,
        *,
        trace_id: str,
        analysis_context: AnalysisContext,
        capability: ProfessionalCapability,
        agent_result: Mapping[str, Any],
        calculated_at: datetime,
    ) -> dict[str, Any]:
        scenario = analysis_context.mode is CalculationMode.SCENARIO
        return {
            "trace_id": trace_id,
            "model_id": capability.model_id,
            "model_version": agent_result.get("model_version") or "unknown",
            "data_as_of": agent_result.get("data_as_of"),
            "data_version": agent_result.get("data_version"),
            "calculated_at": calculated_at.isoformat(),
            "key_inputs": dict(agent_result.get("actual_inputs") or {}),
            "scenario_result": scenario,
            "spatial_object": None if scenario else analysis_context.object.to_dict(),
            "object_title": (
                "情景试算，非具体空间对象结果"
                if scenario
                else f"分析对象：{analysis_context.object.display_name}"
            ),
        }
~~~

关键输入白名单来自能力或 Agent 实际返回，不能把密码、路径、完整提示词等内部字段回显。未知 <code>model_version</code> 用 <code>unknown</code>；未知数据时间保持 null。

- [ ] **Step 6: 让专业 Agent 返回真实溯源素材**

每个 Model-1 至 Model-5 的结构化输出统一增加：

~~~python
{
    "model_version": actual_version_or_unknown,
    "data_as_of": survey_year_or_iso_date_or_none,
    "data_version": dataset_version_or_none,
    "actual_inputs": inputs_actually_consumed,
}
~~~

Model-1 使用历史快照时取实际 <code>survey_year</code>；Model-2 取运行器真实版本；Model-3 取诊断数据版本；Model-4 取过程模型返回版本；Model-5 取实际 RF/ETR 版本。没有证据时返回 <code>unknown/null</code>。

- [ ] **Step 7: 后端标题包裹 LLM 正文**

<code>aggregate_results()</code> 先保留 Agent 摘要作为 <code>answer_body</code>，LLM 成功只替换正文；随后由后端组装：

~~~python
final_result["provenance"] = provenance
final_result["analysis_context"] = state["analysis_context"]
final_result["interaction_state"] = "completed"
final_result["answer"] = (
    provenance["object_title"] + "\n\n" + answer_body
)
~~~

LLM 失败或空响应时仍返回 Agent 摘要和完整溯源。

- [ ] **Step 8: 运行溯源与持久化测试并提交**

Run: <code>python -m pytest tests/analysis_context/test_provenance.py tests/test_base_agent_persist.py tests/test_agent_base.py -q</code>

Expected: PASS。

~~~powershell
git add framework/analysis_context/provenance.py framework/agents tests/analysis_context tests/test_base_agent_persist.py
git commit -m "feat(provenance): persist request trace and actual model inputs"
~~~

---

### Task 8: 收敛 Function Calling 与专业 Agent 的安全边界

**Files:**

- Modify: <code>framework/function_calling/tool_loop.py:20-38,42-224</code>
- Modify: <code>framework/function_calling/specialized_tools.py:22-173</code>
- Modify: <code>framework/agents/specialized/acidification_agent.py:13-173</code>
- Modify: <code>framework/agents/specialized/organic_matter_agent.py:14-213</code>
- Modify: <code>framework/agents/manager.py:142-183</code>
- Modify: <code>tests/test_specialized_tools.py</code>
- Modify: <code>tests/test_function_calling.py</code>
- Modify: <code>tests/test_model4_acidification.py</code>
- Modify: <code>tests/test_model5_fertility_integration.py</code>
- Create: <code>tests/analysis_context/test_agent_safety.py</code>

- [ ] **Step 1: 写工具参数冲突和生产 MOCK 禁止测试**

~~~python
def test_llm_cannot_override_locked_parcel_id(tool_loop, fake_llm):
    fake_llm.next_tool_call(
        "model_4_acidification_remediation",
        {"parcel_id": "P999"},
    )
    result = tool_loop.run("计算这块地的酸化改良剂")
    assert result["success"] is False
    assert result["reason"] == "analysis_object_conflict"
    assert tool_executor.calls == []


def test_acidification_chat_never_uses_mock_when_parcel_missing():
    with pytest.raises(ProfessionalInputRejected) as exc:
        AcidificationRemediationAgent().execute({
            "execution_channel": "chat",
            "guard_passed": True,
            "calculation_mode": "spatial",
        })
    assert exc.value.code == "verified_parcel_required"


def test_model4_scenario_uses_only_supplied_values():
    result = AcidificationRemediationAgent().execute({
        "execution_channel": "chat",
        "guard_passed": True,
        "calculation_mode": "scenario",
        "SJD": 5.1,
        "JHX": 1.2,
        "JLA": 3.4,
        "land_type": "upland",
        "fertilizer_type": "compound",
    })
    assert result["metadata"]["scenario_result"] is True
    assert result["result"]["actual_inputs"]["SJD"] == 5.1
~~~

- [ ] **Step 2: 运行安全测试并确认当前默认地块/MOCK 行为失败**

Run: <code>python -m pytest tests/analysis_context/test_agent_safety.py tests/test_function_calling.py -q</code>

Expected: FAIL；当前系统提示词允许默认地块 1，且 LLM 参数优先覆盖默认参数。

- [ ] **Step 3: 锁定 Function Calling 对象参数**

从系统提示词删除“默认地块 ID 1”，改为“对象参数由后端提供，不得自行选择”。给 <code>ToolCallingLoop</code> 增加 <code>locked_args</code>：

~~~python
LOCKED_SPATIAL_KEYS = frozenset({"parcel_id", "parcel_code", "area_code"})

def _merge_default_args(self, tool_name, llm_args):
    for key in LOCKED_SPATIAL_KEYS:
        if (
            key in llm_args
            and key in self._default_args
            and llm_args[key] != self._default_args[key]
        ):
            raise AnalysisObjectConflict(
                f"工具参数 {key} 与当前分析对象不一致"
            )
    accepted = self._get_accepted_keys(tool_registry.get(tool_name))
    return {
        key: (
            self._default_args[key]
            if key in LOCKED_SPATIAL_KEYS and key in self._default_args
            else llm_args.get(key, self._default_args.get(key))
        )
        for key in accepted
        if key in llm_args or key in self._default_args
    }
    # 锁定字段后端值优先，其他字段保留 LLM 值。
~~~

捕获冲突后返回 <code>reason=analysis_object_conflict</code>，不执行工具。<code>default_args</code> 只能由 <code>_build_verified_execution_context()</code> 构造。

- [ ] **Step 4: 移除专业工具的空间默认值**

<code>Model1/2/3/4</code> 的地块参数在 spatial 模式仍为必需；<code>Model4AcidificationArgs</code> 为 scenario 提供显式分支，但 wrapper 在调用 Agent 前复用能力完整性校验。删除 <code>area_code="lechang"</code>、<code>area_code="440281"</code> 这类可伪装对象来源的默认值。

- [ ] **Step 5: 对酸化与有机质 Agent 做防御性拒绝**

酸化 Agent：

- spatial 仅接受 <code>guard_passed=True</code> 且 ParcelDataAccessor 实际命中；
- DB 查询异常继续抛 503 语义，不转 legacy；
- scenario 只接受五个已验证字段，不调用 <code>MOCK_INPUTS</code>；
- <code>MOCK_INPUTS</code> 迁入显式 <code>execute_demo()</code>，生产聊天不调用。

有机质 Agent：

- spatial 缺地块或 DB 未命中时拒绝；
- 因首期 <code>supports_scenario=False</code>，chat scenario 在守卫处终止；
- <code>_rule_fallback()</code> 仅供显式 demo/test 调用，不能由 <code>execute()</code> 的聊天分支自动触发。

Model-1/2/3 通过 AgentManager 的 <code>execution_channel=chat</code> 和 <code>guard_passed</code> 做共同防御；单模型非聊天 API 保持原有契约，另行迁移时再统一。

- [ ] **Step 6: 更新旧测试的安全语义**

把“缺输入走 mock/默认结果”的断言改为：

- 生产 chat：拒绝或在上层返回 <code>needs_analysis_object</code>；
- 显式 demo helper：仍可验证历史演示输出；
- DB 命中：保持真实模型结果；
- scenario：只验证 Model-4 完整输入。

- [ ] **Step 7: 运行 Function Calling 和专业模型回归并提交**

Run: <code>python -m pytest tests/analysis_context/test_agent_safety.py tests/test_specialized_tools.py tests/test_function_calling.py tests/test_model4_acidification.py tests/test_model5_fertility_integration.py -q</code>

Expected: PASS，且任何生产聊天缺对象用例不包含 YTK、MBNT、pH、施肥量等具体数值。

~~~powershell
git add framework/function_calling framework/agents/specialized framework/agents/manager.py tests
git commit -m "fix(safety): block mock spatial results in production chat"
~~~

---

### Task 9: 抽取聊天服务并让 HTTP 与 SSE 使用同一事务和响应契约

**Files:**

- Create: <code>framework/api/services/__init__.py</code>
- Create: <code>framework/api/services/chat_service.py</code>
- Modify: <code>framework/api/routes/chat.py:1-244</code>
- Modify: <code>framework/models/message.py:16-26</code>
- Create: <code>tests/analysis_context/test_chat_api.py</code>
- Create: <code>tests/analysis_context/test_chat_sse.py</code>
- Modify: <code>tests/test_agent_integration.py</code>

- [ ] **Step 1: 写 HTTP 状态矩阵集成测试**

参数化覆盖：

~~~python
@pytest.mark.parametrize(
    "body,expected_http,expected_code",
    [
        (missing_parcel_body(), 200, "needs_analysis_object"),
        (missing_scenario_input_body(), 200, "needs_scenario_inputs"),
        (unknown_object_body(), 422, "analysis_object_invalid"),
        (stale_version_body(), 409, "analysis_context_conflict"),
    ],
)
def test_chat_analysis_context_matrix(
    client, auth_header, body, expected_http, expected_code
):
    response = client.post(
        "/api/v1/chat/", json=body, headers=auth_header
    )
    assert response.status_code == expected_http
    payload = response.get_json()
    code = (
        payload.get("error", {}).get("code")
        or payload["data"]["interaction_state"]
    )
    assert code == expected_code
~~~

验证 503 时旧对象不变；needs 状态保存两条消息且快照相同；422/409/503 不保存消息；切换到 P002 后旧消息仍指向 P001。

- [ ] **Step 2: 运行 API 测试并确认新契约缺失**

Run: <code>python -m pytest tests/analysis_context/test_chat_api.py -q</code>

Expected: FAIL；响应缺少 <code>interaction_state</code>/<code>analysis_context</code> 或状态码不符。

- [ ] **Step 3: 实现共用 ChatRequestService**

~~~python
@dataclass
class PreparedChat:
    conversation: Conversation
    user_message: Message
    history: list[dict[str, str]]
    orchestrator_request: dict[str, Any]
    context_snapshot: dict[str, Any]


class ChatRequestService:
    def prepare(
        self, *, user_id: int, body: Mapping[str, Any]
    ) -> PreparedChat:
        """鉴权会话、解析上下文、提交对象更新和用户消息."""
        conversation = self._get_or_create_owned_conversation(user_id, body)
        resolved = self._context_service.resolve(
            conversation, user_id=user_id, body=body
        )
        return self._persist_user_message_and_build_request(
            conversation, body, resolved
        )

    def persist_assistant(
        self,
        prepared: PreparedChat,
        result: Mapping[str, Any],
    ) -> Message:
        """保存正文、来源、Agent、建议和不可变上下文/溯源快照."""
        message = self._assistant_message_from_result(prepared, result)
        db.session.add(message)
        db.session.commit()
        return message

    def build_response(
        self,
        prepared: PreparedChat,
        result: Mapping[str, Any],
        *,
        message_id: int | None,
    ) -> dict[str, Any]:
        return self._response_serializer.serialize(
            prepared=prepared,
            result=result,
            message_id=message_id,
        )
~~~

助手消息的 <code>analysis_context_snapshot</code> 格式：

~~~json
{
  "mode": "spatial",
  "version": 4,
  "object": {},
  "trace_id": "trace-1",
  "provenance": {}
}
~~~

用户消息保存解析后的 mode/version/object，不含尚未产生的 provenance。

- [ ] **Step 4: 在路由外捕获领域错误**

~~~python
try:
    prepared = chat_request_service.prepare(
        user_id=int(get_jwt_identity()),
        body=request.get_json() or {},
    )
except AnalysisContextError as exc:
    return jsonify({
        "status": "error",
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    }), exc.http_status
~~~

两个路由都在创建 SSE Response 前执行 <code>prepare()</code>，因此 409/422/503 能使用真实 HTTP 状态码。

- [ ] **Step 5: 让 needs 状态走确定性保存**

非流式直接持久化编排器的确定性结果。SSE 对 needs 状态发送：

~~~text
data: {"event":"meta","data":{"interaction_state":"needs_analysis_object","required_object_types":["parcel"]}}

data: {"event":"done","data":{"interaction_state":"needs_analysis_object","answer":"请选择地块后再计算"}}
~~~

不得发送 token 事件，不得再次调 LLM。两条路径都调用 <code>persist_assistant()</code> 与 <code>build_response()</code>。

- [ ] **Step 6: 写完成结果的 HTTP/SSE 一致和 trace 一致测试**

测试固定路由 trace，分别调用 HTTP 与 SSE，断言字段集合和语义相同：

- <code>interaction_state</code>；
- <code>analysis_context.mode/version/object</code>；
- <code>provenance</code> 全部字段；
- <code>scenario_result</code> 与 <code>spatial_object</code>；
- 对象标题；
- 消息快照 trace；
- <code>ModelExecutionLog.trace_id</code>。

- [ ] **Step 7: 运行聊天集成回归并提交**

Run: <code>python -m pytest tests/analysis_context/test_chat_api.py tests/analysis_context/test_chat_sse.py tests/test_agent_integration.py -q</code>

Expected: PASS。

~~~powershell
git add framework/api/services framework/api/routes/chat.py framework/models/message.py tests/analysis_context tests/test_agent_integration.py
git commit -m "feat(api): unify chat analysis context across HTTP and SSE"
~~~

---

### Task 10: 增加运行统计、API 文档、发布验证与回滚说明

**Files:**

- Create: <code>framework/observability/analysis_context_metrics.py</code>
- Modify: <code>framework/api/routes/observability.py:29-57</code>
- Modify: <code>framework/observability/__init__.py</code>
- Modify: <code>tests/test_observability_api.py</code>
- Create: <code>tests/analysis_context/test_execution_statistics.py</code>
- Modify: <code>docs/openapi.json</code>
- Modify: <code>docs/api.md:136-330</code>
- Modify: <code>README.md:129-167</code>
- Modify: <code>docs/chat-routing-keywords.md</code>
- Create: <code>docs/deployment/chat-analysis-context-rollout.md</code>

- [ ] **Step 1: 写多级运行统计查询测试**

~~~python
def test_execution_statistics_group_by_area_model_and_status(db_session):
    seed_execution_logs(db_session)
    rows = query_execution_statistics(
        object_type="parcel",
        area_code="440281",
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 31),
    )
    assert rows == [{
        "area_code": "440281",
        "agent_id": "model-4",
        "status": "ok",
        "count": 2,
    }]
~~~

同时用 SQLAlchemy inspector 断言查询过滤列有索引，并证明查询不访问 <code>kb_conversation.analysis_object</code>。

- [ ] **Step 2: 实现执行统计与交互状态指标**

~~~python
def query_execution_statistics(
    *,
    object_type: str | None = None,
    area_code: str | None = None,
    agent_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    query = db.session.query(
        ModelExecutionLog.area_code,
        ModelExecutionLog.agent_id,
        ModelExecutionLog.status,
        db.func.count(ModelExecutionLog.id).label("count"),
    )
    query = apply_execution_log_filters(
        query,
        object_type=object_type,
        area_code=area_code,
        agent_id=agent_id,
        date_from=date_from,
        date_to=date_to,
    )
    rows = query.group_by(
        ModelExecutionLog.area_code,
        ModelExecutionLog.agent_id,
        ModelExecutionLog.status,
    ).all()
    return [row._asdict() for row in rows]
~~~

在 dashboard 增加：

- <code>needs_analysis_object</code> 次数；
- <code>needs_scenario_inputs</code> 次数；
- 422/409/503 次数；
- 旧字段使用次数；
- 按对象类型、区域、模型、状态和时间的运行统计。

交互错误/待输入计数使用已有 JSONL/观测事件机制新增稳定事件名；完成模型调用统计直接查询 <code>model_execution_log</code>。业务面积、指标均值等不得从执行日志推断。

- [ ] **Step 3: 更新 OpenAPI schema 和示例**

<code>docs/openapi.json</code> 增加并引用：

- <code>AnalysisObjectRef</code>；
- <code>AnalysisObject</code>；
- <code>AnalysisContextRequest</code>；
- <code>AnalysisContextSnapshot</code>；
- <code>ResultProvenance</code>；
- <code>RecoverableInteraction</code>；
- <code>AnalysisContextError</code>。

为 <code>POST /api/v1/chat/</code> 与 <code>/stream</code> 添加 set/inherit/clear、Model-4 scenario、needs、409、422、503 示例。旧 <code>parcel_id</code>、<code>parcel_code</code>、<code>area_code</code> 标记 <code>deprecated: true</code>，并解释双 ID 只有权威映射一致时可用。

- [ ] **Step 4: 更新开发者和部署文档**

<code>docs/api.md</code> 给出可复制请求/响应；README 只保留入口摘要并链接 API 文档。发布文档固定顺序：

1. 备份数据库并运行迁移 <code>upgrade</code>；
2. 导入精确区域目录；
3. 回填已确认的 <code>legacy_parcel_code</code> 映射；
4. 部署兼容读取；
5. 启用中央守卫；
6. 观察 needs/409/422/503/旧字段指标；
7. 客户端切换到新协议；
8. 回滚时先关闭守卫，再运行带非空检查的 downgrade。

- [ ] **Step 5: 校验文档与 OpenSpec**

Run: <code>python -m json.tool docs/openapi.json</code>

Expected: 输出格式化 JSON，无解析错误。

Run: <code>D:\soft\Node.js\node_global\openspec.ps1 validate add-chat-analysis-object-context --strict</code>

Expected: <code>Change 'add-chat-analysis-object-context' is valid</code>。

- [ ] **Step 6: 运行聚焦测试和完整回归**

Run: <code>python -m pytest tests/analysis_context tests/test_specialized_tools.py tests/test_execute_models_pipeline.py tests/test_agent_integration.py tests/test_observability_api.py -q</code>

Expected: PASS。

Run: <code>python -m pytest -q</code>

Expected: PASS；若有依赖真实 PostgreSQL、外部模型或本地数据文件的既有跳过项，只接受测试标记中已声明的 SKIP，不接受本变更新增的失败或意外 XFAIL。

- [ ] **Step 7: 做最终安全扫描**

~~~powershell
rg -n "默认地块 ID|falling back to MOCK_INPUTS|MOCK_INPUTS" framework/agents framework/function_calling
rg -n "parcel_id.*parcel_code|parcel_code.*parcel_id" framework/analysis_context framework/api framework/agents
rg -n "trace_id=str\(uuid\.uuid4|trace_id = str\(uuid\.uuid4" framework/agents
git diff --check
git status --short
~~~

Expected:

- 生产聊天提示词不再包含默认地块；
- MOCK 只存在于明确 demo/test helper；
- 双 ID 比较只存在于权威映射适配器；
- Agent 持久化不再覆盖编排 trace；
- <code>git diff --check</code> 无输出；
- 状态中只有本任务文件和用户原有未提交文件。

- [ ] **Step 8: 提交文档、统计与最终验证**

~~~powershell
git add framework/observability framework/api/routes/observability.py tests/test_observability_api.py tests/analysis_context/test_execution_statistics.py docs/openapi.json docs/api.md README.md docs/chat-routing-keywords.md docs/deployment/chat-analysis-context-rollout.md
git commit -m "docs(api): publish analysis context contract and rollout"
~~~

记录最终测试数量、跳过数量、迁移往返结果和 OpenSpec 严格校验结果，交付时说明尚未包含前端选择器、全国区域目录和统计页面。

---

## Completion Checklist

- [ ] 无对象地块问题返回 200 + <code>needs_analysis_object</code>，且工具、Agent、总结 LLM、执行日志调用数均为 0。
- [ ] 非法/越权/冲突/验证不可用分别返回 422/422/409/503，原会话对象和消息数量不变。
- [ ] set/inherit/clear 在单会话内正确工作，不跨会话继承。
- [ ] Model-4 scenario 仅在五项输入完整时运行，结果固定标明非具体空间对象。
- [ ] 所有专业执行路径只消费已验证对象；LLM 工具参数不能覆盖对象。
- [ ] HTTP 与 SSE 使用相同上下文、守卫、响应和持久化服务。
- [ ] API 响应、助手消息快照和执行日志共享 trace、对象版本与溯源。
- [ ] 可按对象类型、区域、模型、状态和时间对执行日志做索引聚合。
- [ ] OpenAPI JSON、OpenSpec 严格校验、聚焦测试和完整测试均通过。
- [ ] 没有修改或暂存用户原有无关变更。
