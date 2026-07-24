# 耕地质量稳定性模型数据目录

本目录存放模型1（耕地质量稳定性与退化风险评价模型）所需的 3 期历史 shapefile 测试数据。

## 数据文件

| 文件 | 说明 |
|------|------|
| `2018_测试数据.shp` (及 .cpg/.dbf/.prj/.shx) | 2018 年耕地质量测试数据 |
| `2021_测试数据.shp` (及 .cpg/.dbf/.prj/.shx) | 2021 年耕地质量测试数据 |
| `2024_测试数据.shp` (及 .cpg/.dbf/.prj/.shx) | 2024 年耕地质量测试数据 |

## 必需字段

每期 shapefile 需包含以下字段：

- 12 指标 LSD/QZ：`LSD1`~`LSD12`、`QZ1`~`QZ12`
- 综合质量指数：`ZHQZ`
- 耕地质量等级：`GDZLDJ`
- 地块 ID：`ID`
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

## 预计算流程

数据部署后，运行离线预计算脚本生成持久化结果：

```bash
python -m src.ai_culti_demo.farmland_stability.precompute
```

预计算结果存储在 SQLite 数据库（`instance/farmland_stability.db`），在线查询通过 `get_parcel_result(parcel_id, module)` 接口读取。
