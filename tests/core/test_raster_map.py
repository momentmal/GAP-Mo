from geo_activity_playground.core.raster_map import (
    format_sample_tile_url,
    normalize_tile_url_template,
    tile_url_template_error,
)

OSM_URL = "https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"


def test_normalize_short_zoom_placeholder() -> None:
    assert normalize_tile_url_template("https://example.org/{z}/{x}/{y}.png") == (
        "https://example.org/{zoom}/{x}/{y}.png"
    )


def test_normalize_keeps_canonical_url() -> None:
    assert normalize_tile_url_template(OSM_URL) == OSM_URL


def test_valid_url_has_no_error() -> None:
    assert tile_url_template_error(OSM_URL) is None


def test_query_parameters_are_allowed() -> None:
    assert (
        tile_url_template_error(
            "https://api.maptiler.com/maps/outdoor-v4/{zoom}/{x}/{y}.png?key=secret"
        )
        is None
    )


def test_short_zoom_placeholder_is_rejected_before_normalization() -> None:
    error = tile_url_template_error("https://example.org/{z}/{x}/{y}.png")
    assert error is not None
    assert "{zoom}" in error


def test_missing_placeholder_is_rejected() -> None:
    error = tile_url_template_error("https://example.org/{zoom}/{x}.png")
    assert error is not None
    assert "{y}" in error


def test_unknown_placeholder_is_rejected() -> None:
    error = tile_url_template_error("https://example.org/{zoom}/{x}/{y}/{foo}.png")
    assert error is not None
    assert "{foo}" in error


def test_unbalanced_braces_are_rejected() -> None:
    assert tile_url_template_error("https://example.org/{zoom/{x}/{y}.png") is not None


def test_sample_url_is_formatted() -> None:
    assert format_sample_tile_url(OSM_URL) == (
        "https://tile.openstreetmap.org/14/8514/5504.png"
    )


def test_sample_url_of_broken_template_is_none() -> None:
    assert format_sample_tile_url("https://example.org/{z}/{x}/{y}.png") is None
