import asyncio
import logging
import ccxt.async_support as ccxt
import pandas as pd

logger = logging.getLogger(__name__)


class PublicExchange:
    def __init__(self, settings):
        self.exchange_cls = getattr(ccxt, settings.exchange_id)
        self.settings = settings
        self.exchange = self._build()

    def _build(self):
        return self.exchange_cls({"enableRateLimit": True, "options": {"defaultType": self.settings.market_type}, "timeout": self.settings.request_timeout_ms})

    async def reconnect(self):
        old = self.exchange
        try:
            await old.close()
        finally:
            self.exchange = self._build()

    @staticmethod
    def error_category(exc: Exception) -> str:
        name = type(exc).__name__.lower()
        if "ratelimit" in name: return "rate_limit"
        if "timeout" in name: return "timeout"
        if "dns" in name or "resolve" in name: return "dns"
        if "network" in name or "available" in name or "connection" in name: return "network"
        return "exchange"

    async def fetch(self, symbol, timeframe):
        last = None
        for attempt in range(self.settings.max_retries):
            try:
                rows = await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=self.settings.ohlcv_limit)
                frame = pd.DataFrame(rows, columns=["timestamp","open","high","low","close","volume"])
                frame["timestamp"] = pd.to_datetime(frame.timestamp, unit="ms", utc=True)
                frame = frame.drop_duplicates("timestamp").sort_values("timestamp").set_index("timestamp")
                now = pd.Timestamp.now(tz="UTC")
                frame = frame[frame.index + pd.Timedelta(timeframe) <= now] if timeframe in {"15m","1h","4h"} else frame.iloc[:-1]
                return frame
            except Exception as exc:
                last = exc
                logger.warning("ohlcv fetch failed", extra={"symbol": symbol, "timeframe": timeframe, "attempt": attempt + 1, "category": self.error_category(exc), "error_type": type(exc).__name__, "error": str(exc) or repr(exc)})
                if attempt >= 1:
                    try: await self.reconnect()
                    except Exception: logger.exception("exchange reconnect failed")
                await asyncio.sleep(self.settings.retry_backoff_seconds * (attempt + 1))
        raise RuntimeError(f"failed to fetch {symbol} {timeframe}: {type(last).__name__}: {last}") from last

    async def fetch_ticker(self, symbol):
        last = None
        for attempt in range(self.settings.max_retries):
            try:
                ticker = await self.exchange.fetch_ticker(symbol)
                bid, ask = ticker.get("bid"), ticker.get("ask")
                if bid is None or ask is None:
                    book = await self.exchange.fetch_order_book(symbol, limit=5)
                    bid = book.get("bids", [[None]])[0][0] if book.get("bids") else None
                    ask = book.get("asks", [[None]])[0][0] if book.get("asks") else None
                return {"bid": bid, "ask": ask, "last": ticker.get("last"), "timestamp": ticker.get("timestamp")}
            except Exception as exc:
                last = exc
                logger.warning("ticker fetch failed", extra={"symbol": symbol, "attempt": attempt + 1, "category": self.error_category(exc), "error_type": type(exc).__name__, "error": str(exc) or repr(exc)})
                if attempt >= 1:
                    try: await self.reconnect()
                    except Exception: logger.exception("exchange reconnect failed")
                await asyncio.sleep(self.settings.retry_backoff_seconds * (attempt + 1))
        raise RuntimeError(f"failed to fetch ticker {symbol}: {type(last).__name__}: {last}") from last

    async def close(self): await self.exchange.close()

