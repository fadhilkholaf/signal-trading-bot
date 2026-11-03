# Signal-only cryptocurrency technical-analysis bot

This bot evaluates BTC/USDT and ETH/USDT using public Binance OHLCV data only. It produces deterministic `LONG`, `SHORT`, or `NO TRADE` decisions, stores candles/signals/alerts in SQLite, and sends actionable alerts to Telegram. It never authenticates to an exchange and never places, changes, or cancels orders. It makes no profitability claim.

## GitHub setup

Do not commit `.env` or the SQLite database. Start from the template:

```bash
git clone <your-repository-url>
cd trading-bot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

The repository includes GitHub Actions CI for Python 3.12 compilation and tests. Configure deployment secrets directly on the VPS rather than storing them in GitHub.

Telegram alerts use formatted HTML sections for market levels, timeframe alignment, indicators, explanation, and UTC signal time.

## Strategy profile

The default profile is `AGGRESSIVE`. It requires a 5/10 condition score plus mandatory candle, SMC, liquidity, spread, volatility, conflict, and risk gates. It monitors BTC/USDT and ETH/USDT by default, allows at most eight sent alerts per pair per UTC day, and applies a 30-minute per-pair cooldown. `DRY_RUN=true` is mandatory.

Profile settings can be overridden in `.env`:

```dotenv
STRATEGY_PROFILE=CONSERVATIVE_MODERATE
MIN_CONDITIONS_REQUIRED=7
MAX_SPREAD_PERCENT=0.10
MAX_ALERTS_PER_PAIR_PER_DAY=3
COOLDOWN_MINUTES=90
```

For the testing profile:

```dotenv
STRATEGY_PROFILE=AGGRESSIVE
DRY_RUN=true
SYMBOLS=BTC/USDT,ETH/USDT
MIN_CONDITIONS_REQUIRED=5
MIN_RISK_REWARD=1.5
MAX_ALERTS_PER_PAIR_PER_DAY=8
COOLDOWN_MINUTES=30
MIN_VOLUME_RATIO=0.50
MAX_SPREAD_PERCENT=0.25
MAX_ATR_PERCENT=0.12
MAX_TRUE_RANGE_ZSCORE=5.0
USE_5M_ENTRY_REFINEMENT=true
ENTRY_REFINEMENT_TIMEFRAME=5m
```

AGGRESSIVE still follows the 4H direction. It may accept a 1H countertrend setup only when a confirmed 1H CHOCH points back toward the 4H direction. 5M is an optional entry refinement and falls back to the 15M setup when unavailable.

## Support/resistance and SMC

The strategy now uses objective confluence detectors rather than discretionary annotations:

- Confirmed swing highs/lows are clustered into horizontal support/resistance levels using ATR distance; levels require the configured minimum number of reactions.
- BOS requires a closed candle beyond a confirmed swing. CHOCH requires that break to reverse the prior confirmed structure.
- Liquidity sweeps require a wick through a confirmed swing followed by a close back inside.
- Order blocks use configurable opposite-color candle body and displacement rules.
- Fair value gaps use the configurable three-candle gap definition.
- LONG/SHORT still require the existing 4H/1H/15M indicator alignment, plus a nearby directional support/resistance, order-block, or FVG zone and a directional SMC event.
- Conflicts, insufficient reactions, invalidation proximity, or missing confluence produce `NO TRADE`.

All S/R and SMC thresholds are configurable through the `SR_*` and `SMC_*` variables in `.env.example`. Evaluation explanations and persisted indicator snapshots record the satisfied zones and events.

## Futures market data

Public futures candles are supported without exchange API keys. For Binance USDT-margined perpetuals, use:

```dotenv
MARKET_TYPE=swap
SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT
```

This changes only the public market-data source. The application remains signal-only and never submits futures orders. Use `spot` with `BTC/USDT,ETH/USDT` for spot data.

## Install

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, or set `TELEGRAM_ENABLED=false` for local testing. All strategy thresholds are configurable in `.env`.

## Run and test

```bash
python -m app.main
pytest -q
```

For a one-shot local smoke test that never sends Telegram:

```bash
python -m app.main --once --no-telegram
```

Only closed candles are used. The first run needs enough data to warm up the indicators. Logs are structured JSON by default.

## Backtest

Put `4h.csv`, `1h.csv`, and `15m.csv` in a directory. Each must contain `timestamp,open,high,low,close,volume`.

```bash
python scripts/backtest.py --symbol BTC/USDT --data-dir ./historical
```

The backtest uses only data available at each closed 15M candle and reports signal counts plus configured fee/slippage assumptions. It is a historical simulation, not a performance guarantee.

## VPS/systemd

Create a dedicated non-root `tradingbot` user, install the project under `/opt/trading-bot`, create `.venv`, install dependencies, and put secrets in `/opt/trading-bot/.env` with mode `0600`.

```bash
sudo cp systemd/trading-bot.service /etc/systemd/system/
sudo cp systemd/trading-bot-watchdog.service /etc/systemd/system/
sudo cp systemd/trading-bot-watchdog.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trading-bot
sudo systemctl enable --now trading-bot-watchdog.timer
sudo journalctl -u trading-bot -f
```

Check both services and the timer:

```bash
sudo systemctl status trading-bot
sudo systemctl status trading-bot-watchdog.timer
sudo journalctl -u trading-bot-watchdog.service -f
```

Back up `data/trading_bot.sqlite3` before upgrades. The main service and watchdog are permanently alert-only. The watchdog checks `data/heartbeat.json`, warns about stale data or a stopped service, suppresses repeated warnings, and can send a recovery message.

