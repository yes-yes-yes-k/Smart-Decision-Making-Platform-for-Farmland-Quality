---
change: import-lechang-soil-data
design-doc: docs/superpowers/specs/2026-07-23-import-lechang-soil-data-design.md
base-ref: d480d687c0a826fa724e42b64ee63b0c109e8621
archived-with: import-lechang-soil-data
---

# 乐昌土壤数据导入 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将 `data/lechang/` 下的乐昌土壤数据批量导入数据库，建立 8 张表的 SQLAlchemy 模型底座，并改造 `soil_data_loader.py` 从 DB 读取真实数据（保留 mock 降级）。

**Architecture:** 按数据源分表存储（8 个 SQLAlchemy 模型）；独立导入脚本 `scripts/import_lechang_data.py` 用 pandas 读 Excel（.xlsx 用 openpyxl、.xls 用 xlrd），做列名映射 + 幂等 DELETE/INSERT；`soil_data_loader.py` 改为 SQLAlchemy 查询，DB 空时降级 mock。本次只建底座，不接线 agent。

**Tech Stack:** Python 3.10+、Flask 3、Flask-SQLAlchemy 3.1、SQLAlchemy 2.0、pandas 3.0、openpyxl 3.1（.xlsx）、xlrd 2.0（.xls）、unittest/pytest 9。

## Global Constraints

- 模型文件位置固定：`framework/models/soil_data.py`，复用 `framework/models/user.py` 的 `db` 实例。
- 导入脚本位置固定：`scripts/import_lechang_data.py`，支持 .xlsx（openpyxl）与 .xls（xlrd）；加密文件须跳过并 warning，不抛异常。
- `soil_data_loader.py` 保留 mock fallback（`_generate_mock_data` / `_generate_third_survey_mock` / `_generate_formula_mock` 不删除）。
- 列名含尾随/前导空格需 `strip()`（源列名 ` Ni`、`TK `）。
- datetime 字段转 ISO 字符串存储（`strftime('%Y-%m-%d %H:%M:%S')`），模型字段用 `String(30)`。
- 幂等导入：每张表先 `DELETE` 后 `bulk_insert_mappings`，每表独立 commit，不使用单一事务。
- 当前 `load_soil_data` 无消费者，本次只建底座，不修改任何 agent 代码、不接线模型 4/5/6（Non-Goal）。
- 所有模型字段除 `id` 外允许 NULL（源数据列名不统一，缺失列允许 NULL）。
- 测试风格统一用 `unittest.TestCase`（与现有 `tests/` 一致），可用 `python -m pytest` 或 `python -m unittest` 运行。
- 8 张可读数据源：6 个 .xlsx 可读；2 类 .xls（农业化学化、粮食产量）当前加密，建表但不导入。

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `framework/models/soil_data.py` | 8 个 SQLAlchemy 模型定义 | 新建 |
| `framework/models/__init__.py` | 注册新模型触发 metadata 登记 | 修改 |
| `init_db.py` | `db.create_all()` 发现新表 | 修改 |
| `scripts/import_lechang_data.py` | Excel→DB 幂等导入脚本 | 新建 |
| `framework/domain/data/soil_data_loader.py` | 从 DB 读取，DB 空降级 mock | 修改 |
| `tests/test_soil_data_models.py` | 模型建表/字段/插入测试 | 新建 |
| `tests/test_import_lechang_data.py` | 导入脚本映射/幂等/加密跳过测试 | 新建 |
| `tests/test_soil_data_loader_db.py` | loader DB 读取/mock 降级测试 | 新建 |

---

### Task 1: 土壤数据模型定义、注册与建表

**Files:**
- Create: `framework/models/soil_data.py`
- Modify: `framework/models/__init__.py`
- Modify: `init_db.py`
- Test: `tests/test_soil_data_models.py`

**Interfaces:**
- Consumes: `framework/models/user.py` 的 `db`（SQLAlchemy 实例）
- Produces: 8 个模型类（`ThirdSurveyTopsoil`、`ThirdSurveyProfile`、`ThirdSurveySiteCondition`、`ThirdSurveyBulkDensity`、`SecondSurveyPoint`、`FormulaFertilization`、`AgriChemicalization`、`GrainYield`），表名分别为 `third_survey_topsoils`、`third_survey_profiles`、`third_survey_site_conditions`、`third_survey_bulk_densities`、`second_survey_points`、`formula_fertilizations`、`agri_chemicalizations`、`grain_yields`。每个模型有自增 `id` 主键，其余字段 nullable。

- [x] **Step 1: 写失败测试**

创建 `tests/test_soil_data_models.py`：

```python
import unittest

from flask import Flask
from sqlalchemy import inspect, String

from framework.models.user import db


class SoilDataModelsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        cls.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(cls.app)
        import framework.models.soil_data  # noqa: F401 触发模型注册
        with cls.app.app_context():
            db.create_all()

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_all_eight_tables_created(self):
        from framework.models import soil_data
        expected_tables = {
            soil_data.ThirdSurveyTopsoil.__tablename__,
            soil_data.ThirdSurveyProfile.__tablename__,
            soil_data.ThirdSurveySiteCondition.__tablename__,
            soil_data.ThirdSurveyBulkDensity.__tablename__,
            soil_data.SecondSurveyPoint.__tablename__,
            soil_data.FormulaFertilization.__tablename__,
            soil_data.AgriChemicalization.__tablename__,
            soil_data.GrainYield.__tablename__,
        }
        actual_tables = set(inspect(db.engine).get_table_names())
        self.assertTrue(expected_tables.issubset(actual_tables), expected_tables - actual_tables)

    def test_bulk_density_datetime_fields_are_string(self):
        from framework.models.soil_data import ThirdSurveyBulkDensity
        cols = ThirdSurveyBulkDensity.__table__.columns
        self.assertIsInstance(cols["sample_time"].type, String)
        self.assertIsInstance(cols["report_time"].type, String)

    def test_topsoil_ni_field_exists_and_nullable(self):
        from framework.models.soil_data import ThirdSurveyTopsoil
        col = ThirdSurveyTopsoil.__table__.columns["ni"]
        self.assertTrue(col.nullable)

    def test_can_insert_and_query_topsoil(self):
        from framework.models.soil_data import ThirdSurveyTopsoil
        rec = ThirdSurveyTopsoil(sample_id="S001", ph=5.5, som=15.2, ni=12.3)
        db.session.add(rec)
        db.session.commit()
        got = ThirdSurveyTopsoil.query.filter_by(sample_id="S001").first()
        self.assertIsNotNone(got)
        self.assertAlmostEqual(got.ph, 5.5)
        self.assertAlmostEqual(got.ni, 12.3)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_soil_data_models.py -v`
Expected: FAIL，错误为 `ModuleNotFoundError: No module named 'framework.models.soil_data'`

- [x] **Step 3: 创建模型文件**

创建 `framework/models/soil_data.py`：

