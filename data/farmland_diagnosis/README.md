# 耕地诊断模型数据目录

本目录存放模型3（耕地质量主要问题精准识别与酸化改良模型）所需的 CSV 测试数据。

## 数据文件

| 文件 | 说明 | 大小 |
|------|------|------|
| `test.csv` | 原始指标数据（输入） | ~1.7MB |
| `test_with_LD.csv` | 含隶属度计算结果（calculator.py 输出） | ~7.3MB |
| `test_with_LD_diagnosis.csv` | 含障碍诊断结果（calculator2.py 输出） | ~6.8MB |

## 数据字段

### test.csv（输入）

12 项耕地质量指标原始值，包含：pH、有机质、有效磷、速效钾、耕层厚度、容重、阳离子交换量等。

### test_with_LD.csv（中间结果）

在原始指标基础上新增各指标的隶属度值和综合权重。

### test_with_LD_diagnosis.csv（诊断结果）

在中间结果基础上新增：障碍类型、主要障碍因素、次要障碍因素、酸化程度分区、改良方案。

## 数据来源

外部数据源：`F:\BaiduNetdiskDownload\模型3\模型3\`

## 部署方式

CSV 为大文件，已通过 `.gitignore` 排除，不入库。部署时需手动从外部数据源复制：

```powershell
$src = "F:\BaiduNetdiskDownload\模型3\模型3"
$dst = "data\farmland_diagnosis"
foreach ($f in @("test.csv","test_with_LD.csv","test_with_LD_diagnosis.csv")) {
    Copy-Item "$src\$f" $dst -Force
}
```

## 批量评价流程

数据部署后，运行批量评价和诊断脚本：

```bash
# 批量评价（生成 test_with_LD.csv）
python -m src.ai_culti_demo.farmland_diagnosis.batch_evaluate

# 批量障碍诊断（生成 test_with_LD_diagnosis.csv）
python -m src.ai_culti_demo.farmland_diagnosis.batch_diagnose
```

在线查询通过 `query_parcel(parcel_id)` 和 `query_acidification(parcel_id)` 接口读取诊断结果。
