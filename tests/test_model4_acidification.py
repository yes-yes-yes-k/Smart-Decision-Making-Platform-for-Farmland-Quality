# tests/test_model4_acidification.py
r"""Task 2: 过程模型核心实现 —— 4 子模型 + 统一入口测试。

EXPECTED 数值由模型5源码 (D:\destkop\模型5\模型5\02_酸化模型计算-地块.py)
在 pHstart=4.31, Hex=1.56, Alex=4.08（默认参数）下实际运行得到，
作为正确性闸门（±0.01）。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import math
from ai_culti_demo.farmland_diagnosis.acidification import calculate_acidification_amendment

PHSTART, HEX, ALEX = 4.31, 1.56, 4.08

# 由模型5源码实际运行得到（pHstart=4.31, Hex=1.56, Alex=4.08，默认参数）
EXPECTED = {
    "paddy_urea":     {"ytk": 5423.819572068497,  "mbnt": 36951.2817398645},
    "paddy_compound": {"ytk": 5401.165208898515,  "mbnt": 37309.08734902578},
    "upland_urea":    {"ytk": 6930.7207016014145, "mbnt": 8021.4736205481895},
    "upland_compound":{"ytk": 6413.593476901521,  "mbnt": 11814.123053654765},
}


def _approx(a, b, tol=0.01):
    return a is not None and b is not None and abs(a - b) <= tol


# --- Step 2: 计算正确性 + 子模型选择（覆盖 6.1/6.2） ---
def test_four_submodels_calculation():
    cases = [
        ("paddy",  "urea",     "paddy_urea"),
        ("paddy",  "compound", "paddy_compound"),
        ("upland", "urea",     "upland_urea"),
        ("upland", "compound", "upland_compound"),
    ]
    for lt, ft, sub in cases:
        r = calculate_acidification_amendment(PHSTART, HEX, ALEX, land_type=lt, fertilizer_type=ft)
        assert r["status"] == "success", f"{sub} status={r.get('status')}, reason={r.get('reason')}"
        assert r["sub_model"] == sub
        assert _approx(r["ytk"], EXPECTED[sub]["ytk"]), f"{sub} ytk={r['ytk']} expected={EXPECTED[sub]['ytk']}"
        assert _approx(r["mbnt"], EXPECTED[sub]["mbnt"]), f"{sub} mbnt={r['mbnt']} expected={EXPECTED[sub]['mbnt']}"


def test_submodel_selection():
    assert calculate_acidification_amendment(PHSTART,HEX,ALEX,land_type="upland",fertilizer_type="compound")["sub_model"]=="upland_compound"
    assert calculate_acidification_amendment(PHSTART,HEX,ALEX,land_type="upland",fertilizer_type="urea")["sub_model"]=="upland_urea"
    assert calculate_acidification_amendment(PHSTART,HEX,ALEX,land_type="paddy",fertilizer_type="compound")["sub_model"]=="paddy_compound"
    assert calculate_acidification_amendment(PHSTART,HEX,ALEX,land_type="paddy",fertilizer_type="urea")["sub_model"]=="paddy_urea"


# --- Step 8: 非法回退 / 校验 / 覆盖（覆盖 6.3/6.4/6.5） ---
def test_invalid_land_fertilizer_fallback():
    r = calculate_acidification_amendment(4.31,1.56,4.08,land_type="foo",fertilizer_type="bar")
    assert r["status"] == "success"
    assert r["land_type"] == "upland" and r["fertilizer_type"] == "compound"
    assert "warning" in r and "upland" in r["warning"]


def test_missing_input_rejected():
    # SJD(pHstart) 缺失
    r = calculate_acidification_amendment(None,1.56,4.08)
    assert r["status"] == "rejected" and r["reason"] == "missing_input"
    # JHX(Hex) 缺失
    r_hex = calculate_acidification_amendment(4.31,None,4.08)
    assert r_hex["status"] == "rejected" and r_hex["reason"] == "missing_input"
    # JLA(Alex) 缺失
    r_alex = calculate_acidification_amendment(4.31,1.56,None)
    assert r_alex["status"] == "rejected" and r_alex["reason"] == "missing_input"


def test_out_of_range_rejected():
    r1 = calculate_acidification_amendment(2.5,1.56,4.08)
    assert r1["status"]=="rejected" and r1["reason"]=="input_out_of_range"
    r2 = calculate_acidification_amendment(4.31,-1.0,4.08)
    assert r2["status"]=="rejected" and r2["reason"]=="input_out_of_range"
    # JLA(Alex) 负数
    r3 = calculate_acidification_amendment(4.31,1.56,-1.0)
    assert r3["status"]=="rejected" and r3["reason"]=="input_out_of_range"


def test_optional_param_override():
    default = calculate_acidification_amendment(4.31,1.56,4.08,land_type="upland",fertilizer_type="urea")
    custom = calculate_acidification_amendment(4.31,1.56,4.08,land_type="upland",fertilizer_type="urea",FertN=200.0)
    assert custom["customized_params"] == {"FertN": 200.0}
    assert abs(custom["ytk"] - default["ytk"]) > 0.01 or abs(custom["mbnt"] - default["mbnt"]) > 0.01


def test_model_version_present():
    r = calculate_acidification_amendment(PHSTART, HEX, ALEX)
    assert r.get("model_version") == "process_v1_20260801"
