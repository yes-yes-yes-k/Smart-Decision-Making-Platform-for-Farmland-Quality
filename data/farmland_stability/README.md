# 模型1 v2 数据部署与分发说明

本目录存放模型1 v2（`model1_v2_20260801`）“耕地质量等级稳定性与退化风险识别模型”的三期运行数据和本地预计算产物。模型运行时只读取本目录，不依赖外部模型交付路径。

## 数据版本与来源

| 项目 | 说明 |
| --- | --- |
| 模型版本 | `model1_v2_20260801` |
| 数据期次 | 2018、2021、2024 |
| 当前期 | 2024 |
| 地块统一编码 | `TYBH` |
| 原始交付来源 | 模型1 v2 交付包，最近更新时间 2026-08-01 |
| 本机交付包位置 | `D:\work\2026\0801\模型1_v2\模型1_v2`，仅用于一次性导入和校验，不是运行依赖 |
| 项目运行位置 | `data/farmland_stability` |

分发前应确认耕地质量空间数据的授权范围、脱敏要求和接收方权限。不得将该数据直接提交到公开 Git 仓库。

## 标准数据包

标准数据包用于接收方在本地重新执行模型1 v2。必须同时提供以下 15 个原始输入文件和本目录的 `manifest.json`：

| 年份 | 必需组件 |
| --- | --- |
| 2018 | `2018_测试数据.cpg`、`.dbf`、`.prj`、`.shp`、`.shx` |
| 2021 | `2021_测试数据.cpg`、`.dbf`、`.prj`、`.shp`、`.shx` |
| 2024 | `2024_测试数据.cpg`、`.dbf`、`.prj`、`.shp`、`.shx` |

Shapefile 的五个组件缺一不可。接收方应将它们解压到项目的 `data/farmland_stability` 目录，不要嵌套额外目录。

## SHA-256 校验值

以下校验值对应本机已完成 v2 输出比对的原始输入数据。接收方可以在 PowerShell 中使用 `Get-FileHash <文件> -Algorithm SHA256` 校验。

| 文件 | 大小（字节） | SHA-256 |
| --- | ---: | --- |
| `2018_测试数据.cpg` | 5 | `3AD3031F5503A4404AF825262EE8232CC04D4EA6683D42C5DD0A2F2A27AC9824` |
| `2018_测试数据.dbf` | 14,780,658 | `E0665841671D60D4F84A563F84F9D415FC2ABE40A27E571EB4562198C51D0B3D` |
| `2018_测试数据.prj` | 176 | `B10DBE4D6D1DE908D340F892C90B3D31A552630AF3742BB515BFE1BD26124F2C` |
| `2018_测试数据.shp` | 20,918,264 | `F55FFEABF1B3CE9C79E40DD8C135EBF02255044D831A0F0B7F7ED58EEA736D21` |
| `2018_测试数据.shx` | 44,004 | `A850E616209C57945B3A172D52F5CE56FB80EE83F77E2FE1BC813678A6CAD416` |
| `2021_测试数据.cpg` | 5 | `3AD3031F5503A4404AF825262EE8232CC04D4EA6683D42C5DD0A2F2A27AC9824` |
| `2021_测试数据.dbf` | 14,780,658 | `43361577A91F7D20B3BDEE685DD51DFAA6C236DCDEE1214EA5123BB9E81828F4` |
| `2021_测试数据.prj` | 176 | `B10DBE4D6D1DE908D340F892C90B3D31A552630AF3742BB515BFE1BD26124F2C` |
| `2021_测试数据.shp` | 20,918,264 | `F55FFEABF1B3CE9C79E40DD8C135EBF02255044D831A0F0B7F7ED58EEA736D21` |
| `2021_测试数据.shx` | 44,004 | `A850E616209C57945B3A172D52F5CE56FB80EE83F77E2FE1BC813678A6CAD416` |
| `2024_测试数据.cpg` | 5 | `3AD3031F5503A4404AF825262EE8232CC04D4EA6683D42C5DD0A2F2A27AC9824` |
| `2024_测试数据.dbf` | 14,780,658 | `BE2FD9EE572BD5AE32ACE21F88D06E0F1DACF344A777D39CB08B4BE9FE8C7185` |
| `2024_测试数据.prj` | 176 | `B10DBE4D6D1DE908D340F892C90B3D31A552630AF3742BB515BFE1BD26124F2C` |
| `2024_测试数据.shp` | 20,918,264 | `F55FFEABF1B3CE9C79E40DD8C135EBF02255044D831A0F0B7F7ED58EEA736D21` |
| `2024_测试数据.shx` | 44,004 | `A850E616209C57945B3A172D52F5CE56FB80EE83F77E2FE1BC813678A6CAD416` |

## 输入字段口径

每期数据必须具有下列字段：

- 地块与分区：`TYBH`、`PJFQ`。
- 质量结果：`ZHQZ`、`GDZLDJ`。
- 12 个 v2 指标：`SJD`、`YJZ`、`YXL`、`SXJ`、`TRRZ`、`GCZD`、`GGNL`、`PSNL`、`DXBW`、`ZDGX`、`YXTCHD`、`GCHD`。
- 每个指标对应的隶属度和权重字段：`<指标>LSD`、`<指标>QZ`。

`manifest.json` 已声明当前期为 2024、三期计算年份和 `id_column=TYBH`。三期文件均参与模型1的历史趋势、关键因子退化和持续低质等时间序列计算。

## 接收方部署步骤

1. 获取项目代码，并将标准数据包解压到 `data/farmland_stability`。
2. 使用本项目指定的 Python 3.12 Conda 环境安装项目依赖。模型1需要 GeoPandas、SciPy、Shapely、Pyogrio 和 PROJ 数据库。
3. 校验上述 15 个文件的 SHA-256。
4. 在项目根目录执行预计算：

```powershell
& 'C:\Users\PC\.conda\envs\agent_culti_demo_py312\python.exe' `
  -m ai_culti_demo.farmland_stability.precompute
```

5. 成功后将生成以下本地文件：

```text
data/farmland_stability/stability_results.db
data/farmland_stability/stability_results.shp
data/farmland_stability/stability_results.xlsx
```

预计算会处理三期数据中的 5,488 个地块，并将九模块结果保存到 `stability_results.db`，供模型1在线查询和 Agent 调用。

## 快速演示包

快速演示包适用于接收方无需重新预计算、直接进行模型1查询的场景。它应包含：

- 标准数据包的全部内容；
- 已生成的 `stability_results.db`；
- 可选的 `stability_results.shp` 和 `stability_results.xlsx`，用于 GIS 或表格审阅。

接收方将快速演示包解压到相同目录后，可直接调用模型1查询。若替换任一原始 Shapefile，必须重新运行预计算，不能继续使用旧的 `stability_results.db`。

## Git 与分发边界

原始 Shapefile 和预计算结果均被 `.gitignore` 排除，避免大文件和受控空间数据进入仓库。`manifest.json`、本 README 和模型代码会纳入版本控制，确保部署方式和字段口径可追溯。
