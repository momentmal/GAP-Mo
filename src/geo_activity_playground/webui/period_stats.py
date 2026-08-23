import dataclasses
import datetime

import pandas as pd
from flask_babel import lazy_gettext as _


@dataclasses.dataclass
class PeriodStats:
    label: str
    activities: int
    distance_km: float
    elevation_gain: float
    hours: float
    # Relative change in distance against the same stretch of the previous
    # period, e.g. this month so far against last month up to the same day.
    # None when the previous period had no activities to compare against.
    distance_change: float | None


def _period_bounds(
    today: datetime.date,
) -> list[tuple[str, datetime.date, datetime.date]]:
    """Label, start of the current period, and start of the previous one."""
    week = today - datetime.timedelta(days=today.weekday())
    month = today.replace(day=1)
    previous_month = (month - datetime.timedelta(days=1)).replace(day=1)
    year = today.replace(month=1, day=1)
    return [
        (str(_("This week")), week, week - datetime.timedelta(days=7)),
        (str(_("This month")), month, previous_month),
        (str(_("This year")), year, year.replace(year=year.year - 1)),
    ]


def _aggregate(df: pd.DataFrame, start: datetime.date, end: datetime.date) -> pd.Series:
    window = df.loc[
        (df["start_local"] >= pd.Timestamp(start))
        & (df["start_local"] < pd.Timestamp(end))
    ]
    return pd.Series(
        {
            "activities": len(window),
            "distance_km": window["distance_km"].sum(),
            "elevation_gain": window["elevation_gain"].sum(),
            "hours": window["hours"].sum(),
        }
    )


def get_period_stats(df: pd.DataFrame) -> list[PeriodStats]:
    """Totals for week, month and year so far, each against the previous period."""
    if df.empty:
        return []
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    df = df.loc[df["start_local"].notna()]

    stats = []
    for label, start, previous_start in _period_bounds(today):
        current = _aggregate(df, start, tomorrow)
        # Compare like with like: only the elapsed part of the previous period.
        elapsed = tomorrow - start
        previous = _aggregate(df, previous_start, previous_start + elapsed)
        stats.append(
            PeriodStats(
                label=label,
                activities=int(current["activities"]),
                distance_km=float(current["distance_km"]),
                elevation_gain=float(current["elevation_gain"]),
                hours=float(current["hours"]),
                distance_change=(
                    float(current["distance_km"] / previous["distance_km"] - 1)
                    if previous["distance_km"] > 0
                    else None
                ),
            )
        )
    return stats