```python
"""乐昌土壤数据 SQLAlchemy 模型。

按数据源分表，8 个模型。所有字段除 id 外允许 NULL（源数据列名不统一）。
datetime 字段（接样时间/报告时间）以 ISO 字符串存入 String(30) 列。
"""
from .user import db


class ThirdSurveyTopsoil(db.Model):
    """三普表层土点位数据（来源：01_乐昌市土壤三普表层土点位数据_fake.xlsx）。"""
    __tablename__ = "third_survey_topsoils"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sample_id = db.Column(db.String(64), comment="ID")
    lon = db.Column(db.Float, comment="经度")
    lat = db.Column(db.Float, comment="纬度")
    city = db.Column(db.String(64), comment="City")
    county = db.Column(db.String(64), comment="County")
    lulc = db.Column(db.String(64), comment="LULC")
    texture = db.Column(db.String(64), comment="质地")
    sm = db.Column(db.String(64), comment="SM")
    ph = db.Column(db.Float, comment="pH")
    cec = db.Column(db.Float, comment="CEC")
    som = db.Column(db.Float, comment="SOM")
    tn = db.Column(db.Float, comment="TN")
    tp = db.Column(db.Float, comment="TP")
    tk = db.Column(db.Float, comment="TK（源列名含尾随空格）")
    ap = db.Column(db.Float, comment="AP")
    ak = db.Column(db.Float, comment="AK")
    sak = db.Column(db.Float, comment="SAK")
    exchangeable_base_sum = db.Column(db.Float, comment="交换性盐基总量")
    exchangeable_ca = db.Column(db.Float, comment="交换性钙")
    exchangeable_mg = db.Column(db.Float, comment="交换性镁")
    exchangeable_na = db.Column(db.Float, comment="交换性钠")
    exchangeable_k = db.Column(db.Float, comment="交换性钾")
    water_soluble_salt_sum = db.Column(db.Float, comment="水溶性盐总量")
    conductivity = db.Column(db.Float, comment="电导率")
    s = db.Column(db.Float, comment="S")
    si = db.Column(db.Float, comment="Si")
    fe = db.Column(db.Float, comment="Fe")
    mn = db.Column(db.Float, comment="Mn")
    cu = db.Column(db.Float, comment="Cu")
    zn = db.Column(db.Float, comment="Zn")
    b = db.Column(db.Float, comment="B")
    mu = db.Column(db.Float, comment="Mu")
    hg = db.Column(db.Float, comment="Hg")
    as_ = db.Column("as", db.Float, comment="As（Python 关键字加下划线）")
    pb = db.Column(db.Float, comment="Pb")
    cd = db.Column(db.Float, comment="Cd")
    cr = db.Column(db.Float, comment="Cr")
    ni = db.Column(db.Float, comment="Ni（源列名含前导空格）")


class ThirdSurveyProfile(db.Model):
    """三普剖面理化和基本数据（来源：乐昌市土壤三普剖面理化和基本数据_fake.xlsx）。"""
    __tablename__ = "third_survey_profiles"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sample_no = db.Column(db.String(64), comment="样品编号")
    original_sample_no = db.Column(db.String(64), comment="原样品编号")
    point_no = db.Column(db.String(64), comment="样点编号")
    lon = db.Column(db.Float, comment="经度")
    lat = db.Column(db.Float, comment="纬度")
    admin_region = db.Column(db.String(128), comment="行政区划")
    land_use_type = db.Column(db.String(128), comment="土地利用类型")
    lab = db.Column(db.String(128), comment="检测实验室")
    ph = db.Column(db.Float, comment="pH")
    organic_matter = db.Column(db.Float, comment="有机质")
    total_n = db.Column(db.Float, comment="全氮")
    total_p = db.Column(db.Float, comment="全磷")
    total_k = db.Column(db.Float, comment="全钾")
    avail_p = db.Column(db.Float, comment="有效磷")
    quick_k = db.Column(db.Float, comment="速效钾")
    slow_k = db.Column(db.Float, comment="缓效钾")
    cation_exchange_capacity = db.Column(db.Float, comment="阳离子交换量")
    exchangeable_acid_total = db.Column(db.Float, comment="交换性酸总量")
    soil_order = db.Column(db.String(64), comment="土纲")
    soil_suborder = db.Column(db.String(64), comment="亚纲")
    soil_group = db.Column(db.String(64), comment="土类")
    soil_subgroup = db.Column(db.String(64), comment="亚类")
    soil_genus = db.Column(db.String(64), comment="土属")
    soil_species = db.Column(db.String(64), comment="土种")
    effective_soil_depth = db.Column(db.Float, comment="有效土层厚度")
    plow_layer_depth = db.Column(db.Float, comment="耕作层厚度")


class ThirdSurveySiteCondition(db.Model):
    """三普立地条件（来源：乐昌市土壤三普立地条件_fake.xlsx）。"""
    __tablename__ = "third_survey_site_conditions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    point_no = db.Column(db.String(64), comment="样点编号")
    lon = db.Column(db.Float, comment="经度")
    lat = db.Column(db.Float, comment="纬度")
    admin_region = db.Column(db.String(128), comment="行政区划")
    location = db.Column(db.String(128), comment="坐落位置")
    sample_type = db.Column(db.String(64), comment="采样类型")
    land_class = db.Column(db.String(64), comment="地类")
    soil_type = db.Column(db.String(64), comment="土壤类型")
    survey_time = db.Column(db.String(30), comment="调查时间（ISO 字符串）")
    altitude = db.Column(db.Float, comment="海拔高度")
    weather = db.Column(db.String(64), comment="天气情况")
    macro_landform = db.Column(db.String(64), comment="大地形")
    meso_landform = db.Column(db.String(64), comment="中地形")
    micro_landform = db.Column(db.String(64), comment="小地形")
    slope_position = db.Column(db.String(64), comment="地形部位")
    slope = db.Column(db.Float, comment="坡度")
    slope_aspect = db.Column(db.String(64), comment="坡向")
    parent_rock = db.Column(db.String(128), comment="母岩")
    parent_material = db.Column(db.String(128), comment="母质")
    vegetation_type = db.Column(db.String(128), comment="植被类型")
    vegetation_coverage = db.Column(db.Float, comment="植被覆盖度")
    land_use_current = db.Column(db.String(128), comment="土地利用类型现状")
    irrigation_guarantee_rate = db.Column(db.String(64), comment="灌溉保证率")
    drainage_condition = db.Column(db.String(64), comment="排水条件")
    cropping_system = db.Column(db.String(64), comment="熟制类型")
    rotation_first = db.Column(db.String(128), comment="轮作制度第一季")
    fertilization_method = db.Column(db.String(128), comment="施肥方式")


class ThirdSurveyBulkDensity(db.Model):
    """三普土壤容重（来源：乐昌市三普土壤容重_fake.xlsx）。"""
    __tablename__ = "third_survey_bulk_densities"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    admin_region = db.Column(db.String(128), comment="行政区划")
    lon = db.Column(db.Float, comment="经度")
    lat = db.Column(db.Float, comment="纬度")
    sample_time = db.Column(db.String(30), comment="接样时间（datetime 转 ISO 字符串）")
    report_time = db.Column(db.String(30), comment="报告时间（datetime 转 ISO 字符串）")
    bulk_density_1 = db.Column(db.Float, comment="土壤容重1")
    bulk_density_2 = db.Column(db.Float, comment="土壤容重2")
    bulk_density_3 = db.Column(db.Float, comment="土壤容重3")
    bulk_density_4 = db.Column(db.Float, comment="土壤容重4")
    bulk_density_avg = db.Column(db.Float, comment="土壤容重平均值")
    test_method = db.Column(db.String(128), comment="检测方法")


class SecondSurveyPoint(db.Model):
    """二普点数据（来源：01_乐昌市二普点数据.xlsx）。"""
    __tablename__ = "second_survey_points"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sample_id = db.Column(db.String(64), comment="ID")
    seq = db.Column(db.Integer, comment="序号")
    city = db.Column(db.String(64), comment="市")
    county = db.Column(db.String(64), comment="县")
    data_source = db.Column(db.String(128), comment="数据来源")
    report_page = db.Column(db.String(32), comment="报告页码")
    point_no = db.Column(db.String(64), comment="样点编号")
    sampling_location = db.Column(db.String(255), comment="二普采样地点")
    current_address = db.Column(db.String(255), comment="现行地址")
    lon = db.Column(db.Float, comment="经度")
    lat = db.Column(db.Float, comment="纬度")
    soil_type_2p = db.Column(db.String(64), comment="二普土类")
    subgroup_2p = db.Column(db.String(64), comment="二普亚类")
    soil_genus_2p = db.Column(db.String(64), comment="二普土属")
    soil_species_2p = db.Column(db.String(64), comment="二普土种")
    ph_water_l1 = db.Column(db.Float, comment="第一层pH水提")
    ph_salt_l1 = db.Column(db.Float, comment="第一层pH盐提")
    om_l1 = db.Column(db.Float, comment="第一层有机质%")
    tn_l1 = db.Column(db.Float, comment="第一层全氮%")
    tp_l1 = db.Column(db.Float, comment="第一层全磷P2O5%")
    tk_l1 = db.Column(db.Float, comment="第一层全钾K2O%")
    alkali_n_l1 = db.Column(db.Float, comment="第一层碱解氮PPM")
    avail_p_l1 = db.Column(db.Float, comment="第一层速效磷PPM")
    avail_k_l1 = db.Column(db.Float, comment="第一层速效钾PPM")
    plow_layer_depth_cm = db.Column(db.Float, comment="耕层厚度cm")
    effective_depth_cm = db.Column(db.Float, comment="有效土层厚度cm")


class FormulaFertilization(db.Model):
    """测土配方表层土数据（来源：乐昌市测土配方表层土数据2008_fake.xlsx）。"""
    __tablename__ = "formula_fertilizations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sample_id = db.Column(db.String(64), comment="ID")
    sample_date = db.Column(db.String(30), comment="采样日期")
    year = db.Column(db.Integer, comment="年份")
    city = db.Column(db.String(64), comment="市")
    county = db.Column(db.String(64), comment="县")
    town = db.Column(db.String(64), comment="镇")
    lat = db.Column(db.Float, comment="纬度")
    lon = db.Column(db.Float, comment="经度")
    altitude = db.Column(db.Float, comment="海拔m")
    landform = db.Column(db.String(64), comment="地貌")
    terrain = db.Column(db.String(64), comment="地形")
    surface_slope = db.Column(db.String(64), comment="地面坡度")
    field_slope = db.Column(db.String(64), comment="田面坡度")
    slope_aspect = db.Column(db.String(64), comment="坡向")
    usual_groundwater = db.Column(db.String(64), comment="通常地下水")
    max_groundwater = db.Column(db.String(64), comment="最高地下水")
    min_groundwater = db.Column(db.String(64), comment="最深地下水")
    infrastructure = db.Column(db.String(128), comment="基础设施")
    drainage_capacity = db.Column(db.String(64), comment="排水能力")
    irrigation_capacity = db.Column(db.String(64), comment="灌溉能力")
    water_source = db.Column(db.String(64), comment="水源条件")
    cropping_system = db.Column(db.String(64), comment="熟制")
    planting_system = db.Column(db.String(128), comment="种植制度")
    annual_yield_kg_mu = db.Column(db.Float, comment="年产量kg/亩")
    crop = db.Column(db.String(128), comment="作物")
    soil_type = db.Column(db.String(64), comment="土类")
    soil_subgroup = db.Column(db.String(64), comment="土亚类")
    soil_genus = db.Column(db.String(64), comment="土属")
    soil_species = db.Column(db.String(64), comment="土种")
    parent_material = db.Column(db.String(128), comment="成土母质")
    profile_structure = db.Column(db.String(128), comment="剖面构型")
    soil_texture = db.Column(db.String(64), comment="土壤质地")
    soil_structure = db.Column(db.String(64), comment="土壤结构")
    obstacle_factor = db.Column(db.String(128), comment="障碍因素")
    erosion_degree = db.Column(db.String(64), comment="侵蚀程度")
    ph = db.Column(db.Float, comment="pH")
    organic_matter = db.Column(db.Float, comment="有机质")
    total_n = db.Column(db.Float, comment="全氮")
    alkali_n = db.Column(db.Float, comment="碱解氮")
    avail_p = db.Column(db.Float, comment="有效磷")
    slow_k = db.Column(db.Float, comment="缓效钾")
    quick_k = db.Column(db.Float, comment="速效钾")
    exchangeable_ca = db.Column(db.Float, comment="交换性钙")
    exchangeable_mg = db.Column(db.Float, comment="交换性镁")
    avail_fe = db.Column(db.Float, comment="有效铁")
    avail_mn = db.Column(db.Float, comment="有效锰")
    avail_cu = db.Column(db.Float, comment="有效铜")
    avail_zn = db.Column(db.Float, comment="有效锌")
    water_sol_b = db.Column(db.Float, comment="水溶态硼")
    avail_mo = db.Column(db.Float, comment="有效钼")
    avail_s = db.Column(db.Float, comment="有效硫")


class AgriChemicalization(db.Model):
    """农业化学化情况（来源：各县(区)农村电气化和农业化学化情况2020-2024，当前加密）。"""
    __tablename__ = "agri_chemicalizations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    year = db.Column(db.Integer, comment="年份")
    county = db.Column(db.String(64), comment="县区")
    chemical_fertilizer_amount = db.Column(db.Float, comment="化肥施用量")


class GrainYield(db.Model):
    """粮食作物播种面积和产量（来源：各县(区)粮食作物播种面积和产量2020-2024，当前加密）。"""
    __tablename__ = "grain_yields"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    year = db.Column(db.Integer, comment="年份")
    county = db.Column(db.String(64), comment="县区")
    sown_area = db.Column(db.Float, comment="播种面积")
    yield_ = db.Column("yield", db.Float, comment="产量（yield 为保留字，列名 yield）")
```

