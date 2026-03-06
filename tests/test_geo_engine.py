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
    result = engine.calculate_coverage(4.71, -74.07, 4.6)

    assert result["polygon_count"] == 2
    assert result["population_covered"] == 300
    assert abs(result["total_value"] - 2000.0) < 0.01


def test_strtree_initialized(engine):
    """El indice espacial debe estar construido tras la inicializacion exitosa."""
    assert engine._sindex is not None
