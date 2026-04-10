"""Tests para el endpoint GET /export/csv."""
import csv
import io
import re
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.config import Settings

# Resultado fijo que devuelve el mock del GeoEngine
_MOCK_RESULT = {"total_value": 1234.56, "population_covered": 300, "polygon_count": 2}

_DEFAULT_SETTINGS = Settings(
    grid_data="n6_1k_aniop_ipm.geojson",
    data_path=Path("./tests/fixtures"),
    val_min=0,
    max_points=5,
    log_level="INFO",
    env="test",
)


def _make_client() -> TestClient:
    """Crea un TestClient con GeoEngine mockeado para no cargar el GeoJSON real."""
    mock_engine = MagicMock()
    mock_engine.calculate_coverage.return_value = _MOCK_RESULT
    app.state.geo_engine = mock_engine
    app.state.settings = _DEFAULT_SETTINGS
    return TestClient(app, raise_server_exceptions=False)


def test_export_csv_encoding_utf8_sig():
    """El contenido debe comenzar con BOM UTF-8 (\\ufeff) para compatibilidad con Excel."""
    client = _make_client()
    response = client.get("/export/csv?name=Test&lat=4.71&lng=-74.07&radius_km=8.23")
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf"), (
        "El CSV debe empezar con BOM UTF-8 (\\ufeff / EF BB BF)"
    )


def test_export_csv_columns():
    """El CSV debe contener exactamente las columnas requeridas."""
    client = _make_client()
    response = client.get("/export/csv?name=Proyecto&lat=4.71&lng=-74.07&radius_km=8.23")
    assert response.status_code == 200

    # Decodificar omitiendo el BOM
    text = response.content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    columnas_esperadas = {"nombre", "lat", "lng", "radio_km", "valor_total_cop", "poblacion"}
    assert set(reader.fieldnames) == columnas_esperadas


def test_export_csv_content_disposition():
    """El header Content-Disposition debe indicar descarga con filename timestamped."""
    client = _make_client()
    response = client.get("/export/csv?name=Mi%20Proyecto")
    assert response.status_code == 200
    cd = response.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert re.search(
        r'filename=".+_export_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.csv"', cd
    ), f"Filename no tiene formato esperado: {cd}"
