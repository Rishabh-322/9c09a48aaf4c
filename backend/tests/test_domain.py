from datetime import date, datetime, time, timezone
import pytest
from app.domain import analyse_day, choose_forecasts, decision_cutoff, parse_cutoff, metrics, ensure_delivery_in_scope, summarise_month, compare_cutoffs


def test_decision_cutoff_is_day_before_in_uk():
    assert decision_cutoff(date(2026, 1, 16), time(12)) == datetime(2026, 1, 15, 12, tzinfo=timezone.utc)


def test_forecasts_reject_hindsight_and_choose_latest_per_target():
    target = '2026-01-16T00:00:00Z'
    rows = [
        {'startTime': target, 'publishTime': '2026-01-15T08:00:00Z', 'generation': 900},
        {'startTime': target, 'publishTime': '2026-01-15T11:00:00Z', 'generation': 1000},
        {'startTime': target, 'publishTime': '2026-01-15T16:00:00Z', 'generation': 3000},
        {'startTime': target, 'publishTime': '2026-01-17T00:00:00Z', 'generation': 4000},
    ]
    picked = choose_forecasts(rows, decision_cutoff(date(2026, 1, 16), time(12)))
    assert next(iter(picked.values()))['generation'] == 1000


def test_report_aligns_hourly_forecast_with_two_half_hour_actuals():
    forecasts = [{'startTime': '2026-01-16T00:00:00Z', 'publishTime': '2026-01-15T08:00:00Z', 'generation': 1200}]
    actuals = [
        {'startTime': '2026-01-16T00:30:00Z', 'fuelType': 'WIND', 'generation': 1000},
        {'startTime': '2026-01-16T00:00:00Z', 'fuelType': 'WIND', 'generation': 800},
        {'startTime': '2026-01-16T00:00:00Z', 'fuelType': 'GAS', 'generation': 5000},
    ]
    report = analyse_day(date(2026, 1, 16), time(12), forecasts, actuals, 'test')
    assert len(report['periods']) == 24
    assert report['statistics']['matched_periods'] == 1
    assert report['statistics']['period_minutes'] == 60
    assert report['statistics']['mae'] == 300
    assert report['statistics']['bias'] == 300
    assert report['statistics']['coverage_pct'] == 4.2
    assert report['statistics']['forecast_energy_mwh'] == 1200
    assert report['statistics']['actual_energy_mwh'] == 900
    assert report['periods'][0]['actual_half_hours_mw'] == [800, 1000]
    assert report['periods'][0]['actual_mw'] == 900
    assert report['periods'][1]['forecast_mw'] is None


def test_partial_actual_hour_is_not_filled_in():
    forecasts = [{'startTime': '2026-01-16T01:00:00Z', 'publishTime': '2026-01-15T08:00:00Z', 'generation': 1200}]
    actuals = [{'startTime': '2026-01-16T01:00:00Z', 'fuelType': 'WIND', 'generation': 1000}]
    report = analyse_day(date(2026, 1, 16), time(12), forecasts, actuals, 'test')
    assert report['periods'][1]['status'] == 'incomplete-actual'
    assert report['periods'][1]['actual_half_hours_mw'] == [1000, None]
    assert report['periods'][1]['actual_mw'] is None
    assert report['statistics']['matched_periods'] == 0


def test_cutoff_comparison_uses_same_target_and_blocks_future_revision():
    forecasts = [
        {'startTime': '2026-01-16T00:00:00Z', 'publishTime': '2026-01-15T08:00:00Z', 'generation': 1200},
        {'startTime': '2026-01-16T00:00:00Z', 'publishTime': '2026-01-15T16:00:00Z', 'generation': 1500},
        {'startTime': '2026-01-16T00:00:00Z', 'publishTime': '2026-01-15T23:00:00Z', 'generation': 9999},
    ]
    actuals = [
        {'startTime': '2026-01-16T00:00:00Z', 'fuelType': 'WIND', 'generation': 1000},
        {'startTime': '2026-01-16T00:30:00Z', 'fuelType': 'WIND', 'generation': 1000},
    ]
    report = compare_cutoffs(date(2026, 1, 16), time(9), time(18), forecasts, actuals, 'test')
    assert report['early']['statistics']['mae'] == 200
    assert report['late']['statistics']['mae'] == 500
    assert report['revised_hours'] == 1
    assert report['net_forecast_change_mwh'] == 300
    with pytest.raises(ValueError):
        compare_cutoffs(date(2026, 1, 16), time(18), time(9), forecasts, actuals, 'test')


def test_mape_excludes_zero_actual_and_metrics_are_signed():
    calculated = metrics([100, -100], [0, 1000])
    assert calculated['mae'] == 100
    assert calculated['rmse'] == 100
    assert calculated['bias'] == 0
    assert calculated['mape'] == 10


def test_invalid_cutoff_and_delivery_rejected():
    with pytest.raises(ValueError):
        parse_cutoff('25:61')
    with pytest.raises(ValueError):
        ensure_delivery_in_scope(date(2026, 1, 1))


