import json

import pandas as pd

from app.health import Heartbeat


def test_heartbeat_initializes_and_records_market_data(tmp_path):
    path = tmp_path / "heartbeat.json"
    heartbeat = Heartbeat(str(path))
    heartbeat.initialize("AGGRESSIVE", ("BTC/USDT",), ("4h", "1h", "15m"))
    frame = pd.DataFrame({"close": [100]}, index=pd.to_datetime(["2026-01-01"], utc=True))
    heartbeat.mark_data("BTC/USDT", {"15m": frame}, {"timestamp": 1760000000000})
    heartbeat.mark_cycle()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["profile"] == "AGGRESSIVE"
    assert payload["last_cycle_at"]
    assert "BTC/USDT|15m" in payload["last_data_at"]
    assert "BTC/USDT" in payload["last_ticker_at"]
