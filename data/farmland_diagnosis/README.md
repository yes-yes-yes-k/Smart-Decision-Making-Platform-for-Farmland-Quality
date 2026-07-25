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

## 通过 HTTP API 部署

通过 `POST /api/v1/data/import` 接口上传 CSV，需 admin 权限。接口会将上传文件部署为本目录下的 `test.csv`（固定文件名），并自动触发 `bulk_evaluate` 批量评价。

### 必需列

CSV 需包含以下 14 列（列名一致，顺序不限）：

`一级农业区`、`二级农业区`、`pH`、`有机质`、`有效磷`、`速效钾`、`容重`、`耕层质地`、`灌溉能力`、`排水能力`、`地形部位`、`质地构型`、`有效土层`、`耕层厚度`

文件编码支持 UTF-8（失败时回退 GBK），大小限制 200MB。

### curl 示例

```bash
# 1. 登录获取 token（需 admin 账号）
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 2. 上传 CSV（替换 <token>）
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <token>" \
  -F "data_type=csv" \
  -F "file=@/path/to/test.csv"
```

部署成功后接口返回 `deployed_path` 与 `backup_path`，部署前会自动备份现有 `test.csv` 到 `backup/YYYYMMDD-HHMMSS/`（保留最近 3 份）。触发 `bulk_evaluate` 失败时会自动回滚到备份。

## 批量评价流程

数据部署后，运行批量评价和诊断脚本：

```bash
# 批量评价（生成 test_with_LD.csv）
python -m src.ai_culti_demo.farmland_diagnosis.batch_evaluate

# 批量障碍诊断（生成 test_with_LD_diagnosis.csv）
python -m src.ai_culti_demo.farmland_diagnosis.batch_diagnose
```

在线查询通过 `query_parcel(parcel_id)` 和 `query_acidification(parcel_id)` 接口读取诊断结果。
