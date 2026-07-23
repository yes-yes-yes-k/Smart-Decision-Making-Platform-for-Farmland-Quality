---
comet_change: import-lechang-soil-data
role: technical-design
canonical_spec: openspec
---

# Design Doc: import-lechang-soil-data

## 1. 概述

将 `data/lechang/` 目录下的乐昌市土壤数据（三普、二普、测土配方、农业化学化、粮食产量）批量导入数据库，按数据源分表存储。改造 `soil_data_loader.py` 从 DB 读取真实数据替代文件读取和 mock 生成逻辑，为模型 4/5/6 建立可查询的土壤数据底座。

OpenSpec 上游产物为事实源，本设计为其深度技术细化。

## 2. 现状分析

### 2.1 数据文件清单（已验证）

| 文件 | 格式 | 行数 | 列数 | 状态 |
|------|------|------|------|------|
| 01_乐昌市土壤三普表层土点位数据_fake.xlsx | xlsx | 649 | 52 | 可读 |
| 乐昌市三普土壤容重_fake.xlsx | xlsx | 1003 | 11 | 可读 |
| 乐昌市土壤三普剖面理化和基本数据_fake.xlsx | xlsx | 216 | 97 | 可读 |
| 乐昌市土壤三普立地条件_fake.xlsx | xlsx | 848 | 111 | 可读 |
| 01_乐昌市二普点数据.xlsx | xlsx | 82 | 39 | 可读 |
| 乐昌市测土配方表层土数据2008_fake.xlsx | xlsx | 1233 | 57 | 可读 |
| 各县(区)农村电气化和农业化学化情况2020-2024(1).xls | xls | - | - | **加密，无法读取** |
| 各县(区)粮食作物播种面积和产量2020-2024(1).xls | xls | - | - | **加密，无法读取** |

### 2.2 消费者现状（已验证）

全量搜索 `load_soil_data` 调用：**当前无任何消费者**。`load_soil_data()` 仅在 `framework/domain/data/soil_data_loader.py:7` 定义，没有任何 agent 或模块 import/调用它。所有 specialized agents（StabilityRiskAgent、ProblemIdentificationAgent、FertilityMLAgent 等）使用各自硬编码的 mock 数据。

本次变更只建立数据底座和 DB 读取能力，不修改 agent 代码（符合 Non-Goal）。消费者接线留待后续变更。

### 2.3 数据库现状

- 开发环境：SQLite `development.db`，仅含 User/Conversation/Message/Document 四张应用表
- 生产环境：SQLite `instance/production.db`
- ORM：SQLAlchemy，通过 `framework/models/user.py` 的 `db` 实例管理

## 3. 架构设计

### 3.1 组件划分

```
data/lechang/*.xlsx          scripts/import_lechang_data.py
       │                            │
       │ (pandas read_excel)        │ (列名映射 + DELETE/INSERT)
       ▼                            ▼
  DataFrame ──────────────► framework/models/soil_data.py (8 个 SQLAlchemy 模型)
                                    │
                                    │ db.create_all() (init_db.py)
                                    ▼
                            SQLite/MySQL 表
                                    │
                                    │ SQLAlchemy query
                                    ▼
                    framework/domain/data/soil_data_loader.py
                                    │
                                    │ load_soil_data() → dict
                                    ▼
                            (未来) models 4/5/6 agents
```

### 3.2 模块职责

| 模块 | 职责 | 依赖 |
|------|------|------|
| `framework/models/soil_data.py` | 8 个 SQLAlchemy 模型定义 | `framework/models/user.py` (db) |
| `scripts/import_lechang_data.py` | 从 Excel 导入到 DB，幂等执行 | pandas, openpyxl, xlrd, soil_data 模型 |
| `framework/domain/data/soil_data_loader.py` | 从 DB 读取土壤数据，DB 空时降级 mock | soil_data 模型, db |
| `framework/models/__init__.py` | 注册新模型 | soil_data 模型 |
| `init_db.py` | 建表 | framework.api.app, 所有模型 |

## 4. 详细设计

### 4.1 SQLAlchemy 模型设计（framework/models/soil_data.py）

8 个模型按数据源分表，表名复数形式。通用字段：`id`（自增主键）。所有字段允许 NULL（因各数据源列名不统一，缺失列允许 NULL）。

**列名映射策略**：Excel 中文列名 → SQLAlchemy 英文字段名，通过导入脚本的硬编码映射表完成。模型字段使用英文名，注释中标注中文原名。

#### 4.1.1 ThirdSurveyTopsoil（third_survey_topsoils）

来源：`01_乐昌市土壤三普表层土点位数据_fake.xlsx`（649 行 × 52 列）

