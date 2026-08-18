# tests/calculations/test_acidification_calculation.py
from framework.domain.calculations.acidification_calculation import (
    paddy_urea, paddy_compound, upland_urea, upland_compound, calculate_acidification
)

def test_paddy_urea_returns_all_outputs():
    """paddy_urea 返回 7 个输出字段."""
    result = paddy_urea(SJD=5.0, Hex=3.0, Alex=0.5)
    assert "Adep" in result
    assert "Acrop" in result
    assert "ANcy" in result
    assert "Aagri" in result
    assert "Aback" in result
    assert "YTK" in result
    assert "MBNT" in result

def test_paddy_urea_ytk_positive():
    """paddy_urea YTK > 0 for valid inputs."""
    result = paddy_urea(SJD=5.0, Hex=3.0, Alex=0.5)
    assert result["YTK"] > 0
    assert result["MBNT"] > 0

def test_paddy_urea_known_value():
    """对照原始公式: paddy_urea(SJD=5, Hex=3, Alex=0.5) 的 YTK 值.

    独立重算计划公式（默认参数）下的 YTK，验证实现与公式一致。
    """
    import math
    # 默认参数（与 paddy_urea 默认值一致）
    RPH, R, Y, S = 5.5, 1893, 5109, 5109
    Yp, Yk, Yca, Ymg = 0.35, 0.19, 0.03, 0.12
    Sp, Sk, Sca, Smg = 0.176, 1.99, 0.54, 0.212
    FertN, Ndep, pHtarget = 180, 47.6, 6.5
    SJD, Hex, Alex = 5.0, 3.0, 0.5
    # 独立重算
    Adep = 10**(-RPH)*667*(R/1000)*1000*15
    Hgrain = (-Y*Yp*1000/100/30.97 + Y*Yk*1000/100/39.1
              + Y*Yca*1000/100*2/40.08 + Y*Ymg*1000/100*2/24.305)
    Hstraw = (-S*Sp*1000/100/30.97 + S*Sk*1000/100/39.1
              + S*Sca*1000/100*2/40.08 + S*Smg*1000/100*2/24.305)
    Acrop = Hgrain + Hstraw
    Anit = 2.221*math.exp(0.0048*(FertN+Ndep))*1000/14
    Ano3_runoff = (Ndep - (0.16*Ndep + 2.97))*1000/14*2
    Avol = (Ndep - (0.16*Ndep + 2.97))*1000/14*2
    ANcy = Anit + Ano3_runoff + 0 + Avol
    Aagri = Adep + Acrop + ANcy
    Aback = (6.25*10**(9-SJD) - 6.25*10**(9-pHtarget)
             + 2.5*Hex*10**7 + 2.5*Alex*10**7) / 1000
    expected_ytk = (Aback + 0.8*Aagri) / 17.042 * 0.6
    result = paddy_urea(SJD=5.0, Hex=3.0, Alex=0.5)
    assert abs(result["YTK"] - expected_ytk) < 1e-6

def test_upland_urea_different_ytk_coefficient():
    """upland_urea YTK 系数 0.77 (vs paddy 0.6)."""
    paddy_result = paddy_urea(SJD=5.0, Hex=3.0, Alex=0.5)
    upland_result = upland_urea(SJD=5.0, Hex=3.0, Alex=0.5)
    # upland 的 YTK 应大于 paddy（系数 0.77 > 0.6，且 crop 常数更大）
    assert upland_result["YTK"] != paddy_result["YTK"]

def test_calculate_acidification_paddy_urea():
    """calculate_acidification 选择 paddy_urea 函数."""
    result = calculate_acidification(
        SJD=5.0, Hex=3.0, Alex=0.5,
        land_type="paddy", fertilizer_type="urea", pHtarget=6.5)
    assert result["YTK"] > 0
    assert result["MBNT"] > 0

def test_calculate_acidification_upland_compound():
    """calculate_acidification 选择 upland_compound 函数."""
    result = calculate_acidification(
        SJD=5.0, Hex=3.0, Alex=0.5,
        land_type="upland", fertilizer_type="compound", pHtarget=6.0)
    assert result["YTK"] > 0
    assert result["MBNT"] > 0
