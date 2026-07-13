## Why

项目代码和数据配置中存在硬编码的 Windows 绝对路径（如 `D:\\work\\AcidMap`、`D:\\work\\2026\\0704\\耕地质量大模型-数据\\耕地质量大模型-数据`），这些路径指向开发机器上的外部目录，在其他环境中无法使用，且违反了项目可移植性原则。

## What Changes

- 将 `data/lechang/catalog.json` 中的 `source_root` 从绝对路径改为项目相对路径
- 将 `src/ai_culti_demo/diagnosis.py` 中 `referenced_assets` 的绝对路径改为项目相对路径
- 将 `src/ai_culti_demo/thematic_models.py` 中 `referenced_assets` 的绝对路径改为项目相对路径

## Impact

- **代码影响**: 3 个文件修改，改动量极小
- **功能影响**: 无功能变化（这些路径仅用于 lineage/溯源记录，`runtime_dependency: "none"`）
- **可移植性**: 项目可在不同环境中正确引用数据路径