核心字段（完整列名见导入脚本映射表）：
- `id`, `sample_id`(ID), `lon`, `lat`, `city`(City), `county`(County)
- `lulc`(LULC), `texture`(质地), `sm`(SM)
- `ph`(pH), `cec`(CEC), `som`(SOM), `tn`(TN), `tp`(TP), `tk`(TK)
- `ap`(AP), `ak`(AK), `sak`(SAK)
- 交换性系列：`exchangeable_base_sum`(交换性盐基总量), `exchangeable_ca`(交换性钙), `exchangeable_mg`(交换性镁), `exchangeable_na`(交换性钠), `exchangeable_k`(交换性钾)
- 水溶性系列：`water_soluble_salt_sum`(水溶性盐总量), `conductivity`(电导率), 及各离子
- 微量元素：`s`(S), `si`(Si), `fe`(Fe), `mn`(Mn), `cu`(Cu), `zn`(Zn), `b`(B), `mu`(Mu)
- 重金属：`hg`(Hg), `as`(As), `pb`(Pb), `cd`(Cd), `cr`(Cr), `ni`(Ni，注意源列名 ` Ni` 含前导空格)

**特殊处理**：源列名 ` Ni`（前导空格）、`TK `（尾随空格）在导入时 strip() 后映射。

#### 4.1.2 ThirdSurveyProfile（third_survey_profiles）

来源：`乐昌市土壤三普剖面理化和基本数据_fake.xlsx`（216 行 × 97 列）

核心字段：
- `id`, `sample_no`(样品编号), `original_sample_no`(原样品编号), `point_no`(样点编号), `lon`, `lat`
- `admin_region`(行政区划), `land_use_type`(土地利用类型), `lab`(检测实验室)
- `ph`(pH), `organic_matter`(有机质), `total_n`(全氮), `total_p`(全磷), `total_k`(全钾)
- `avail_p`(有效磷), `quick_k`(速效钾), `slow_k`(缓效钾)
- `cation_exchange_capacity`(阳离子交换量), `exchangeable_acid_total`(交换性酸总量)
- 土壤分类：`soil_order`(土纲), `soil_suborder`(亚纲), `soil_group`(土类), `soil_subgroup`(亚类), `soil_genus`(土属), `soil_species`(土种)
- 剖面信息：`effective_soil_depth`(有效土层厚度), `plow_layer_depth`(耕作层厚度)

#### 4.1.3 ThirdSurveySiteCondition（third_survey_site_conditions）

来源：`乐昌市土壤三普立地条件_fake.xlsx`（848 行 × 111 列）

核心字段：
- `id`, `point_no`(样点编号), `lon`, `lat`, `admin_region`(行政区划)
- `location`(坐落位置), `sample_type`(采样类型), `land_class`(地类), `soil_type`(土壤类型)
- `survey_time`(调查时间), `altitude`(海拔高度), `weather`(天气情况)
- 地形：`macro_landform`(大地形), `meso_landform`(中地形), `micro_landform`(小地形), `slope_position`(地形部位), `slope`(坡度), `slope_aspect`(坡向)
- 母岩母质：`parent_rock`(母岩), `parent_material`(母质)
- 植被：`vegetation_type`(植被类型), `vegetation_coverage`(植被覆盖度)
- 土地利用：`land_use_current`(土地利用类型现状), `irrigation_guarantee_rate`(灌溉保证率), `drainage_condition`(排水条件)
- 耕作：`cropping_system`(熟制类型), `rotation_first`(轮作制度第一季), `fertilization_method`(施肥方式)

#### 4.1.4 ThirdSurveyBulkDensity（third_survey_bulk_densities）

来源：`乐昌市三普土壤容重_fake.xlsx`（1003 行 × 11 列）

字段：
- `id`, `admin_region`(行政区划), `lon`, `lat`
- `sample_time`(接样时间, datetime), `report_time`(报告时间, datetime)
- `bulk_density_1`(土壤容重1), `bulk_density_2`(土壤容重2), `bulk_density_3`(土壤容重3), `bulk_density_4`(土壤容重4)
- `bulk_density_avg`(土壤容重平均值), `test_method`(检测方法)

**datetime 处理**：`接样时间`/`报告时间` 为 datetime64，导入时转为 ISO 字符串（`strftime('%Y-%m-%d %H:%M:%S')`），模型字段类型 `String(30)`。

#### 4.1.5 SecondSurveyPoint（second_survey_points）

来源：`01_乐昌市二普点数据.xlsx`（82 行 × 39 列）