说明：`as` / `yield` 是 Python 与 SQL 保留字，用 `db.Column("as", ...)` 形式指定真实列名，属性名加下划线后缀（`as_` / `yield_`）。导入脚本 `bulk_insert_mappings` 使用列名键（`"as"`、`"yield"`），与数据库列名一致。

- [x] **Step 4: 注册模型**

修改 `framework/models/__init__.py`，在末尾追加：

```python
from .soil_data import (
    ThirdSurveyTopsoil,
    ThirdSurveyProfile,
    ThirdSurveySiteCondition,
    ThirdSurveyBulkDensity,
    SecondSurveyPoint,
    FormulaFertilization,
    AgriChemicalization,
    GrainYield,
)
```

- [x] **Step 5: 更新 init_db.py 触发模型注册**

修改 `init_db.py`，在 `from framework.models.user import db, User` 之后插入一行注册新模型。原第 12 行：

```python
from framework.models.user import db, User
```

改为：

```python
from framework.models.user import db, User
import framework.models  # noqa: F401  触发 soil_data 等模型注册，使 db.create_all() 发现新表
```

- [x] **Step 6: 运行测试验证通过**

Run: `python -m pytest tests/test_soil_data_models.py -v`
Expected: 4 passed

- [x] **Step 7: Commit**

