import hashlib
import logging
import math
from datetime import datetime, timezone

from .risk import calculate_levels, stop_too_close_to_levels
from app.models import Signal, SignalType
from app.indicators.technical import add_indicators, confirmed_pivots, structure_direction
from app.indicators.smc import level_near_price, smc_snapshot, support_resistance, zone_near_price

logger = logging.getLogger(__name__)


def _valid(row, fields):
    return all(row.get(field) is not None and math.isfinite(float(row[field])) for field in fields)


def _zone_kind(zone):
    return zone.kind if hasattr(zone, "kind") else zone["kind"]


def _trend(frame, settings):
    row = frame.iloc[-1]
    structure = structure_direction(frame, settings.pivot_left_bars, settings.pivot_right_bars)
    if row.ema50 > row.ema200 and row.close > row.ema50 and structure == "bullish": return "bullish"
    if row.ema50 < row.ema200 and row.close < row.ema50 and structure == "bearish": return "bearish"
    return "neutral"


def _indicator_direction(frame, settings):
    row = frame.iloc[-1]
    if not _valid(row, ["ema20", "ema50", "rsi", "macd", "macd_signal", "macd_hist"]): return "neutral"
    if row.ema20 > row.ema50 and settings.rsi_long_min <= row.rsi <= settings.rsi_long_max and row.macd > row.macd_signal and row.macd_hist > 0 and row.close > row.ema20: return "bullish"
    if row.ema20 < row.ema50 and settings.rsi_short_min <= row.rsi <= settings.rsi_short_max and row.macd < row.macd_signal and row.macd_hist < 0 and row.close < row.ema20: return "bearish"
    return "neutral"


def _spread(market, settings):
    if not market: return None, "spread unavailable"
    bid, ask = market.get("bid"), market.get("ask")
    timestamp = market.get("timestamp")
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid: return None, "spread invalid or unavailable"
    if timestamp is not None and (datetime.now(timezone.utc).timestamp() * 1000 - timestamp) > settings.max_ticker_age_seconds * 1000: return None, "spread ticker stale"
    spread = (ask - bid) / ((ask + bid) / 2) * 100
    return spread, "spread excessive" if spread > settings.max_spread_percent else None


def _countertrend_choch_allowed(settings, trend, indicator_direction, structure_snapshot):
    return bool(settings.strategy_profile == "AGGRESSIVE" and trend in {"bullish", "bearish"} and indicator_direction != trend and structure_snapshot.get("event") == "CHOCH" and structure_snapshot.get("event_direction") == trend)


def meets_condition_threshold(condition_results: dict[str, bool], minimum: int) -> bool:
    return sum(bool(value) for value in condition_results.values()) >= minimum


