# 知识平台开源组件清单

本清单用于选型与许可证治理，不表示所有组件已经安装。机器可读基线位于 `governance/knowledge-platform/oss-components.cdx.json`，采用 CycloneDX 1.5；生产引入前必须固定工件 SHA-256，并通过 `GraphExtractionBackend` 或 `GraphStore` 一致性测试。

| 组件 | 评估基线 | 计划用途 | 许可证 | 当前决策 |
|---|---:|---|---|---|
| Microsoft GraphRAG | 3.3.0 | 实体、关系、claim 候选抽取 | MIT | 首选抽取适配器，待金标评测 |
| OpenSPG / KAG | 0.8.0 | 领域构图、标准化与推理对照 | Apache-2.0 | 离线 POC/候选回退，暂不作为强依赖 |
| Apache AGE | 1.6.0-pg16 | PostgreSQL 属性图与 openCypher 查询 | Apache-2.0 | 已固定 PG16 release；默认仍使用 JSON，双读通过后才允许切主读 |
| Neo4j GraphRAG Python | 1.21.0 | 构图实验 | Apache-2.0 | 延后，不作为默认路径 |

## 官方来源

- Microsoft GraphRAG: <https://github.com/microsoft/graphrag>
- OpenSPG: <https://github.com/OpenSPG/openspg>
- KAG: <https://github.com/OpenSPG/KAG>
- Apache AGE: <https://age.apache.org/>
- Neo4j GraphRAG Python: <https://github.com/neo4j/neo4j-graphrag-python>

## 引入门槛

1. 固定版本与工件哈希；
2. 记录直接和传递依赖许可证；
3. 生成机器可读 SBOM；
4. 通过候选契约、幂等、证据定位和 schema 方向测试；
5. 与当前生产版本执行结果差异评估；
6. 预留关闭和回退开关。

## 校验与升级门禁

只校验当前 SBOM：

```powershell
python scripts/check_knowledge_platform_components.py `
  --candidate governance/knowledge-platform/oss-components.cdx.json
```

升级时同时传入已批准基线和候选文件。新增、删除、版本或源码 revision 变化必须附带通过的金标评测报告；许可证或源码地址变化还必须人工完成供应链审核。状态为 `selected` 的组件必须记录已验证的工件 SHA-256，只有处于 `evaluation` 或 `deferred` 的组件可以暂记为待下载校验。
