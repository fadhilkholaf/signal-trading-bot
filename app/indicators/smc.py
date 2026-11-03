from dataclasses import dataclass
import math
import pandas as pd

from .technical import atr, confirmed_pivots, structure_direction


@dataclass(frozen=True)
class Level:
    price: float
    kind: str
    reactions: int
    last_index: int


@dataclass(frozen=True)
class Zone:
    kind: str
    low: float
    high: float
    index: int
    age: int = 0


def _atr_value(frame: pd.DataFrame, settings) -> float:
    values = atr(frame, settings.atr_period).dropna()
    return float(values.iloc[-1]) if not values.empty else 0.0


def support_resistance(frame: pd.DataFrame, settings) -> list[Level]:
    """Cluster confirmed swing reactions into objective, minimum-reaction levels."""
    current_atr = _atr_value(frame, settings)
    distance = current_atr * settings.sr_merge_atr_distance
    highs, lows = confirmed_pivots(frame, settings.sr_swing_left_bars, settings.sr_swing_right_bars)
    candidates = [(float(frame.high.iloc[i]), "resistance", i) for i in highs]
    candidates += [(float(frame.low.iloc[i]), "support", i) for i in lows]
    clusters: list[dict] = []
    for price, kind, index in sorted(candidates, key=lambda item: item[0]):
        cluster = next((c for c in clusters if c["kind"] == kind and abs(price - c["price"]) <= distance), None)
        if cluster:
            cluster["prices"].append(price)
            cluster["price"] = sum(cluster["prices"]) / len(cluster["prices"])
            cluster["last_index"] = max(cluster["last_index"], index)
        else:
            clusters.append({"price": price, "prices": [price], "kind": kind, "last_index": index})
    levels = [Level(c["price"], c["kind"], len(c["prices"]), c["last_index"]) for c in clusters if len(c["prices"]) >= settings.sr_min_reactions]
    return sorted(levels, key=lambda level: level.price)[-settings.sr_max_levels:]


def _crossed_up(frame: pd.DataFrame, index: int, level: float) -> bool:
    return index > 0 and float(frame.close.iloc[index]) > level >= float(frame.close.iloc[index - 1])


def _crossed_down(frame: pd.DataFrame, index: int, level: float) -> bool:
    return index > 0 and float(frame.close.iloc[index]) < level <= float(frame.close.iloc[index - 1])


def _latest_prior_pivot(frame: pd.DataFrame, kind: str, settings) -> tuple[int, float] | None:
    highs, lows = confirmed_pivots(frame, settings.smc_swing_left_bars, settings.smc_swing_right_bars)
    indexes = highs if kind == "high" else lows
    indexes = [i for i in indexes if i < len(frame) - settings.smc_swing_right_bars]
    if not indexes:
        return None
    index = indexes[-1]
    return index, float(frame.high.iloc[index] if kind == "high" else frame.low.iloc[index])


def _unbroken_before(frame: pd.DataFrame, pivot_index: int, level: float, direction: str) -> bool:
    closes = frame.close.iloc[pivot_index + 1:]
    if direction == "bullish":
        return not bool((closes > level).any())
    return not bool((closes < level).any())


def _event(frame: pd.DataFrame, settings) -> tuple[str, str | None]:
    """Return current-candle BOS/CHOCH event only after a close beyond a pivot."""
    index = len(frame) - 1
    prior = frame.iloc[:-1]
    if len(prior) < settings.smc_swing_left_bars + settings.smc_swing_right_bars + 3:
        return "neutral", None
    previous_structure = structure_direction(prior, settings.smc_swing_left_bars, settings.smc_swing_right_bars)
    high = _latest_prior_pivot(prior, "high", settings)
    low = _latest_prior_pivot(prior, "low", settings)
    bullish = high and _unbroken_before(prior, high[0], high[1], "bullish") and _crossed_up(frame, index, high[1])
    bearish = low and _unbroken_before(prior, low[0], low[1], "bearish") and _crossed_down(frame, index, low[1])
    if bullish:
        return "bullish", "CHOCH" if previous_structure == "bearish" else "BOS"
    if bearish:
        return "bearish", "CHOCH" if previous_structure == "bullish" else "BOS"
    return "neutral", None