```bash
git add framework/models/soil_data.py framework/models/__init__.py init_db.py tests/test_soil_data_models.py
git commit -m "feat(soil): 新增 8 个乐昌土壤数据 SQLAlchemy 模型并注册建表"
```

---

### Task 2: 数据导入脚本（幂等 / 列名映射 / 加密跳过 / CLI）

**Files:**
- Create: `scripts/import_lechang_data.py`
- Test: `tests/test_import_lechang_data.py`

**Interfaces:**
- Consumes: Task 1 的 8 个模型、`framework.models.user.db`、`framework.api.app.create_app`
- Produces:
  - `import_one_source(model_class, column_map, file_paths, dry_run=False) -> int`：在当前 `app_context` 内对单数据源执行 strip→rename→datetime→DELETE→INSERT，返回导入行数；加密文件返回 0 并 warning。
  - `run_import(area="lechang", data_dir=None, dry_run=False) -> dict`：遍历 `DATA_SOURCES` 调 `import_one_source`，返回 `{source_name: rows}`。
  - `main()`：解析 `--area` / `--dry-run`，建 app 并在 `app_context` 内调 `run_import`。
  - `_prepare_dataframe(df, column_map, model_class) -> pd.DataFrame`：strip 列名、rename、datetime 转 ISO、仅保留模型字段列。

- [x] **Step 1: 写失败测试**

创建 `tests/test_import_lechang_data.py`：

```python
import unittest
from unittest import mock

import pandas as pd
from flask import Flask

from framework.models.user import db
import framework.models.soil_data  # noqa: F401


def _make_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
    return app


class ImportPrepareTests(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_column_map_strips_and_renames(self):
        from scripts.import_lechang_data import _prepare_dataframe, COLUMN_MAPS
        from framework.models.soil_data import ThirdSurveyTopsoil
        # 源列名含前导/尾随空格（如 " Ni"、"TK "）
        df = pd.DataFrame(
            {" Ni": [12.0], "TK ": [18.0], "pH": [5.5], "未映射列": [99]}
        )
        out = _prepare_dataframe(df, COLUMN_MAPS["third_survey_topsoil"], ThirdSurveyTopsoil)
        self.assertIn("ni", out.columns)
        self.assertIn("tk", out.columns)
        self.assertIn("ph", out.columns)
        self.assertNotIn("未映射列", out.columns)  # 非模型字段被丢弃
        self.assertEqual(len(out), 1)

    def test_datetime_converted_to_iso_string(self):
        from scripts.import_lechang_data import _prepare_dataframe, COLUMN_MAPS
        from framework.models.soil_data import ThirdSurveyBulkDensity
        df = pd.DataFrame(
            {"接样时间": pd.to_datetime(["2024-01-02 03:04:05"]), "土壤容重1": [1.2]}
        )
        out = _prepare_dataframe(df, COLUMN_MAPS["third_survey_bulk_density"], ThirdSurveyBulkDensity)
        self.assertEqual(out["sample_time"].iloc[0], "2024-01-02 03:04:05")
        self.assertEqual(out["bulk_density_1"].iloc[0], 1.2)


class ImportIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_idempotent_import_deletes_then_inserts(self):
        from scripts.import_lechang_data import import_one_source, COLUMN_MAPS
        from framework.models.soil_data import ThirdSurveyTopsoil
        # 预置旧数据
        db.session.add(ThirdSurveyTopsoil(sample_id="OLD", ph=9.9))
        db.session.commit()

        df1 = pd.DataFrame({"ID": ["A"], "pH": [5.0]})
        df2 = pd.DataFrame({"ID": ["A"], "pH": [5.0]})

        with mock.patch("scripts.import_lechang_data._read_excel", return_value=df1):
            n1 = import_one_source(ThirdSurveyTopsoil, COLUMN_MAPS["third_survey_topsoil"], ["x.xlsx"])
        with mock.patch("scripts.import_lechang_data._read_excel", return_value=df2):
            n2 = import_one_source(ThirdSurveyTopsoil, COLUMN_MAPS["third_survey_topsoil"], ["x.xlsx"])

        self.assertEqual(n1, 1)
        self.assertEqual(n2, 1)
        rows = ThirdSurveyTopsoil.query.all()
        self.assertEqual(len(rows), 1)  # 旧数据被删，无重复
        self.assertEqual(rows[0].sample_id, "A")
        self.assertIsNone(ThirdSurveyTopsoil.query.filter_by(sample_id="OLD").first())


class ImportEncryptedSkipTests(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_encrypted_file_skipped_with_zero_rows(self):
        from scripts.import_lechang_data import import_one_source, COLUMN_MAPS
        from framework.models.soil_data import AgriChemicalization

        def _raise(*args, **kwargs):
            raise Exception("Workbook is encrypted")

        with mock.patch("scripts.import_lechang_data._read_excel", side_effect=_raise):
            n = import_one_source(AgriChemicalization, COLUMN_MAPS["agri_chemicalization"], ["enc.xls"])

        self.assertEqual(n, 0)

    def test_missing_file_returns_zero(self):
        from scripts.import_lechang_data import import_one_source, COLUMN_MAPS
        from framework.models.soil_data import GrainYield
        n = import_one_source(GrainYield, COLUMN_MAPS["grain_yield"], ["nonexistent.xls"])
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_import_lechang_data.py -v`
Expected: FAIL，错误为 `ModuleNotFoundError: No module named 'scripts.import_lechang_data'`

