from typing import Any

import altair as alt
import pandas as pd

from ..core.datamodel import UiConfig


def make_kind_scale(meta: pd.DataFrame, config: UiConfig) -> alt.Scale:
    kinds = sorted(meta["kind"].unique())
    return alt.Scale(domain=kinds, scheme=config.color_scheme_for_kind)


def to_vega(chart: alt.TopLevelMixin, height: int | None = None) -> str:
    """Serialize a chart that fills the width of whatever container it is put in.

    Vega-Lite's `"container"` width survives compilation to Vega as a signal
    reading `containerSize()`; `embedChart` in the frontend keeps that signal in
    sync with the container the chart actually ended up in.
    """
    properties: dict[str, Any] = {"width": "container"}
    if height is not None:
        properties["height"] = height
    return chart.properties(**properties).to_json(format="vega")
