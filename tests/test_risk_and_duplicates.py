from types import SimpleNamespace
from app.strategy.risk import calculate_levels, stop_too_close_to_levels
from app.models import Signal, SignalType
from app.storage.database import Database
from datetime import datetime, timezone


def settings(): return SimpleNamespace(stop_atr_multiplier=1.5, swing_stop_atr_buffer=.2, min_risk_reward=2, max_risk_atr_multiplier=5)


def test_long_risk_reward():
    stop, target, risk = calculate_levels("LONG", 100, 2, 96, settings())
    assert abs(stop - 95.6) < 1e-9 and abs(target - 108.8) < 1e-9 and (target-100)/risk >= 2


def test_stop_distance_rejects_insufficient_invalidation_buffer():
    level = SimpleNamespace(price=96)
    assert stop_too_close_to_levels("LONG", 95.8, [level], 2, .25)
    assert not stop_too_close_to_levels("LONG", 95.4, [level], 2, .25)
    assert stop_too_close_to_levels("SHORT", 104.2, [SimpleNamespace(price=104)], 2, .25)


def test_duplicate_fingerprint_and_cooldown(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    s = Signal("BTC/USDT", SignalType.LONG, 100, 99, 101, 96, 108, 2, ("4H","1H","15M"), {}, "ok", 1, datetime.now(timezone.utc), fingerprint="same")
    db.save_signal(s); assert db.can_alert(s, 60, False)
    db.record_alert(s, "sent"); assert not db.can_alert(s, 60, False)


def test_failed_alert_can_retry(tmp_path):
    db = Database(str(tmp_path / "retry.db"))
    s = Signal("ETH/USDT", SignalType.NO_TRADE, 100, 99, 101, None, None, None, (), {}, "unclear", 1, datetime.now(timezone.utc), fingerprint="retry")
    db.save_signal(s); db.record_alert(s, "failed", error="temporary")
    assert db.can_alert(s, 60, True)
    db.record_alert(s, "sent", message_id="123")
    assert not db.can_alert(s, 60, True)

