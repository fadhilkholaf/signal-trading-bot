import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.config import Settings
from app.health import Heartbeat
from app.logging_config import configure_logging
from app.notifications.telegram import TelegramNotifier

logger = logging.getLogger("trading_bot.watchdog")


def _parse(value):
    return datetime.fromisoformat(value) if value else None


def _load_state(path: str) -> dict:
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError): return {"incidents": {}}


def _save_state(path: str, state: dict) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _incident_message(kind: str, details: str, settings) -> str:
    now = datetime.now(timezone.utc).isoformat()
    return f"⚠️ <b>{kind}</b>\n📋 Profile: <code>{settings.strategy_profile}</code>\n{details}\n🕒 UTC: <code>{now}</code>"


def _check_incident(kind, active, details, state, settings, notifier):
    incidents = state.setdefault("incidents", {})
    incident = incidents.setdefault(kind, {"active": False, "last_notified_at": None})
    now = datetime.now(timezone.utc)
    last = _parse(incident.get("last_notified_at"))
    should_notify = active and (not incident["active"] or not last or now - last >= timedelta(minutes=settings.watchdog_warning_cooldown_minutes))
    if should_notify and settings.telegram_enabled:
        notifier.send_text(_incident_message(kind, details, settings))
        incident["last_notified_at"] = now.isoformat()
        logger.warning("watchdog warning sent", extra={"incident": kind, "details": details})
    elif should_notify:
        logger.warning("watchdog warning suppressed because Telegram is disabled", extra={"incident": kind, "details": details})
    if not active and incident["active"] and settings.watchdog_send_recovery and settings.telegram_enabled:
        notifier.send_text(_incident_message("SERVICE RECOVERED", f"Recovered incident: {kind}", settings))
        logger.info("watchdog recovery sent", extra={"incident": kind})
    incident["active"] = active


def main():
    settings = Settings.from_env()
    configure_logging(settings.log_level, settings.log_json)
    heartbeat = Heartbeat(settings.heartbeat_path).read()
    state = _load_state(settings.watchdog_state_path)
    notifier = TelegramNotifier(settings)
    now = datetime.now(timezone.utc)
    if not heartbeat:
        _check_incident("SERVICE STOPPED", True, f"Heartbeat missing: <code>{settings.heartbeat_path}</code>", state, settings, notifier)
        _check_incident("DATA STALE", False, "No heartbeat available", state, settings, notifier)
        _save_state(settings.watchdog_state_path, state)
        return
    cycle = _parse(heartbeat.get("last_cycle_at"))
    stopped = not cycle or now - cycle > timedelta(seconds=settings.service_stopped_after_seconds)
    _check_incident("SERVICE STOPPED", stopped, f"Last cycle: <code>{cycle.isoformat() if cycle else 'never'}</code>", state, settings, notifier)
    stale_items = []
    for key, value in heartbeat.get("last_data_at", {}).items():
        timestamp = _parse(value)
        if not timestamp or now - timestamp > timedelta(seconds=settings.data_stale_after_seconds): stale_items.append(key)
    expected = [f"{symbol}|{timeframe}" for symbol in heartbeat.get("symbols", []) for timeframe in heartbeat.get("timeframes", [])]
    stale_items.extend(key for key in expected if key not in heartbeat.get("last_data_at", {}))
    stale = bool(stale_items)
    _check_incident("DATA STALE", stale, f"Affected markets: <code>{', '.join(sorted(set(stale_items))) or 'none'}</code>", state, settings, notifier)
    _save_state(settings.watchdog_state_path, state)


if __name__ == "__main__": main()
