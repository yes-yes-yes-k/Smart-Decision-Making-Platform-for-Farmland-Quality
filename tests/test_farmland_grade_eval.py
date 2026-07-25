"""farmland_grade_eval runner.parse_output 单元测试。

使用捕获的真实 Fortran exe 输出样本（A0001 地块）验证 parse_output 各字段解析正确，
并覆盖空输出/格式异常等边界场景。
"""
import sys
from pathlib import Path

import pytest

# 将 src 加入 sys.path 以便导入 ai_culti_demo 包
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner


# 捕获的真实 exe 输出样本（A0001 地块）
REAL_OUTPUT_A0001 = """成功读取 1193 个采样点数据。

请输入要查询的地块代码 (输入 quit 退出): ------------------------------------------------
地块代码：A0001
经度：  112.973801
纬度：   25.324301
县区名称：武江区
二级农业区名称：闽南粤中农林水产区
------------------- 原始指标值 -------------------
酸碱度(SJD):    4.600
有机质含量(YJZ):   16.200
有效磷含量(YXL):   66.900
速效钾含量(SXJ):   51.700
土壤容重(TRRZ):    1.240
有效土层厚度(YXTCHD):  120.000
耕层厚度(GCHD):   17.000
耕层质地(GCZD): 黏壤土
排水能力(PSNL): 基本满足
灌溉能力(GGNL): 满足
地形部位(DXBW): 丘陵下部
质地构型(ZDGX): 薄层型
------------------------------------------------
耕地质量综合指数：  0.6728
耕地质量等级：10等
------------ 障碍度因子（从大到小） ------------
质地构型    :  0.1690  中度障碍
地形部位    :  0.1516  中度障碍
有机质      :  0.1484  中度障碍
速效钾      :  0.1384  中度障碍
排水能力    :  0.1292  中度障碍
酸碱度      :  0.1008  中度障碍
灌溉能力    :  0.0766  轻度障碍
质地构成    :  0.0506  轻度障碍
耕层厚度    :  0.0294  轻度障碍
土壤容重    :  0.0059  轻度障碍
有效磷      :  0.0000  无障碍
有效土层厚度:  0.0000  无障碍
------------------------------------------------

|----------------------------------------------------------------------------------------|
|   评价指标   | 原数据  |  潜力值  |  原综合指数  |  潜在指数  |  原等级  |  潜在等级  |
|----------------------------------------------------------------------------------------|
| 灌溉能力     | 满足     | 充分满足 |       0.6728 |     0.6979 |     10等 |       10等 |
|----------------------------------------------------------------------------------------|
| 原耕地质量综合指数为            0.6728，耕地质量等级为       10等
| 全部指标改良后潜在综合指数为    0.8786，潜在耕地质量等级为    2等
------------------------------------------------------------------------------------------

请输入要查询的地块代码 (输入 quit 退出): 程序结束。
"""


@pytest.fixture
def runner():
    return FarmlandGradeRunner()


class TestParseOutputRealSample:
    """使用真实 exe 输出样本验证 parse_output 各字段解析正确。"""

    def test_parses_parcel_info_correctly(self, runner):
        result = runner.parse_output(REAL_OUTPUT_A0001)
        parcel_info = result["parcel_info"]

        assert parcel_info["地块代码"] == "A0001"
        assert parcel_info["经度"] == "112.973801"
        assert parcel_info["纬度"] == "25.324301"
        assert parcel_info["县区名称"] == "武江区"
        assert parcel_info["二级农业区名称"] == "闽南粤中农林水产区"

    def test_parses_all_12_indicators(self, runner):
        result = runner.parse_output(REAL_OUTPUT_A0001)
        indicators = result["indicators"]

        assert len(indicators) == 12
        # 验证第一项指标
        assert indicators[0] == {
            "name": "酸碱度",
            "code": "SJD",
            "raw_value": "4.600",
        }
        # 验证最后一项指标
        assert indicators[-1] == {
            "name": "质地构型",
            "code": "ZDGX",
            "raw_value": "薄层型",
        }

    def test_parses_composite_index_as_float(self, runner):
        result = runner.parse_output(REAL_OUTPUT_A0001)
        assert result["composite_index"] == 0.6728
        assert isinstance(result["composite_index"], float)

    def test_parses_quality_grade_as_string(self, runner):
        result = runner.parse_output(REAL_OUTPUT_A0001)
        assert result["quality_grade"] == "10等"

    def test_parses_all_12_obstacle_degrees(self, runner):
        result = runner.parse_output(REAL_OUTPUT_A0001)
        obstacles = result["obstacle_degree"]

        assert len(obstacles) == 12
        # 验证第一项（最大障碍度）
        assert obstacles[0] == {
            "rank": 1,
            "indicator": "质地构型",
            "degree": 0.169,
            "level": "中度障碍",
        }
        # 验证最后一项（最小障碍度）
        assert obstacles[-1] == {
            "rank": 12,
            "indicator": "有效土层厚度",
            "degree": 0.0,
            "level": "无障碍",
        }

    def test_obstacle_ranks_are_sequential(self, runner):
        result = runner.parse_output(REAL_OUTPUT_A0001)
        ranks = [obs["rank"] for obs in result["obstacle_degree"]]
        assert ranks == list(range(1, 13))

    def test_obstacle_degrees_are_sorted_descending(self, runner):
        result = runner.parse_output(REAL_OUTPUT_A0001)
        degrees = [obs["degree"] for obs in result["obstacle_degree"]]
        assert degrees == sorted(degrees, reverse=True)

    def test_raw_output_preserved(self, runner):
        result = runner.parse_output(REAL_OUTPUT_A0001)
        assert result["raw_output"] == REAL_OUTPUT_A0001

    def test_no_extra_parcel_info_from_quit_prompt(self, runner):
        """确保 '请输入要查询的地块代码 (输入 quit 退出): 程序结束。' 不被误解析为 parcel_info。"""
        result = runner.parse_output(REAL_OUTPUT_A0001)
        parcel_info = result["parcel_info"]
        # 不应包含 '请输入要查询的地块代码' 这个误解析的 key
        assert "请输入要查询的地块代码" not in parcel_info
        assert len(parcel_info) == 5  # 只应有 5 个字段


