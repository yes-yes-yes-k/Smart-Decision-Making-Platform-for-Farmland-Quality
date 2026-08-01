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
            ejnyq=1, xqmc=8, zdgc=6, psnl=3, ggnl=2, dxbw=6, zdgx=6,
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
            "1.240,120.000,17.000,0.0,0.0,1,8,6,3,2,6,6\n"
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


# ========== 评价层测试 ==========

class TestEvaluation:
    """核心评价函数测试。"""

    @pytest.fixture
    def config(self):
        from ai_culti_demo.farmland_grade_eval.config import EvaluationConfig
        return EvaluationConfig()

    @pytest.fixture
    def parcel_a0001(self):
        """A0001 地块数据（与 exe 历史输出对应的已知值）。"""
        from ai_culti_demo.farmland_grade_eval.models import Parcel
        return Parcel(
            tybh="A0001", jd=112.973801, wd=25.324301, mj=100.0,
            sjd=4.600, yjz=16.200, yxl=66.900, sxj=51.700, trrz=1.240,
            yxtchd=120.000, gchd=17.000, jhxllz=0.0, jhxqlz=0.0,
            ejnyq=1, xqmc=8, zdgc=6, psnl=3, ggnl=2, dxbw=6, zdgx=6,
        )

    def test_a0001_composite_index_matches_exe(self, config, parcel_a0001):
        """A0001 综合指数与 exe 历史输出 0.6728 一致（容差 < 0.01）。"""
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        result = evaluate_land_quality(config, parcel_a0001)
        assert abs(result.quality_index - 0.6728) < 0.01

    def test_a0001_grade_is_10(self, config, parcel_a0001):
        """A0001 质量等级为 10 等。"""
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        result = evaluate_land_quality(config, parcel_a0001)
        assert result.grade == 10

    def test_a0001_has_12_membership_values(self, config, parcel_a0001):
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        result = evaluate_land_quality(config, parcel_a0001)
        assert len(result.y) == 12

    def test_invalid_ejnyq_raises_value_error(self, config):
        from ai_culti_demo.farmland_grade_eval.models import Parcel
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        parcel = Parcel(
            tybh="X", jd=0, wd=0, mj=0, sjd=5.0, yjz=20, yxl=30, sxj=100,
            trrz=1.35, yxtchd=60, gchd=20, jhxllz=0, jhxqlz=0,
            ejnyq=99, xqmc=1, zdgc=3, psnl=1, ggnl=1, dxbw=1, zdgx=1,
        )
        with pytest.raises(ValueError, match="无效的二级农业区代码"):
            evaluate_land_quality(config, parcel)

    def test_invalid_zdgc_raises_value_error(self, config):
        from ai_culti_demo.farmland_grade_eval.models import Parcel
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        parcel = Parcel(
            tybh="X", jd=0, wd=0, mj=0, sjd=5.0, yjz=20, yxl=30, sxj=100,
            trrz=1.35, yxtchd=60, gchd=20, jhxllz=0, jhxqlz=0,
            ejnyq=1, xqmc=1, zdgc=99, psnl=1, ggnl=1, dxbw=1, zdgx=1,
        )
        with pytest.raises(ValueError, match="ZDGC 编码超出范围"):
            evaluate_land_quality(config, parcel)


