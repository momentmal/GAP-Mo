from flask import Flask

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.datamodel import DB, Activity


def _activity_with_new_tiles() -> Activity:
    return max(
        DB.session.scalars(DB.select(Activity)),
        key=lambda activity: sum(activity.new_tile_counts.values()),
    )


def test_emoji_string_lists_new_tiles_per_zoom_level(seeded_app: Flask) -> None:
    with seeded_app.app_context():
        activity = _activity_with_new_tiles()
        counts = activity.new_tile_counts
        zoom_levels = ConfigAccessor().ui().explorer_zoom_levels
        assert set(zoom_levels) <= set(counts)
        for zoom in zoom_levels:
            assert f" {counts[zoom]}" in activity.emoji_string


def test_home_page_shows_new_tile_counts(seeded_app: Flask, seeded_client) -> None:
    with seeded_app.app_context():
        expected = _activity_with_new_tiles().emoji_string

    response = seeded_client.get("/")
    assert response.status_code == 200
    assert "🟨" in expected
    assert expected in response.data.decode()
