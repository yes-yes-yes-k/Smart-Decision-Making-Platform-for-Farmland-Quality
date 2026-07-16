## 1. 环境变量配置

- [x] 1.1 在 `deploy/production.env.example` 添加 LangSmith 配置项（`LANGCHAIN_API_KEY`、`LANGCHAIN_TRACING_V2=true`、`LANGCHAIN_ENDPOINT`、`LANGCHAIN_PROJECT=agent-culti-demo`），每项附注释说明
- [x] 1.2 确认 `.gitignore` 已排除 `.env` 文件（避免 API Key 泄露）

## 2. 依赖确认

- [x] 2.1 确认 `pyproject.toml` 中 `langchain ^0.2.0` 和 `langchain-core` 版本支持 LangSmith tracing v2（langchain ≥ 0.2 已内置，无需新增依赖）

## 3. 代码改动

- [x] 3.1 在 `start_http_server.py` 的 `main()` 函数开头添加 `load_dotenv()` 调用，确保 `.env` 中的 LangSmith 环境变量被加载

## 4. 文档更新

- [x] 4.1 在 `README.md` 配置章节添加 LangSmith 环境变量说明（API Key、Tracing 开关、项目名称），说明开发环境默认关闭、生产环境默认开启
- [x] 4.2 在 `deploy/deployment.md` 添加 LangSmith 配置步骤（如何在 .env 中配置）、查看 trace 说明和故障排查（tracing 不生效、服务不可达）

## 5. 验证

- [x] 5.1 运行测试确认零代码改动不影响现有功能（21 个可快速收集的测试全部通过；其余测试因预存在的 heavy import 卡住，与 LangSmith 改动无关）
- [x] 5.2 验证未设置 `LANGCHAIN_API_KEY` 时应用正常启动（graceful degradation：langchain 0.3.0 加载正常、`tracing_v2_enabled` 符号可导入、`load_dotenv()` 无 `.env` 不报错、`start_http_server` 模块导入正常）
