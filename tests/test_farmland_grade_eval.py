"""farmland_grade_eval Python 模型单元测试。

覆盖数据层（models/config/data_loader）、评价层（evaluation/obstacle）、
runner 集成、潜力分析、县域统计、conditioner 库函数、部署校验、向后兼容。
"""
import sys
import os
import tempfile
from pathlib import Path

import pytest

# 将 src 加入 sys.path 以便导入 ai_culti_demo 包
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ========== 数据层测试 ==========

class TestModels:
    """数据类实例化测试。"""

    def test_parcel_dataclass_has_20_fields(self):
        from ai_culti_demo.farmland_grade_eval.models import Parcel
        parcel = Parcel(
            tybh="A0001", jd=112.97, wd=25.32, mj=100.0,
            sjd=4.6, yjz=16.2, yxl=66.9, sxj=51.7, trrz=1.24,
            yxtchd=120.0, gchd=17.0, jhxllz=0.0, jhxqlz=0.0,
            ejnyq=1, xqmc=8, zdgc=6, psnl=3, ggnl=2, dxbw=6, zdgx=5,
        )
        assert parcel.tybh == "A0001"
        assert parcel.sjd == 4.6
        assert parcel.ejnyq == 1

    def test_quality_result_dataclass(self):
        from ai_culti_demo.farmland_grade_eval.models import QualityResult
        r = QualityResult(y=[0.5] * 12, quality_index=0.7, grade=8)
        assert len(r.y) == 12
        assert r.quality_index == 0.7
        assert r.grade == 8


class TestEvaluationConfig:
    """配置类参数完整性测试。"""

    def test_config_has_all_parameters(self):
        from ai_culti_demo.farmland_grade_eval.config import EvaluationConfig
        cfg = EvaluationConfig()
        assert cfg.max_ejnyq == 4
        assert len(cfg.a) == 4  # 4 个二级农业区
        assert len(cfg.c) == 4
        assert len(cfg.weights) == 4
        assert len(cfg.weights[0]) == 12  # 12 个指标权重
        assert len(cfg.limits) == 4
        assert len(cfg.limits[0]) == 9  # 9 个等级阈值
        assert len(cfg.zdgc_names) == 12
        assert len(cfg.psnl_names) == 4
        assert len(cfg.ggnl_names) == 4
        assert len(cfg.dxbw_names) == 11
        assert len(cfg.zdgx_names) == 7
        assert len(cfg.ejnyq_names) == 4
        assert len(cfg.xqmc_names) == 10
        assert len(cfg.indicator_names) == 12


class TestDataLoader:
    """CSV 数据加载器测试。"""

    @pytest.fixture
    def sample_csv(self, tmp_path):
        """创建包含 2 行测试数据的 CSV 文件。"""
        csv_content = (
            "SiteID,JD,WD,MJ,SJD,YJZ,YXL,SXJ,TRRZ,YXTCHD,GCHD,"
            "JHXLLZ,JHXQLZ,EJNYQcode,XQMCcode,GCZDcode,PSNLcode,"
            "GGNLcode,DXBWcode,ZDGXcode\n"
            "A0001,112.973801,25.324301,100.0,4.600,16.200,66.900,51.700,"
            "1.240,120.000,17.000,0.0,0.0,1,8,6,3,2,6,5\n"
            "A0002,113.0,25.3,80.0,5.5,25.0,30.0,100.0,1.35,60.0,20.0,"
            "0.0,0.0,1,8,3,1,1,1,2\n"
        )
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(csv_content, encoding="utf-8-sig")
        return str(csv_path)

    def test_load_parcels_returns_list(self, sample_csv):
        from ai_culti_demo.farmland_grade_eval.data_loader import load_parcels_from_csv
        parcels = load_parcels_from_csv(sample_csv)
        assert len(parcels) == 2

    def test_load_parcels_first_row_fields(self, sample_csv):
        from ai_culti_demo.farmland_grade_eval.data_loader import load_parcels_from_csv
        parcels = load_parcels_from_csv(sample_csv)
        p = parcels[0]
        assert p.tybh == "A0001"
        assert p.sjd == 4.600
        assert p.ejnyq == 1
        assert p.xqmc == 8
        assert p.zdgc == 6

    def test_load_parcels_skips_insufficient_fields(self, tmp_path):
        """字段不足的行应被跳过（打印警告），不中断加载。"""
        csv_content = (
            "SiteID,JD,WD,MJ,SJD,YJZ,YXL,SXJ,TRRZ,YXTCHD,GCHD,"
            "JHXQLZ,EJNYQcode,XQMCcode,GCZDcode,PSNLcode,"
            "GGNLcode,DXBWcode,ZDGXcode\n"
            "A0001,112.97,25.32,100.0,4.6,16.2,66.9,51.7,1.24,120.0,17.0,"
            "0.0,1,8,6,3,2,6,5\n"
        )
        csv_path = tmp_path / "short.csv"
        csv_path.write_text(csv_content, encoding="utf-8-sig")
        from ai_culti_demo.farmland_grade_eval.data_loader import load_parcels_from_csv
        parcels = load_parcels_from_csv(str(csv_path))
        assert len(parcels) == 0  # 19 列 < 20，跳过

    def test_load_parcels_missing_file_raises(self, tmp_path):
        from ai_culti_demo.farmland_grade_eval.data_loader import load_parcels_from_csv
        with pytest.raises(FileNotFoundError):
            load_parcels_from_csv(str(tmp_path / "nonexistent.csv"))