- [x] **Step 3: 创建导入脚本**

创建 `scripts/import_lechang_data.py`：

```python
"""乐昌市土壤数据导入脚本。

从 data/<area>/ 下的 Excel 文件批量导入到数据库。
- 支持 .xlsx（openpyxl）与 .xls（xlrd）
- 加密文件跳过并 warning，不抛异常
- 幂等：每张表先 DELETE 后 bulk_insert_mappings，每表独立 commit
- datetime 字段转 ISO 字符串存储

用法:
    python scripts/import_lechang_data.py --area lechang
    python scripts/import_lechang_data.py --area lechang --dry-run
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Type

import pandas as pd
from sqlalchemy import inspect as sa_inspect

# 确保 src 在 sys.path（与 init_db.py 一致）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from framework.api.app import create_app  # noqa: E402
from framework.models.user import db  # noqa: E402
import framework.models.soil_data as soil_data_models  # noqa: E402,F401 触发注册
from framework.models.soil_data import (  # noqa: E402
    ThirdSurveyTopsoil,
    ThirdSurveyProfile,
    ThirdSurveySiteCondition,
    ThirdSurveyBulkDensity,
    SecondSurveyPoint,
    FormulaFertilization,
    AgriChemicalization,
    GrainYield,
)

logger = logging.getLogger("import_lechang")

# 各数据源列名映射表：{源 Excel 列名: 模型英文字段名}
# 源列名含前导/尾随空格的（如 " Ni"、"TK "）写其 strip 后形式，由 _prepare_dataframe 统一 strip。
COLUMN_MAPS: Dict[str, Dict[str, str]] = {
    "third_survey_topsoil": {
        "ID": "sample_id", "lon": "lon", "lat": "lat", "经度": "lon", "纬度": "lat",
        "City": "city", "County": "county", "LULC": "lulc", "质地": "texture", "SM": "sm",
        "pH": "ph", "CEC": "cec", "SOM": "som", "TN": "tn", "TP": "tp", "TK": "tk",
        "AP": "ap", "AK": "ak", "SAK": "sak",
        "交换性盐基总量": "exchangeable_base_sum", "交换性钙": "exchangeable_ca",
        "交换性镁": "exchangeable_mg", "交换性钠": "exchangeable_na", "交换性钾": "exchangeable_k",
        "水溶性盐总量": "water_soluble_salt_sum", "电导率": "conductivity",
        "S": "s", "Si": "si", "Fe": "fe", "Mn": "mn", "Cu": "cu", "Zn": "zn",
        "B": "b", "Mu": "mu",
        "Hg": "hg", "As": "as", "Pb": "pb", "Cd": "cd", "Cr": "cr", "Ni": "ni",
    },
    "third_survey_profile": {
        "样品编号": "sample_no", "原样品编号": "original_sample_no", "样点编号": "point_no",
        "lon": "lon", "lat": "lat", "经度": "lon", "纬度": "lat",
        "行政区划": "admin_region", "土地利用类型": "land_use_type", "检测实验室": "lab",
        "pH": "ph", "有机质": "organic_matter", "全氮": "total_n", "全磷": "total_p", "全钾": "total_k",
        "有效磷": "avail_p", "速效钾": "quick_k", "缓效钾": "slow_k",
        "阳离子交换量": "cation_exchange_capacity", "交换性酸总量": "exchangeable_acid_total",
        "土纲": "soil_order", "亚纲": "soil_suborder", "土类": "soil_group",
        "亚类": "soil_subgroup", "土属": "soil_genus", "土种": "soil_species",
        "有效土层厚度": "effective_soil_depth", "耕作层厚度": "plow_layer_depth",
    },
    "third_survey_site_condition": {
        "样点编号": "point_no", "lon": "lon", "lat": "lat", "经度": "lon", "纬度": "lat",
        "行政区划": "admin_region", "坐落位置": "location", "采样类型": "sample_type",
        "地类": "land_class", "土壤类型": "soil_type", "调查时间": "survey_time",
        "海拔高度": "altitude", "天气情况": "weather",
        "大地形": "macro_landform", "中地形": "meso_landform", "小地形": "micro_landform",
        "地形部位": "slope_position", "坡度": "slope", "坡向": "slope_aspect",
        "母岩": "parent_rock", "母质": "parent_material",
        "植被类型": "vegetation_type", "植被覆盖度": "vegetation_coverage",
        "土地利用类型现状": "land_use_current", "灌溉保证率": "irrigation_guarantee_rate",
        "排水条件": "drainage_condition", "熟制类型": "cropping_system",
        "轮作制度第一季": "rotation_first", "施肥方式": "fertilization_method",
    },
    "third_survey_bulk_density": {
        "行政区划": "admin_region", "lon": "lon", "lat": "lat", "经度": "lon", "纬度": "lat",
        "接样时间": "sample_time", "报告时间": "report_time",
        "土壤容重1": "bulk_density_1", "土壤容重2": "bulk_density_2",
        "土壤容重3": "bulk_density_3", "土壤容重4": "bulk_density_4",
        "土壤容重平均值": "bulk_density_avg", "检测方法": "test_method",
    },
    "second_survey_point": {
        "ID": "sample_id", "序号": "seq", "市": "city", "县": "county",
        "数据来源": "data_source", "报告页码": "report_page", "样点编号": "point_no",
        "二普采样地点": "sampling_location", "现行地址": "current_address",
        "lon": "lon", "lat": "lat", "经度": "lon", "纬度": "lat",
        "二普土类": "soil_type_2p", "二普亚类": "subgroup_2p", "二普土属": "soil_genus_2p",
        "二普土种": "soil_species_2p",
        "第一层pH水提": "ph_water_l1", "第一层pH盐提": "ph_salt_l1",
        "第一层有机质%": "om_l1", "第一层全氮%": "tn_l1", "第一层全磷P2O5%": "tp_l1",
        "第一层全钾K2O%": "tk_l1", "第一层碱解氮PPM": "alkali_n_l1",
        "第一层速效磷PPM": "avail_p_l1", "第一层速效钾PPM": "avail_k_l1",
        "耕层厚度cm": "plow_layer_depth_cm", "有效土层厚度cm": "effective_depth_cm",
    },
    "formula_fertilization": {
        "ID": "sample_id", "采样日期": "sample_date", "年份": "year",
        "市": "city", "县": "county", "镇": "town",
        "lat": "lat", "lon": "lon", "纬度": "lat", "经度": "lon", "海拔m": "altitude",
        "地貌": "landform", "地形": "terrain", "地面坡度": "surface_slope",
        "田面坡度": "field_slope", "坡向": "slope_aspect",
        "通常地下水": "usual_groundwater", "最高地下水": "max_groundwater",
        "最深地下水": "min_groundwater", "基础设施": "infrastructure",
        "排水能力": "drainage_capacity", "灌溉能力": "irrigation_capacity",
        "水源条件": "water_source", "熟制": "cropping_system",
        "种植制度": "planting_system", "年产量kg/亩": "annual_yield_kg_mu", "作物": "crop",
        "土类": "soil_type", "土亚类": "soil_subgroup", "土属": "soil_genus",
        "土种": "soil_species", "成土母质": "parent_material", "剖面构型": "profile_structure",
        "土壤质地": "soil_texture", "土壤结构": "soil_structure",
        "障碍因素": "obstacle_factor", "侵蚀程度": "erosion_degree",
        "pH": "ph", "有机质": "organic_matter", "全氮": "total_n", "碱解氮": "alkali_n",
        "有效磷": "avail_p", "缓效钾": "slow_k", "速效钾": "quick_k",
        "交换性钙": "exchangeable_ca", "交换性镁": "exchangeable_mg",
        "有效铁": "avail_fe", "有效锰": "avail_mn", "有效铜": "avail_cu",
        "有效锌": "avail_zn", "水溶态硼": "water_sol_b", "有效钼": "avail_mo", "有效硫": "avail_s",
    },
    "agri_chemicalization": {
        "年份": "year", "县区": "county", "化肥施用量": "chemical_fertilizer_amount",
    },
    "grain_yield": {
        "年份": "year", "县区": "county", "播种面积": "sown_area", "产量": "yield",
    },
}

# 数据源配置：source_name -> (模型类, 文件名模板列表)
# 文件名模板支持年份通配符 {year}，遍历 2020-2024 匹配；单文件直接给出文件名。
DATA_SOURCES: Dict[str, tuple] = {
    "third_survey_topsoil": (
        ThirdSurveyTopsoil,
        ["01_乐昌市土壤三普表层土点位数据_fake.xlsx"],
    ),
    "third_survey_profile": (
        ThirdSurveyProfile,
        ["乐昌市土壤三普剖面理化和基本数据_fake.xlsx"],
    ),
    "third_survey_site_condition": (
        ThirdSurveySiteCondition,
        ["乐昌市土壤三普立地条件_fake.xlsx"],
    ),
    "third_survey_bulk_density": (
        ThirdSurveyBulkDensity,
        ["乐昌市三普土壤容重_fake.xlsx"],
    ),
    "second_survey_point": (
        SecondSurveyPoint,
        ["01_乐昌市二普点数据.xlsx"],
    ),
    "formula_fertilization": (
        FormulaFertilization,
        ["乐昌市测土配方表层土数据2008_fake.xlsx"],
    ),
    "agri_chemicalization": (
        AgriChemicalization,
        ["各县(区)农村电气化和农业化学化情况{year}(1).xls"],
    ),
    "grain_yield": (
        GrainYield,
        ["各县(区)粮食作物播种面积和产量{year}(1).xls"],
    ),
}

FAKE_SOURCES = {"third_survey_topsoil", "third_survey_profile",
                 "third_survey_site_condition", "third_survey_bulk_density",
                 "formula_fertilization"}


def _read_excel(path: str) -> pd.DataFrame:
    """读取 Excel，按扩展名选择引擎。加密文件抛异常由调用方捕获。"""
    if path.lower().endswith(".xls"):
        return pd.read_excel(path, engine="xlrd")
    return pd.read_excel(path, engine="openpyxl")


def _resolve_files(patterns: List[str], data_dir: str) -> List[str]:
    """解析文件名模板。{year} 通配符展开为 2020-2024；无通配符原样返回存在的文件。"""
    resolved: List[str] = []
    for pat in patterns:
        if "{year}" in pat:
            for year in range(2020, 2025):
                p = os.path.join(data_dir, pat.format(year=year))
                if os.path.exists(p):
                    resolved.append(p)
        else:
            p = os.path.join(data_dir, pat)
            if os.path.exists(p):
                resolved.append(p)
    return resolved


def _prepare_dataframe(df: pd.DataFrame, column_map: Dict[str, str], model_class) -> pd.DataFrame:
    """strip 列名 -> rename -> datetime 转 ISO -> 仅保留模型字段列。"""
    # 1. 列名 strip（处理 " Ni" / "TK "）
    df = df.rename(columns={c: str(c).strip() for c in df.columns})
    # 2. 映射表 key 也 strip，构造实际 rename
    stripped_map = {str(k).strip(): v for k, v in column_map.items()}
    df = df.rename(columns=stripped_map)
    # 3. datetime 列转 ISO 字符串
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")
    # 4. 仅保留模型定义的字段，丢弃未映射列
    model_fields = {c.name for c in model_class.__table__.columns}
    keep = [c for c in df.columns if c in model_fields]
    return df[keep].copy()


def import_one_source(model_class, column_map: Dict[str, str], file_paths: List[str],
                      dry_run: bool = False) -> int:
    """对单数据源执行幂等导入，返回导入行数。加密/缺失文件返回 0。"""
    if not file_paths:
        logger.warning("未找到数据文件，跳过: %s", model_class.__tablename__)
        return 0

    frames: List[pd.DataFrame] = []
    for path in file_paths:
        try:
            raw = _read_excel(path)
        except Exception as e:  # noqa: BLE001
            if "encrypted" in str(e).lower():
                logger.warning("文件已加密，跳过: %s", path)
                continue
            logger.error("读取失败 %s: %s", path, e)
            continue
        frames.append(_prepare_dataframe(raw, column_map, model_class))

    if not frames:
        return 0

    df = pd.concat(frames, ignore_index=True)
    records = df.to_dict(orient="records")
    # 移除全为 None 的空记录键，避免主键冲突（id 由 DB 自增，剔除）
    for rec in records:
        rec.pop("id", None)

    if dry_run:
        logger.info("[dry-run] %s 将导入 %d 行（不写库）", model_class.__tablename__, len(records))
        return len(records)

    db.session.query(model_class).delete()
    if records:
        db.session.bulk_insert_mappings(model_class, records)
    db.session.commit()  # 每表独立 commit
    logger.info("导入完成: %s %d 行%s",
                model_class.__tablename__, len(records),
                "（脱敏 _fake 数据）" if model_class.__tablename__.startswith(("third_survey", "formula")) else "")
    return len(records)


def run_import(area: str = "lechang", data_dir: Optional[str] = None,
               dry_run: bool = False) -> Dict[str, int]:
    """遍历所有数据源执行导入，返回 {source_name: rows}。"""
    if data_dir is None:
        data_dir = str(PROJECT_ROOT / "data" / area)
    if not os.path.isdir(data_dir):
        logger.error("数据目录不存在: %s", data_dir)
        return {}

    results: Dict[str, int] = {}
    for source_name, (model_class, patterns) in DATA_SOURCES.items():
        files = _resolve_files(patterns, data_dir)
        results[source_name] = import_one_source(
            model_class, COLUMN_MAPS[source_name], files, dry_run=dry_run
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="乐昌土壤数据导入")
    parser.add_argument("--area", default="lechang", help="区域目录名（默认 lechang）")
    parser.add_argument("--dry-run", action="store_true", help="预览不写库")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = create_app()
    with app.app_context():
        results = run_import(area=args.area, dry_run=args.dry_run)

    print("=" * 60)
    print("导入结果汇总：")
    for name, rows in results.items():
        print(f"  {name}: {rows} 行")
    if args.dry_run:
        print("（dry-run 模式，未实际写库）")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

- [x] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_import_lechang_data.py -v`
Expected: 5 passed（prepare ×2、idempotent ×1、encrypted ×1、missing ×1）