def liquidity_sweep(frame: pd.DataFrame, settings) -> str:
    index = len(frame) - 1
    prior = frame.iloc[:-1]
    high = _latest_prior_pivot(prior, "high", settings)
    low = _latest_prior_pivot(prior, "low", settings)
    row = frame.iloc[-1]
    if high and row.high > high[1] and row.close <= high[1]:
        return "bearish"
    if low and row.low < low[1] and row.close >= low[1]:
        return "bullish"
    return "neutral"


def order_blocks(frame: pd.DataFrame, settings) -> list[Zone]:
    zones: list[Zone] = []
    current_atr = _atr_value(frame, settings)
    start = max(1, len(frame) - settings.smc_order_block_lookback)
    for i in range(start, len(frame) - 1):
        candle = frame.iloc[i]
        body = abs(candle.close - candle.open)
        candle_range = candle.high - candle.low
        if candle_range <= 0 or body / candle_range < settings.smc_order_block_min_body_ratio:
            continue
        displacement = abs(frame.close.iloc[i + 1] - candle.close)
        if displacement < settings.smc_displacement_atr * current_atr:
            continue
        if candle.close < candle.open and frame.close.iloc[i + 1] > candle.high:
            zone = Zone("bullish_order_block", float(candle.low), float(candle.high), i, len(frame) - 1 - i)
            if not bool((frame.close.iloc[i + 2:] < zone.low).any()): zones.append(zone)
        if candle.close > candle.open and frame.close.iloc[i + 1] < candle.low:
            zone = Zone("bearish_order_block", float(candle.low), float(candle.high), i, len(frame) - 1 - i)
            if not bool((frame.close.iloc[i + 2:] > zone.high).any()): zones.append(zone)
    return [zone for zone in zones if zone.age <= settings.smc_zone_max_age][-settings.smc_max_zones:]


def fair_value_gaps(frame: pd.DataFrame, settings) -> list[Zone]:
    zones: list[Zone] = []
    current_atr = _atr_value(frame, settings)
    start = max(0, len(frame) - settings.smc_fvg_lookback - 2)
    for i in range(start, len(frame) - 2):
        first, third = frame.iloc[i], frame.iloc[i + 2]
        if third.low > first.high and third.low - first.high >= settings.smc_fvg_min_atr * current_atr:
            zone = Zone("bullish_fvg", float(first.high), float(third.low), i + 1, len(frame) - 1 - (i + 1))
            if not bool((frame.close.iloc[i + 3:] < zone.low).any()): zones.append(zone)
        if third.high < first.low and first.low - third.high >= settings.smc_fvg_min_atr * current_atr:
            zone = Zone("bearish_fvg", float(third.high), float(first.low), i + 1, len(frame) - 1 - (i + 1))
            if not bool((frame.close.iloc[i + 3:] > zone.high).any()): zones.append(zone)
    return [zone for zone in zones if zone.age <= settings.smc_zone_max_age][-settings.smc_max_zones:]


def smc_snapshot(frame: pd.DataFrame, settings) -> dict:
    direction, structure_event = _event(frame, settings)
    def zone_dict(zone: Zone) -> dict:
        return {"kind": zone.kind, "low": zone.low, "high": zone.high, "source_index": zone.index, "age": zone.age}
    def level_dict(level: Level) -> dict:
        return {"price": level.price, "kind": level.kind, "reactions": level.reactions, "last_index": level.last_index}
    levels = support_resistance(frame, settings)
    return {"structure": structure_direction(frame, settings.smc_swing_left_bars, settings.smc_swing_right_bars), "event_direction": direction, "event": structure_event, "liquidity_sweep": liquidity_sweep(frame, settings), "levels": [level_dict(level) for level in levels], "order_blocks": [zone_dict(zone) for zone in order_blocks(frame, settings)], "fair_value_gaps": [zone_dict(zone) for zone in fair_value_gaps(frame, settings)]}


def zone_near_price(zone: Zone | dict, price: float, atr_value: float, tolerance_atr: float) -> bool:
    tolerance = atr_value * tolerance_atr
    low = zone.low if isinstance(zone, Zone) else zone["low"]
    high = zone.high if isinstance(zone, Zone) else zone["high"]
    return low - tolerance <= price <= high + tolerance or abs(price - low) <= tolerance or abs(price - high) <= tolerance


def level_near_price(level: Level, price: float, atr_value: float, tolerance_atr: float) -> bool:
    return abs(level.price - price) <= atr_value * tolerance_atr

