import collections
import datetime
from typing import Any

import altair as alt
import flask
import pandas as pd
import sqlalchemy
from flask import render_template
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ...core.config import ConfigAccessor
from ...core.datamodel import (
    DB,
    Activity,
    count_activities,
    get_activity_by_id,
    query_activity_meta,
)
from ...features.equipment.stats import get_equipment_status
from ...features.hall_of_fame.blueprint import nominate_activities
from ...features.maintenance.stats import get_due_tasks
from ...features.summary.plots import plot_year_cumulative
from ..columns import (
    META_COLUMNS,
    ColumnDescription,
    column_distance,
)
from ..period_stats import get_period_stats
from ..plot_util import make_kind_scale, to_vega


def register_entry_views(app: flask.Flask, config_accessor: ConfigAccessor) -> None:
    @app.route("/")
    def index() -> ResponseReturnValue:
        config = config_accessor.ui()
        context: dict[str, Any] = {
            "latest_activities": [],
            "due_tasks": get_due_tasks(),
            "period_stats": [],
            "equipment_status": [],
            "recent_records": [],
            "show_progress_markers": config.show_progress_markers,
        }
        df = query_activity_meta()

        if count_activities():
            kind_scale = make_kind_scale(df, config_accessor.ui())
            context["last_30_days_plot"] = {
                column.display_name: _last_30_days_meta_plot(df, kind_scale, column)
                for column in META_COLUMNS
            }
            dated = df.loc[df["start_local"].notna()]
            context["period_stats"] = get_period_stats(df)
            context["year_cumulative_plot"] = plot_year_cumulative(
                dated, column_distance
            )
            context["equipment_status"] = get_equipment_status(limit=6)
            context["recent_records"] = _recent_records(dated)

            context["latest_activities"] = collections.defaultdict(list)
            for activity in DB.session.scalars(
                sqlalchemy.select(Activity)
                .where(Activity.start.is_not(None))
                .order_by(Activity.start.desc())
                .limit(100)
            ):
                context["latest_activities"][activity.start_local_tz.date()].append(
                    {"activity": activity}
                )

        return render_template("home.html.j2", **context)


_RECENT_RECORD_DAYS = 90
_RECENT_RECORD_LIMIT = 5
_RECENT_RECORD_REASONS = 2


def _recent_records(meta: pd.DataFrame) -> list[tuple[Activity, list[str]]]:
    """Hall-of-fame nominations restricted to the recent past.

    The all-time records are on their own page; here the interesting question is
    what stood out lately.
    """
    cutoff = pd.Timestamp(
        datetime.date.today() - datetime.timedelta(days=_RECENT_RECORD_DAYS)
    )
    recent = meta.loc[meta["start_local"] >= cutoff]
    if recent.empty:
        return []
    # The sidebar has no room for the per-kind and per-equipment records that
    # the hall of fame lists, nor for every reason an activity qualifies under.
    nominations = nominate_activities(recent, by_group=False)
    activities = [
        (get_activity_by_id(activity_id), reasons[:_RECENT_RECORD_REASONS])
        for activity_id, reasons in nominations.items()
    ]
    activities.sort(key=lambda pair: pair[0].start, reverse=True)
    return activities[:_RECENT_RECORD_LIMIT]


def _last_30_days_meta_plot(
    meta: pd.DataFrame, kind_scale: alt.Scale, column: ColumnDescription
) -> str:
    before_30_days = pd.to_datetime(
        datetime.datetime.now() - datetime.timedelta(days=31)
    )
    return to_vega(
        alt.Chart(
            meta.loc[meta["start_local"] > before_30_days],
            height=200,
            title=_("%(display_name)s per day") % {"display_name": column.display_name},
        )
        .mark_bar()
        .encode(
            alt.X("yearmonthdate(start_local)", title=_("Date")),
            alt.Y(f"sum({column.name})", title=f"{column.name} / {column.unit}"),
            alt.Color("kind", scale=kind_scale, title=_("Kind")),
            [
                alt.Tooltip("yearmonthdate(start_local)", title=_("Date")),
                alt.Tooltip("kind", title=_("Kind")),
                alt.Tooltip(
                    f"sum({column.name})",
                    format=column.format,
                    title=f"{column.display_name} / {column.unit}",
                ),
            ],
        )
    )