def make_signal(symbol: str, frames: dict[str, object], settings, market: dict | None = None) -> Signal:
    four, one, fifteen = (add_indicators(frames[x], settings) for x in ("4h", "1h", "15m"))
    row, prev = fifteen.iloc[-1], fifteen.iloc[-2]
    trend, indicator_direction = _trend(four, settings), _indicator_direction(one, settings)
    four_smc, one_smc, fifteen_smc = (smc_snapshot(frame, settings) for frame in (four, one, fifteen))
    countertrend_choch = _countertrend_choch_allowed(settings, trend, indicator_direction, one_smc)
    direction = trend if trend in {"bullish", "bearish"} and (indicator_direction == trend or countertrend_choch) else None
    levels = support_resistance(fifteen, settings)
    atr_value = float(row.atr) if _valid(row, ["atr"]) else 0.0
    spread_percent, spread_failure = _spread(market, settings)
    refinement_status = "not_configured"
    entry_atr = atr_value
    refined_entry = float(row.close)
    if settings.use_5m_entry_refinement:
        refinement = frames.get(settings.entry_refinement_timeframe)
        if refinement is None or len(refinement) < 2:
            refinement_status = "fallback_15m_unavailable"
        else:
            refined = add_indicators(refinement, settings)
            refined_row, refined_prev = refined.iloc[-1], refined.iloc[-2]
            refined_body = abs(refined_row.close - refined_row.open) / (refined_row.high - refined_row.low) if refined_row.high > refined_row.low else 0
            refined_ok = bool(direction == "LONG" and refined_row.close > refined_prev.high and refined_body >= settings.min_body_ratio or direction == "SHORT" and refined_row.close < refined_prev.low and refined_body >= settings.min_body_ratio)
            if refined_ok and _valid(refined_row, ["atr"]):
                refinement_status, refined_entry, entry_atr = "used", float(refined_row.close), float(refined_row.atr)
            else:
                refinement_status = "fallback_15m_unconfirmed"
    body_ratio = abs(row.close - row.open) / (row.high - row.low) if row.high > row.low else 0
    pullback = bool(atr_value and min(abs(row.close-row.ema20), abs(row.close-row.ema50)) <= settings.pullback_atr_distance * atr_value)
    candle = bool((direction == "LONG" and row.close > prev.high and body_ratio >= settings.min_body_ratio and row.close > (row.high+row.low)/2) or (direction == "SHORT" and row.close < prev.low and body_ratio >= settings.min_body_ratio and row.close < (row.high+row.low)/2))
    current_support = [level for level in levels if level.kind == "support" and level_near_price(level, float(row.close), atr_value, settings.sr_near_atr_distance)]
    current_resistance = [level for level in levels if level.kind == "resistance" and level_near_price(level, float(row.close), atr_value, settings.sr_near_atr_distance)]
    bullish_zones = [zone for zone in fifteen_smc["order_blocks"] + fifteen_smc["fair_value_gaps"] if _zone_kind(zone) in {"bullish_order_block", "bullish_fvg"} and zone_near_price(zone, float(row.close), atr_value, settings.smc_zone_tolerance_atr)]
    bearish_zones = [zone for zone in fifteen_smc["order_blocks"] + fifteen_smc["fair_value_gaps"] if _zone_kind(zone) in {"bearish_order_block", "bearish_fvg"} and zone_near_price(zone, float(row.close), atr_value, settings.smc_zone_tolerance_atr)]
    bullish_event = fifteen_smc["liquidity_sweep"] == "bullish" or fifteen_smc["event_direction"] == "bullish"
    bearish_event = fifteen_smc["liquidity_sweep"] == "bearish" or fifteen_smc["event_direction"] == "bearish"
    directional_zones = bool(current_support or bullish_zones) if direction == "LONG" else bool(current_resistance or bearish_zones) if direction == "SHORT" else False
    smc_confirmation = (bullish_event if direction == "LONG" else bearish_event if direction == "SHORT" else False) or countertrend_choch
    volume_ok = all(_valid(frame.iloc[-1], ["volume_ratio"]) and frame.iloc[-1].volume_ratio >= settings.min_volume_ratio for frame in (four, one, fifteen))
    volatility_ok = atr_value > 0 and float(row.atr) / float(row.close) <= settings.max_atr_percent and (not _valid(row, ["tr_zscore"]) or abs(float(row.tr_zscore)) <= settings.max_true_range_zscore)
    complete_ok = all(len(frame) > 1 and frame.index.is_monotonic_increasing for frame in (four, one, fifteen)) and bool(market is None or market.get("candles_complete", True))
    structure_conflict = bool(direction and ((four_smc["structure"] not in {"neutral", direction}) or (fifteen_smc["structure"] not in {"neutral", direction}) or (one_smc["structure"] not in {"neutral", direction} and not countertrend_choch)))
    conflict = structure_conflict or bool(bullish_zones and bearish_zones) or bool(current_support and current_resistance)
    entry = refined_entry
    highs, lows = confirmed_pivots(fifteen, settings.pivot_left_bars, settings.pivot_right_bars)
    all_support = [level for level in levels if level.kind == "support" and level.price < entry]
    all_resistance = [level for level in levels if level.kind == "resistance" and level.price > entry]
    swing = None
    if direction == "LONG" and lows: swing = min([float(fifteen.low.iloc[lows[-1]])] + [level.price for level in all_support])
    if direction == "SHORT" and highs: swing = max([float(fifteen.high.iloc[highs[-1]])] + [level.price for level in all_resistance])
    stop = target = rr = None
    risk_quality = False
    if direction:
        try:
            stop, target, risk = calculate_levels(direction, entry, entry_atr, swing, settings)
            rr = abs(target-entry) / risk
            nearby = all_support if direction == "LONG" else all_resistance
            risk_quality = rr >= settings.min_risk_reward and not stop_too_close_to_levels(direction, stop, nearby, entry_atr, settings.sr_stop_distance_atr)
        except (ValueError, TypeError):
            risk_quality = False
    conditions = {
        "4h_trend": bool(direction and trend == direction),
        "4h_structure": bool(direction and four_smc["structure"] == direction),
        "1h_ema": bool(direction and (indicator_direction == direction or countertrend_choch)),
        "1h_rsi_macd": bool(direction and (indicator_direction == direction or countertrend_choch)),
        "1h_structure_volume": bool(direction and (one_smc["structure"] in {direction, "neutral"} or countertrend_choch) and volume_ok),
        "15m_pullback": pullback and bool(direction),
        "15m_candle": candle,
        "smc_confirmation": smc_confirmation,
        "sr_confluence": directional_zones,
        "risk_quality": risk_quality,
    }
    score = sum(conditions.values())
    hard_failures = []
    if not conditions["4h_trend"] or not conditions["4h_structure"]: hard_failures.append("4H trend or structure not aligned")
    if not conditions["1h_ema"] or not conditions["1h_rsi_macd"] or not conditions["1h_structure_volume"]: hard_failures.append("1H confirmation incomplete")
    if not conditions["15m_candle"] or not complete_ok: hard_failures.append("15M candle incomplete or unconfirmed")
    if not conditions["smc_confirmation"]: hard_failures.append("no directional SMC event")
    if not conditions["sr_confluence"]: hard_failures.append("no valid S/R or SMC zone confluence")
    if not volatility_ok: hard_failures.append("abnormal volatility")
    if not volume_ok: hard_failures.append("insufficient volume")
    if spread_failure: hard_failures.append(spread_failure)
    if spread_percent is None: hard_failures.append("spread unavailable")
    if conflict: hard_failures.append("indicator, SMC, or S/R conflict")
    if not conditions["risk_quality"]: hard_failures.append(f"invalid stop or risk/reward below 1:{settings.min_risk_reward:g}")
    if not meets_condition_threshold(conditions, settings.min_conditions_required): hard_failures.append(f"condition score {score}/10 below {settings.min_conditions_required}/10")
    signal = SignalType(direction) if direction and not hard_failures else SignalType.NO_TRADE
    satisfied = [name for name, passed in conditions.items() if passed]
    explanation = f"Profile={settings.strategy_profile}; conditions={score}/10; passed: {', '.join(satisfied) or 'none'}; " + ("all hard gates passed" if signal != SignalType.NO_TRADE else "; ".join(dict.fromkeys(hard_failures)) or "uncertain")
    indicators = {"4h": {"ema50": float(four.iloc[-1].ema50), "ema200": float(four.iloc[-1].ema200), "structure": trend, "smc_structure": four_smc["structure"]}, "1h": {"ema20": float(one.iloc[-1].ema20), "ema50": float(one.iloc[-1].ema50), "rsi": float(one.iloc[-1].rsi), "macd": float(one.iloc[-1].macd), "macd_hist": float(one.iloc[-1].macd_hist), "volume_ratio": float(one.iloc[-1].volume_ratio), "smc_structure": one_smc["structure"], "countertrend_choch": countertrend_choch}, "15m": {"atr": atr_value, "volume_ratio": float(row.volume_ratio), "tr_zscore": float(row.tr_zscore), "valid_levels": fifteen_smc["levels"], "smc_event": fifteen_smc["event"], "liquidity_sweep": fifteen_smc["liquidity_sweep"], "nearby_zones": [_zone_kind(zone) for zone in bullish_zones + bearish_zones]}, "entry_refinement": {"timeframe": settings.entry_refinement_timeframe, "status": refinement_status, "entry": refined_entry, "atr": entry_atr}, "profile": settings.strategy_profile, "condition_score": score, "condition_results": conditions, "spread_percent": spread_percent, "hard_gate_failures": list(dict.fromkeys(hard_failures))}
    source_ms = int(frames["15m"].index[-1].timestamp() * 1000)
    raw = f"{symbol}|{source_ms}|{signal}|{entry:.8f}|{stop}|{target}|{settings.strategy_profile}|{score}|{settings.strategy_version()}"
    fingerprint = hashlib.sha256(raw.encode()).hexdigest()
    rejection_reasons = tuple(dict.fromkeys(hard_failures))
    return Signal(symbol, signal, entry, entry-settings.entry_zone_atr_width*entry_atr if entry else None, entry+settings.entry_zone_atr_width*entry_atr if entry else None, stop, target, rr, ("4H", "1H", "15M") if signal != SignalType.NO_TRADE else (), indicators, explanation, source_ms, rejection_reasons=rejection_reasons, fingerprint=fingerprint, profile=settings.strategy_profile, condition_score=score, condition_results=conditions, spread_percent=spread_percent, hard_gate_failures=rejection_reasons)
