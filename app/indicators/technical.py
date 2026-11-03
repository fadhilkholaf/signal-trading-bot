import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    # A run with no losses has RSI 100; avoid turning the valid terminal value into NaN.
    return 100 - (100 / (1 + gain / loss.replace(0, np.finfo(float).eps)))


def macd(close: pd.Series, fast: int, slow: int, signal: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, sig, line - sig


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    prev = frame["close"].shift(1)
    tr = pd.concat([frame["high"] - frame["low"], (frame["high"] - prev).abs(), (frame["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def true_range(frame: pd.DataFrame) -> pd.Series:
    prev = frame["close"].shift(1)
    return pd.concat([frame["high"] - frame["low"], (frame["high"] - prev).abs(), (frame["low"] - prev).abs()], axis=1).max(axis=1)


def volume_ratio(frame: pd.DataFrame, period: int = 20) -> pd.Series:
    return frame["volume"] / frame["volume"].rolling(period, min_periods=period).mean()


def add_indicators(frame: pd.DataFrame, settings) -> pd.DataFrame:
    out = frame.copy()
    out["ema20"] = ema(out.close, settings.ema_fast_1h)
    out["ema50"] = ema(out.close, settings.ema_slow_1h)
    out["ema200"] = ema(out.close, settings.ema_slow_4h)
    out["rsi"] = rsi(out.close, settings.rsi_period)
    out["macd"], out["macd_signal"], out["macd_hist"] = macd(out.close, settings.macd_fast, settings.macd_slow, settings.macd_signal)
    out["atr"] = atr(out, settings.atr_period)
    out["volume_ratio"] = volume_ratio(out, settings.volume_sma_period)
    out["true_range"] = true_range(out)
    lookback = settings.volatility_lookback
    out["tr_zscore"] = (out.true_range - out.true_range.rolling(lookback).mean()) / out.true_range.rolling(lookback).std()
    return out


def confirmed_pivots(frame: pd.DataFrame, left: int, right: int) -> tuple[list[int], list[int]]:
    highs, lows = [], []
    for i in range(left, len(frame) - right):
        high = frame.high.iloc[i]
        low = frame.low.iloc[i]
        if high >= frame.high.iloc[i-left:i+right+1].max(): highs.append(i)
        if low <= frame.low.iloc[i-left:i+right+1].min(): lows.append(i)
    return highs, lows


def structure_direction(frame: pd.DataFrame, left: int, right: int) -> str:
    highs, lows = confirmed_pivots(frame, left, right)
    if len(highs) < 2 or len(lows) < 2: return "neutral"
    bullish = frame.high.iloc[highs[-1]] > frame.high.iloc[highs[-2]] and frame.low.iloc[lows[-1]] > frame.low.iloc[lows[-2]]
    bearish = frame.high.iloc[highs[-1]] < frame.high.iloc[highs[-2]] and frame.low.iloc[lows[-1]] < frame.low.iloc[lows[-2]]
    return "bullish" if bullish else "bearish" if bearish else "neutral"

