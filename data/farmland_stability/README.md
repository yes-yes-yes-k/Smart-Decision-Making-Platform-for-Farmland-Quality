# 耕地质量稳定性模型数据目录

本目录存放模型1 v2（2026-08-01，耕地质量稳定性与退化风险评价模型）所需的 3 期 Shapefile 数据。运行时只读取本目录，不依赖外部模型交付路径。

## 数据文件

| 文件 | 说明 |
|------|------|
| `2018_测试数据.shp` (及 .cpg/.dbf/.prj/.shx) | 2018 年耕地质量测试数据 |
| `2021_测试数据.shp` (及 .cpg/.dbf/.prj/.shx) | 2021 年耕地质量测试数据 |
| `2024_测试数据.shp` (及 .cpg/.dbf/.prj/.shx) | 2024 年耕地质量测试数据 |

## 必需字段

每期 shapefile 需包含以下字段：

- 12 指标 LSD/QZ：`SJD`、`YJZ`、`YXL`、`SXJ`、`TRRZ`、`GCZD`、`GGNL`、`PSNL`、`DXBW`、`ZDGX`、`YXTCHD`、`GCHD` 的 `LSD`、`QZ` 后缀字段
- 综合质量指数：`ZHQZ`
- 耕地质量等级：`GDZLDJ`
- 地块统一编码：`TYBH`
- 区域字段：`PJFQ`（评价分区）

## 数据来源

外部数据源：`F:\BaiduNetdiskDownload\模型1\`

## 部署方式

shapefile 为大文件（每期约 36MB），已通过 `.gitignore` 排除，不入库。部署时需手动从外部数据源复制：

```powershell
$src = "F:\BaiduNetdiskDownload\模型1"
$dst = "data\farmland_stability"
foreach ($year in @("2018","2021","2024")) {
    foreach ($ext in @("cpg","dbf","prj","shp","shx")) {
        Copy-Item "$src\${year}_测试数据.$ext" $dst -Force
    }
}
```

## 通过 HTTP API 部署

通过 `POST /api/v1/data/import` 接口上传 shapefile zip 包，需 admin 权限。接口会将 zip 解压并扁平化部署到本目录，并自动触发 `precompute.main` 预计算与持久化。

### zip 打包要求

zip 包内需包含：

- 1 个 `manifest.json` 清单文件
- 每期 shapefile 的 5 个组件文件（`.shp` / `.cpg` / `.dbf` / `.prj` / `.shx`）

限制：文件数 ≤ 30、解压后总大小 ≤ 200MB、不得包含路径穿越条目。

### manifest.json 格式

清单文件需包含以下 5 个字段：

```json
{
    "current_year": 2024,
    "history_years": [2020, 2021],
    "years": [2020, 2021, 2024],
    "current_filename": "current.shp",
    "history_filenames": ["2020.shp", "2021.shp"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `current_year` | int | 当期年份 |
| `history_years` | array | 历史年份列表 |
| `years` | array | 全部年份列表（含当期） |
| `current_filename` | string | 当期 shapefile 主文件名（.shp） |
| `history_filenames` | array | 历史期 shapefile 主文件名列表（.shp） |

### curl 示例

```bash
# 1. 登录获取 token（需 admin 账号）
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 2. 上传 shapefile zip 包（替换 <token>）
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <token>" \
  -F "data_type=shapefile" \
  -F "file=@/path/to/stability_data.zip"
```

部署成功后接口返回 `deployed_path` 与 `backup_path`，部署前会自动备份现有 shapefile 到 `backup/YYYYMMDD-HHMMSS/`（保留最近 3 份）。触发 `precompute.main` 失败或超时（600s）时会自动回滚到备份。

## 预计算流程

数据部署后，运行离线预计算脚本生成持久化结果：

```bash
python -m src.ai_culti_demo.farmland_stability.precompute
```

预计算结果存储在 SQLite 数据库（`instance/farmland_stability.db`），在线查询通过 `get_parcel_result(parcel_id, module)` 接口读取。
