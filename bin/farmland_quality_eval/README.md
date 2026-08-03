# 耕地质量等级评价 Python 模型部署目录

本目录存放耕地质量等级和障碍度评价的 CSV 数据文件。

## 部署文件

| 文件 | 说明 |
|------|------|
| `Farmland_quality_Level_Database.csv` | 耕地质量评价指标数据库（CSV，20 字段，1193 地块） |

## 数据来源

外部数据源：`D:\destkop\模型\模型2\Farmland_quality_Level_Database.csv`

## 部署方式

CSV 文件已入库（不再被 .gitignore 排除），无需手动复制。如需更新数据，通过 HTTP API 上传：

```bash
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <token>" \
  -F "data_type=dat" \
  -F "file=@/path/to/Farmland_quality_Level_Database.csv"
```

## 调用契约

包装器 `src/ai_culti_demo/farmland_grade_eval/runner.py` 通过 Python 直接调用评价模块：

- **数据加载**：`load_parcels_from_csv` 读取 CSV（UTF-8-sig），解析为 Parcel 列表
- **评价计算**：`evaluate_land_quality` 计算隶属度、综合指数、等级
- **障碍度**：`compute_obstacle_factors` 计算障碍度因子排序
- **缓存**：类级缓存 + mtime 校验，CSV 重新部署后自动失效重载

## 启动时部署校验

系统启动时会调用 `FarmlandGradeRunner.check_deployment()` 校验：

- CSV 文件存在且非空

校验失败时返回 `status: "error"`，`error.code: "DEPLOYMENT_ERROR"`，阻止后续调用。

## 模型版本

`MODEL_VERSION = "python_v1_20260801"`

## 通过 HTTP API 部署

通过 `POST /api/v1/data/import` 接口上传 CSV 文件（data_type=dat），需 admin 权限。接口会将上传文件部署为本目录下的 `Farmland_quality_Level_Database.csv`（固定文件名），并自动触发 `FarmlandGradeRunner.check_deployment` 部署校验。

校验要求：文件非空、≤ 200MB、UTF-8 编码、含 20 个必需字段。

部署成功后接口返回 `deployed_path` 与 `backup_path`，部署前会自动备份现有 CSV 文件到 `backup/YYYYMMDD-HHMMSS/`（保留最近 3 份）。触发 `check_deployment` 失败时会自动回滚到备份。
