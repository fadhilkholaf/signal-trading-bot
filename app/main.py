import asyncio
import argparse
import logging
from .config import Settings
from .logging_config import configure_logging
from .data.exchange import PublicExchange
from .storage.database import Database
from .strategy.signal_engine import make_signal
from .notifications.telegram import TelegramNotifier
from .health import Heartbeat

logger = logging.getLogger(__name__)


async def run_once(settings, exchange, db, notifier, heartbeat=None):
    for symbol in settings.symbols:
        try:
            market = None
            try:
                market = await exchange.fetch_ticker(symbol)
            except Exception:
                logger.exception("ticker fetch failed: %s", symbol)
            frames = {tf: await exchange.fetch(symbol, tf) for tf in settings.timeframes}
            if settings.use_5m_entry_refinement and settings.entry_refinement_timeframe not in frames:
                try:
                    frames[settings.entry_refinement_timeframe] = await exchange.fetch(symbol, settings.entry_refinement_timeframe)
                except Exception:
                    logger.warning("optional entry refinement unavailable", extra={"symbol": symbol, "timeframe": settings.entry_refinement_timeframe})
            if settings.use_5m_entry_refinement:
                market = market or {}
                market["candles_complete"] = True
            if any(len(frame) < 220 for frame in frames.values()): raise ValueError("insufficient closed candles")
            if heartbeat: heartbeat.mark_data(symbol, frames, market)
            for tf, frame in frames.items(): db.save_candles(settings.exchange_id, symbol, tf, [(int(i.timestamp()*1000), r.open,r.high,r.low,r.close,r.volume) for i,r in frame.iterrows()])
            signal = make_signal(symbol, frames, settings, market); db.save_signal(signal)
            logger.info("signal evaluated: %s %s (%s)", symbol, signal.signal.value, signal.explanation)
            if settings.telegram_enabled and db.can_alert(signal, settings.cooldown_minutes, settings.telegram_send_no_trade, settings.max_alerts_per_pair_per_day, settings.alert_day_timezone):
                try:
                    message_id = notifier.send(signal); db.record_alert(signal, "sent", message_id); logger.info("alert sent: %s %s", symbol, signal.signal.value)
                except Exception as exc:
                    db.record_alert(signal, "failed", error=str(exc)); logger.exception("telegram alert failed")
        except Exception:
            logger.exception("symbol evaluation failed: %s", symbol)
    if heartbeat: heartbeat.mark_cycle()


async def async_main(once: bool = False, disable_telegram: bool = False):
    settings = Settings.from_env(); configure_logging(settings.log_level, settings.log_json)
    db = Database(settings.database_path); exchange = PublicExchange(settings); notifier = TelegramNotifier(settings); heartbeat = Heartbeat(settings.heartbeat_path)
    # The required heartbeat set is the base strategy set; optional 5M refinement never makes health fail.
    heartbeat.initialize(settings.strategy_profile, settings.symbols, settings.timeframes)
    try:
        while True:
            await run_once(settings, exchange, db, notifier, heartbeat)
            if once: break
            await asyncio.sleep(settings.poll_interval_seconds)
    finally: await exchange.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Signal-only cryptocurrency analysis bot")
    parser.add_argument("--once", action="store_true", help="evaluate once and exit")
    parser.add_argument("--no-telegram", action="store_true", help="disable Telegram for this run")
    args = parser.parse_args()
    if args.no_telegram:
        import os
        os.environ["TELEGRAM_ENABLED"] = "false"
    asyncio.run(async_main(once=args.once, disable_telegram=args.no_telegram))

