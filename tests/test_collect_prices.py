import pandas as pd
import pytest
import collect_prices as cp

def _df(dates, closes):
    return pd.DataFrame({"종가": closes},
                        index=pd.to_datetime(dates))

def test_horizon_dates_calendar_add():
    h = cp.horizon_dates("2025-01-31")
    assert h["1M"] == "20250228"          # 말일 보정
    assert h["6M"] == "20250731"
    assert "NOW" in h

def test_horizon_dates_skips_future():
    h = cp.horizon_dates("2026-07-01")    # 실행일 기준 12M 미도래
    assert "12M" not in h and "NOW" in h

def test_calc_returns_next_trading_day_and_excess():
    px = _df(["2024-01-02", "2024-02-05"], [12000, 15000])
    idx = _df(["2024-01-02", "2024-02-05"], [800.0, 840.0])
    out = cp.calc_returns(px, idx, base_price=10000,
                          listing_date="2024-01-02",
                          horizons={"1M": "20240202"})   # 2/2 휴장 → 2/5 종가
    r = out[0]
    assert r["abs_return"] == 50.0                       # 15000/10000-1
    assert r["excess_return"] == pytest.approx(45.0)     # 50% - 지수 5%
    assert r["price_date"] == "2024-02-05"

def test_calc_returns_delisted_null():
    px = _df(["2024-01-02"], [12000])                    # 이후 데이터 없음
    idx = _df(["2024-01-02", "2024-08-01"], [800.0, 900.0])
    out = cp.calc_returns(px, idx, 10000, "2024-01-02",
                          {"6M": "20240702"})
    assert out[0]["abs_return"] is None
