import pandas as pd
import sqlalchemy
from flask import Blueprint, render_template

from ...core.config import ConfigAccessor
from ...core.datamodel import DB, query_activity_meta
from ...core.meta_search import apply_search_filter
from ...features.plot_builder.analysis import make_parametric_plot
from ...features.plot_builder.model import PlotSpec
from ...webui.authenticator import Authenticator
from ...webui.columns import META_COLUMNS
from ...webui.search_context import search_context
from .plots import (
    heatmap_per_day,
    plot_per_iso_week,
    plot_per_year_per_kind,
    plot_year_cumulative,
)


def make_summary_blueprint(
    config_accessor: ConfigAccessor,
    authenticator: Authenticator,
) -> Blueprint:
    blueprint = Blueprint("summary", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        primitives, search_vars = search_context(authenticator)

        df = apply_search_filter(primitives)

        df_without_nan = df.loc[~pd.isna(df["start_local"])]

        return render_template(
            "summary/index.html.j2",
            **search_vars,
            custom_plots=[
                (spec, make_parametric_plot(query_activity_meta(), spec))
                for spec in DB.session.scalars(sqlalchemy.select(PlotSpec)).all()
            ],
            plot_per_year_per_kind={
                column.display_name: plot_per_year_per_kind(df_without_nan, column)
                for column in META_COLUMNS
            },
            plot_per_year_cumulative={
                column.display_name: plot_year_cumulative(df_without_nan, column)
                for column in META_COLUMNS
            },
            plot_per_iso_week={
                column.display_name: plot_per_iso_week(df_without_nan, column)
                for column in META_COLUMNS
            },
            heatmap_per_day={
                column.display_name: heatmap_per_day(df_without_nan, column)
                for column in META_COLUMNS
            },
        )

    return blueprint
