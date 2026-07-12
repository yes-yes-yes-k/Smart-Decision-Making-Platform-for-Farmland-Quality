# standalone-integration-runtime Specification

## Purpose
TBD - created by archiving change bootstrap-lechang-county-demo. Update Purpose after archive.
## Requirements
### Requirement: 集成运行时必须独立于历史项目进程
系统 MUST 以当前仓库内的实现、资产和数据作为运行基础，不得把 `D:\work\AcidMap` 或 `D:\work\suan\AcidificationModel\api` 的在线进程、服务状态或运行时数据库作为能力可用前提。

#### Scenario: 在历史项目未启动时调用基础能力
- **WHEN** 调用方在未启动 `AcidMap` 和 `AcidificationModel/api` 的情况下调用当前仓库提供的基础能力接口
- **THEN** 系统 MUST 仍能返回可用结果，或在本仓库自身约束下返回结构化错误，而不是要求先启动历史项目服务

### Requirement: 集成实现不得修改历史项目源码
系统 MUST 通过参考资源、迁移实现、重写实现或本地封装的方式构建能力，不得要求修改 `D:\work\AcidMap` 或 `D:\work\suan\AcidificationModel\api` 的源码作为前置条件。

#### Scenario: 实现基础能力时引用历史项目
- **WHEN** 开发者为当前仓库实现地图、诊断或结果整理能力时参考历史项目
- **THEN** 系统 MUST 能在不改动历史项目源码的前提下完成实现，并将当前能力边界保持在本仓库内

### Requirement: 参考来源必须可追溯
系统 MUST 对从历史项目参考而来的资源、数据样例或实现思路保留来源说明，便于后续维护时区分“本仓库实现”和“历史项目参考来源”。

#### Scenario: 查看能力来源说明
- **WHEN** 维护者查看某项基础能力所依赖的本地资产或实现说明
- **THEN** 系统 MUST 能说明该能力参考了哪个历史项目、参考的是数据还是实现思路，以及当前仓库如何独立承载该能力

