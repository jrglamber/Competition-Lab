from math import ceil
from datetime import timezone

def nominal_ev(prize, price, sold):
    if not all(x is not None for x in (prize, price, sold)) or price <= 0 or sold <= 0:
        return None
    return float(prize)/(float(price)*int(sold))-1.0

def threshold_field(prize, price, threshold=.40):
    if not prize or not price:
        return None
    return int(float(prize)/(float(price)*(1+threshold)))

def _aware_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def hours_to_close(closes_at, now):
    closes_at=_aware_utc(closes_at); now=_aware_utc(now)
    if closes_at is None or now is None:
        return None
    return max(0.0,(closes_at-now).total_seconds()/3600)

def project_final(sold, closes_at, now, velocity_per_hour=0.0, observations=1):
    """Conservative closing-field projection.

    Until we have enough forward observations, do not pretend zero observed velocity
    means zero future sales. Bootstrap with a time-to-close buffer, then switch to
    measured velocity once >=3 observations exist.
    """
    if sold is None or closes_at is None:
        return None
    hours=hours_to_close(closes_at,now)
    if observations < 3:
        # Deliberately conservative bootstrap. It is not an entry model; it only
        # prevents first-snapshot EV from being treated as actionable.
        if hours <= 1: pct=.10
        elif hours <= 6: pct=.20
        elif hours <= 24: pct=.35
        elif hours <= 72: pct=.60
        else: pct=1.00
        extra=sold*pct
    else:
        # Once forward history exists, measured velocity drives the projection,
        # with a 25% acceleration allowance and a minimum late-sales reserve.
        velocity_extra=max(0.0,velocity_per_hour)*hours*1.25
        if hours <= 1: reserve=sold*.05
        elif hours <= 6: reserve=sold*.10
        elif hours <= 24: reserve=sold*.15
        else: reserve=sold*.05
        extra=max(velocity_extra,reserve)
    return int(ceil(sold+extra))
