def calculate_levels(direction: str, entry: float, atr_value: float, swing: float | None, settings) -> tuple[float, float, float]:
    if direction == "LONG":
        atr_stop = entry - settings.stop_atr_multiplier * atr_value
        swing_stop = swing - settings.swing_stop_atr_buffer * atr_value if swing else atr_stop
        stop = min(atr_stop, swing_stop)
        risk = entry - stop
        target = entry + risk * settings.min_risk_reward
    else:
        atr_stop = entry + settings.stop_atr_multiplier * atr_value
        swing_stop = swing + settings.swing_stop_atr_buffer * atr_value if swing else atr_stop
        stop = max(atr_stop, swing_stop)
        risk = stop - entry
        target = entry - risk * settings.min_risk_reward
    if risk <= 0 or risk > settings.max_risk_atr_multiplier * atr_value: raise ValueError("invalid risk distance")
    return stop, target, risk


def stop_too_close_to_levels(direction: str, stop: float, levels, atr_value: float, buffer_atr: float) -> bool:
    """Return true when a protective stop has not cleared a relevant level by the buffer."""
    buffer_value = atr_value * buffer_atr
    if direction == "LONG":
        return any(stop > level.price - buffer_value for level in levels)
    return any(stop < level.price + buffer_value for level in levels)

