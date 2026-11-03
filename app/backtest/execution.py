from dataclasses import dataclass


@dataclass
class Trade:
    direction: str
    entry: float
    exit: float
    stop: float
    target: float
    gross_r: float
    net_return: float
    fee: float
    slippage: float


def execute_next_open(signal, next_bar, future_bars, fee_bps: float, slippage_bps: float) -> Trade | None:
    if signal.signal.value not in {"LONG", "SHORT"} or signal.stop_loss is None or signal.take_profit is None:
        return None
    direction = signal.signal.value
    slip = slippage_bps / 10000
    entry = float(next_bar.open) * (1 + slip if direction == "LONG" else 1 - slip)
    exit_price = None
    for _, bar in future_bars.iterrows():
        if direction == "LONG":
            if bar.low <= signal.stop_loss: exit_price = signal.stop_loss * (1 - slip); break
            if bar.high >= signal.take_profit: exit_price = signal.take_profit * (1 - slip); break
        else:
            if bar.high >= signal.stop_loss: exit_price = signal.stop_loss * (1 + slip); break
            if bar.low <= signal.take_profit: exit_price = signal.take_profit * (1 + slip); break
    if exit_price is None: return None
    risk = abs(entry - signal.stop_loss)
    gross_r = (exit_price - entry) / risk if direction == "LONG" else (entry - exit_price) / risk
    fee = (entry + exit_price) * fee_bps / 10000
    slippage = abs(entry - float(next_bar.open)) + abs(exit_price - (signal.take_profit if gross_r >= 0 else signal.stop_loss))
    return Trade(direction, entry, exit_price, signal.stop_loss, signal.take_profit, gross_r, gross_r * risk / entry - fee / entry, fee, slippage)

