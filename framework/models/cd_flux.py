"""Cd 通量核算表（阶段 5：输入/输出/净通量与当年浓度）。

与原系统 AcidMap 的 ``FluxCd_input_data`` / ``FluxCd_output_data`` 同构：

- 输入表保存初始 Cd 与七项通量分量（大气沉降/灌溉/农化投入/地下渗漏/地表径流/
  籽粒移除/秸秆移除）以及可选容重 ``bd020_90``；
- 输出表保存计算后的 ``In_Cd / Out_Cd / Net_Cd / End_Cd``；
- 与原系统唯一的差异：两表都给 ``(parcel_id, sample_id)`` 加唯一约束。
  原系统主键只有自增 ID、无唯一约束，覆盖写遗漏会重复累积行（design 决策 1）。

输入数据依赖外部供给（CSV 导入）：新库没有 flux 表、容重表为空，
大气沉降/灌溉/农化投入无现成来源（design 决策 2）。
"""
from .user import db


class CdFluxInput(db.Model):
    """Cd 通量输入（原系统 ``FluxCd_input_data``）。"""

    __tablename__ = "cd_flux_input"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键")
    parcel_id = db.Column(db.String(64), nullable=False, comment="地块唯一编号（对应原系统 Farmland_ID）")
    sample_id = db.Column(db.String(64), nullable=False, comment="样点编号（地块级口径时为 parcel_id）")
    initial_cd = db.Column(db.Float, comment="初始 Cd 总量 [g/ha]（对应 Initial_Cd）")
    atmospheric_deposition = db.Column(db.Float, nullable=False, comment="大气沉降输入 [g/ha/a]（DQCJ_Cd）")
    irrigation_input = db.Column(db.Float, nullable=False, comment="灌溉输入 [g/ha/a]（GGS_Cd）")
    agro_chemicals_input = db.Column(db.Float, nullable=False, comment="农化投入 [g/ha/a]（NCP_Cd）")
    groundwater_leaching = db.Column(db.Float, nullable=False, comment="地下渗漏输出 [g/ha/a]（DX_Cd）")
    surface_runoff = db.Column(db.Float, nullable=False, comment="地表径流输出 [g/ha/a]（DB_Cd）")
    grain_removal = db.Column(db.Float, nullable=False, comment="籽粒移除输出 [g/ha/a]（ZL_Cd）")
    straw_removal = db.Column(db.Float, nullable=False, comment="秸秆移除输出 [g/ha/a]（JG_Cd）")
    bd020_90 = db.Column(db.Float, comment="0-20cm 容重（缺失时计算按 1.0 回退）")
    imported_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="导入时间"
    )

    __table_args__ = (
        db.UniqueConstraint("parcel_id", "sample_id", name="uk_cd_flux_input_parcel_sample"),
        db.Index("idx_cd_flux_input_parcel_id", "parcel_id"),
    )


class CdFluxOutput(db.Model):
    """Cd 通量输出（原系统 ``FluxCd_output_data``）。"""

    __tablename__ = "cd_flux_output"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键")
    parcel_id = db.Column(db.String(64), nullable=False, comment="地块唯一编号")
    sample_id = db.Column(db.String(64), nullable=False, comment="样点编号")
    in_cd = db.Column(db.Float, comment="输入通量 [g/ha/a]（In_Cd）")
    out_cd = db.Column(db.Float, comment="输出通量 [g/ha/a]（Out_Cd）")
    net_cd = db.Column(db.Float, comment="净通量 [g/ha/a]（Net_Cd）")
    end_cd = db.Column(db.Float, comment="当年 Cd 浓度 [mg/kg]（End_Cd）")
    computed_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="计算时间"
    )

    __table_args__ = (
        db.UniqueConstraint("parcel_id", "sample_id", name="uk_cd_flux_output_parcel_sample"),
        db.Index("idx_cd_flux_output_parcel_id", "parcel_id"),
    )
