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


# --- Task 3: model_4_execution 入口测试（覆盖 6.6） ---
from framework.domain.other_models.model_4 import model_4_execution


def test_model4_execution_direct_inputs():
    r = model_4_execution({"SJD": 4.31, "JHX": 1.56, "JLA": 4.08}, land_type="upland", fertilizer_type="urea")
    assert r["status"] == "success"
    assert r["sub_model"] == "upland_urea"
    assert r["model_version"] == "process_v1_20260801"
    assert r["ytk"] is not None


def test_model4_execution_parcel_id_supplement(monkeypatch):
    from framework.domain.other_models import model_4
    monkeypatch.setattr(model_4, "_query_sjd_by_parcel_id", lambda parcel_id, db_path=None: 5.5)
    r = model_4_execution({"parcel_id": "1", "JHX": 1.56, "JLA": 4.08})
    assert r["status"] == "success"


def test_model4_execution_parcel_id_not_found(monkeypatch):
    from framework.domain.other_models import model_4
    monkeypatch.setattr(model_4, "_query_sjd_by_parcel_id", lambda parcel_id, db_path=None: None)
    r = model_4_execution({"parcel_id": "999", "JHX": 1.56, "JLA": 4.08})
    assert r["status"] == "rejected" and r["reason"] == "cannot_get_ph"


def test_model4_execution_missing_input():
    r = model_4_execution({"SJD": 4.31})
    assert r["status"] == "rejected" and r["reason"] == "missing_input"


# --- Task 1 (sync-acidification-model-v2): _finalize 返回 7 字段（方案 A） ---
from ai_culti_demo.farmland_diagnosis.acidification import (
    _paddy_urea, _paddy_compound, _upland_urea, _upland_compound,
    _PADDY_DEFAULTS, _UPLAND_DEFAULTS, _PADDY_COMPOUND_EXTRA, _UPLAND_COMPOUND_EXTRA,
)

_SEVEN_KEYS = {"Adep", "Acrop", "ANcy", "Aagri", "Aback", "ytk", "mbnt"}


def test_submodel_returns_seven_fields():
    """方案 A 重构闸门：4 个子模型函数必须返回恰好 7 字段 dict。

    keys = {Adep, Acrop, ANcy, Aagri, Aback, ytk, mbnt}，
    其中 Adep/Acrop/ANcy/Aagri 为中间变量，Aback/ytk/mbnt 为收尾计算结果。
    """
    paddy_p = dict(_PADDY_DEFAULTS); paddy_p.update(_PADDY_COMPOUND_EXTRA)
    upland_p = dict(_UPLAND_DEFAULTS); upland_p.update(_UPLAND_COMPOUND_EXTRA)
    submodels = [
        ("paddy_urea",      _paddy_urea,      dict(_PADDY_DEFAULTS)),
        ("paddy_compound",  _paddy_compound,  paddy_p),
        ("upland_urea",     _upland_urea,     dict(_UPLAND_DEFAULTS)),
        ("upland_compound", _upland_compound, upland_p),
    ]
    for name, fn, p in submodels:
        out = fn(PHSTART, HEX, ALEX, p)
        assert isinstance(out, dict), f"{name} 未返回 dict"
        assert set(out.keys()) == _SEVEN_KEYS, (
            f"{name} 返回字段不符：expected={sorted(_SEVEN_KEYS)}, got={sorted(out.keys())}"
        )
        # 中间变量必须为有限数值（非 None/NaN）
        for k in _SEVEN_KEYS:
            v = out[k]
            assert v is not None and not (isinstance(v, float) and math.isnan(v)), (
                f"{name}.{k} 为 None/NaN: {v!r}"
            )


# --- Task 2 (sync-acidification-model-v2): _build_params 参数装配 ---
from ai_culti_demo.farmland_diagnosis.acidification import _build_params


def test_build_params():
    """`_build_params` 必须返回与内联逻辑等价的默认参数 dict 副本（不含可配覆盖）。"""
    # upland / urea：仅基础默认参数
    assert _build_params("upland", "urea") == dict(_UPLAND_DEFAULTS)
    # upland / compound：基础 + 复合肥额外参数
    expected_upland_c = dict(_UPLAND_DEFAULTS); expected_upland_c.update(_UPLAND_COMPOUND_EXTRA)
    assert _build_params("upland", "compound") == expected_upland_c
    # paddy / urea：仅基础默认参数
    assert _build_params("paddy", "urea") == dict(_PADDY_DEFAULTS)
    # paddy / compound：基础 + 复合肥额外参数
    expected_paddy_c = dict(_PADDY_DEFAULTS); expected_paddy_c.update(_PADDY_COMPOUND_EXTRA)
    assert _build_params("paddy", "compound") == expected_paddy_c

    # 返回必须是副本：修改返回值不得污染模块级常量
    p = _build_params("upland", "compound")
    p["FertN"] = 9999.0
    p["YN"] = -1.0
    assert _UPLAND_DEFAULTS["FertN"] == 180.0
    assert _UPLAND_COMPOUND_EXTRA["YN"] == 1.91
