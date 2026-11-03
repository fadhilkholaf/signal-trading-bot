import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (exchange TEXT, symbol TEXT, timeframe TEXT, open_time INTEGER, open REAL, high REAL, low REAL, close REAL, volume REAL, is_closed INTEGER, PRIMARY KEY(exchange,symbol,timeframe,open_time));
CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY, symbol TEXT, signal TEXT, price REAL, entry_low REAL, entry_high REAL, stop_loss REAL, take_profit REAL, risk_reward REAL, aligned_timeframes TEXT, indicators TEXT, explanation TEXT, rejection_reasons TEXT, source_candle_ms INTEGER, timestamp_utc TEXT, fingerprint TEXT UNIQUE, profile TEXT DEFAULT 'CONSERVATIVE_MODERATE', condition_score INTEGER DEFAULT 0, condition_results TEXT DEFAULT '{}', spread_percent REAL, hard_gate_failures TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE, symbol TEXT, signal TEXT, sent_at TEXT, status TEXT, message_id TEXT, error TEXT, retry_count INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS backtest_runs (id INTEGER PRIMARY KEY, started_at TEXT, config TEXT, result TEXT);
CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(symbol,timeframe,open_time);
CREATE INDEX IF NOT EXISTS idx_alerts_symbol_signal ON alerts(symbol,signal,sent_at);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate_signals()
        self.conn.commit()

    def _migrate_signals(self):
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(signals)")}
        additions = {"profile": "TEXT DEFAULT 'CONSERVATIVE_MODERATE'", "condition_score": "INTEGER DEFAULT 0", "condition_results": "TEXT DEFAULT '{}'", "spread_percent": "REAL", "hard_gate_failures": "TEXT DEFAULT '[]'"}
        for name, definition in additions.items():
            if name not in existing: self.conn.execute(f"ALTER TABLE signals ADD COLUMN {name} {definition}")

    def save_candles(self, exchange, symbol, timeframe, rows):
        self.conn.executemany("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?)", [(exchange,symbol,timeframe,*r,1) for r in rows]); self.conn.commit()

    def save_signal(self, s):
        import json
        self.conn.execute("INSERT OR IGNORE INTO signals(symbol,signal,price,entry_low,entry_high,stop_loss,take_profit,risk_reward,aligned_timeframes,indicators,explanation,rejection_reasons,source_candle_ms,timestamp_utc,fingerprint,profile,condition_score,condition_results,spread_percent,hard_gate_failures) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (s.symbol,s.signal.value,s.price,s.entry_low,s.entry_high,s.stop_loss,s.take_profit,s.risk_reward,json.dumps(s.aligned_timeframes),json.dumps(s.indicators),s.explanation,json.dumps(s.rejection_reasons),s.source_candle_ms,s.timestamp_utc.isoformat(),s.fingerprint,s.profile,s.condition_score,json.dumps(s.condition_results),s.spread_percent,json.dumps(s.hard_gate_failures))); self.conn.commit()

    def can_alert(self, s, cooldown_minutes: int, send_no_trade: bool, max_alerts_per_pair_per_day: int = 3, day_timezone: str = "UTC") -> bool:
        if s.signal.value == "NO TRADE" and not send_no_trade: return False
        existing = self.conn.execute("SELECT status FROM alerts WHERE fingerprint=?", (s.fingerprint,)).fetchone()
        # A failed delivery must remain retryable after a transient/network or code error.
        if existing and existing[0] == "sent": return False
        from datetime import datetime, timezone, timedelta
        from zoneinfo import ZoneInfo
        now = datetime.now(timezone.utc)
        local_day = now.astimezone(ZoneInfo(day_timezone)).date()
        sent_today = 0
        for item in self.conn.execute("SELECT sent_at FROM alerts WHERE symbol=? AND status='sent'", (s.symbol,)):
            if datetime.fromisoformat(item[0]).astimezone(ZoneInfo(day_timezone)).date() == local_day: sent_today += 1
        if sent_today >= max_alerts_per_pair_per_day: return False
        # Cooldown is per pair, regardless of whether the previous alert was LONG, SHORT, or NO TRADE.
        row = self.conn.execute("SELECT sent_at FROM alerts WHERE symbol=? AND status='sent' ORDER BY id DESC LIMIT 1", (s.symbol,)).fetchone()
        if not row: return True
        return datetime.now(timezone.utc) - datetime.fromisoformat(row[0]) >= timedelta(minutes=cooldown_minutes)

    def record_alert(self, s, status, message_id=None, error=None):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("INSERT INTO alerts(fingerprint,symbol,signal,sent_at,status,message_id,error) VALUES (?,?,?,?,?,?,?) ON CONFLICT(fingerprint) DO UPDATE SET sent_at=excluded.sent_at,status=excluded.status,message_id=excluded.message_id,error=excluded.error", (s.fingerprint,s.symbol,s.signal.value,now,status,message_id,error)); self.conn.commit()