class TestObstacle:
    """障碍度计算测试。"""

    @pytest.fixture
    def config(self):
        from ai_culti_demo.farmland_grade_eval.config import EvaluationConfig
        return EvaluationConfig()

    def test_a0001_obstacle_factors_sorted_descending(self, config):
        from ai_culti_demo.farmland_grade_eval.models import Parcel
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        from ai_culti_demo.farmland_grade_eval.obstacle import compute_obstacle_factors
        parcel = Parcel(
            tybh="A0001", jd=112.973801, wd=25.324301, mj=100.0,
            sjd=4.600, yjz=16.200, yxl=66.900, sxj=51.700, trrz=1.240,
            yxtchd=120.000, gchd=17.000, jhxllz=0.0, jhxqlz=0.0,
            ejnyq=1, xqmc=8, zdgc=6, psnl=3, ggnl=2, dxbw=6, zdgx=6,
        )
        result = evaluate_land_quality(config, parcel)
        obstacles = compute_obstacle_factors(config, parcel.ejnyq, result.y)
        assert len(obstacles) == 12
        factors = [o.factor for o in obstacles]
        assert factors == sorted(factors, reverse=True)

    def test_a0001_top_obstacle_is_zdgx(self, config):
        """A0001 首要障碍因子为质地构型（与 exe 历史输出一致）。"""
        from ai_culti_demo.farmland_grade_eval.models import Parcel
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        from ai_culti_demo.farmland_grade_eval.obstacle import compute_obstacle_factors
        parcel = Parcel(
            tybh="A0001", jd=112.973801, wd=25.324301, mj=100.0,
            sjd=4.600, yjz=16.200, yxl=66.900, sxj=51.700, trrz=1.240,
            yxtchd=120.000, gchd=17.000, jhxllz=0.0, jhxqlz=0.0,
            ejnyq=1, xqmc=8, zdgc=6, psnl=3, ggnl=2, dxbw=6, zdgx=6,
        )
        result = evaluate_land_quality(config, parcel)
        obstacles = compute_obstacle_factors(config, parcel.ejnyq, result.y)
        assert obstacles[0].name.strip() == "质地构型"
        assert abs(obstacles[0].factor - 0.169) < 0.01


# ========== Runner 集成测试 ==========

@pytest.fixture
def runner():
    from ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner
    return FarmlandGradeRunner()


class TestRunnerDeployment:
    """部署校验测试。"""

    def test_check_deployment_csv_exists(self, runner):
        """CSV 已部署时 check_deployment 返回 ready=True。"""
        result = runner.check_deployment()
        assert result["csv_exists"] is True
        assert result["ready"] is True
        assert "csv_path" in result

    def test_check_deployment_csv_missing(self, tmp_path):
        """CSV 不存在时 check_deployment 返回 ready=False。"""
        from ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner
        runner = FarmlandGradeRunner(dat_path=str(tmp_path / "nonexistent.csv"))
        result = runner.check_deployment()
        assert result["csv_exists"] is False
        assert result["ready"] is False


class TestRunnerRun:
    """runner.run() 端到端测试（需要 CSV 已部署）。"""

    def test_run_a0001_returns_ok(self, runner):
        result = runner.run("A0001")
        assert result["status"] == "ok"
        assert result["parcel_code"] == "A0001"
        assert result["model_version"] == "python_v1_20260801"

    def test_run_a0001_composite_index_regression(self, runner):
        """A0001 综合指数与 exe 历史输出 0.6728 一致。"""
        result = runner.run("A0001")
        assert abs(result["composite_index"] - 0.6728) < 0.01

    def test_run_a0001_quality_grade(self, runner):
        result = runner.run("A0001")
        assert result["quality_grade"] == "10等"

    def test_run_a0001_parcel_info(self, runner):
        result = runner.run("A0001")
        info = result["parcel_info"]
        assert info["地块代码"] == "A0001"
        assert "经度" in info
        assert "纬度" in info
        assert info["县区名称"] == "武江区"
        assert info["二级农业区名称"].strip() == "闽南粤中农林水产区"

    def test_run_a0001_indicators_format(self, runner):
        """12 项指标，数值型 raw_value 格式为 {:.3f}，概念型为名称。"""
        result = runner.run("A0001")
        indicators = result["indicators"]
        assert len(indicators) == 12
        assert indicators[0] == {"name": "酸碱度", "code": "SJD", "raw_value": "4.600"}
        # 概念型指标（耕层质地）
        gczd = [i for i in indicators if i["code"] == "GCZD"][0]
        assert gczd["name"] == "耕层质地"
        assert gczd["raw_value"] == "黏壤土"

    def test_run_a0001_obstacle_degree(self, runner):
        """12 项障碍度，按 degree 降序，rank 1-12 递增。"""
        result = runner.run("A0001")
        obstacles = result["obstacle_degree"]
        assert len(obstacles) == 12
        assert obstacles[0]["indicator"] == "质地构型"
        assert abs(obstacles[0]["degree"] - 0.169) < 0.01
        assert obstacles[0]["level"].strip() == "中度障碍"
        assert [o["rank"] for o in obstacles] == list(range(1, 13))
        degrees = [o["degree"] for o in obstacles]
        assert degrees == sorted(degrees, reverse=True)

    def test_run_invalid_parcel_returns_error(self, runner):
        result = runner.run("INVALID_CODE_99999")
        assert result["status"] == "error"
        assert result["error"]["code"] == "PARCEL_NOT_FOUND"

    def test_run_csv_missing_returns_deployment_error(self, tmp_path):
        from ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner
        runner = FarmlandGradeRunner(dat_path=str(tmp_path / "nonexistent.csv"))
        result = runner.run("A0001")
        assert result["status"] == "error"
        assert result["error"]["code"] == "DEPLOYMENT_ERROR"


