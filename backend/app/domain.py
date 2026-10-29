"""Pure analytics and time-selection logic: no network calls."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from math import sqrt
from statistics import mean
from zoneinfo import ZoneInfo

UK = ZoneInfo('Europe/London')
UTC = timezone.utc
FIRST_DELIVERY = date(2026, 1, 2)
LAST_DELIVERY = date(2026, 2, 1)


def parse_timestamp(raw: str | datetime) -> datetime:
    if isinstance(raw, datetime):
        value = raw
    else:
        value = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('Upstream timestamps must include timezone information')
    return value.astimezone(UTC)


def timestamp(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace('+00:00', 'Z')


def decision_cutoff(delivery: date, cutoff: time) -> datetime:
    """Purchase decision is the preceding UK calendar day, local wall-clock time."""
    date_before = delivery - timedelta(days=1)
    return datetime.combine(date_before, cutoff, tzinfo=UK).astimezone(UTC)


def parse_cutoff(raw: str) -> time:
    try:
        parsed = time.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError('Cut-off must use HH:MM (24-hour UK local time)') from exc
    if parsed.tzinfo is not None or parsed.second or parsed.microsecond:
        raise ValueError('Cut-off must use HH:MM (24-hour UK local time)')
    return parsed


def ensure_delivery_in_scope(delivery: date) -> None:
    if not FIRST_DELIVERY <= delivery <= LAST_DELIVERY:
        raise ValueError('Choose a delivery date from 2 January through 1 February 2026')


def valid_number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
        if not (-1e100 < number < 1e100) or number < 0:
            return None
        return number
    except (ValueError, TypeError):
        return None


def choose_forecasts(rows: list[dict], cutoff_utc: datetime) -> dict[datetime, dict]:
    """Latest *published by* cutoff for each target startTime; never use hindsight."""
    selected: dict[datetime, dict] = {}
    for record in rows:
        try:
            target = parse_timestamp(record['startTime'])
            published = parse_timestamp(record['publishTime'])
            generation = valid_number(record.get('generation'))
        except (ValueError, KeyError, TypeError):
            continue
        if generation is None or published > cutoff_utc or published > target:
            continue
        old = selected.get(target)
        if old is None or published > parse_timestamp(old['publishTime']):
            selected[target] = {
                'publishTime': timestamp(published),
                'generation': generation,
            }
    return selected


def choose_actuals(rows: list[dict]) -> dict[datetime, dict]:
    """Keep latest published revision of actual WIND measurements for each target."""
    selected: dict[datetime, dict] = {}
    for record in rows:
        if str(record.get('fuelType', '')).upper() != 'WIND':
            continue
        try:
            target = parse_timestamp(record['startTime'])
            value = valid_number(record.get('generation'))
        except (ValueError, KeyError, TypeError):
            continue
        if value is None:
            continue
        publication = record.get('publishTime') or record.get('publishingTime')
        try:
            published = parse_timestamp(publication) if publication else target
        except (TypeError, ValueError):
            published = target
        old = selected.get(target)
        if old is None or published >= parse_timestamp(old['published']):
            selected[target] = {'generation': value, 'published': timestamp(published)}
    return selected


def metrics(errors: list[float], actuals: list[float]) -> dict:
    """Signed error is forecast minus actual; positive bias = over-forecast."""
    if not errors:
        return {'mae': None, 'rmse': None, 'bias': None, 'mape': None, 'n': 0}
    nonzero_ratios = [abs(err) / a * 100 for err, a in zip(errors, actuals) if a > 0]
    return {
        'mae': round(mean(abs(x) for x in errors), 1),
        'rmse': round(sqrt(mean(x * x for x in errors)), 1),
        'bias': round(mean(errors), 1),
        'mape': round(mean(nonzero_ratios), 1) if nonzero_ratios else None,
        'n': len(errors),
    }


def analyse_day(delivery: date, cutoff: time, forecast_rows: list[dict], actual_rows: list[dict], mode: str) -> dict:
    """Match hourly WINDFOR power with the mean of two FUELHH half-hour MW readings.

    WINDFOR supplies hourly targets; FUELHH supplies half-hourly outturn. A valid
    hourly actual requires both constituent readings. No missing measurements
    are interpolated, and all selected forecasts existed before the decision.
    """
    ensure_delivery_in_scope(delivery)
    cutoff_dt = decision_cutoff(delivery, cutoff)
    forecasts = choose_forecasts(forecast_rows, cutoff_dt)
    actuals = choose_actuals(actual_rows)
    start = datetime.combine(delivery, time.min, tzinfo=UK).astimezone(UTC)
    stop = datetime.combine(delivery + timedelta(days=1), time.min, tzinfo=UK).astimezone(UTC)
    periods = []
    errors, matched_actuals = [], []
    point = start
    while point < stop:
        forecast = forecasts.get(point)
        # FUELHH power readings cover successive thirty-minute intervals.
        # The arithmetic mean is the equivalent average MW for the full hour.
        half_hours = [actuals.get(point), actuals.get(point + timedelta(minutes=30))]
        half_hour_values = [item['generation'] if item else None for item in half_hours]
        complete_actual = all(v is not None for v in half_hour_values)
        actual_mw = round(sum(half_hour_values) / 2, 2) if complete_actual else None
        forecast_mw = forecast['generation'] if forecast else None
        error_mw = round(forecast_mw - actual_mw, 2) if forecast_mw is not None and actual_mw is not None else None
        if error_mw is not None:
            errors.append(error_mw)
            matched_actuals.append(actual_mw)
        if error_mw is not None:
            status = 'matched'
        elif not complete_actual and any(v is not None for v in half_hour_values):
            status = 'incomplete-actual'
        elif forecast_mw is not None:
            status = 'forecast-only'
        elif actual_mw is not None:
            status = 'actual-only'
        else:
            status = 'missing'
        periods.append({
            'time': timestamp(point),
            'label': point.astimezone(UK).strftime('%H:%M'),
            'forecast_mw': forecast_mw,
            'actual_mw': actual_mw,
            'actual_half_hours_mw': half_hour_values,
            'error_mw': error_mw,
            'published_at': forecast['publishTime'] if forecast else None,
            'status': status,
        })
        point += timedelta(hours=1)

    forecast_values = [p['forecast_mw'] for p in periods if p['forecast_mw'] is not None]
    actual_values = [p['actual_mw'] for p in periods if p['actual_mw'] is not None]
    matched_periods = [p for p in periods if p['error_mw'] is not None]
    sample_count = len(errors)
    coverage = round(sample_count / len(periods) * 100, 1)
    # Each *hourly* MW value represents one hour of energy, not half an hour.
    abs_mwh = round(sum(abs(x) for x in errors), 1)
    # Important: forecast and actual energy totals must use the SAME matched
    # hours. Otherwise, partial coverage produces misleading comparisons.
    forecast_mwh = round(sum(p['forecast_mw'] for p in matched_periods), 1) if matched_periods else None
    actual_mwh = round(sum(p['actual_mw'] for p in matched_periods), 1) if matched_periods else None
    measured = metrics(errors, matched_actuals)
    direction = 'over-forecast' if measured['bias'] is not None and measured['bias'] > 0 else 'under-forecast' if measured['bias'] is not None and measured['bias'] < 0 else 'neutral'
    largest_miss = max(matched_periods, key=lambda p: abs(p['error_mw']), default=None)
    # This is NOT a purchased energy quantity. It is a retrospective sum of
    # hour-long forecast-minus-actual MW errors on identical matched hours.
    net_energy_error_mwh = round(sum(p['error_mw'] for p in matched_periods), 1) if matched_periods else None
    publication_times = sorted({p['published_at'] for p in periods if p['published_at']})
    decision_brief = {
        'net_energy_error_mwh': net_energy_error_mwh,
        'largest_miss': {
            'time_utc': largest_miss['time'],
            'hour_uk': largest_miss['label'],
            'error_mw': largest_miss['error_mw'],
        } if largest_miss else None,
        'distinct_publications': len(publication_times),
        'latest_publication_utc': publication_times[-1] if publication_times else None,
        'status': 'unavailable' if sample_count == 0 else 'complete' if sample_count == len(periods) else 'partial',
        'limitation': 'Retrospective wind-only diagnostic; not a purchase quantity or trading recommendation.',
    }
    return {
        'delivery_date': delivery.isoformat(),
        'decision_date': (delivery - timedelta(days=1)).isoformat(),
        'cutoff_uk': cutoff.strftime('%H:%M'),
        'cutoff_utc': timestamp(cutoff_dt),
        'timezone': 'Europe/London',
        'source': mode,
        'method': 'hourly WINDFOR MW vs mean of two complete FUELHH half-hour MW values',
        'decision_brief': decision_brief,
        'statistics': {
            **measured,
            'coverage_pct': coverage,
            'matched_periods': sample_count,
            'forecast_periods': len(forecast_values),
            'actual_periods': len(actual_values),
            'total_periods': len(periods),
            'period_minutes': 60,
            'raw_actual_half_hours': sum(v is not None for p in periods for v in p['actual_half_hours_mw']),
            'absolute_error_mwh': abs_mwh,
            'energy_basis': 'matched_hours_only',
            'forecast_energy_mwh': forecast_mwh,
            'actual_energy_mwh': actual_mwh,
            'direction': direction,
        },
        'periods': periods,
    }


def compare_cutoffs(delivery: date, early_cutoff: time, late_cutoff: time, forecast_rows: list[dict], actual_rows: list[dict], mode: str) -> dict:
    """Use the SAME upstream data for both as-of scenarios to avoid confounding."""
    if early_cutoff >= late_cutoff:
        raise ValueError('Early cut-off must precede late cut-off')
    early = analyse_day(delivery, early_cutoff, forecast_rows, actual_rows, mode)
    late = analyse_day(delivery, late_cutoff, forecast_rows, actual_rows, mode)
    differences = []
    for a, b in zip(early['periods'], late['periods']):
        if a['forecast_mw'] is not None and b['forecast_mw'] is not None:
            differences.append(b['forecast_mw'] - a['forecast_mw'])
    changed = [delta for delta in differences if abs(delta) > 1e-9]
    # Overall MAEs may be based on different hours at different cut-offs.
    # The decision comparison therefore also calculates a *paired* MAE on
    # only the target hours matched in both scenarios.
    common_errors = [
        (a['error_mw'], b['error_mw'])
        for a, b in zip(early['periods'], late['periods'])
        if a['error_mw'] is not None and b['error_mw'] is not None
    ]
    common_early = round(mean(abs(a) for a, _ in common_errors), 1) if common_errors else None
    common_late = round(mean(abs(b) for _, b in common_errors), 1) if common_errors else None
    delta_mae = round(common_late - common_early, 1) if common_errors else None
    common_comparison = {
        'matched_hours': len(common_errors),
        'early_mae_mw': common_early,
        'late_mae_mw': common_late,
        'delta_mae_mw': delta_mae,
        'outcome': 'unavailable' if delta_mae is None else 'later_worse' if delta_mae > 0 else 'later_better' if delta_mae < 0 else 'unchanged',
        'method': 'Paired MAE on identical hours matched at BOTH cut-offs; positive delta = later forecast worse.',
    }
    return {
        'delivery_date': delivery.isoformat(), 'source': mode,
        'early': {'cutoff_uk': early['cutoff_uk'], 'statistics': early['statistics']},
        'late': {'cutoff_uk': late['cutoff_uk'], 'statistics': late['statistics']},
        'comparable_forecast_hours': len(differences),
        'revised_hours': len(changed),
        'net_forecast_change_mwh': round(sum(differences), 1) if differences else None,
        'largest_revision_mw': round(max((abs(x) for x in differences), default=0), 1),
        'common_comparison': common_comparison,
        'note': 'Retrospective scenario comparison, not an actual trading or market-gate-closure recommendation.',
    }


def summarise_month(days: list[dict], cutoff: str, mode: str) -> dict:
    all_errors, all_actuals = [], []
    daily = []
    for day in days:
        paired = [p for p in day['periods'] if p['error_mw'] is not None]
        all_errors.extend(p['error_mw'] for p in paired)
        all_actuals.extend(p['actual_mw'] for p in paired)
        daily.append({'delivery_date': day['delivery_date'], **day['statistics']})
    expected = sum(day['statistics']['total_periods'] for day in days)
    return {
        'source': mode,
        'cutoff_uk': cutoff,
        'days': daily,
        'statistics': {
            **metrics(all_errors, all_actuals),
            'coverage_pct': round(len(all_errors) / expected * 100, 1) if expected else 0,
            'matched_periods': len(all_errors),
            'total_periods': expected,
        },
    }
