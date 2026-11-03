# OpenSPG / KAG 离线 POC 环境结论

## 结论

任务 2.3 当前采用“记录环境/依赖阻断证据”路径，而不是声明已经完成可运行抽取。2026-10-23 的工作区探测结果位于 `artifacts/knowledge_platform/openspg-poc-environment.json`：当前 Windows 环境存在 `wsl.exe` 命令但子系统未安装，同时无 Docker CLI / Docker Compose；项目虚拟环境也没有 `kag` 与 `knext` 模块，且尚未配置隔离的 OpenSPG Server 和模型提供方。因此 `ready_for_offline_poc=false`。

OpenSPG/KAG 官方快速开始要求通过 Docker Compose 启动引擎及依赖镜像；开发者示例还需要先提交项目 Schema，再运行 Builder，Builder 的 `SchemaClient` 会访问 OpenSPG 服务。该运行模型不适合未经隔离直接塞入当前主服务虚拟环境。

## 复现探测

探测只记录能力是否存在和版本文本，不读取或输出模型密钥：

```powershell
python scripts/probe_openspg_environment.py `
  --output artifacts/knowledge_platform/openspg-poc-environment.json
```

若把它用作 CI 强制门禁，增加 `--require-ready`；环境不完整时退出码为 2。

## 解除阻断条件

后续开展真实 POC 时必须：

1. 使用独立容器/虚拟环境固定 OpenSPG/KAG 0.8.0 工件与 SHA-256，不修改主应用依赖；
2. 提供隔离的 OpenSPG Server、测试 project 和耕地质量 Schema；
3. 使用非生产模型凭据，只处理 94 条金标对应的脱敏片段；
4. 将 Builder 输出转换为现有 `ExtractionResult`，不允许 Writer 连接生产图；
5. 运行 adapter conformance suite，并记录质量、吞吐、成本和版本后，才能进入任务 2.5。

## 官方依据

- <https://github.com/OpenSPG/KAG>
- <https://github.com/OpenSPG/KAG/tree/master/kag/examples/medicine>
- <https://github.com/OpenSPG/KAG/blob/master/kag/builder/component/extractor/schema_free_extractor.py>
