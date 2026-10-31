## 1. 移植数据集导入

- [ ] 1.1 新增 `framework/domain/other_models/heavy_metal_cd_ported.py`：源表读取（`Farmland_data`/`CropCd_input_data`/`EffCd_input_data`/`MSM_output_data`）、特征行组装、`SGD_` 命名空间生成
- [ ] 1.2 列映射按 ORM 语义硬编码（`CropCd_input_data` 的 `AvaP`/`AvaK` 交叉）：`available_phosphorus ← AvaK_IDW`、`available_potassium ← AvaP_IDW`；有效态不交叉
- [ ] 1.3 新增 `scripts/import_ported_cd_dataset.py`：`--model` / `--limit` / `--apply` / `--rollback`，默认 dry-run 打印预检与前 5 行预测
- [ ] 1.4 导入走现有 `run(rows=..., apply=True)`，复用覆盖写与单事务；不写第二套推理
- [ ] 1.5 `parcel_info` 插入 `SGD_` 行（质心来自 `Farmland_data.lon/lan`，`legacy_parcel_code=soilgd:<id>`，`geom` 为空）

## 2. 乡镇归属

- [ ] 2.1 新增表 `cd_ported_parcel_township`（`parcel_id` PK、`township_id`、`township_name`、`distance_m`、`assigned_at`）
- [ ] 2.2 归属实现：`ST_Contains(township.geom, point(lon,lat))`；未命中时回退最近乡镇并记录距离
- [ ] 2.3 新增 `scripts/migrate_add_ported_dataset_tables.py`（幂等 `create_all` + 结构校验）
- [ ] 2.4 覆盖率实测：40100 个点中有多少落在乡镇多边形内、多少走回退归属，并把分布写入文档

## 3. 数据来源维度

- [ ] 3.1 统计服务增加 `source` 参数（`native|ported|all`，默认 `all`）与 `source_breakdown`
- [ ] 3.2 明细与 CSV 导出同样支持 `source`
- [ ] 3.3 阶段 3 的乡镇统计对移植数据可用（走 `cd_ported_parcel_township`），并在响应标注归属来源
- [ ] 3.4 路由参数校验：非法 `source` 返回 400

## 4. 回归验收

- [ ] 4.1 导入后比对：作物 Cd `local ln` vs `LnCropCd`，最大绝对差 < 1e-4
- [ ] 4.2 有效态 Cd：`local 浓度` vs `LnEffCd` 列值（该列实为浓度），最大相对差 < 1e-4
- [ ] 4.3 不达标时脚本非零退出并打印差异分布（中位/最大/超过容差的样本数）

## 5. 文档与验证

- [ ] 5.1 新增 `docs/cd-ported-dataset.md`：命名空间规则、导入命令、回滚命令、来源维度说明、与业务方数据并存策略
- [ ] 5.2 测试 `tests/test_heavy_metal_cd_ported.py`：命名空间隔离、列映射交叉、`source` 过滤、乡镇归属回退、回滚只删 `SGD_`
- [ ] 5.3 真实导入探针：先用 `--limit 200` 验证链路，再全量 40100；导入后核对两模型结果行数、统计 `source_breakdown`、乡镇归属覆盖率
- [ ] 5.4 `openspec validate import-cd-ported-dataset` 与 `git diff --check`
- [ ] 5.5 归档时回填 `docs/cd-migration-roadmap.md`（新增 D1 数据通道条目）

## 未完成（需人工确认后执行）

- **`SGD_` 前缀是否接受**（Open Question 1）。
- **是否把 40100 个移植点写进 `parcel_info`**（Open Question 2）：写了点位/明细可直接用，但地块总数从 5488 变 45588。
- **统计默认来源**：`all`（本提案默认）还是 `native`（Open Question 3）。
- **业务方数据到位后的处置**：并存 / 替换 / 清理移植数据，另开 change。
