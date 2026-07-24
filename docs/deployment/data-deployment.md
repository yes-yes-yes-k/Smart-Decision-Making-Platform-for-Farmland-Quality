# 数据部署说明

本文档说明 add-stability-risk-and-grade-evaluation change 所需的外部数据文件部署方式。

## 目录结构

```
项目根/
├── data/
│   ├── farmland_stability/      # 模型1 shapefile 测试数据
│   │   ├── 2018_测试数据.shp (+ .cpg/.dbf/.prj/.shx)
│   │   ├── 2021_测试数据.shp (+ .cpg/.dbf/.prj/.shx)
│   │   ├── 2024_测试数据.shp (+ .cpg/.dbf/.prj/.shx)
│   │   └── README.md
│   ├── farmland_diagnosis/      # 模型3 CSV 测试数据
│   │   ├── test.csv                    # 原始指标数据
│   │   ├── test_with_LD.csv            # 含隶属度计算结果
│   │   ├── test_with_LD_diagnosis.csv  # 含障碍诊断结果
│   │   └── README.md
│   ├── fertility/               # 已有：Fertility ML 训练数据（入库）
│   └── lechang/                 # 已有：乐昌土壤数据
├── bin/
│   └── farmland_quality_eval/   # Fortran exe 及数据库
│       ├── Farmland_quality_evaluation.exe
│       ├── Farmlands_Quality_Level_Database.dat
│       └── README.md
└── instance/
    └── farmland_stability.db    # 预计算结果 SQLite（运行时生成）
```

## 外部数据源

所有外部数据位于 `F:\BaiduNetdiskDownload\`：

| 模型 | 外部路径 | 用途 |
|------|---------|------|
| 模型1（稳定性风险） | `F:\BaiduNetdiskDownload\模型1\` | 3 期 shapefile 测试数据 |
| 模型3（诊断/酸化） | `F:\BaiduNetdiskDownload\模型3\模型3\` | CSV 测试数据 |
| 耕地质量等级 exe | `F:\BaiduNetdiskDownload\耕地质量等级和障碍度\` | Fortran exe + .dat 数据库 |

## 一键部署脚本

在项目根目录执行以下 PowerShell 脚本完成全部数据部署：

```powershell
# 模型1 shapefile
$src1 = "F:\BaiduNetdiskDownload\模型1"
$dst1 = "data\farmland_stability"
foreach ($year in @("2018","2021","2024")) {
    foreach ($ext in @("cpg","dbf","prj","shp","shx")) {
        Copy-Item "$src1\${year}_测试数据.$ext" $dst1 -Force
    }
}

# 模型3 CSV
$src3 = "F:\BaiduNetdiskDownload\模型3\模型3"
$dst3 = "data\farmland_diagnosis"
foreach ($f in @("test.csv","test_with_LD.csv","test_with_LD_diagnosis.csv")) {
    Copy-Item "$src3\$f" $dst3 -Force
}

# Fortran exe
$srcE = "F:\BaiduNetdiskDownload\耕地质量等级和障碍度"
$dstE = "bin\farmland_quality_eval"
Copy-Item "$srcE\Farmland_quality_evaluation.exe" $dstE -Force
Copy-Item "$srcE\Farmlands_Quality_Level_Database.dat" $dstE -Force
```

## 版本控制策略

以下文件通过 `.gitignore` 排除，不入库（大文件/二进制）：

- `data/farmland_stability/*`（shapefile，每期约 36MB）
- `data/farmland_diagnosis/*`（CSV，最大约 7MB）
- `bin/farmland_quality_eval/*`（exe/.dat 二进制）

各目录保留 `README.md` 入库，记录文件结构和部署方式。

## 部署后验证

部署完成后，运行以下命令验证文件完整性：

```powershell
# 验证模型1 shapefile（每期 5 个文件）
Get-ChildItem data\farmland_stability\*.shp | Measure-Object | Select-Object Count
# 期望：3

# 验证模型3 CSV
Get-ChildItem data\farmland_diagnosis\*.csv | Measure-Object | Select-Object Count
# 期望：3

# 验证 exe 部署
Test-Path bin\farmland_quality_eval\Farmland_quality_evaluation.exe
Test-Path bin\farmland_quality_eval\Farmlands_Quality_Level_Database.dat
# 期望：True / True
```

## 预计算与初始化

数据部署后，按需运行以下初始化命令：

```bash
# 模型1 离线预计算（处理 3 期 shapefile，生成 SQLite 结果）
python -m src.ai_culti_demo.farmland_stability.precompute

# 模型3 批量评价和诊断（处理 CSV，生成诊断结果）
python -m src.ai_culti_demo.farmland_diagnosis.batch_evaluate
python -m src.ai_culti_demo.farmland_diagnosis.batch_diagnose
```

预计算结果存储在 `instance/` 目录下，已通过 `.gitignore` 排除。
