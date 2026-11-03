from types import SimpleNamespace

import pandas as pd
import pytest

from app.config import Settings
from app.strategy.signal_engine import _countertrend_choch_allowed, make_signal, meets_condition_threshold


def test_aggressive_profile_defaults(tmp_path):
    env = tmp_path / "aggressive.env"
    env.write_text("STRATEGY_PROFILE=AGGRESSIVE\nTELEGRAM_ENABLED=false\n", encoding="utf-8")
    settings = Settings.from_env(env)
    assert settings.strategy_profile == "AGGRESSIVE"
    assert settings.min_conditions_required == 5
    assert settings.min_risk_reward == 1.5
    assert settings.max_alerts_per_pair_per_day == 8
    assert settings.cooldown_minutes == 30
    assert settings.use_5m_entry_refinement is True
    assert settings.dry_run is True


def test_dry_run_cannot_be_disabled(tmp_path):
    env = tmp_path / "unsafe.env"
    env.write_text("STRATEGY_PROFILE=AGGRESSIVE\nDRY_RUN=false\nTELEGRAM_ENABLED=false\n", encoding="utf-8")
    with pytest.raises(ValueError, match="DRY_RUN"):
        Settings.from_env(env)


def test_countertrend_requires_choch_back_to_four_hour_direction():
    settings = SimpleNamespace(strategy_profile="AGGRESSIVE")
    snapshot = {"event": "CHOCH", "event_direction": "bullish"}
    assert _countertrend_choch_allowed(settings, "bullish", "bearish", snapshot)
    assert not _countertrend_choch_allowed(settings, "bullish", "bearish", {"event": "BOS", "event_direction": "bullish"})
    assert not _countertrend_choch_allowed(settings, "bullish", "bullish", snapshot)


def test_aggressive_condition_threshold_is_five_of_ten():
    conditions = {f"condition_{index}": index < 5 for index in range(10)}
    assert meets_condition_threshold(conditions, 5)
    assert not meets_condition_threshold({**conditions, "condition_4": False}, 5)


def test_aggressive_5m_refinement_falls_back_cleanly(tmp_path):
    env = tmp_path / "aggressive.env"
    env.write_text("STRATEGY_PROFILE=AGGRESSIVE\nTELEGRAM_ENABLED=false\n", encoding="utf-8")
    settings = Settings.from_env(env)
    index = pd.date_range("2026-01-01", periods=300, freq="15min", tz="UTC")
    base = pd.DataFrame({"open": range(100, 400), "high": range(101, 401), "low": range(99, 399), "close": range(100, 400), "volume": [1000] * 300}, index=index)
    frames = {"4h": base.copy(), "1h": base.copy(), "15m": base.copy()}
    signal = make_signal("BTC/USDT", frames, settings, {"bid": 399.9, "ask": 400.0, "timestamp": index[-1].timestamp() * 1000})
    assert signal.indicators["entry_refinement"]["status"] == "fallback_15m_unavailable"
