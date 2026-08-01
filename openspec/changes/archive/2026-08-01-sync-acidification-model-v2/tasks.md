## 1. 版本标识升级

- [x] 1.1 在 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 将 `MODEL_VERSION` 从 `process_v1_20260801` 升级为 `process_v2_20260801`
- [x] 1.2 在 `framework/domain/other_models/model_4.py` 同步 3 处 fallback 返回值中的 `model_version` 字段（`process_v1_20260801` → `process_v2_20260801`，含 model_unavailable 和 cannot_get_ph 两处）
- [x] 1.3 更新 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 模块 docstring 中的源码路径引用（从 `02_酸化模型计算-地块.py` 更新为 `02_酸化模型计算.py` v2 版本，注明"原理文档 01_产酸过程计算公式.docx 有笔误，以源码为准"）

## 2. run_csv 批量计算函数实现

- [x] 2.1 在 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 新增 `run_csv(input_file, output_file, land_type, fertilizer_type) -> pd.DataFrame` 函数，签名与 v2 源码一致
- [x] 2.2 实现 CSV 读取逻辑：支持 `SJD` 或 `pH` 列名（`p = "SJD" if "SJD" in df else "pH"`），校验必填列（SJD/pH、Hex、Alex），缺失抛 `ValueError`
- [x] 2.3 实现批量计算逻辑：构建子模型映射 `{("paddy","urea"):_paddy_urea, ...}`，对每行数据调用对应子模型（含 NaN 行输出 7 个 None，不抛异常）
- [x] 2.4 实现 CSV 输出逻辑：输出列包含输入列（TYBH/SJD/Hex/Alex）+ 中间变量列（Adep/Acrop/ANcy/Aagri/Aback）+ 结果列（YTK/MBNT），结果保留 2 位小数（`round(x,2)`），编码 `utf-8-sig`
- [x] 2.5 run_csv 内部调用项目现有的 `_paddy_urea`/`_paddy_compound`/`_upland_urea`/`_upland_compound` 子模型函数（不重复实现公式），传入默认参数组装逻辑（复用 `_PADDY_DEFAULTS`/`_UPLAND_DEFAULTS`/`_PADDY_COMPOUND_EXTRA`/`_UPLAND_COMPOUND_EXTRA`）

## 3. CLI 脚本实现

- [x] 3.1 新建 `scripts/run_acidification_batch.py`，使用 argparse 定义 4 个必填参数：`--input`、`--output`、`--land`（paddy|upland）、`--fertilizer`（urea|compound）
- [x] 3.2 在 CLI 脚本中调用 `ai_culti_demo.farmland_diagnosis.acidification.run_csv`，处理异常（ValueError 友好提示，退出码 1）
- [x] 3.3 CLI 脚本成功时输出处理行数，退出码 0；在 docstring 中提示"输入数据质量由用户自行检查，run_csv 不做越界校验"

## 4. v2 测试数据准备

- [x] 4.1 创建目录 `tests/data/acidification_v2/`
- [x] 4.2 复制 v2 源码目录的 `03_Data.csv` 到 `tests/data/acidification_v2/03_Data.csv`（393 地块输入数据）
- [x] 4.3 复制 v2 源码目录的 `04_旱地复合肥计算结果.csv` 到 `tests/data/acidification_v2/04_upland_compound_expected.csv`（期望输出，旱地+复合肥场景）

## 5. 回归测试实现

- [x] 5.1 在 `tests/test_model4_acidification.py` 新增 `test_acidification_v2_regression` 测试函数：读取 `tests/data/acidification_v2/03_Data.csv` 和 `04_upland_compound_expected.csv`
- [x] 5.2 测试调用 `run_csv` 以 `land_type="upland"`、`fertilizer_type="compound"` 执行批量计算，对比 393 个地块的 `YTK`/`MBNT` 与期望值偏差 < 0.01
- [x] 5.3 测试覆盖极端值场景：验证输入数据中 `Alex=8.95`、`SJD=4.19`、`Hex=1.62` 等极端值行能正常计算（不单独断言，通过全量对比覆盖）

## 6. 现有测试更新

- [x] 6.1 更新 `tests/test_model4_acidification.py` 中 `test_model_version_present` 的断言：`process_v1_20260801` → `process_v2_20260801`
- [x] 6.2 更新 `tests/test_model4_acidification.py` 中 `test_model4_execution_direct_inputs` 的 `model_version` 断言：`process_v1_20260801` → `process_v2_20260801`
- [x] 6.3 运行现有 `test_model4_acidification.py` 全部测试，确认无回归（除版本号断言外，其他测试逻辑不变）

## 7. 文档与 spec 同步

- [x] 7.1 确认 delta spec `openspec/changes/sync-acidification-model-v2/specs/farmland-acidification-improvement-model/spec.md` 内容完整（已在 open 阶段创建）
- [x] 7.2 检查 `framework/agents/specialized/acidification_agent.py` 的 `model_version` 字段透传是否正确（无代码改动，仅验证）
- [x] 7.3 检查是否需要更新 `README.md` 或 `api.md` 中关于酸化模型版本的描述（run_csv 不暴露为 API，通常无需更新 api.md；README 若有版本提及则同步）

## 8. 集成验证

- [x] 8.1 运行 `python scripts/run_acidification_batch.py --input tests/data/acidification_v2/03_Data.csv --output tests/data/acidification_v2/_test_output.csv --land upland --fertilizer compound`，确认 CLI 脚本工作正常
- [x] 8.2 对比 CLI 脚本输出与 `04_upland_compound_expected.csv`，确认完全一致
- [x] 8.3 运行完整测试套件 `pytest tests/test_model4_acidification.py -v`，确认所有测试通过
- [x] 8.4 运行酸化相关 agent 测试（`tests/test_agent_specialized.py` 等），确认 model_version 透传无回归