- [x] **Step 5: Commit**

```bash
git add scripts/import_lechang_data.py tests/test_import_lechang_data.py
git commit -m "feat(import): 新增乐昌土壤数据幂等导入脚本（列名映射/加密跳过/dry-run）"
```

---

### Task 3: soil_data_loader 改造为 DB 读取

**Files:**
- Modify: `framework/domain/data/soil_data_loader.py`
- Test: `tests/test_soil_data_loader_db.py`

**Interfaces:**
- Consumes: Task 1 的 `ThirdSurveyTopsoil`、`FormulaFertilization`，`framework.models.user.db`
- Produces: `load_soil_data(area_code="lechang") -> Dict[str, Any]`，返回结构保持 `{"third_survey": DataFrame, "formula_fertilization": DataFrame}` 不变；DB 空或查询失败时降级 `_generate_mock_data()`。新增私有 `_query_to_dataframe(model_class) -> pd.DataFrame`。

- [x] **Step 1: 写失败测试**

创建 `tests/test_soil_data_loader_db.py`：

```python
import unittest

import pandas as pd
from flask import Flask

from framework.models.user import db
import framework.models.soil_data  # noqa: F401


def _make_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
    return app


class SoilDataLoaderDbTests(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_returns_real_data_when_db_populated(self):
        from framework.models.soil_data import ThirdSurveyTopsoil, FormulaFertilization
        db.session.add(ThirdSurveyTopsoil(sample_id="R1", ph=4.2, som=11.0))
        db.session.add(FormulaFertilization(sample_id="F1", ph=5.0, organic_matter=20.0))
        db.session.commit()

        from framework.domain.data.soil_data_loader import load_soil_data
        result = load_soil_data()

        self.assertIn("third_survey", result)
        self.assertIn("formula_fertilization", result)
        self.assertGreaterEqual(len(result["third_survey"]), 1)
        self.assertGreaterEqual(len(result["formula_fertilization"]), 1)
        # 非空 DB 不应返回 mock 的 623 行规模
        self.assertNotEqual(len(result["third_survey"]), 623)

    def test_falls_back_to_mock_when_db_empty(self):
        from framework.domain.data.soil_data_loader import load_soil_data
        result = load_soil_data()
        self.assertIn("third_survey", result)
        self.assertIn("formula_fertilization", result)
        # mock 第三普固定 623 行
        self.assertEqual(len(result["third_survey"]), 623)

    def test_returns_structure_has_expected_keys(self):
        from framework.domain.data.soil_data_loader import load_soil_data
        result = load_soil_data()
        self.assertEqual(set(result.keys()), {"third_survey", "formula_fertilization"})
        self.assertIsInstance(result["third_survey"], pd.DataFrame)
        self.assertIsInstance(result["formula_fertilization"], pd.DataFrame)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_soil_data_loader_db.py -v`
