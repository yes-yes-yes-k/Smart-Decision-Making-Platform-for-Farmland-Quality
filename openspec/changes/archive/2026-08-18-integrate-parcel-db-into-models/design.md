## Context

当前 5 个专题模型 Agent 的数据来源分散且未接入 DB：Model-1 用硬编码 `MOCK_COUNTIES`，Model-2 读取 CSV，Model-3/4 查询 SQLite 文件，Model-5 从用户传入参数获取。V3.0 ORM 模型（`ParcelInfo`、5 个结果表、`ModelExecutionLog`）虽已定义且 `db.create_all()` 建表，但生产代码从未引用。`SoilDataLoader` 已实现 DB 读取能力但仅被测试代码调用。详见 proposal.md。

约束：
- PostgreSQL 16 + PostGIS 3.4 已部署
- `parcel_info` 表 `soil_indicators` 字段为 JSON 类型，含 terrain_position/soil_ph/organic_matter 等指标
- `parcel_id` 已通过路由链（chat.py → nodes.py → context）传递到各 Agent
- 保留现有数据源作为 fallback，不破坏向后兼容

## Goals / Non-Goals

**Goals:**
- 5 个 Agent 统一通过 `parcel_id` 从 `parcel_info` 表获取地块指标
- 计算结果同步持久化到 V3.0 结果表 + `model_execution_log`
- DB 不可达时自动降级到现有数据源

**Non-Goals:**
- 不修改模型算法本身（仅修改数据来源和结果持久化）
- 不变更 DB schema（V3.0 表已存在）
- 不迁移 SQLite/CSV 中的历史数据到 PostgreSQL
- 不修改路由/可观测性代码（已由 persist-routing-observability 完成）

## Decisions

### Decision 1: 新增 `ParcelDataAccessor` 作为 DB 读取统一入口

**选择**：在 `framework/domain/data/` 新增 `ParcelDataAccessor` 类，封装 `parcel_id` → `ParcelInfo.soil_indicators` 查询逻辑。

**理由**：`SoilDataLoader` 现有方法 `load_soil_data()` 查询的是 `ThirdSurveyTopsoil` 和 `FormulaFertilization` 表，与 `parcel_info` 表结构不同。直接修改 `SoilDataLoader` 会破坏现有测试。新增专门的 accessor 职责更清晰。

**备选方案**：
- 在各 Agent 内直接查询：违反 DRY，5 处重复代码
- 修改 `SoilDataLoader` 增加 `load_parcel_info()`：可行但混淆了两个不同数据源的职责

### Decision 2: 在 `BaseAgent` 增加持久化钩子 `_persist_result()`

**选择**：在 `BaseAgent.execute()` 或 `analyze()` 的成功路径上调用 `_persist_result(agent_id, parcel_id, inputs, outputs, status)`，子类通过 `_get_result_model()` 返回对应 ORM 模型类。

**理由**：5 个 Agent 的持久化模式一致（写 execution_log → 写结果表），在基类实现避免重复。子类只需提供 ORM 模型类引用和结果字段映射。

**备选方案**：
- 在每个 Agent 子类各自实现：5 处重复代码
- 用装饰器模式：增加复杂度，调试困难

### Decision 3: 持久化失败不阻断用户结果

**选择**：`_persist_result()` 内部 try/except 捕获所有 DB 异常，记录 ERROR 日志后在返回结果中标记 `persisted: false`，但不抛出异常。

**理由**：用户最关心的是拿到计算结果；持久化是辅助功能，不应因 DB 问题导致用户拿不到结果。

### Decision 4: execution_log + 结果表在同一事务中写入

**选择**：使用 `db.session.begin()` 上下文管理器，先写 `model_execution_log` 获取 `execution_id`，再用该 ID 写结果表，最后 commit。失败时整体 rollback。

**理由**：保证 execution_log 和结果表的一致性，避免出现有日志无结果或有结果无日志的情况。

### Decision 5: 降级路径保留现有数据源不变

**选择**：各 Agent 的 `_collect_inputs` 先尝试 DB 查询，失败时调用现有的 `_collect_inputs_from_legacy()` 方法（重命名当前实现），不修改 legacy 逻辑。

**理由**：最小改动原则，降低引入回归的风险。

## Risks / Trade-offs

- **[Risk] `parcel_info` 表可能无数据** → 降级到 fallback 数据源并记录 WARNING，不阻断服务
- **[Risk] `soil_indicators` JSON 字段结构不统一** → 在 `ParcelDataAccessor` 中做字段名映射和缺失字段处理
- **[Risk] 同步持久化增加响应延迟** → 可接受，因为 DB 写入通常 <50ms；如后续成为瓶颈可改为异步
- **[Trade-off] 保留 legacy 数据源增加维护成本** → 换取向后兼容和渐进迁移安全性

## Migration Plan

1. 新增 `ParcelDataAccessor` 和 `BaseAgent._persist_result()`，不修改现有 Agent 逻辑
2. 逐个 Agent 改造 `_collect_inputs`：DB 优先 + legacy fallback
3. 逐个 Agent 改造 `execute`：调用 `_persist_result()`
4. 每步改造后运行测试验证
5. 回滚策略：如 DB 集成出问题，删除 `ParcelDataAccessor` 调用即可恢复纯 legacy 路径
