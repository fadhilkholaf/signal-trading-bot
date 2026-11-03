from .execution import execute_next_open
from .reporting import summarize
from app.strategy.signal_engine import make_signal


def run(frames: dict, symbol: str, settings):
    base = frames["15m"]
    trades = []
    for i in range(220, len(base) - 1):
        cutoff = base.index[i]
        available = {tf: frame[frame.index <= cutoff] for tf, frame in frames.items()}
        signal = make_signal(symbol, available, settings)
        trade = execute_next_open(signal, base.iloc[i + 1], base.iloc[i + 2:], settings.backtest_fee_bps, settings.backtest_slippage_bps)
        if trade: trades.append(trade)
    return summarize(trades)

