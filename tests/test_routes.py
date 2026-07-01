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
    response = client.get("/map?lat=4.71&lng=-74.07&radius_km=8.2")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_create_assignment():
    client = _make_client()
    response = client.post(
        "/v1/assignments",
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
        "/v1/assignments",
        data={"name": "Test", "lat": 4.71, "lng": -74.07, "radius_km": 99.0},
    )
    assert response.status_code == 400
    assert "error" in response.json()


def test_unexpected_exception_returns_500():
    client = _make_client(side_effect=RuntimeError("fallo inesperado"))
    response = client.post(
        "/v1/assignments",
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
        "/v1/assignments",
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
        "/v1/assignments",
        data={"name": "Test", "lat": 4.71, "lng": -74.07, "radius_km": 8.23},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == 1_000_000
    assert data["min_applied"] is True


def test_response_has_min_applied_field():
    client = _make_client()
    response = client.post(
        "/v1/assignments",
        data={"name": "Test", "lat": 4.71, "lng": -74.07, "radius_km": 8.23},
    )
    assert response.status_code == 200
    assert "min_applied" in response.json()


# ---------------------------------------------------------------------------
# POST /assignments/multi
# ---------------------------------------------------------------------------

_MOCK_MULTI_RESULT = {
    "points_count": 2,
    "raw_total": 2000.0,
    "total_value": 2000.0,
    "population_covered": 300,
    "polygon_count": 2,
    "min_applied": False,
    "deduplication_adjustment": 0.0,
    "polygons_geojson": None,
    "overlap_geojson": None,
}


def _make_multi_client(max_points=5):
    mock_engine = MagicMock()
    mock_engine.calculate_coverage.return_value = _MOCK_RESULT
    mock_engine.calculate_multi_coverage.return_value = _MOCK_MULTI_RESULT
    settings = Settings(
        grid_data="n6_1k_aniop_ipm.geojson",
        data_path=Path("./tests/fixtures"),
        val_min=0,
        max_points=max_points,
        log_level="INFO",
        env="test",
    )
    app.state.geo_engine = mock_engine
    app.state.settings = settings
    return TestClient(app, raise_server_exceptions=False)


def test_multi_assignment_two_points_returns_200():
    client = _make_multi_client()
    response = client.post(
        "/v1/assignments/multi",
        json={"points": [
            {"lat": 4.71, "lng": -74.07, "radius_km": 8.23},
            {"lat": 4.72, "lng": -74.08, "radius_km": 21.94},
        ]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["points_count"] == 2
    assert "map_html" in data
    assert "total" in data
    assert data["population_covered"] == 300
    assert data["polygon_count"] == 2


def test_multi_assignment_exceeds_max_points_returns_422():
    client = _make_multi_client(max_points=5)
    points = [{"lat": 4.71 + i * 0.01, "lng": -74.07, "radius_km": 8.23} for i in range(6)]
    response = client.post("/v1/assignments/multi", json={"points": points})
    assert response.status_code == 422


def test_422_message_contains_configured_limit():
    client = _make_multi_client(max_points=3)
    points = [{"lat": 4.71 + i * 0.01, "lng": -74.07, "radius_km": 8.23} for i in range(4)]
    response = client.post("/v1/assignments/multi", json={"points": points})
    assert response.status_code == 422
    assert "3" in response.json()["detail"]


def test_single_point_endpoint_unchanged():
    client = _make_multi_client()
    response = client.post(
        "/v1/assignments",
        data={"name": "Test", "lat": 4.71, "lng": -74.07, "radius_km": 8.23},
    )
    assert response.status_code == 200
    assert response.json()["value"] == 5000.0


def test_multi_accepts_json_content_type():
    client = _make_multi_client()
    response = client.post(
        "/v1/assignments/multi",
        json={"points": [{"lat": 4.71, "lng": -74.07, "radius_km": 8.23}]},
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# V2 Endpoints
# ---------------------------------------------------------------------------

def test_v2_assignment_returns_200():
    client = _make_client()
    response = client.post(
        "/v2/assignments",
        data={"name": "Test V2", "lat": 4.71, "lng": -74.07, "radius_km": 8.2},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == 5000.0
    assert "map_html" in data


def test_v2_assignment_passes_allowed_radii():
    """V2 endpoint debe pasar allowed_radii al engine."""
    from unittest.mock import call
    mock_engine = MagicMock()
    mock_engine.calculate_coverage.return_value = _MOCK_RESULT
    app.state.geo_engine = mock_engine
    app.state.settings = _DEFAULT_SETTINGS
    client = TestClient(app, raise_server_exceptions=False)

    client.post(
        "/v2/assignments",
        data={"name": "Test", "lat": 4.71, "lng": -74.07, "radius_km": 8.2},
    )
    _, kwargs = mock_engine.calculate_coverage.call_args
    assert kwargs["allowed_radii"] == [8.2, 21.9, 35.8]


def test_v2_multi_assignment_returns_200():
    client = _make_multi_client()
    response = client.post(
        "/v2/assignments/multi",
        json={"points": [
            {"lat": 4.71, "lng": -74.07, "radius_km": 8.2},
            {"lat": 4.72, "lng": -74.08, "radius_km": 21.9},
        ]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["points_count"] == 2


def test_v2_multi_passes_allowed_radii():
    """V2 multi endpoint debe pasar allowed_radii al engine."""
    mock_engine = MagicMock()
    mock_engine.calculate_multi_coverage.return_value = _MOCK_MULTI_RESULT
    app.state.geo_engine = mock_engine
    app.state.settings = _DEFAULT_SETTINGS
    client = TestClient(app, raise_server_exceptions=False)

    client.post(
        "/v2/assignments/multi",
        json={"points": [{"lat": 4.71, "lng": -74.07, "radius_km": 8.2}]},
    )
    _, kwargs = mock_engine.calculate_multi_coverage.call_args
    assert kwargs["allowed_radii"] == [8.2, 21.9, 35.8]


def test_v1_assignment_still_works():
    """V1 endpoint debe seguir funcionando sin cambios (regresion)."""
    client = _make_client()
    response = client.post(
        "/v1/assignments",
        data={"name": "Test", "lat": 4.71, "lng": -74.07, "radius_km": 8.23},
    )
    assert response.status_code == 200
    assert response.json()["value"] == 5000.0


def test_v2_export_csv_returns_200():
    client = _make_client()
    response = client.get("/v2/export/csv?name=Test&lat=4.71&lng=-74.07&radius_km=8.2")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]


def test_v2_compare_returns_comparisons():
    """El endpoint /v2/compare debe retornar comparaciones v1 vs v2."""
    mock_engine = MagicMock()
    mock_engine.calculate_coverage.return_value = _MOCK_RESULT
    app.state.geo_engine = mock_engine
    app.state.settings = _DEFAULT_SETTINGS
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/v2/compare",
        json={"points": [{"lat": 4.71, "lng": -74.07, "ring": 1}]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "comparisons" in data
    assert len(data["comparisons"]) == 1
    comp = data["comparisons"][0]
    assert comp["v1"]["radius_km"] == 8.23
    assert comp["v2"]["radius_km"] == 8.2
    assert "delta_total" in comp
    assert "delta_population" in comp


# ---------------------------------------------------------------------------
# POST /v2/overlap
# ---------------------------------------------------------------------------

_MOCK_OVERLAP_RESULT = {
    "overlap_exists": True,
    "value": 1500.0,
    "population": 80,
    "polygon_count": 1,
    "overlap_geojson": None,
    "polygons_in_overlap": None,
}

_MOCK_OVERLAP_EMPTY = {
    "overlap_exists": False,
    "value": 0.0,
    "population": 0,
    "polygon_count": 0,
    "overlap_geojson": None,
    "polygons_in_overlap": None,
}


def _make_overlap_client(overlap_result=None, settings=None):
    mock_engine = MagicMock()
    mock_engine.calculate_coverage.return_value = _MOCK_RESULT
    mock_engine.calculate_overlap_coverage.return_value = (
        overlap_result or _MOCK_OVERLAP_RESULT
    )
    app.state.geo_engine = mock_engine
    app.state.settings = settings if settings is not None else _DEFAULT_SETTINGS
    return TestClient(app, raise_server_exceptions=False)


def test_overlap_returns_200():
    """Request valido retorna 200 con estructura completa."""
    client = _make_overlap_client()
    response = client.post("/v2/overlap", json={
        "point_a": {"lat": 5.73, "lng": -73.05, "radius_km": 8.2},
        "point_b": {"lat": 5.77, "lng": -73.02, "radius_km": 8.2},
    })
    assert response.status_code == 200
    data = response.json()
    assert data["overlap_exists"] is True
    assert "overlap" in data
    assert "view_a" in data
    assert "view_b" in data
    assert data["overlap"]["value"] == 1500.0
    assert data["overlap"]["population"] == 80


def test_overlap_no_intersection_returns_false():
    """Puntos lejanos retornan overlap_exists=false."""
    client = _make_overlap_client(overlap_result=_MOCK_OVERLAP_EMPTY)
    response = client.post("/v2/overlap", json={
        "point_a": {"lat": 4.71, "lng": -74.07, "radius_km": 8.2},
        "point_b": {"lat": 10.0, "lng": -75.0, "radius_km": 8.2},
    })
    assert response.status_code == 200
    data = response.json()
    assert data["overlap_exists"] is False
    assert data["overlap"]["value"] == 0.0


def test_overlap_views_have_map_html():
    """Ambas vistas incluyen map_html."""
    client = _make_overlap_client()
    response = client.post("/v2/overlap", json={
        "point_a": {"lat": 5.73, "lng": -73.05, "radius_km": 8.2},
        "point_b": {"lat": 5.77, "lng": -73.02, "radius_km": 8.2},
    })
    data = response.json()
    assert "map_html" in data["view_a"]
    assert "map_html" in data["view_b"]
    assert len(data["view_a"]["map_html"]) > 0
    assert len(data["view_b"]["map_html"]) > 0


def test_overlap_validates_bounds():
    """Lat/lng fuera de Colombia retorna 422."""
    client = _make_overlap_client()
    response = client.post("/v2/overlap", json={
        "point_a": {"lat": 50.0, "lng": -74.07, "radius_km": 8.2},
        "point_b": {"lat": 5.77, "lng": -73.02, "radius_km": 8.2},
    })
    assert response.status_code == 422


def test_overlap_rejects_invalid_radius():
    """Radio no v2 retorna 400 via ValueError del engine."""
    client = _make_overlap_client()
    mock_engine = app.state.geo_engine
    mock_engine.calculate_coverage.side_effect = ValueError("Radio invalido: 99.0 km")
    response = client.post("/v2/overlap", json={
        "point_a": {"lat": 5.73, "lng": -73.05, "radius_km": 99.0},
        "point_b": {"lat": 5.77, "lng": -73.02, "radius_km": 8.2},
    })
    assert response.status_code == 400
    assert "Radio invalido" in response.json()["error"]


# ---------------------------------------------------------------------------
# POST /v2/overlap — Multi-coordenada
# ---------------------------------------------------------------------------

_MOCK_MULTI_COV_RESULT = {
    "points_count": 2,
    "raw_total": 8000.0,
    "total_value": 8000.0,
    "population_covered": 200,
    "polygon_count": 2,
    "min_applied": False,
    "deduplication_adjustment": 0.0,
    "polygons_geojson": None,
    "overlap_geojson": None,
}


def _make_overlap_multi_client(overlap_result=None, settings=None):
    mock_engine = MagicMock()
    mock_engine.calculate_coverage.return_value = _MOCK_RESULT
    mock_engine.calculate_multi_coverage.return_value = _MOCK_MULTI_COV_RESULT
    mock_engine.calculate_overlap_coverage.return_value = (
        overlap_result or _MOCK_OVERLAP_RESULT
    )
    app.state.geo_engine = mock_engine
    app.state.settings = settings if settings is not None else _DEFAULT_SETTINGS
    return TestClient(app, raise_server_exceptions=False)


def test_overlap_multi_format_returns_200():
    """Request con points_a/points_b retorna 200."""
    client = _make_overlap_multi_client()
    response = client.post("/v2/overlap", json={
        "points_a": [
            {"lat": 5.73, "lng": -73.05, "radius_km": 8.2},
            {"lat": 5.74, "lng": -73.06, "radius_km": 21.9},
        ],
        "points_b": [
            {"lat": 5.77, "lng": -73.02, "radius_km": 8.2},
        ],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["overlap_exists"] is True
    assert "view_a" in data
    assert "view_b" in data


def test_overlap_legacy_format_still_works():
    """Request con point_a/point_b sigue funcionando."""
    client = _make_overlap_multi_client()
    response = client.post("/v2/overlap", json={
        "point_a": {"lat": 5.73, "lng": -73.05, "radius_km": 8.2},
        "point_b": {"lat": 5.77, "lng": -73.02, "radius_km": 8.2},
    })
    assert response.status_code == 200
    data = response.json()
    assert data["overlap_exists"] is True


def test_overlap_mixed_format_rejected():
    """Enviar point_a + points_a juntos retorna 422."""
    client = _make_overlap_multi_client()
    response = client.post("/v2/overlap", json={
        "point_a": {"lat": 5.73, "lng": -73.05, "radius_km": 8.2},
        "points_a": [{"lat": 5.74, "lng": -73.06, "radius_km": 8.2}],
        "point_b": {"lat": 5.77, "lng": -73.02, "radius_km": 8.2},
    })
    assert response.status_code == 422


def test_overlap_missing_proponent_rejected():
    """Omitir uno de los proponentes retorna 422."""
    client = _make_overlap_multi_client()
    response = client.post("/v2/overlap", json={
        "point_a": {"lat": 5.73, "lng": -73.05, "radius_km": 8.2},
    })
    assert response.status_code == 422


def test_overlap_exceeds_max_points():
    """Mas de MAX_POINTS por proponente retorna 422."""
    settings = Settings(
        grid_data="n6_1k_aniop_ipm.geojson",
        data_path=Path("./tests/fixtures"),
        val_min=0,
        max_points=2,
        log_level="INFO",
        env="test",
    )
    client = _make_overlap_multi_client(settings=settings)
    response = client.post("/v2/overlap", json={
        "points_a": [
            {"lat": 5.73, "lng": -73.05, "radius_km": 8.2},
            {"lat": 5.74, "lng": -73.06, "radius_km": 8.2},
            {"lat": 5.75, "lng": -73.07, "radius_km": 8.2},
        ],
        "points_b": [{"lat": 5.77, "lng": -73.02, "radius_km": 8.2}],
    })
    assert response.status_code == 422


def test_overlap_multi_views_have_map_html():
    """Ambas vistas incluyen map_html con multi-puntos."""
    client = _make_overlap_multi_client()
    response = client.post("/v2/overlap", json={
        "points_a": [
            {"lat": 5.73, "lng": -73.05, "radius_km": 8.2},
            {"lat": 5.74, "lng": -73.06, "radius_km": 8.2},
        ],
        "points_b": [{"lat": 5.77, "lng": -73.02, "radius_km": 8.2}],
    })
    data = response.json()
    assert "map_html" in data["view_a"]
    assert "map_html" in data["view_b"]
    assert len(data["view_a"]["map_html"]) > 0


def test_overlap_empty_points_list_rejected():
    """Lista vacia points_a: [] retorna 422."""
    client = _make_overlap_multi_client()
    response = client.post("/v2/overlap", json={
        "points_a": [],
        "points_b": [{"lat": 5.77, "lng": -73.02, "radius_km": 8.2}],
    })
    assert response.status_code == 422