字段：
- `id`, `sample_id`(ID), `seq`(序号), `city`, `county`, `data_source`(数据来源), `report_page`(报告页码)
- `point_no`(样点编号), `sampling_location`(二普采样地点), `current_address`(现行地址), `lon`, `lat`
- 土壤分类：`soil_type_2p`(二普土类), `subgroup_2p`(二普亚类), `soil_genus_2p`(二普土属), `soil_species_2p`(二普土种)
- 第一层理化：`ph_water_l1`(第一层pH水提), `ph_salt_l1`(第一层pH盐提), `om_l1`(第一层有机质%), `tn_l1`(第一层全氮%), `tp_l1`(第一层全磷P2O5%), `tk_l1`(第一层全钾K2O%)
- `alkali_n_l1`(第一层碱解氮PPM), `avail_p_l1`(第一层速效磷PPM), `avail_k_l1`(第一层速效钾PPM)
- 深度质地：`plow_layer_depth_cm`(耕层厚度cm), `effective_depth_cm`(有效土层厚度cm), 各层深度和质地

#### 4.1.6 FormulaFertilization（formula_fertilizations）

来源：`乐昌市测土配方表层土数据2008_fake.xlsx`（1233 行 × 57 列）

字段：
- `id`, `sample_id`(ID), `sample_date`(采样日期), `year`(年份), `city`(市), `county`(县), `town`(镇), `lat`, `lon`, `altitude`(海拔m)
- 地形：`landform`(地貌), `terrain`(地形), `surface_slope`(地面坡度), `field_slope`(田面坡度), `slope_aspect`(坡向)
- 地下水：`usual_groundwater`(通常地下水), `max_groundwater`(最高地下水), `min_groundwater`(最深地下水)
- 基础设施：`infrastructure`(基础设施), `drainage_capacity`(排水能力), `irrigation_capacity`(灌溉能力), `water_source`(水源条件)
- 种植：`cropping_system`(熟制), `planting_system`(种植制度), `annual_yield_kg_mu`(年产量kg/亩), `crop`(作物)
- 土壤：`soil_type`(土类), `soil_subgroup`(土亚类), `soil_genus`(土属), `soil_species`(土种), `parent_material`(成土母质), `profile_structure`(剖面构型), `soil_texture`(土壤质地), `soil_structure`(土壤结构), `obstacle_factor`(障碍因素), `erosion_degree`(侵蚀程度)
- 理化：`ph`(pH), `organic_matter`(有机质), `total_n`(全氮), `alkali_n`(碱解氮), `avail_p`(有效磷), `slow_k`(缓效钾), `quick_k`(速效钾), `exchangeable_ca`(交换性钙), `exchangeable_mg`(交换性镁)
- 微量元素：`avail_fe`(有效铁), `avail_mn`(有效锰), `avail_cu`(有效铜), `avail_zn`(有效锌), `water_sol_b`(水溶态硼), `avail_mo`(有效钼), `avail_s`(有效硫)

#### 4.1.7 AgriChemicalization（agri_chemicalizations）

来源：5 个 .xls 文件（2020-2024），**当前加密无法读取**。

字段（待解密后确认，预计）：
- `id`, `year`(年份), `county`(县区), `chemical_fertilizer_amount`(化肥施用量), 其他农业化学化指标

**当前状态**：表结构先建（基于推断的最小字段），导入脚本检测到加密后跳过并 warning。

#### 4.1.8 GrainYield（grain_yields）

来源：5 个 .xls 文件（2020-2024），**当前加密无法读取**。

字段（待解密后确认，预计）：
- `id`, `year`(年份), `county`(县区), `sown_area`(播种面积), `yield`(产量)

**当前状态**：同 AgriChemicalization，建表但暂不导入。

### 4.2 导入脚本设计（scripts/import_lechang_data.py）

```
scripts/import_lechang_data.py
├── 主入口 main()
├── 数据源配置 DATA_SOURCES (dict: source_name → {file_pattern, model, column_map})
├── import_one_source(source_name, data_dir, model_class, column_map)
│   ├── 定位文件（支持通配符匹配年份文件）
│   ├── pandas.read_excel(path, engine='openpyxl'|'xlrd')
│   ├── 检测加密：捕获 "Workbook is encrypted" → warning + 跳过
│   ├── 列名映射：df.rename(columns=column_map)
│   ├── datetime 转 ISO 字符串
│   ├── 幂等：db.session.query(model).delete() → db.session.bulk_insert_mappings()
│   └── 日志：导入行数、跳过原因、脱敏标注
└── 命令行参数：--area lechang (默认)、--dry-run (预览不写库)
```

**幂等策略**：按数据源逐表处理，每张表先 `DELETE FROM <table>` 再 `bulk_insert_mappings`。整个导入过程不使用单一事务（避免单表失败回滚已成功的表），每张表独立 commit。

