"""Backtest entry point. Historical CSVs must contain timestamp,open,high,low,close,volume."""
import argparse
import pandas as pd
from app.config import Settings
from app.backtest.runner import run


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--symbol", default="BTC/USDT"); parser.add_argument("--data-dir", required=True); args = parser.parse_args()
    frames = {tf: pd.read_csv(f"{args.data_dir}/{tf}.csv", parse_dates=["timestamp"], index_col="timestamp") for tf in ("4h","1h","15m")}
    settings = Settings.from_env(); print({"symbol": args.symbol, **run(frames, args.symbol, settings), "fee_bps": settings.backtest_fee_bps, "slippage_bps": settings.backtest_slippage_bps, "mode": settings.backtest_execution_model})


if __name__ == "__main__": main()

