"""Tests para las rutas principales de la aplicación."""
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.config import Settings

_MOCK_RESULT = {
    "total_value": 5000.0,
    "population_covered": 100,
    "polygon_count": 1,
    "polygons_geojson": None,
}

_DEFAULT_SETTINGS = Settings(
    grid_data="n6_1k_aniop_ipm.geojson",
    data_path=Path("./tests/fixtures"),
    val_min=0,
    max_points=5,
    log_level="INFO",
    env="test",
)


def _make_client(side_effect=None, settings=None, total_value=None) -> TestClient:
    mock_engine = MagicMock()
    if side_effect:
        mock_engine.calculate_coverage.side_effect = side_effect
    else:
        result = dict(_MOCK_RESULT)
        if total_value is not None:
            result["total_value"] = total_value
        mock_engine.calculate_coverage.return_value = result
    app.state.geo_engine = mock_engine
    app.state.settings = settings if settings is not None else _DEFAULT_SETTINGS
    return TestClient(app, raise_server_exceptions=False)


def test_health():
    client = _make_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "geosight"}


def test_index():
    client = _make_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_get_map():
    client = _make_client()
    response = client.get("/map?lat=4.71&lng=-74.07&radius_km=8.23")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_create_assignment():
    client = _make_client()
    response = client.post(
        "/assignments",
        data={"name": "Test", "lat": 4.71, "lng": -74.07, "radius_km": 8.23},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == 5000.0
    assert data["population"] == 100
    assert "map_html" in data


def test_value_error_returns_400():
    client = _make_client(side_effect=ValueError("Radio invalido: 99.0"))
    response = client.post(
        "/assignments",
        data={"name": "Test", "lat": 4.71, "lng": -74.07, "radius_km": 99.0},
    )
    assert response.status_code == 400
    assert "error" in response.json()


def test_unexpected_exception_returns_500():
    client = _make_client(side_effect=RuntimeError("fallo inesperado"))
    response = client.post(
        "/assignments",
        data={"name": "Test", "lat": 4.71, "lng": -74.07, "radius_km": 8.23},
    )
    assert response.status_code == 500
    assert response.json()["error"] == "Error interno del servidor"


def test_min_applied_false_when_value_above_floor():
    settings = Settings(
        grid_data="n6_1k_aniop_ipm.geojson",
        data_path=Path("./tests/fixtures"),
        val_min=1000,
        max_points=5,
        log_level="INFO",
        env="test",
    )
    client = _make_client(settings=settings, total_value=5000.0)
    response = client.post(
        "/assignments",
        data={"name": "Test", "lat": 4.71, "lng": -74.07, "radius_km": 8.23},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == 5000.0
    assert data["min_applied"] is False


def test_min_applied_true_when_value_below_floor():
    settings = Settings(
        grid_data="n6_1k_aniop_ipm.geojson",
        data_path=Path("./tests/fixtures"),
        val_min=1_000_000,
        max_points=5,
        log_level="INFO",
        env="test",
    )
    client = _make_client(settings=settings, total_value=50.0)
    response = client.post(
        "/assignments",
        data={"name": "Test", "lat": 4.71, "lng": -74.07, "radius_km": 8.23},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == 1_000_000
    assert data["min_applied"] is True


def test_response_has_min_applied_field():
    client = _make_client()
    response = client.post(
        "/assignments",
        data={"name": "Test", "lat": 4.71, "lng": -74.07, "radius_km": 8.23},
    )
    assert response.status_code == 200
    assert "min_applied" in response.json()
