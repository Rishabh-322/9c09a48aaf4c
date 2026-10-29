"""Illustrative synthetic samples ONLY. Never presented as Elexon measurements."""
from datetime import date, datetime, time, timedelta, timezone
from math import sin, cos, pi
import random
from .domain import timestamp


def demo_rows(delivery: date) -> tuple[list[dict], list[dict]]:
    rng = random.Random(delivery.toordinal())
    forecast_rows, actual_rows = [], []
    start = datetime.combine(delivery, time.min, tzinfo=timezone.utc)
    decision = start - timedelta(days=1)
    actual_by_half_hour = []
    for i in range(48):
        target = start + timedelta(minutes=30 * i)
        drift = (delivery.toordinal() % 9) * 190
        actual = max(600, 8000 + drift + 2550 * sin(i / 48 * 2 * pi + 0.4) + 1350 * cos(i / 48 * 4 * pi + .7) + rng.uniform(-280, 280))
        actual_by_half_hour.append(actual)
        actual_rows.append({'fuelType': 'WIND', 'generation': round(actual), 'startTime': timestamp(target), 'publishTime': timestamp(target + timedelta(hours=1))})
    for hour in range(24):
        target = start + timedelta(hours=hour)
        avg_actual = (actual_by_half_hour[hour*2] + actual_by_half_hour[hour*2+1]) / 2
        forecast = max(600, avg_actual + 650 * sin(hour / 5 + delivery.day) + rng.uniform(-650, 650))
        # A few explicitly missing hourly targets for realistic demo-only gaps.
        if hour in (5, 14, 20):
            continue
        forecast_rows.append({'generation': round(forecast), 'startTime': timestamp(target), 'publishTime': timestamp(decision + timedelta(hours=8))})
        forecast_rows.append({'generation': round(forecast * 1.015), 'startTime': timestamp(target), 'publishTime': timestamp(decision + timedelta(hours=16))})
        forecast_rows.append({'generation': round(forecast * .98), 'startTime': timestamp(target), 'publishTime': timestamp(decision + timedelta(hours=23))})
    return forecast_rows, actual_rows
