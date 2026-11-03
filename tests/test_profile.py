from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.models import Signal, SignalType
from app.notifications.telegram import format_signal
from app.storage.database import Database
from app.strategy.signal_engine import _spread


def test_conservative_moderate_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")
    env_file = tmp_path / "empty.env"
    env_file.write_text("TELEGRAM_ENABLED=false\n", encoding="utf-8")
    settings = Settings.from_env(env_file)
    assert settings.strategy_profile == "AGGRESSIVE"
    assert settings.symbols == ("BTC/USDT", "ETH/USDT")
    assert settings.cooldown_minutes == 30
    assert settings.max_alerts_per_pair_per_day == 8
    assert settings.min_conditions_required == 5
    assert settings.max_spread_percent == .25


def test_unknown_profile_fails(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")
    monkeypatch.setenv("STRATEGY_PROFILE", "UNKNOWN")
    with pytest.raises(ValueError, match="Unknown strategy profile"):
        Settings.from_env()


def test_spread_validation():
    settings = SimpleNamespace(max_spread_percent=.10, max_ticker_age_seconds=120)
    assert _spread({"bid": 100, "ask": 100.05, "timestamp": datetime.now(timezone.utc).timestamp() * 1000}, settings)[0] < .10
    assert _spread({"bid": 100, "ask": 100.50, "timestamp": datetime.now(timezone.utc).timestamp() * 1000}, settings)[1] == "spread excessive"
    assert _spread({"bid": 100, "ask": None}, settings)[1] == "spread invalid or unavailable"
    assert _spread({"bid": 101, "ask": 100}, settings)[1] == "spread invalid or unavailable"


def _signal(fingerprint):
    return Signal("BTC/USDT", SignalType.LONG, 100, 99, 101, 95, 110, 2, ("4H", "1H", "15M"), {}, "test", 1, datetime.now(timezone.utc), fingerprint=fingerprint, condition_score=8, spread_percent=.02)


def test_daily_alert_cap_and_failed_retry(tmp_path):
    db = Database(str(tmp_path / "alerts.db"))
    for index in range(3):
        signal = _signal(f"sent-{index}")
        db.save_signal(signal)
        assert db.can_alert(signal, 0, False, 3, "UTC")
        db.record_alert(signal, "sent", str(index))
    fourth = _signal("fourth")
    db.save_signal(fourth)
    assert not db.can_alert(fourth, 0, False, 3, "UTC")
    failed = _signal("failed")
    db.save_signal(failed)
    db.record_alert(failed, "failed", error="temporary")
    assert not db.can_alert(failed, 0, False, 3, "UTC")


def test_telegram_contains_profile_and_score():
    message = format_signal(_signal("format"))
    assert "CONSERVATIVE_MODERATE" in message
    assert "8/10" in message
    assert "0.020%" in message

