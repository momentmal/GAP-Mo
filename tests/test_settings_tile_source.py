import pytest
from flask import Flask

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.webui.blueprints import settings_blueprint

DEFAULT_URL = "https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"


@pytest.fixture
def no_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_blueprint, "probe_tile_url", lambda _url: None)


def _post(app: Flask, url: str):
    return app.test_client().post(
        "/settings/tile-source",
        data={
            "map_tile_url": url,
            "map_tile_attribution": "© OpenStreetMap",
            "hillshade_opacity": "0.5",
            "hillshade_blend_mode": "multiply",
        },
    )


def test_short_zoom_placeholder_is_normalized(app: Flask, no_probe: None) -> None:
    response = _post(app, "https://example.org/{z}/{x}/{y}.png")
    assert response.status_code == 200
    with app.app_context():
        assert (
            ConfigAccessor().map().map_tile_url
            == "https://example.org/{zoom}/{x}/{y}.png"
        )


def test_unknown_placeholder_keeps_config_and_input(app: Flask, no_probe: None) -> None:
    response = _post(app, "https://example.org/{zoom}/{x}/{foo}.png")
    assert response.status_code == 200
    assert "{foo}" in response.data.decode()
    with app.app_context():
        assert ConfigAccessor().map().map_tile_url == DEFAULT_URL


def test_unreachable_tile_server_keeps_config(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        settings_blueprint, "probe_tile_url", lambda _url: "status 403: Forbidden"
    )
    response = _post(app, "https://example.org/{zoom}/{x}/{y}.png")
    assert response.status_code == 200
    assert "403" in response.data.decode()
    with app.app_context():
        assert ConfigAccessor().map().map_tile_url == DEFAULT_URL


def test_other_settings_are_saved_despite_bad_url(app: Flask, no_probe: None) -> None:
    _post(app, "https://example.org/{zoom}/{x}/{foo}.png")
    with app.app_context():
        assert ConfigAccessor().map().map_tile_attribution == "© OpenStreetMap"
        assert ConfigAccessor().tile().hillshade_opacity == 0.5


def test_broken_stored_url_does_not_break_the_page(app: Flask) -> None:
    with app.app_context():
        config_accessor = ConfigAccessor()
        config_accessor.map().map_tile_url = "https://example.org/{z}/{x}/{y}.png"
        config_accessor.save()
    response = app.test_client().get("/settings/tile-source")
    assert response.status_code == 200
