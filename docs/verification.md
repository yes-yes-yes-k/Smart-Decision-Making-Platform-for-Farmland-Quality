# 验证记录

## 验证目标

本 change 的验证重点是基础能力是否可被调用、返回是否结构化、是否包含来源与回退说明，以及是否不依赖历史项目在线运行。

## 验证命令

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests
python -m ai_culti_demo.cli overview
python -m ai_culti_demo.cli diagnose --topic acidification
python -m ai_culti_demo.cli diagnose --topic bad-topic
python -m ai_culti_demo.cli report --topic improvement
python -m ai_culti_demo.cli verify
openspec validate bootstrap-lechang-county-demo --strict
```

## 验收点

| 验收点 | 覆盖方式 |
| --- | --- |
| 总览接口返回区域和图层列表 | `test_overview_returns_layers` |
| 诊断接口支持酸化主题 | `test_diagnosis_returns_machine_readable_payload` |
| 缺少坐标时返回回退说明 | `test_diagnosis_marks_missing_location_fallback` |
| 无效主题返回结构化错误 | `test_invalid_topic_returns_error_code` |
| 结果整理接口返回结构化字段 | `test_report_summary_uses_diagnosis` |
| 非侵入式运行时校验 | `test_runtime_check_has_no_external_runtime_dependency` |

## 当前限制

- 当前诊断结论为规则占位结果，可靠性标记为 `demo_stub`。
- 当前没有读取 shapefile 或 tif 的真实几何内容，只返回来源元数据与可调用契约。
- 当前 HTTP Server 使用 Python 标准库，适合联调，不作为生产服务形态。
