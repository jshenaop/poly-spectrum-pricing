"""Tests para las rutas principales de la aplicación."""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import app

_MOCK_RESULT = {
    "total_value": 5000.0,
    "population_covered": 100,
    "polygon_count": 1,
    "polygons_geojson": None,
}


def _make_client(side_effect=None) -> TestClient:
    mock_engine = MagicMock()
    if side_effect:
        mock_engine.calculate_coverage.side_effect = side_effect
    else:
        mock_engine.calculate_coverage.return_value = _MOCK_RESULT
    app.state.geo_engine = mock_engine
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