Expected: `test_returns_real_data_when_db_populated` FAIL（当前 loader 从文件/mock 读取，空 DB 不会返回真实数据；`test_falls_back_to_mock_when_db_empty` 可能通过，但前者会因读不到真实数据失败）

- [x] **Step 3: 改造 loader**

将 `framework/domain/data/soil_data_loader.py` 整体替换为：

```python
from __future__ import annotations
import logging
import os
from typing import Any, Dict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _query_to_dataframe(model_class) -> pd.DataFrame:
    """将 SQLAlchemy 模型查询结果转为 DataFrame，列名为模型字段名。"""
    columns = [c.name for c in model_class.__table__.columns]
    rows = [
        {col: getattr(instance, col) for col in columns}
        for instance in model_class.query.all()
    ]
    return pd.DataFrame(rows, columns=columns)


def load_soil_data(area_code: str = "lechang") -> Dict[str, Any]:
    """从数据库读取土壤数据，DB 为空或查询失败时降级 mock。

    返回结构保持不变：{"third_survey": DataFrame, "formula_fertilization": DataFrame}
    """
    try:
        from framework.models.soil_data import ThirdSurveyTopsoil, FormulaFertilization

        third_survey_df = _query_to_dataframe(ThirdSurveyTopsoil)
        formula_df = _query_to_dataframe(FormulaFertilization)

        if third_survey_df.empty and formula_df.empty:
            logger.warning("DB 土壤数据表为空，降级到 mock 数据")
            return _generate_mock_data()
        return {"third_survey": third_survey_df, "formula_fertilization": formula_df}
    except Exception as e:
        logger.warning("从 DB 读取土壤数据失败，降级到 mock: %s", e)
        return _generate_mock_data()


def _generate_mock_data() -> Dict[str, Any]:
    return {"third_survey": _generate_third_survey_mock(), "formula_fertilization": _generate_formula_mock()}


def _generate_third_survey_mock() -> pd.DataFrame:
    np.random.seed(42)
    n_points = 623
    ph_values = np.random.uniform(4.0, 7.0, n_points)
    return pd.DataFrame({
        "pH": ph_values.round(2),
        "交换性酸": np.random.uniform(0.5, 3.0, n_points).round(2),
        "交换性Al": np.random.uniform(0.1, 2.5, n_points).round(2),
        "交换性H": np.random.uniform(0.05, 0.8, n_points).round(2),
        "CEC": np.random.uniform(8.0, 25.0, n_points).round(2),
        "容重": np.random.uniform(1.0, 1.4, n_points).round(2),
        "有机质": np.random.uniform(10.0, 30.0, n_points).round(2),
    })


def _generate_formula_mock() -> pd.DataFrame:
    np.random.seed(123)
    n_points = 1256
    ph_values = np.random.uniform(4.0, 7.0, n_points)
    return pd.DataFrame({
        "pH": ph_values.round(2),
        "交换性酸": np.random.uniform(0.5, 3.0, n_points).round(2),
        "交换性Al": np.random.uniform(0.1, 2.5, n_points).round(2),
        "交换性H": np.random.uniform(0.05, 0.8, n_points).round(2),
        "CEC": np.random.uniform(8.0, 25.0, n_points).round(2),
        "容重": np.random.uniform(1.0, 1.4, n_points).round(2),
        "有机质": np.random.uniform(10.0, 30.0, n_points).round(2),
    })
```

注意：改造移除了旧的文件读取逻辑（`_load_third_survey_data`）与 `os`/文件依赖，因当前无消费者且 Design Doc 明确从 DB 读取。`_generate_mock_data` 等三个 mock 函数完整保留作为降级。

