import datetime

from flask import Blueprint, Response
from flask.typing import ResponseReturnValue

from ...core.config import ConfigAccessor
from ...core.datamodel import (
    apply_privacy_zones,
    get_activity_by_id,
    get_time_series,
    query_activity_meta,
)
from .render import make_day_sharepic, make_sharepic


def make_sharepic_blueprint(config_accessor: ConfigAccessor) -> Blueprint:
    blueprint = Blueprint("sharepic", __name__, template_folder="templates")

    @blueprint.route("/activity/<int:id>.png")
    def activity(id: int) -> ResponseReturnValue:
        activity = get_activity_by_id(id)
        time_series = apply_privacy_zones(get_time_series(id))
        if len(time_series) == 0:
            time_series = get_time_series(id)
        return Response(
            make_sharepic(
                activity,
                time_series,
                config_accessor.ui().sharepic_suppressed_fields,
                config_accessor.map(),
            ),
            mimetype="image/png",
        )

    @blueprint.route("/day/<int:year>/<int:month>/<int:day>.png")
    def day(year: int, month: int, day: int) -> ResponseReturnValue:
        config = config_accessor.map()
        meta = query_activity_meta()
        selection = meta["start_local"].dt.date == datetime.date(year, month, day)
        activities_that_day = meta.loc[selection]

        time_series = [
            get_time_series(activity_id) for activity_id in activities_that_day["id"]
        ]
        assert len(activities_that_day) > 0
        assert len(time_series) > 0
        return Response(
            make_day_sharepic(activities_that_day, time_series, config),
            mimetype="image/png",
        )

    return blueprint
