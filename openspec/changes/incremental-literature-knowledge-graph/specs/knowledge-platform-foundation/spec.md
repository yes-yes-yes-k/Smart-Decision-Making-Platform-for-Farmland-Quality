## Purpose

定义面向 10 万级来源与规范知识对象的平台容量、开源组件适配边界、图存储运行模型和可重复验收标准，使知识工程可以分阶段扩展而不锁定单一产品。

## ADDED Requirements

### Requirement: Explicit Capacity Envelope

平台 SHALL 以至少 100,000 份来源文档、100,000 个规范实体和 1,000,000 条有效关系证据作为容量规划与压测基线。日常单文档更新和在线查询 MUST NOT 依赖全量实体、关系或证据加载到单进程内存。

#### Scenario: Single document is incrementally processed at target scale
- **WHEN** 平台已包含容量基线数据且一篇新文献完成索引
- **THEN** 系统 SHALL 只处理该文献及受影响的候选、实体和关系，不得扫描或重写全图

#### Scenario: Synthetic scale data is generated
- **WHEN** 运维人员生成容量压测数据
- **THEN** 数据 SHALL 明确标记为 synthetic、与生产命名空间隔离且可完整清理

### Requirement: Pluggable Open-source Backends

平台 SHALL 通过稳定接口接入实体/关系抽取器、图存储和任务执行器。业务 Schema、正式实体 ID、证据契约、审核状态和发布 API MUST NOT 依赖某个开源产品的私有 ID 或内部数据格式。

#### Scenario: Extraction backend is replaced
- **WHEN** 管理员从 GraphRAG adapter 切换到通过一致性测试的其他抽取 adapter
- **THEN** 候选 SHALL 使用相同外部契约进入校验和审核，现有正式实体 ID 与审核 API SHALL 保持兼容

#### Scenario: Backend emits vendor-specific relationship types
- **WHEN** 抽取后端返回未映射到活动 schema 的产品私有关系类型
- **THEN** 系统 SHALL 将其隔离为扩展候选或拒绝结果，不得直接写入正式图

### Requirement: Backend Provenance and License Inventory

每次抽取和发布 SHALL 记录后端名称、版本、配置摘要和 schema 版本。部署 SHALL 维护所用开源组件的固定版本、许可证、来源和软件物料清单；依赖升级 SHALL 在进入生产前通过适配器一致性和结果差异检查。

#### Scenario: Open-source dependency is upgraded
- **WHEN** GraphRAG、OpenSPG、Apache AGE 或其关键依赖版本发生变化
- **THEN** 系统 SHALL 生成许可证/SBOM 差异和金标结果差异，未通过门槛时不得切换生产版本

### Requirement: Scalable Operational Graph Store

目标生产图 SHALL 使用 PostgreSQL + Apache AGE 或通过相同一致性测试的 `GraphStore` 实现进行持久化和有界查询。JSON 图 SHALL 只作为迁移兼容、回退或审计导出，不得作为 10 万级平台唯一的在线事实存储。

#### Scenario: Existing v0.4 graph is migrated
- **WHEN** 管理员把现有 v0.4 JSON 导入目标图存储
- **THEN** 实体、关系、证据引用、稳定 ID 和 schema 版本 SHALL 保持一致，并 SHALL 通过代表性查询双读对比

#### Scenario: Target graph store is unavailable during migration
- **WHEN** AGE 在切换主读前不可用或健康检查失败
- **THEN** 系统 SHALL 保持兼容图存储和向量检索可用，不得把未验证 AGE 实例设为主读

### Requirement: Append-only Release Semantics

正式实体、关系和证据变更 SHALL 使用可审计的追加式版本记录及有效发布区间；生产发布和回滚 SHALL 通过原子活动版本切换完成，而不是复制或覆盖整张图。发布后 SHALL 能异步导出带校验和的审计快照。

#### Scenario: Incremental release is activated
- **WHEN** 一个发布只包含少量已批准关系和证据变更
- **THEN** 系统 SHALL 写入增量版本记录并原子切换活动 release，不得重写未变化的全量知识

#### Scenario: Release is rolled back
- **WHEN** 管理员回滚到一个已验证的兼容 release
- **THEN** 系统 SHALL 在 60 秒内切换活动版本、保留后续变更审计且不中断向量检索

### Requirement: Bounded Permission-safe Graph Queries

在线图查询 SHALL 要求关系类型/方向过滤、最大跳数、top-k、超时和结果大小上限。图存储 SHALL 只返回稳定知识 ID 和证据引用；证据正文 SHALL 通过现有权限过滤的 chunk 读取接口解析。

#### Scenario: High-degree entity is queried
- **WHEN** 用户查询连接大量关系的实体
- **THEN** 系统 SHALL 在配置的跳数、top-k 和超时内返回有界结果，不得执行无界全图遍历

#### Scenario: Graph references an unauthorized chunk
- **WHEN** 图查询命中当前用户无权读取的文档证据
- **THEN** 权限过滤的 chunk 解析 SHALL 排除该证据，图存储属性不得旁路返回正文

### Requirement: Repeatable Scale Benchmark

仓库 SHALL 提供可重复的 synthetic 数据生成器、benchmark manifest 和自动验收报告。完整基准 SHALL 覆盖 100,000 文档元数据、100,000 实体、1,000,000 关系证据和 100,000 待处理任务，并记录硬件、组件版本、索引、并发和数据分布。

#### Scenario: Full capacity benchmark completes
- **WHEN** 完整基准在记录的参考环境执行
- **THEN** 1 至 2 跳 top-100 图查询（不含 LLM 与向量正文读取）P95 SHALL 不超过 1 秒，发布激活和回滚 SHALL 不超过 60 秒

#### Scenario: Workers restart during backlog processing
- **WHEN** 多个 worker 处理 100,000 个任务期间发生重复投递和进程重启
- **THEN** 任务计数 SHALL 守恒且不得产生重复业务生效

#### Scenario: Benchmark misses a gate
- **WHEN** 任一容量、正确性、延迟或恢复门槛未通过
- **THEN** 报告 SHALL 标记失败并保留诊断数据，系统 MUST NOT 通过缩小声明容量把结果标记为通过

### Requirement: Backup and Restore Verification

平台 SHALL 对关系表、AGE 图数据、活动 release 和证据引用实施一致的备份恢复流程。恢复演练 SHALL 校验实体数、关系数、有效证据数、活动版本和抽样证据解析。

#### Scenario: Knowledge platform is restored
- **WHEN** 运维人员从同一恢复点恢复 PostgreSQL/AGE 和知识治理数据
- **THEN** 系统 SHALL 通过数量、校验和、活动版本和抽样权限安全查询验证后才能恢复主读
