def compute_score(current_count: int, baseline_avg: float, smoothing: float) -> float:
    """Ratio-to-baseline: how many times above its own recent normal a term is right now."""
    return current_count / (baseline_avg + smoothing)


def update_baseline(old_avg: float | None, current_count: int, alpha: float) -> float:
    """Exponential moving average - a trailing baseline without storing full history per term."""
    if old_avg is None:
        return float(current_count)
    return alpha * current_count + (1 - alpha) * old_avg
