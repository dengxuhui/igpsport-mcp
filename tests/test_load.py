import pandas as pd
import pytest

from igpsport_mcp.analysis import load


def _series(values, start="2026-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype="float64")


def test_empty_input():
    df = load.compute_load(pd.Series(dtype="float64"))
    assert list(df.columns) == ["tss", "ctl", "atl", "tsb"]
    assert df.empty


def test_constant_tss_converges_ctl_atl_equal():
    df = load.compute_load(_series([100.0] * 400))
    last = df.iloc[-1]
    assert last["ctl"] == pytest.approx(100.0, abs=1.0)
    assert last["atl"] == pytest.approx(100.0, abs=0.01)
    assert last["tsb"] == pytest.approx(0.0, abs=1.0)


def test_matches_direct_ewm_formula():
    s = _series([50, 0, 120, 0, 0, 90, 200])
    df = load.compute_load(s)
    exp_ctl = s.ewm(alpha=1 / 42, adjust=False).mean()
    exp_atl = s.ewm(alpha=1 / 7, adjust=False).mean()
    assert df["ctl"].to_numpy() == pytest.approx(exp_ctl.to_numpy())
    assert df["atl"].to_numpy() == pytest.approx(exp_atl.to_numpy())
    assert df["tsb"].to_numpy() == pytest.approx((exp_ctl - exp_atl).to_numpy())


def test_sparse_input_is_filled_with_rest_days():
    # Two rides 3 days apart -> the 2 gap days must appear with tss=0.
    s = pd.Series(
        [100.0, 80.0],
        index=pd.to_datetime(["2026-01-01", "2026-01-04"]),
    )
    df = load.compute_load(s)
    assert len(df) == 4
    assert df["tss"].tolist() == [100.0, 0.0, 0.0, 80.0]


def test_same_day_tss_is_summed():
    s = pd.Series(
        [30.0, 40.0],
        index=pd.to_datetime(["2026-01-01", "2026-01-01"]),
    )
    df = load.compute_load(s)
    assert len(df) == 1
    assert df["tss"].iloc[0] == 70.0


def test_interpret_form_buckets():
    assert "very overloaded" in load.interpret_form(80, 120, -35)
    assert load.interpret_form(80, 100, -20).count("overloaded") == 1  # not "very"
    assert "neutral" in load.interpret_form(70, 70, 0)
    assert "fresh" in load.interpret_form(70, 55, 15)
    assert "detraining" in load.interpret_form(40, 10, 30)