class TestParseOutputBoundaryScenarios:
    """覆盖空输出/格式异常等边界场景。"""

    def test_empty_output(self, runner):
        result = runner.parse_output("")
        assert result["parcel_info"] == {}
        assert result["indicators"] == []
        assert result["composite_index"] is None
        assert result["quality_grade"] is None
        assert result["obstacle_degree"] == []

    def test_whitespace_only_output(self, runner):
        result = runner.parse_output("   \n\n  \n")
        assert result["parcel_info"] == {}
        assert result["indicators"] == []

    def test_no_parcel_code_line(self, runner):
        """无地块代码行时，parcel_info 应为空。"""
        output = """经度：  112.973801
纬度：   25.324301
------------------- 原始指标值 -------------------
酸碱度(SJD):    4.600
"""
        result = runner.parse_output(output)
        # 没有 '地块代码：' 行触发 parcel section，parcel_info 应为空
        assert result["parcel_info"] == {}

    def test_malformed_indicator_line_skipped(self, runner):
        """格式异常的指标行应被跳过，不影响其他指标解析。"""
        output = """地块代码：A0001
------------------- 原始指标值 -------------------
酸碱度(SJD):    4.600
这是格式错误的行没有冒号和括号
有机质含量(YJZ):   16.200
"""
        result = runner.parse_output(output)
        indicators = result["indicators"]
        assert len(indicators) == 2
        assert indicators[0]["name"] == "酸碱度"
        assert indicators[1]["name"] == "有机质含量"

    def test_obstacle_line_with_invalid_degree_skipped(self, runner):
        """障碍度值非数字的行应被跳过。"""
        output = """------------ 障碍度因子（从大到小） ------------
质地构型    :  0.1690  中度障碍
无效指标    :  abc  无效
地形部位    :  0.1516  中度障碍
"""
        result = runner.parse_output(output)
        obstacles = result["obstacle_degree"]
        assert len(obstacles) == 2
        assert obstacles[0]["indicator"] == "质地构型"
        assert obstacles[1]["indicator"] == "地形部位"

    def test_partial_sections_only_parcel(self, runner):
        """只有 parcel_info section 的输出。"""
        output = """地块代码：A0001
经度：  112.973801
纬度：   25.324301
"""
        result = runner.parse_output(output)
        assert result["parcel_info"]["地块代码"] == "A0001"
        assert result["indicators"] == []
        assert result["composite_index"] is None
        assert result["quality_grade"] is None
        assert result["obstacle_degree"] == []

    def test_composite_with_english_colon(self, runner):
        """综合指数行使用英文冒号时也能正确解析。"""
        output = """耕地质量综合指数: 0.85
耕地质量等级: 5等
"""
        result = runner.parse_output(output)
        assert result["composite_index"] == 0.85
        assert result["quality_grade"] == "5等"

    def test_potential_table_not_parsed_as_obstacle(self, runner):
        """潜力值表格行不应被误解析为 obstacle。"""
        output = """------------ 障碍度因子（从大到小） ------------
质地构型    :  0.1690  中度障碍
------------------------------------------------
|----------------------------------------------------------------------------------------|
|   评价指标   | 原数据  |  潜力值  |  原综合指数  |  潜在指数  |  原等级  |  潜在等级  |
|----------------------------------------------------------------------------------------|
| 灌溉能力     | 满足     | 充分满足 |       0.6728 |     0.6979 |     10等 |       10等 |
"""
        result = runner.parse_output(output)
        obstacles = result["obstacle_degree"]
        # 只应解析到 1 个障碍度项（质地构型），潜力值表格不应被误解析
        assert len(obstacles) == 1
        assert obstacles[0]["indicator"] == "质地构型"


class TestRunnerRunIntegration:
    """runner.run() 端到端集成测试（需要 exe 部署）。"""

    def test_run_with_valid_parcel_code_returns_ok(self, runner):
        """如果 exe 已部署，验证 runner.run('A0001') 返回 status=ok 且所有字段非空。

        如果 exe 未部署，跳过此测试（避免在 CI 环境失败）。
        """
        deployment = runner.check_deployment()
        if not deployment["ready"]:
            pytest.skip("exe 未部署，跳过端到端测试")

        result = runner.run("A0001")
        assert result["status"] == "ok"
        assert result["parcel_info"]["地块代码"] == "A0001"
        assert len(result["indicators"]) == 12
        assert result["composite_index"] is not None
        assert result["quality_grade"] is not None
        assert len(result["obstacle_degree"]) == 12

    def test_run_with_invalid_parcel_code_returns_error(self, runner):
        """如果 exe 已部署，验证无效地块代码返回 PARCEL_NOT_FOUND 错误。"""
        deployment = runner.check_deployment()
        if not deployment["ready"]:
            pytest.skip("exe 未部署，跳过端到端测试")

        result = runner.run("INVALID_CODE_99999")
        assert result["status"] == "error"
        assert result["error"]["code"] == "PARCEL_NOT_FOUND"
