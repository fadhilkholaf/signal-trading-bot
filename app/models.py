from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class SignalType(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO TRADE"


@dataclass(frozen=True)
class Signal:
    symbol: str
    signal: SignalType
    price: float | None
    entry_low: float | None
    entry_high: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None
    aligned_timeframes: tuple[str, ...]
    indicators: dict[str, Any]
    explanation: str
    source_candle_ms: int
    timestamp_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rejection_reasons: tuple[str, ...] = ()
    fingerprint: str = ""
    profile: str = "CONSERVATIVE_MODERATE"
    condition_score: int = 0
    condition_results: dict[str, bool] = field(default_factory=dict)
    spread_percent: float | None = None
    hard_gate_failures: tuple[str, ...] = ()