def test_month_rollup_weighted_by_matched_intervals():
    a = analyse_day(date(2026, 1, 16), time(12), [{'startTime':'2026-01-16T00:00:00Z','publishTime':'2026-01-15T08:00:00Z','generation':110}], [{'startTime':'2026-01-16T00:00:00Z','fuelType':'WIND','generation':100}, {'startTime':'2026-01-16T00:30:00Z','fuelType':'WIND','generation':100}], 'test')
    b = analyse_day(date(2026, 1, 17), time(12), [], [], 'test')
    out = summarise_month([a,b], '12:00', 'test')
    assert out['statistics']['n'] == 1
    assert out['statistics']['mae'] == 10
    assert out['statistics']['total_periods'] == 48


def test_energy_totals_use_only_identical_matched_hours():
    forecasts = [
        {'startTime': '2026-01-16T00:00:00Z', 'publishTime': '2026-01-15T08:00:00Z', 'generation': 1200},
        {'startTime': '2026-01-16T01:00:00Z', 'publishTime': '2026-01-15T08:00:00Z', 'generation': 3000},
    ]
    actuals = [
        {'startTime': '2026-01-16T00:00:00Z', 'fuelType': 'WIND', 'generation': 800},
        {'startTime': '2026-01-16T00:30:00Z', 'fuelType': 'WIND', 'generation': 1000},
        # Hour 01 has an available forecast but only half the actual data.
        {'startTime': '2026-01-16T01:00:00Z', 'fuelType': 'WIND', 'generation': 900},
        # Hour 02 has complete actual data but no forecast.
        {'startTime': '2026-01-16T02:00:00Z', 'fuelType': 'WIND', 'generation': 500},
        {'startTime': '2026-01-16T02:30:00Z', 'fuelType': 'WIND', 'generation': 500},
    ]
    report = analyse_day(date(2026, 1, 16), time(12), forecasts, actuals, 'test')
    stats = report['statistics']
    assert stats['matched_periods'] == 1
    assert stats['forecast_periods'] == 2
    assert stats['actual_periods'] == 2
    assert stats['forecast_energy_mwh'] == 1200
    assert stats['actual_energy_mwh'] == 900
    assert stats['absolute_error_mwh'] == 300
    assert stats['energy_basis'] == 'matched_hours_only'


def test_brief_is_retrospective_and_uses_only_matched_hours():
    forecasts = [
        {'startTime': '2026-01-16T00:00:00Z', 'publishTime': '2026-01-15T08:00:00Z', 'generation': 1200},
        {'startTime': '2026-01-16T01:00:00Z', 'publishTime': '2026-01-15T08:00:00Z', 'generation': 3000},
    ]
    actuals = [
        {'startTime':'2026-01-16T00:00:00Z', 'fuelType':'WIND', 'generation':800},
        {'startTime':'2026-01-16T00:30:00Z', 'fuelType':'WIND', 'generation':1000},
        {'startTime':'2026-01-16T01:00:00Z', 'fuelType':'WIND', 'generation':2000},
    ]
    day = analyse_day(date(2026, 1, 16), time(12), forecasts, actuals, 'test')
    brief = day['decision_brief']
    assert brief['status'] == 'partial'
    assert brief['net_energy_error_mwh'] == 300  # unmatched hour MUST NOT count
    assert brief['largest_miss']['hour_uk'] == '00:00'
    assert brief['largest_miss']['error_mw'] == 300
    assert brief['distinct_publications'] == 1


def test_compare_cutoffs_uses_only_common_matched_hours():
    forecasts = [
        {'startTime':'2026-01-16T00:00:00Z', 'publishTime':'2026-01-15T08:00:00Z', 'generation':900},
        {'startTime':'2026-01-16T00:00:00Z', 'publishTime':'2026-01-15T16:00:00Z', 'generation':950},
        # Second hour is only forecast after 09:00 and must not enter the paired sample.
        {'startTime':'2026-01-16T01:00:00Z', 'publishTime':'2026-01-15T16:00:00Z', 'generation':2000},
    ]
    actuals = []
    for hour in ('00:00', '00:30', '01:00', '01:30'):
        actuals.append({'startTime':f'2026-01-16T{hour}:00Z', 'fuelType':'WIND','generation':1000})
    result = compare_cutoffs(date(2026, 1, 16), time(9), time(18), forecasts, actuals, 'test')
    assert result['early']['statistics']['n'] == 1
    assert result['late']['statistics']['n'] == 2
    paired = result['common_comparison']
    assert paired['matched_hours'] == 1
    assert paired['early_mae_mw'] == 100
    assert paired['late_mae_mw'] == 50
    assert paired['delta_mae_mw'] == -50
    assert paired['outcome'] == 'later_better'


def test_brief_unavailable_without_matched_hours():
    result = analyse_day(date(2026, 1, 16), time(12), [], [], 'test')
    assert result['decision_brief']['status'] == 'unavailable'
    assert result['decision_brief']['net_energy_error_mwh'] is None
    assert result['decision_brief']['largest_miss'] is None
    paired = compare_cutoffs(date(2026, 1, 16), time(9), time(18), [], [], 'test')['common_comparison']
    assert paired['matched_hours'] == 0
    assert paired['delta_mae_mw'] is None
    assert paired['outcome'] == 'unavailable'
