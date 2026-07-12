# 历史项目参考资产盘点

## 使用边界

当前仓库可以参考历史项目中的资源、数据结构、接口设计和局部实现思路，但不能修改历史项目源码，也不能要求历史项目服务在线运行。

## `D:\work\AcidMap`

| 类别 | 参考位置 | 用途 | 使用方式 |
| --- | --- | --- | --- |
| 空间 API 组织 | `app/api/vector.py`、`app/api/raster.py` | 理解矢量/栅格能力边界 | 只参考接口分层，不直接运行 |
| 图层与数据模型 | `app/models/vector.py`、`app/models/raster.py`、`app/models/county.py` | 设计图层元数据字段 | 迁移为本仓库轻量元数据 |
| Cd 预测模块 | `app/api/cd_prediction.py`、`app/models/cd_prediction/` | 后续扩展重金属风险能力 | 当前 change 不接真实模型 |
| 项目说明 | `README.md` | 了解 FastAPI + PostGIS 架构 | 文档参考 |

## `D:\work\suan\AcidificationModel\api`

| 类别 | 参考位置 | 用途 | 使用方式 |
| --- | --- | --- | --- |
| 酸化诊断链路 | `app/ph_cd_coupling/service.py` | 理解酸化与 Cd 耦合输入输出 | 当前用结构化规则占位 |
| 位置最近邻 | `app/ph_cd_coupling/location_cd_source.py` | 后续实现点位补齐策略 | 当前记录为回退设计 |
| Demo 资产组织 | `demo/ph_cd_coupling_demo/samples/` | 样例请求和 seed 数据组织方式 | 可迁移思路，不依赖运行 |
| 文档生成工具 | `agent/tools/document_generator.py` | 后续报告生成能力参考 | 当前仅输出结构化摘要 |

## 禁止项

- 不修改 `D:\work\AcidMap` 或 `D:\work\suan\AcidificationModel\api` 下的任何源码。
- 不通过启动历史项目服务来完成当前仓库的验证。
- 不把历史项目数据库作为当前仓库接口成功的前置条件。
