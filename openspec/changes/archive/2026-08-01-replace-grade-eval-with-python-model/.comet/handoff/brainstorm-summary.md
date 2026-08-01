# Brainstorm Summary

- Change: replace-grade-eval-with-python-model
- Date: 2026-08-01

## 确认的技术方案

将 model-7（耕地质量等级评价）从 Fortran exe + 二进制 .dat 替换为纯 Python 实现（model2 源码），8 个模块移植到 `src/ai_culti_demo/farmland_grade_eval/` 包。

### 核心映射设计

1. **indicators 组装**：`_build_indicators(parcel, config)` 映射表，12 项 `{name, code, raw_value}`。数值型（SJD/YJZ/YXL/SXJ/TRRZ/YXTCHD/GCHD）用 `"{:.3f}".format(val)`，概念型（GCZD/PSNL/GGNL/DXBW/ZDGX）用 config 名称字典的 strip() 值。与 exe 输出格式（"酸碱度(SJD): 4.600"）完全对齐。

2. **obstacle_degree 映射**：model2 `ObstacleItem(name, factor, degree)` → `{rank: idx+1, indicator: name.strip(), degree: factor, level: degree.strip()}`。`compute_obstacle_factors` 已按 factor 降序排序。

3. **composite_index / quality_grade**：`QualityResult.quality_index` → composite_index（float）；`QualityResult.grade`（int）→ `f"{grade}等"`（string）。

4. **parcel_info 组装**：地块代码=tybh，经度=str(jd)，纬度=str(wd)，县区名称=config.xqmc_names[xqmc-1]，二级农业区名称=config.ejnyq_names[ejnyq-1]。

### 缓存策略（类级缓存 + mtime 校验）

`FarmlandGradeRunner` 类级变量 `_parcels_cache`/`_csv_path_cached`/`_csv_mtime_cached`。每次 `_load_parcels` 先 `os.path.getmtime(csv_path)`，若路径和 mtime 未变则复用缓存，否则重新加载。CSV 重新部署后 mtime 变化自动失效。开销极小（一次 stat 调用）。

### 潜力分析/县域统计返回结构

- `run_potential_analysis(parcel_code, csv_path=None)` → `{status, parcel_code, original:{quality_index,grade}, full_potential:{quality_index,grade}, items:[{indicator,original_value,potential_value,original_quality_index,potential_quality_index,original_grade,potential_grade}]}`
- `run_county_statistics(xqmc_code, csv_path=None)` → `dataclasses.asdict(CountyStats)` + status 包装
- `run_county_potential(xqmc_code, scenario, csv_path=None)` → `dataclasses.asdict(CountyPotentialResult)` + status 包装

### 编码越界错误

`evaluate_land_quality` 对 ejnyq/ZDGC/PSNL/GGNL/DXBW/ZDGX 越界抛 ValueError。runner.run() 包裹 try/except，返回 `{status:"error", error:{code:"INVALID_ENCODING", message:str(e)}}`。

## 关键取舍与风险

| 取舍/风险 | 说明 |
|-----------|------|
| 类级缓存线程安全 | waitress 多线程下类变量读写可能竞争；Python GIL 保证单条赋值原子，最坏情况重复加载一次，可接受 |
| CSV 经纬度精度 | CSV 经度 112.9738 vs exe 输出 112.973801（.dat 存储精度更高），但不影响质量指数计算（仅用 sjd/yjz 等） |
| conditioner 与 model-4 并存 | conditioner 不接 API，文档标注"库函数，API 走 model-4" |
| dataclasses.asdict 递归 | CountyStats/CountyPotentialResult 含 List 字段，asdict 可正确处理 |

## 测试策略

- A0001 回归：对比 Python 输出与 exe 历史输出（composite_index=0.6728、grade="10等"、12 项 obstacle_degree，容差<0.01）
- indicators 格式：验证数值型 raw_value 为 "4.600" 格式、概念型为名称
- 缓存：验证 mtime 变化后重载
- 潜力分析/县域统计：A0001 和武江区(8) 的独立单元测试
- 向后兼容：传 exe_path/dat_path 不报错
- 部署校验：CSV 存在/缺失场景

## Spec Patch

修改 `specs/thematic-data-import/spec.md` 的"耕地质量评价 CSV 数据校验"requirement：
- 20 个必需字段名从 (tybh/jd/wd/mj/sjd/yjz/yxl/sxj/trrz/yxtchd/gchd/jhxllz/jhxqlz/ejnyq/xqmc/zdgc/psnl/ggnl/dxbw/zdgx) 改为实际 CSV 表头名 (SiteID/JD/WD/MJ/SJD/YJZ/YXL/SXJ/TRRZ/YXTCHD/GCHD/JHXLLZ/JHXQLZ/EJNYQcode/XQMCcode/GCZDcode/PSNLcode/GGNLcode/DXBWcode/ZDGXcode)
