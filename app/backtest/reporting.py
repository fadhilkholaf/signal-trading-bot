from statistics import mean, median


def summarize(trades):
    if not trades: return {"trade_count": 0, "wins": 0, "losses": 0, "net_return": 0.0, "max_drawdown": 0.0}
    equity, peak, drawdown = 1.0, 1.0, 0.0
    for trade in trades:
        equity *= 1 + trade.net_return; peak = max(peak, equity); drawdown = max(drawdown, (peak-equity)/peak)
    rs = [t.gross_r for t in trades]
    return {"trade_count": len(trades), "long_count": sum(t.direction == "LONG" for t in trades), "short_count": sum(t.direction == "SHORT" for t in trades), "wins": sum(t.gross_r > 0 for t in trades), "losses": sum(t.gross_r <= 0 for t in trades), "net_return": equity - 1, "max_drawdown": drawdown, "average_r": mean(rs), "median_r": median(rs), "fees": sum(t.fee for t in trades)}

