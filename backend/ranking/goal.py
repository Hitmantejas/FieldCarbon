from math import ceil

MIN_GOAL_PCT, MAX_GOAL_PCT = 1, 90


def suggested_goal_pct(litres_at_stake_high: float, total_litres: float) -> int:
    """Top of the pain-point range as a share of all fuel, rounded up to the next 5% (never below 5%)."""
    share = litres_at_stake_high / total_litres * 100
    return max(5, ceil(share / 5) * 5)


def verdict(reach_low_pct: float, reach_high_pct: float, target_pct: float) -> str:
    if reach_high_pct < target_pct:
        return "falls_short"  # even the best estimate is not enough
    if reach_low_pct >= target_pct:
        return "reaches"      # even the lowest estimate gets there
    return "might_reach"