class TestBackwardCompatibility:
    """向后兼容测试。"""

    def test_run_grade_evaluation_default_path(self):
        from ai_culti_demo.farmland_grade_eval.runner import run_grade_evaluation
        result = run_grade_evaluation("A0001")
        assert result["status"] == "ok"

    def test_run_grade_evaluation_with_exe_path_ignored(self):
        """传 exe_path（旧调用方式）不报错，被忽略。"""
        from ai_culti_demo.farmland_grade_eval.runner import run_grade_evaluation
        result = run_grade_evaluation("A0001", exe_path="bin/nonexistent.exe")
        assert result["status"] == "ok"

    def test_runner_init_with_exe_and_dat_path(self):
        """FarmlandGradeRunner 接受 exe_path 和 dat_path 参数。"""
        from ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner
        runner = FarmlandGradeRunner(exe_path="ignored.exe", dat_path=None)
        assert runner.csv_path is not None  # 使用默认 CSV 路径


# ========== 潜力分析与县域统计测试 ==========

class TestPotentialAnalysis:
    """单地块潜力分析测试。"""

    def test_run_potential_analysis_a0001(self):
        from ai_culti_demo.farmland_grade_eval.runner import run_potential_analysis
        result = run_potential_analysis("A0001")
        assert result["status"] == "ok"
        assert result["parcel_code"] == "A0001"
        assert "original" in result
        assert "full_potential" in result
        assert "items" in result
        assert isinstance(result["items"], list)

    def test_run_potential_analysis_invalid_parcel(self):
        from ai_culti_demo.farmland_grade_eval.runner import run_potential_analysis
        result = run_potential_analysis("INVALID_99999")
        assert result["status"] == "error"
        assert result["error"]["code"] == "PARCEL_NOT_FOUND"


class TestCountyStatistics:
    """县域统计测试。"""

    def test_run_county_statistics_wujiang(self):
        """武江区（xqmc=8）县域常规统计。"""
        from ai_culti_demo.farmland_grade_eval.runner import run_county_statistics
        result = run_county_statistics(8)
        assert result["status"] == "ok"
        assert result["county_code"] == 8
        assert "stats" in result
        assert result["stats"]["parcel_count"] > 0

    def test_run_county_statistics_no_data(self):
        from ai_culti_demo.farmland_grade_eval.runner import run_county_statistics
        result = run_county_statistics(999)
        assert result["status"] == "error"
        assert result["error"]["code"] == "NO_DATA"

    def test_run_county_potential_ideal(self):
        """武江区理想潜力（scenario=1）。"""
        from ai_culti_demo.farmland_grade_eval.runner import run_county_potential
        result = run_county_potential(8, 1)
        assert result["status"] == "ok"
        assert result["scenario"] == 1

    def test_run_county_potential_best(self):
        """武江区最佳潜力（scenario=2）。"""
        from ai_culti_demo.farmland_grade_eval.runner import run_county_potential
        result = run_county_potential(8, 2)
        assert result["status"] == "ok"
        assert result["scenario"] == 2
