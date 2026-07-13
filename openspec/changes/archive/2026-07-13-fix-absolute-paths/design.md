## Context

项目中有 5 处硬编码的 Windows 绝对路径引用，分布在 3 个文件中。这些路径指向开发机器上的外部数据/模型目录，仅用于 lineage 溯源记录，运行时不依赖（`runtime_dependency: "none"`）。

## Changes

### 1. catalog.json source_root

将 `D:\\work\\2026\\0704\\耕地质量大模型-数据\\耕地质量大模型-数据` 改为 `data/lechang/source`。assets 中的 path 字段已经是相对于 source_root 的相对路径，无需修改。

### 2. diagnosis.py referenced_assets

将 `D:\\work\\AcidMap` 和 `D:\\work\\suan\\AcidificationModel\\api` 改为 `external/AcidMap` 和 `external/AcidificationModel/api`，表示这些是外部引用路径。

### 3. thematic_models.py referenced_assets

同 diagnosis.py，将相同的绝对路径改为相同的相对路径。

## Risks

- [数据文件不存在] → `data/lechang/source` 目录可能不存在，但这些路径仅用于溯源记录，不影响运行时功能
- [外部路径语义] → `external/` 前缀表示这些是项目外部引用，清晰区分项目内和项目外路径