- [x] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_soil_data_loader_db.py -v`
Expected: 3 passed

- [x] **Step 5: 确认未破坏现有测试**

Run: `python -m pytest tests/ -v -k "not (soil or import)"`
Expected: 现有测试全部通过（loader 无消费者，移除文件读取不影响其他模块）

- [x] **Step 6: Commit**

```bash
git add framework/domain/data/soil_data_loader.py tests/test_soil_data_loader_db.py
git commit -m "refactor(loader): soil_data_loader 改为从 DB 读取，DB 空降级 mock"
```

---

### Task 4: 端到端集成验证

**Files:**
- 无新增文件；运行 `init_db.py`、导入脚本、loader 验证脚本

**Interfaces:**
- Consumes: Task 1 模型、Task 2 导入脚本、Task 3 loader
- Produces: 验证报告（控制台输出）：8 张表已建、6 个可读数据源导入行数、`load_soil_data()` 返回真实数据、重复导入幂等无重复。

> 说明：tasks.md 5.4「验证模型 4/5/6 能读到真实乐昌数据」与 Design Doc 的 Non-Goal（本次不接线 agent）冲突。遵循 Design Doc（事实源），本 Task 只验证 `load_soil_data()` 返回真实数据，不验证 agent 接线。

- [x] **Step 1: 重建数据库建表**

Run: `python init_db.py`
Expected: 输出 `[初始化] 数据库表结构创建完成`，`development.db` 含 8 张新表（third_survey_topsoils 等）。

- [x] **Step 2: 运行导入脚本（首次）**

Run: `python scripts/import_lechang_data.py --area lechang`
Expected:
- 控制台汇总显示 6 个可读数据源行数 > 0：
  - third_survey_topsoil: 648 行（649 含表头）
  - third_survey_profile: 215 行
  - third_survey_site_condition: 847 行
  - third_survey_bulk_density: 1002 行
  - second_survey_point: 81 行
  - formula_fertilization: 1232 行
- agri_chemicalization: 0 行（日志含 `文件已加密，跳过` warning ×5）
- grain_yield: 0 行（日志含 `文件已加密，跳过` warning ×5）
- 行数与源文件"行数 - 1"一致（表头扣除）；若源文件实际表头/数据行略有差异，以实际为准，但应为非零正数。

- [x] **Step 3: 验证 load_soil_data 返回真实数据**

Run:
```bash
python -c "import sys; sys.path.insert(0,'src'); from framework.api.app import create_app; from framework.models.user import db; import framework.models.soil_data; from framework.domain.data.soil_data_loader import load_soil_data; app=create_app(); ctx=app.app_context(); ctx.push(); r=load_soil_data(); print('third_survey rows:', len(r['third_survey'])); print('formula rows:', len(r['formula_fertilization'])); ctx.pop()"
```
Expected:
- `third_survey rows:` 非 623（真实数据，非 mock）
- `formula rows:` 非 1256（真实数据，非 mock）
- 行数与 Step 2 导入一致。

- [x] **Step 4: 验证幂等（重复导入无重复）**

Run:
```bash
python -c "import sys; sys.path.insert(0,'src'); from framework.api.app import create_app; from framework.models.user import db; import framework.models.soil_data as m; app=create_app(); ctx=app.app_context(); ctx.push(); import sys; sys.path.insert(0,'scripts'); from import_lechang_data import run_import; r1=run_import('lechang'); from framework.models.soil_data import ThirdSurveyTopsoil, FormulaFertilization; n1_t=ThirdSurveyTopsoil.query.count(); n1_f=FormulaFertilization.query.count(); r2=run_import('lechang'); n2_t=ThirdSurveyTopsoil.query.count(); n2_f=FormulaFertilization.query.count(); print('before:', n1_t, n1_f); print('after :', n2_t, n2_f); assert n1_t==n2_t and n1_f==n2_f, 'idempotency broken'; print('idempotent OK'); ctx.pop()"
```
Expected: `before:` 与 `after:` 行数一致，输出 `idempotent OK`。

- [x] **Step 5: 运行全量测试确保不破坏现有功能**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（含本计划新增 3 个测试文件 + 现有测试）。

- [x] **Step 6: Commit 集成验证记录**

```bash
git add -A
git commit --allow-empty -m "chore(soil): 完成乐昌土壤数据底座集成验证（8 表建表/导入/loader 真实读取/幂等）"
```

注：本步骤若无文件改动使用 `--allow-empty` 记录验证节点；若有 `development.db` 之类产物请确认其未被追踪（应在 `.gitignore`）。

---

## Self-Review

**1. Spec coverage（对照 tasks.md / Design Doc）：**

- tasks 1.1-1.5（模型定义/映射注释/注册/init_db）→ Task 1 ✓（1.1 列名分析已由 Design Doc §2.1/§4.1 完成，落地为 COLUMN_MAPS 注释）
- tasks 2.1-2.6（脚本骨架/读 xlsx+xls/列名映射/幂等/日志/CLI）→ Task 2 ✓（`_read_excel` 双引擎、`_resolve_files` 通配符、`_prepare_dataframe` strip+rename+datetime、`import_one_source` DELETE+INSERT+commit、`--area`/`--dry-run`、logging）✓
- tasks 3.1-3.3（DB 读取/mock fallback/结构兼容）→ Task 3 ✓
- tasks 4.1-4.4（3 个测试文件 + 全量测试）→ Task 1/2/3 内嵌 TDD + Task 4 Step 5 全量 ✓
- tasks 5.1-5.3/5.5（init_db 建表/导入/load_soil_data 真实/重复幂等）→ Task 4 ✓
- tasks 5.4（agent 接线）→ 显式排除（Design Doc Non-Goal，已说明）✓
- Design Doc 关键约束：8 模型在 soil_data.py ✓；.xlsx/.xls+加密跳过 ✓；loader DB+mock fallback ✓；列名 strip ✓；datetime→ISO ✓；幂等每表独立 commit ✓；不接线 agent ✓

**2. Placeholder scan：** 无 TBD/TODO；所有代码步骤含完整代码；命令含预期输出。✓

**3. Type consistency：**
- 模型类名、表名在 Task 1/2/3/4 一致（ThirdSurveyTopsoil 等 8 个）✓
- `import_one_source(model_class, column_map, file_paths, dry_run)` 签名在 Task 2 定义、Task 2 测试与 Task 4 Step 4 调用一致 ✓
- `COLUMN_MAPS` / `DATA_SOURCES` 键名（如 `third_survey_topsoil`）在定义与测试一致 ✓
- 保留字字段 `as_`→列名 `as`、`yield_`→列名 `yield`，`bulk_insert_mappings` 用 records（来自 `to_dict`，键为模型字段名 `as`/`yield`），与数据库列名一致 ✓
- `_read_excel` 被 `import_one_source` 内部调用、测试用 `mock.patch("scripts.import_lechang_data._read_excel")` 注入，patch 目标一致 ✓

计划无遗留问题。
