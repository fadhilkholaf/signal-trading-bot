import pandas as pd
from app.indicators.technical import ema, rsi, confirmed_pivots


def test_ema_is_defined_after_warmup():
    result = ema(pd.Series(range(1, 20), dtype=float), 5)
    assert result.iloc[:4].isna().all() and result.iloc[-1] > result.iloc[5]


def test_rsi_rises_on_gain_series():
    result = rsi(pd.Series(range(1, 30), dtype=float), 5)
    assert result.iloc[-1] > 90


def test_pivots_require_confirmation_bars():
    frame = pd.DataFrame({"high":[1,2,3,2,1,2,4,2,1], "low":[0,1,2,1,0,1,3,1,0]})
    highs, lows = confirmed_pivots(frame, 1, 1)
    assert 2 in highs and 6 in highs

