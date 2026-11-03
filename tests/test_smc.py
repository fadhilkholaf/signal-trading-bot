from types import SimpleNamespace
import pandas as pd

from app.indicators.smc import fair_value_gaps, liquidity_sweep, order_blocks, smc_snapshot, support_resistance


def cfg():
    return SimpleNamespace(atr_period=2, sr_swing_left_bars=1, sr_swing_right_bars=1, sr_merge_atr_distance=.5, sr_min_reactions=2, sr_max_levels=20, smc_swing_left_bars=1, smc_swing_right_bars=1, smc_displacement_atr=.2, smc_order_block_lookback=10, smc_order_block_min_body_ratio=.5, smc_fvg_lookback=10, smc_fvg_min_atr=.01, smc_max_zones=10, smc_zone_max_age=30)


def frame(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])


def test_repeated_swings_form_valid_level():
    data = frame([(9,10,8,9,1),(9,10,8,9,1),(9,10,8,9,1),(9,9,7,8,1),(9,10,8,9,1),(9,10,8,9,1),(9,10,8,9,1)])
    levels = support_resistance(data, cfg())
    assert any(level.kind == "resistance" and level.reactions >= 2 for level in levels)


def test_bearish_liquidity_sweep_breaks_and_closes_inside():
    data = frame([(9,8,7,8,1),(9,10,8,9,1),(8,8,7,8,1),(8,11,8,9,1)])
    assert liquidity_sweep(data, cfg()) == "bearish"


def test_fvg_and_order_block_are_detected():
    data = frame([(10,11,9,10,1),(10,10,8,8,1),(8,13,8,13,1),(13,14,12,13,1)])
    assert fair_value_gaps(data, cfg())
    assert order_blocks(data, cfg())


def test_bos_is_reported_after_close_beyond_swing():
    data = frame([(9,8,7,8,1),(9,8,7,8,1),(9,10,8,9,1),(8,8,7,8,1),(8,8,7,8,1),(8,12,8,12,1)])
    assert smc_snapshot(data, cfg())["event"] == "BOS"


def test_bearish_to_bullish_reversal_is_choch():
    data = frame([(9,7,6,8,1),(9,12,9,10,1),(9,10,6,8,1),(9,11,8,9,1),(8,9,5,7,1),(8,8,7,8,1),(8,13,7,12,1)])
    snapshot = smc_snapshot(data, cfg())
    assert snapshot["event"] == "CHOCH" and snapshot["event_direction"] == "bullish"


def test_bullish_to_bearish_reversal_is_choch():
    data = frame([(9,8,7,8,1),(9,10,7,9,1),(9,9,6,8,1),(9,12,8,11,1),(10,11,8,10,1),(9,10,9,9,1),(9,6,5,6,1)])
    snapshot = smc_snapshot(data, cfg())
    assert snapshot["event"] == "CHOCH" and snapshot["event_direction"] == "bearish"


def test_stale_zones_are_excluded():
    settings = cfg(); settings.smc_zone_max_age = 0
    data = frame([(10,11,9,10,1),(10,10,8,8,1),(8,13,8,13,1),(13,14,12,13,1)])
    assert not fair_value_gaps(data, settings)