**列名映射表**：硬编码在导入脚本的 `COLUMN_MAPS` dict 中，结构 `{源列名: 模型字段名}`。strip() 处理在映射前完成（`{k.strip(): v for k, v in column_map.items()}`），并 rename 时对 df.columns 也做 strip。

**加密文件处理**：
```python
try:
    df = pd.read_excel(path, engine='xlrd')
except Exception as e:
    if "encrypted" in str(e).lower():
        logger.warning("文件已加密，跳过: %s", path)
        return 0  # 0 行导入
    raise
```

### 4.3 soil_data_loader.py 改造

```python
def load_soil_data(area_code: str = "lechang") -> Dict[str, Any]:
    """从数据库读取土壤数据，DB 为空时降级 mock。"""
    try:
        from ...models.soil_data import ThirdSurveyTopsoil, FormulaFertilization
        from ...models.user import db
        third_survey_df = _query_to_dataframe(ThirdSurveyTopsoil.query.all())
        formula_df = _query_to_dataframe(FormulaFertilization.query.all())
        if third_survey_df.empty and formula_df.empty:
            logger.warning("DB 土壤数据表为空，降级到 mock 数据")
            return _generate_mock_data()
        return {"third_survey": third_survey_df, "formula_fertilization": formula_df}
    except Exception as e:
        logger.warning("从 DB 读取土壤数据失败，降级到 mock: %s", e)
        return _generate_mock_data()
```

**`_query_to_dataframe`**：将 SQLAlchemy 模型实例列表转为 pandas DataFrame，使用 `model.__table__.columns.keys()` 作为列名，取每个实例的属性值。

**返回结构兼容**：保持 `{"third_survey": DataFrame, "formula_fertilization": DataFrame}` 结构不变，仅数据源从文件/mock 变为 DB。

**mock fallback 保留**：`_generate_mock_data()`、`_generate_third_survey_mock()`、`_generate_formula_mock()` 不删除，作为 DB 为空时的降级。

### 4.4 init_db.py 更新

`init_db.py` 当前通过 `from framework.models.user import db, User` 导入 db。需确保 `framework/models/__init__.py` 注册了新模型后，`db.create_all()` 能发现它们。

修改方式：在 `init_db.py` 的 `from framework.models.user import db, User` 之后添加 `import framework.models  # noqa: F401  触发模型注册`。

## 5. 测试策略

### 5.1 单元测试

**tests/test_soil_data_models.py**：
- 测试 8 个模型可正常建表（SQLite in-memory）
- 测试模型字段类型和 nullable

**tests/test_import_lechang_data.py**：
- 测试列名映射：中文列名 → 英文字段名
- 测试幂等性：连续两次导入，行数一致无重复
- 测试加密文件跳过：mock 加密异常，验证返回 0 行 + warning
- 测试缺失文件跳过

**tests/test_soil_data_loader_db.py**：
- 测试 DB 有数据时返回真实数据（非 mock）
- 测试 DB 为空时降级 mock
- 测试返回结构包含 `third_survey` 和 `formula_fertilization` 键

### 5.2 集成验证

1. `python init_db.py` 创建新表
2. `python scripts/import_lechang_data.py --area lechang` 导入数据
3. Python 验证 `load_soil_data()` 返回真实数据
4. 重复执行导入脚本，验证无重复数据

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| .xls 文件加密 | AgriChemicalization/GrainYield 表为空 | 导入脚本检测加密跳过 + warning；需用户提供解密文件 |
| Excel 列名变化 | 导入失败或字段错位 | 硬编码映射表，列名变化时更新；缺失列允许 NULL |
| load_soil_data 无消费者 | 导入的数据暂未被使用 | 本次只建底座，消费者接线属后续变更（Non-Goal） |
| SQLite 类型限制 | datetime 存储 | 转为 ISO 字符串存储，读取时按需解析 |
| 脱敏数据 | 三普/测土配方为 _fake 数据 | 导入日志标注脱敏，不作为生产级真值 |

## 7. 回滚策略

1. 删除 `framework/models/soil_data.py`
2. 还原 `framework/models/__init__.py`、`init_db.py`、`soil_data_loader.py`
3. 删除 `scripts/import_lechang_data.py`
4. 运行 `init_db.py` 重建数据库（drop_all + create_all 会清除新表）

## 8. 不在本设计范围

- 修改六种专业模型的定义和代码逻辑（属 sync-model-specs-from-overview 变更）
- 将 specialized agents 接线到 load_soil_data()（属后续变更）
- 空间分析和 GIS 可视化
- 训练新的 ML 模型
- 韶关市级别数据
