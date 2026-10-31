"""重金属 Cd 预测结果表（阶段 1：Cd 数据库后端）。

与 AcidMap 原系统 ``CropCd_output_data`` / ``EffCd_output_data`` 同构：

- 只存自然对数值（``exp(ln)`` 还原为 mg/kg），与消费侧既有口径一致；
- **有意不加** ``execution_id`` / ``model_version`` / ``created_at``：
  openspec change ``add-heavy-metal-cd-database-backend`` 的 design 决策 3 记录，
  用户口径为"与原系统保持一致，不追踪是哪个模型算出来的"。
- 与原系统唯一的差异：``(parcel_id, sample_id)`` 加唯一约束。
  原系统主键只有自增 ID、无唯一约束，``DELETE`` 范围未覆盖时会重复累积行（design 决策 1）。
"""
from .user import db


class CdCropPredictionResult(db.Model):
    """作物 Cd 预测结果（原系统 ``CropCd_output_data``）。"""

    __tablename__ = "cd_crop_prediction_result"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键")
    parcel_id = db.Column(db.String(64), nullable=False, comment="地块唯一编号（对应原系统 Farmland_ID）")
    sample_id = db.Column(db.String(64), nullable=False, comment="样点编号（对应原系统 Sample_ID；地块级口径时为 parcel_id）")
    ln_crop_cd = db.Column(db.Float, nullable=False, comment="籽粒镉浓度的自然对数值[ln(mg/kg)]")

    __table_args__ = (
        db.UniqueConstraint("parcel_id", "sample_id", name="uk_cd_crop_prediction_parcel_sample"),
        db.Index("idx_cd_crop_prediction_parcel_id", "parcel_id"),
    )


class CdEffectivePredictionResult(db.Model):
    """土壤有效态 Cd 预测结果（原系统 ``EffCd_output_data``）。"""

    __tablename__ = "cd_effective_prediction_result"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键")
    parcel_id = db.Column(db.String(64), nullable=False, comment="地块唯一编号（对应原系统 Farmland_ID）")
    sample_id = db.Column(db.String(64), nullable=False, comment="样点编号（对应原系统 Sample_ID；地块级口径时为 parcel_id）")
    ln_eff_cd = db.Column(db.Float, nullable=False, comment="有效态镉浓度的自然对数值[ln(mg/kg)]")

    __table_args__ = (
        db.UniqueConstraint("parcel_id", "sample_id", name="uk_cd_effective_prediction_parcel_sample"),
        db.Index("idx_cd_effective_prediction_parcel_id", "parcel_id"),
    )
