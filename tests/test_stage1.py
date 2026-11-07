"""Stage 1 (M2) tests: all synthetic and offline."""
import math

import numpy as np
import pytest

from app import stage1 as s1


def _sea(h=600, w=600, mean_db=-18.0, seed=0, patch=None):
    rng = np.random.default_rng(seed)
    lin = rng.gamma(shape=25.0, scale=1.0 / 25.0, size=(h, w)) * 10 ** (mean_db / 10)
    img = 10 * np.log10(lin)
    if patch:
        r0, r1, c0, c1, drop = patch
        img[r0:r1, c0:c1] -= drop
    return img


TR = (25.0, 0.0, 500000.0, 0.0, -25.0, 3000000.0)   # 25 m pixels, UTM-like


def test_db_linear_roundtrip():
    x = np.array([-25.0, -10.0, 0.0])
    assert np.allclose(s1.lin_to_db(s1.db_to_lin(x)), x)


def test_product_rtc_is_gamma0():
    p = s1.classify_product("Sentinel-1 IW GRD RTC via Microsoft Planetary Computer")
    assert p["quantity"] == "gamma0" and p["status"] == "available"
    assert s1.classify_product("")["status"] == "unavailable"


def test_normalization_known_value_in_linear_space():
    # theta == theta_ref -> unchanged
    out = s1.normalize_incidence(np.array([[-20.0]]), 34.0)
    assert out["status"] == "available"
    assert out["array_db"][0, 0] == pytest.approx(-20.0, abs=1e-9)
    # theta=45: factor = cos34/cos45 -> expected dB shift computed independently
    out = s1.normalize_incidence(np.array([[-20.0]]), 45.0)
    shift = 10 * math.log10(math.cos(math.radians(34)) / math.cos(math.radians(45)))
    assert out["array_db"][0, 0] == pytest.approx(-20.0 + shift, abs=1e-9)


def test_normalization_missing_or_bad_angle_unavailable():
    a = np.full((2, 2), -20.0)
    assert s1.normalize_incidence(a, None)["status"] == "unavailable"
    assert s1.normalize_incidence(a, 95.0)["status"] == "unavailable"
    assert s1.normalize_incidence(a, float("nan"))["status"] == "unavailable"


@pytest.mark.parametrize("speed,gate", [(2.9, "fail_low"), (3.0, "pass"), (7.0, "pass"),
                                        (12.0, "pass"), (12.1, "fail_high")])
def test_wind_gate_bounds(speed, gate):
    assert s1.wind_gate(speed)["gate"] == gate


def test_wind_gate_missing_is_not_pass():
    g = s1.wind_gate(None)
    assert g["status"] == "unavailable" and g["gate"] == "unknown"
    assert s1.wind_speed(float("nan"), 1.0) is None
    assert s1.wind_speed(3.0, 4.0) == pytest.approx(5.0)


def test_cfar_finds_dark_patch_and_reports_retention():
    img = _sea(patch=(250, 330, 250, 350, 8.0))     # 8 dB dark patch
    res = s1.cfar_screen(img, TR, "EPSG:32616")
    assert res["status"] == "available"
    assert res["params"]["block_factor"] == 4        # 100 m / 25 m
    assert res["n_windows"] >= 1
    w = max(res["windows"], key=lambda x: x["cells"])
    # patch rows 250-330, cols 250-350 must lie inside the window (with block rounding)
    assert w["row_range"][0] <= 252 and w["row_range"][1] >= 328
    assert w["col_range"][0] <= 252 and w["col_range"][1] >= 348
    assert 0.0 < res["retained_fraction"] < 0.2


def test_cfar_clean_sea_retains_almost_nothing():
    res = s1.cfar_screen(_sea(), TR, "EPSG:32616")
    assert res["status"] == "available"
    assert res["retained_fraction"] < 0.01


def test_cfar_is_deterministic():
    img = _sea(patch=(100, 180, 100, 180, 7.0))
    a = s1.cfar_screen(img, TR, "EPSG:32616")
    b = s1.cfar_screen(img, TR, "EPSG:32616")
    assert a == b


def test_cfar_all_nan_unavailable():
    res = s1.cfar_screen(np.full((50, 50), np.nan), TR, "EPSG:32616")
    assert res["status"] == "unavailable"


def test_cfar_ignores_nan_border():
    img = _sea()
    img[:, :100] = np.nan
    res = s1.cfar_screen(img, TR, "EPSG:32616")
    assert res["status"] == "available" and res["retained_fraction"] < 0.02


def test_run_stage1_missing_inputs_is_partial_with_warnings():
    img = _sea(patch=(250, 330, 250, 350, 8.0))
    doc = s1.run_stage1(img, TR, "EPSG:32616",
                        source="Sentinel-1 IW GRD RTC via Planetary Computer")
    assert doc["status"] == "partial"
    assert doc["wind_gate"]["gate"] == "unknown"
    assert doc["incidence_normalization"]["applied"] is False
    assert any("wind gate unknown" in w for w in doc["warnings"])


def test_run_stage1_all_inputs_available():
    img = _sea(patch=(250, 330, 250, 350, 8.0))
    doc = s1.run_stage1(img, TR, "EPSG:32616", source="Sentinel-1 RTC",
                        incidence_deg=38.0, wind_ms=6.0, wind_source="test")
    assert doc["status"] == "available"
    assert doc["wind_gate"]["gate"] == "pass"


def test_for_scene_never_raises_and_reports_unavailable():
    class Bad:
        id = "nope"; sar_path = "/nonexistent.tif"; source = ""; t_sat = "2023-01-01T00:00:00Z"
    out = s1.for_scene(Bad())
    assert out["status"] == "unavailable" and out["warnings"]
