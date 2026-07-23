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
