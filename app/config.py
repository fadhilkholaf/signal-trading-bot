from dataclasses import dataclass
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import dotenv_values


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in os.getenv(name, default).split(",") if x.strip())


PROFILE_DEFAULTS = {
    "CONSERVATIVE_MODERATE": {},
    "AGGRESSIVE": {
        "symbols": ("BTC/USDT", "ETH/USDT"),
        "dry_run": True,
        "use_5m_entry_refinement": True,
        "min_conditions_required": 5,
        "min_risk_reward": 1.5,
        "max_alerts_per_pair_per_day": 8,
        "cooldown_minutes": 30,
        "min_volume_ratio": .50,
        "max_spread_percent": .25,
        "max_atr_percent": .12,
        "max_true_range_zscore": 5.0,
    },
}


@dataclass(frozen=True)
class Settings:
    strategy_profile: str = "AGGRESSIVE"
    dry_run: bool = True
    exchange_id: str = "binance"
    market_type: str = "spot"
    symbols: tuple[str, ...] = ("BTC/USDT", "ETH/USDT")
    timeframes: tuple[str, ...] = ("4h", "1h", "15m")
    database_url: str = "sqlite:///data/trading_bot.sqlite3"
    log_level: str = "INFO"
    log_json: bool = True
    telegram_enabled: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_send_no_trade: bool = False
    telegram_send_state_transitions: bool = True
    poll_interval_seconds: int = 15
    cooldown_minutes: int = 90
    max_alerts_per_pair_per_day: int = 3
    min_conditions_required: int = 7
    max_spread_percent: float = .10
    alert_day_timezone: str = "UTC"
    max_ticker_age_seconds: int = 120
    use_5m_entry_refinement: bool = False
    entry_refinement_timeframe: str = "5m"
    heartbeat_path: str = "data/heartbeat.json"
    data_stale_after_seconds: int = 180
    service_stopped_after_seconds: int = 180
    watchdog_check_interval_seconds: int = 60
    watchdog_warning_cooldown_minutes: int = 30
    watchdog_send_recovery: bool = True
    watchdog_state_path: str = "data/watchdog_state.json"
    ohlcv_limit: int = 300
    request_timeout_ms: int = 10000
    max_retries: int = 5
    retry_backoff_seconds: float = 2.0
    ema_fast_4h: int = 50
    ema_slow_4h: int = 200
    ema_fast_1h: int = 20
    ema_slow_1h: int = 50
    rsi_period: int = 14
    rsi_long_min: float = 50
    rsi_long_max: float = 70
    rsi_short_min: float = 30
    rsi_short_max: float = 50
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    volume_sma_period: int = 20
    min_volume_ratio: float = .8
    pivot_left_bars: int = 2
    pivot_right_bars: int = 2
    pullback_atr_distance: float = .5
    min_body_ratio: float = .5
    entry_zone_atr_width: float = .25
    stop_atr_multiplier: float = 1.5
    swing_stop_atr_buffer: float = .2
    min_risk_reward: float = 2.0
    max_risk_atr_multiplier: float = 5.0
    max_atr_percent: float = .08
    max_true_range_zscore: float = 3.0
    volatility_lookback: int = 100
    sr_swing_left_bars: int = 2
    sr_swing_right_bars: int = 2
    sr_merge_atr_distance: float = .50
    sr_min_reactions: int = 2
    sr_max_levels: int = 20
    sr_near_atr_distance: float = .50
    sr_stop_distance_atr: float = .25
    smc_swing_left_bars: int = 2
    smc_swing_right_bars: int = 2
    smc_displacement_atr: float = 1.0
    smc_order_block_lookback: int = 30
    smc_order_block_min_body_ratio: float = .50
    smc_fvg_lookback: int = 30
    smc_fvg_min_atr: float = .10
    smc_max_zones: int = 10
    smc_zone_tolerance_atr: float = .50
    smc_zone_max_age: int = 30
    backtest_fee_bps: float = 10
    backtest_slippage_bps: float = 5
    backtest_execution_model: str = "next_open"

    @classmethod
    def from_env(cls, env_file: str | Path = ".env") -> "Settings":
        file_values = {key: value for key, value in dotenv_values(env_file).items() if value is not None}
        get_value = lambda name, default=None: os.getenv(name, file_values.get(name, default))
        profile = get_value("STRATEGY_PROFILE", cls.strategy_profile)
        if profile not in PROFILE_DEFAULTS:
            raise ValueError(f"Unknown strategy profile: {profile}")
        defaults = {field: getattr(cls, field) for field in cls.__dataclass_fields__}
        defaults.update(PROFILE_DEFAULTS[profile])
        defaults["strategy_profile"] = profile
        values = {}
        for field in cls.__dataclass_fields__:
            env_name = field.upper()
            if field in {"symbols", "timeframes"}:
                values[field] = _csv(env_name, ",".join(defaults[field])) if get_value(env_name) is None else tuple(x.strip() for x in get_value(env_name).split(",") if x.strip())
            elif field in {"log_json", "telegram_enabled", "telegram_send_no_trade", "telegram_send_state_transitions", "dry_run", "use_5m_entry_refinement", "watchdog_send_recovery"}:
                raw = get_value(env_name)
                values[field] = defaults[field] if raw is None else raw.lower() in {"1", "true", "yes", "on"}
            elif field in {"strategy_profile", "exchange_id", "market_type", "database_url", "log_level", "telegram_bot_token", "telegram_chat_id", "backtest_execution_model", "alert_day_timezone"}:
                values[field] = get_value(env_name, defaults[field])
            else:
                default = defaults[field]
                raw = get_value(env_name)
                if raw is None:
                    values[field] = default
                else:
                    values[field] = type(default)(raw)
        if values["telegram_enabled"] and (not values["telegram_bot_token"] or not values["telegram_chat_id"]):
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required when Telegram is enabled")
        if not values["dry_run"]:
            raise ValueError("DRY_RUN must remain true; this bot is permanently alert-only")
        if not 1 <= values["min_conditions_required"] <= 10:
            raise ValueError("MIN_CONDITIONS_REQUIRED must be between 1 and 10")
        if values["max_alerts_per_pair_per_day"] < 1 or values["cooldown_minutes"] < 0 or values["max_spread_percent"] < 0:
            raise ValueError("alert, cooldown, and spread limits must be non-negative; daily alerts must be at least 1")
        try:
            ZoneInfo(values["alert_day_timezone"])
        except Exception as exc:
            raise ValueError(f"Invalid ALERT_DAY_TIMEZONE: {values['alert_day_timezone']}") from exc
        return cls(**values)

    @property
    def database_path(self) -> str:
        return self.database_url.removeprefix("sqlite:///")

    def strategy_version(self) -> str:
        return "1.3.0"

