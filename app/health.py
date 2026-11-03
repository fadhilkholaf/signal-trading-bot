import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Heartbeat:
    def __init__(self, path: str):
        self.path = Path(path)

    def _write(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="heartbeat-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def initialize(self, profile: str, symbols: tuple[str, ...], timeframes: tuple[str, ...]) -> None:
        self._write({"service_started_at": _now(), "last_cycle_at": None, "profile": profile, "pid": os.getpid(), "symbols": list(symbols), "timeframes": list(timeframes), "last_data_at": {}, "last_ticker_at": {}})

    def mark_data(self, symbol: str, frames: dict, ticker: dict | None) -> None:
        payload = self.read() or {}
        now = _now()
        for timeframe, frame in frames.items():
            if len(frame): payload.setdefault("last_data_at", {})[f"{symbol}|{timeframe}"] = now
        if ticker and ticker.get("timestamp"):
            payload.setdefault("last_ticker_at", {})[symbol] = now
        payload["last_data_update_at"] = now
        self._write(payload)

    def mark_cycle(self) -> None:
        payload = self.read() or {}
        payload["last_cycle_at"] = _now()
        self._write(payload)

    def read(self) -> dict | None:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

