"""Tests basicos para GeoEngine.

Usa el fixture en tests/fixtures/n6_1k_aniop_ipm.geojson (3 poligonos):
  - TEST01: ~1.0 km del punto de prueba, personas=100, cop=10.0  -> dentro del buffer 4.6km
  - TEST02: ~1.6 km del punto de prueba, personas=200, cop=5.0   -> dentro del buffer 4.6km
  - TEST03: ~115 km del punto de prueba, personas=500, cop=20.0  -> fuera del buffer

Punto de prueba: lat=4.71, lng=-74.07
Resultado esperado con radio 4.6km:
  total_value = (100 * 10.0) + (200 * 5.0) = 2000.0
  population_covered = 300
  polygon_count = 2
"""
import pytest
from pathlib import Path

from app.geo_engine import GeoEngine

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def engine(monkeypatch):
    """GeoEngine apuntando al fixture de prueba en lugar de los datos reales."""
    monkeypatch.setenv("GEOSIGHT_DATA_PATH", str(FIXTURES_DIR))
    return GeoEngine()


def test_invalid_radius_raises_value_error(engine):
    """Un radio no permitido debe lanzar ValueError con mensaje descriptivo."""
    with pytest.raises(ValueError, match="Radio invalido"):
        engine.calculate_coverage(4.71, -74.07, 99.0)


def test_calculate_coverage_known_result(engine):
    """El calculo con datos de fixture debe producir el resultado exacto conocido."""
    result = engine.calculate_coverage(4.71, -74.07, 8.23)

    assert result["polygon_count"] == 2
    assert result["population_covered"] == 300
    assert abs(result["total_value"] - 2000.0) < 0.01


def test_strtree_initialized(engine):
    """El indice espacial debe estar construido tras la inicializacion exitosa."""
    assert engine._sindex is not None


def test_custom_grid_data_env_var_loads_correctly(monkeypatch):
    """GEOSIGHT_GRID_DATA con el nombre del fixture debe cargar correctamente."""
    monkeypatch.setenv("GEOSIGHT_DATA_PATH", str(FIXTURES_DIR))
    monkeypatch.setenv("GEOSIGHT_GRID_DATA", "n6_1k_aniop_ipm.geojson")
    eng = GeoEngine()
    assert eng._sindex is not None


def test_missing_grid_file_returns_empty_result(monkeypatch):
    """Un nombre de archivo inexistente no debe lanzar excepcion — retorna ceros."""
    monkeypatch.setenv("GEOSIGHT_DATA_PATH", str(FIXTURES_DIR))
    monkeypatch.setenv("GEOSIGHT_GRID_DATA", "nonexistent_grid.geojson")
    eng = GeoEngine()
    result = eng.calculate_coverage(4.71, -74.07, 8.23)
    assert result["total_value"] == 0.0
    assert result["population_covered"] == 0


# ---------------------------------------------------------------------------
# calculate_multi_coverage
# ---------------------------------------------------------------------------

def test_multi_single_point_matches_single_coverage(engine):
    """Un solo punto en multi debe dar el mismo resultado que calculate_coverage."""
    single = engine.calculate_coverage(4.71, -74.07, 8.23)
    multi = engine.calculate_multi_coverage([
        {"lat": 4.71, "lng": -74.07, "radius_km": 8.23},
    ])
    assert multi["raw_total"] == single["total_value"]
    assert multi["population_covered"] == single["population_covered"]


def test_multi_two_far_points_no_deduplication(engine):
    """Dos puntos sin solapamiento no deben tener ajuste de deduplicacion."""
    multi = engine.calculate_multi_coverage([
        {"lat": 4.71, "lng": -74.07, "radius_km": 8.23},
        {"lat": 4.71, "lng": -73.00, "radius_km": 8.23},
    ])
    assert abs(multi["deduplication_adjustment"]) < 0.01


def test_multi_two_identical_points_fully_deduplicates(engine):
    """Dos puntos identicos deben producir el mismo valor que un solo punto."""
    single = engine.calculate_coverage(4.71, -74.07, 8.23)
    multi = engine.calculate_multi_coverage([
        {"lat": 4.71, "lng": -74.07, "radius_km": 8.23},
        {"lat": 4.71, "lng": -74.07, "radius_km": 8.23},
    ])
    assert abs(multi["raw_total"] - single["total_value"]) < 0.01
    assert multi["deduplication_adjustment"] > 0


def test_multi_overlap_geojson_present_for_two_close_points(engine):
    """Dos puntos muy cercanos deben producir overlap_geojson no nulo."""
    multi = engine.calculate_multi_coverage([
        {"lat": 4.71, "lng": -74.07, "radius_km": 8.23},
        {"lat": 4.715, "lng": -74.075, "radius_km": 8.23},
    ])
    assert multi["overlap_geojson"] is not None


def test_multi_different_radii(engine):
    """Dos puntos con diferentes radios deben calcularse correctamente."""
    multi = engine.calculate_multi_coverage([
        {"lat": 4.71, "lng": -74.07, "radius_km": 8.23},
        {"lat": 4.71, "lng": -74.07, "radius_km": 21.94},
    ])
    # El radio mayor debe cubrir al menos lo mismo que el menor
    single_small = engine.calculate_coverage(4.71, -74.07, 8.23)
    assert multi["raw_total"] >= single_small["total_value"]
