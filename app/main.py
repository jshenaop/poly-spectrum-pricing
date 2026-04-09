import csv
import io
import logging
import os
from datetime import datetime
from contextlib import asynccontextmanager

import folium
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.geo_engine import GeoEngine
from app import config

# ---------------------------------------------------------------------------
# Logging — nivel configurable via GEOSIGHT_LOG_LEVEL
# Solo app.* en el nivel configurado; librerias de terceros en WARNING
# para evitar que fiona/geopandas inunden los logs en nivel DEBUG.
# ---------------------------------------------------------------------------
_log_level = os.getenv("GEOSIGHT_LOG_LEVEL", "INFO").upper()
_fmt = "%(asctime)s %(levelname)s %(name)s — %(message)s"
logging.basicConfig(level=logging.WARNING, format=_fmt)
logging.getLogger("app").setLevel(getattr(logging, _log_level, logging.INFO))
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan: GeoEngine se instancia UNA sola vez al arrancar
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = config.load_settings()
    geojson_path = settings.data_path / settings.grid_data
    config.validate_geojson_file(geojson_path)
    logger.info("Iniciando GeoEngine...")
    app.state.settings = settings
    app.state.geo_engine = GeoEngine()
    yield
    logger.info("GeoSight cerrando.")


# ---------------------------------------------------------------------------
# Aplicacion
# ---------------------------------------------------------------------------
_env = os.getenv("GEOSIGHT_ENV", "development")

app = FastAPI(
    title="GeoSight",
    version="1.2.0",
    description=(
        "Plataforma geoespacial de la ANE para valoración de cobertura "
        "radioeléctrica por polígono. Calcula COP/MHz/Año con fórmula v1.1 "
        "(polígonos completos + parciales ponderados por área)."
    ),
    lifespan=lifespan,
)

# CORS: permisivo en development, sin wildcards en production
_cors_origins = ["*"] if _env != "production" else []
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Archivos estaticos y templates
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ---------------------------------------------------------------------------
# Schemas Pydantic v2
# ---------------------------------------------------------------------------

class AssignmentResponse(BaseModel):
    value: float
    population: int
    map_html: str
    min_applied: bool = False


class PointInput(BaseModel):
    lat: float
    lng: float


class MultiAssignmentRequest(BaseModel):
    points: list[PointInput]


class MultiAssignmentResponse(BaseModel):
    points_count: int
    raw_total: float
    deduplication_adjustment: float
    total: float
    min_applied: bool
    map_html: str
    geojson: dict | None
    results: list[dict]


# ---------------------------------------------------------------------------
# Utilidad de mapa Folium
# ---------------------------------------------------------------------------
def _build_map(lat: float, lng: float, radius_km: float, polygons_geojson=None) -> str:
    """Genera un mapa Folium con el circulo de cobertura y retorna su HTML."""
    m = folium.Map(location=[lat, lng], zoom_start=12)

    # Círculo al fondo (se agrega primero → queda debajo)
    folium.Circle(
        location=[lat, lng],
        radius=radius_km * 1000,
        color="#1B7A4A",
        fill=True,
        fill_color="#28A745",
        fill_opacity=0.08,
        tooltip=f"Radio: {radius_km} km",
    ).add_to(m)

    # Polígonos encima del círculo (se agregan después → reciben el tooltip)
    if polygons_geojson:
        folium.GeoJson(
            polygons_geojson,
            style_function=lambda feature: {
                "fillColor": "#28A745",
                "color": "#1B7A4A",
                "weight": 1,
                "fillOpacity": 0.5 if feature["properties"].get("is_partial") else 0.25,
                "opacity": 0.5,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["personas", "cop_ipm_mhz_hab_anio"],
                aliases=["Personas:", "COP/MHz/Año:"],
                localize=True,
            ),
        ).add_to(m)
    folium.Marker(
        location=[lat, lng],
        tooltip=f"({lat:.5f}, {lng:.5f})",
    ).add_to(m)
    return m._repr_html_()


def _build_multi_map(points: list[PointInput], radius_result: dict) -> str:
    """Genera un mapa Folium para multiples puntos con zona de solapamiento."""
    center_lat = sum(p.lat for p in points) / len(points)
    center_lng = sum(p.lng for p in points) / len(points)
    m = folium.Map(location=[center_lat, center_lng], zoom_start=11)

    radius_km = radius_result["radius_km"]
    colors = ["#1B7A4A", "#1A4A7A", "#7A1A4A"]

    for i, pt in enumerate(points):
        color = colors[i % len(colors)]
        folium.Circle(
            location=[pt.lat, pt.lng],
            radius=radius_km * 1000,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.06,
            tooltip=f"Punto {i + 1}: ({pt.lat:.5f}, {pt.lng:.5f})",
        ).add_to(m)
        folium.Marker(
            location=[pt.lat, pt.lng],
            tooltip=f"Punto {i + 1}",
        ).add_to(m)

    if radius_result.get("polygons_geojson"):
        folium.GeoJson(
            radius_result["polygons_geojson"],
            style_function=lambda feature: {
                "fillColor": "#28A745",
                "color": "#1B7A4A",
                "weight": 1,
                "fillOpacity": 0.5 if feature["properties"].get("is_partial") else 0.25,
                "opacity": 0.5,
            },
        ).add_to(m)

    if radius_result.get("overlap_geojson"):
        folium.GeoJson(
            radius_result["overlap_geojson"],
            style_function=lambda _: {
                "fillColor": "#800080",
                "color": "#800080",
                "weight": 1,
                "fillOpacity": 0.25,
                "opacity": 0.6,
            },
            tooltip="Zona de solapamiento",
        ).add_to(m)

    return m._repr_html_()


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Sirve la interfaz web principal de GeoSight.

    Retorna la página HTML construida con HTMX + Jinja2 (govco Kit UI 9.2).
    Incluye formulario de consulta, mapa Folium embebido en iframe y cards
    de resultado que se actualizan sin recarga de página.

    Args:
        request: Objeto Request de FastAPI (requerido por Jinja2).

    Returns:
        HTMLResponse con el contenido de app/templates/index.html.
    """
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/assignments", response_model=AssignmentResponse)
def create_assignment(
    request: Request,
    name: str = Form(...),
    lat: float = Form(...),
    lng: float = Form(...),
    radius_km: float = Form(...),
):
    """Calcular la cobertura geoespacial para un punto y radio dados.

    Proyecta el punto (lat/lng EPSG:4686) a EPSG:3116, construye un buffer
    circular y evalúa todos los polígonos del dataset usando el índice STRtree.

    Fórmula v1.1:
        - Polígono completamente dentro → 100 % de personas.
        - Polígono parcial → ceil(área_solapada / área_total × personas).

    Args:
        request: Objeto Request de FastAPI.
        name: Nombre del proyecto o asignación.
        lat: Latitud en grados decimales (EPSG:4686). Mínimo 5 decimales.
        lng: Longitud en grados decimales (EPSG:4686). Mínimo 5 decimales.
        radius_km: Radio de cobertura. Valores válidos: 8.23, 21.94, 35.85.

    Returns:
        AssignmentResponse con value (COP/MHz/Año), population (personas
        cubiertas), map_html (HTML del mapa Folium) y min_applied.

    Raises:
        ValueError: Si radius_km no es uno de los radios permitidos → HTTP 400.
        Exception: Cualquier error inesperado → HTTP 500.
    """
    engine: GeoEngine = request.app.state.geo_engine
    settings = request.app.state.settings
    result = engine.calculate_coverage(lat, lng, radius_km)

    raw = result["total_value"]
    final = max(raw, settings.val_min)
    min_applied = raw < settings.val_min

    return AssignmentResponse(
        value=final,
        population=result["population_covered"],
        map_html=_build_map(lat, lng, radius_km, result.get("polygons_geojson")),
        min_applied=min_applied,
    )


@app.post("/assignments/multi", response_model=MultiAssignmentResponse)
def create_multi_assignment(request: Request, body: MultiAssignmentRequest):
    """Calcular cobertura para multiples puntos con deduplicacion por union.

    Todos los radios (8.23 / 21.94 / 35.85 km) se calculan siempre.
    Los poligonos solapados entre circulos se cuentan exactamente una vez.

    Args:
        request: Objeto Request de FastAPI.
        body: JSON con lista de puntos {lat, lng}.

    Returns:
        MultiAssignmentResponse con totales, ajuste de deduplicacion y mapa.

    Raises:
        HTTPException 422: Si el numero de puntos supera GEOSIGHT_MAX_POINTS.
    """
    settings = request.app.state.settings
    if len(body.points) > settings.max_points:
        raise HTTPException(
            status_code=422,
            detail=(
                f"El número máximo de coordenadas a procesar en una salida es de "
                f"{settings.max_points}. La solicitud supera el límite de procesamiento."
            ),
        )

    engine: GeoEngine = request.app.state.geo_engine
    multi = engine.calculate_multi_coverage(
        points=[p.model_dump() for p in body.points],
        val_min=settings.val_min,
    )

    # Aggregate across all radii for the summary totals
    raw_total = sum(r["raw_total"] for r in multi["results_by_radius"])
    dedup_adj = sum(r["deduplication_adjustment"] for r in multi["results_by_radius"])
    total = sum(r["total_value"] for r in multi["results_by_radius"])
    any_min = any(r["min_applied"] for r in multi["results_by_radius"])

    # Build map using the smallest radius result that has polygon data
    map_result = next(
        (r for r in multi["results_by_radius"] if r["polygons_geojson"]),
        multi["results_by_radius"][0],
    )
    map_html = _build_multi_map(body.points, map_result)

    # Combine geojson from all radii
    combined_geojson = map_result.get("polygons_geojson")

    return MultiAssignmentResponse(
        points_count=multi["points_count"],
        raw_total=raw_total,
        deduplication_adjustment=dedup_adj,
        total=total,
        min_applied=any_min,
        map_html=map_html,
        geojson=combined_geojson,
        results=multi["results_by_radius"],
    )


@app.get("/map", response_class=HTMLResponse)
def get_map(lat: float = 4.71, lng: float = -74.07, radius_km: float = 8.23):
    """Generar mapa Folium con círculo de cobertura sin ejecutar cálculo.

    Útil para previsualizar el área de cobertura antes de enviar el formulario.
    No consulta el GeoEngine ni los datos geoespaciales.

    Args:
        lat: Latitud central en grados decimales. Default: 4.71 (Bogotá).
        lng: Longitud central en grados decimales. Default: -74.07 (Bogotá).
        radius_km: Radio del círculo a dibujar. Default: 8.23.

    Returns:
        HTMLResponse con el HTML completo del mapa Folium (Leaflet.js).
    """
    return HTMLResponse(_build_map(lat, lng, radius_km))


@app.get("/export/csv")
def export_csv(
    request: Request,
    name: str = "Sin nombre",
    lat: float = 4.71,
    lng: float = -74.07,
    radius_km: float = 8.23,
):
    """Exportar resultado de cobertura como archivo CSV descargable.

    Ejecuta el cálculo de cobertura y retorna el resultado en formato CSV.
    El archivo incluye BOM UTF-8 (\\ufeff) para compatibilidad con Excel en
    español (evita problemas de codificación con tildes y ñ).

    Nombre del archivo: ``{nombre}_export_YYYY-MM-DD_HH-MM-SS.csv``

    Columnas CSV: ``nombre``, ``lat``, ``lng``, ``radio_km``,
    ``valor_total_cop``, ``poblacion``.

    Args:
        request: Objeto Request de FastAPI.
        name: Nombre del proyecto. Los espacios se reemplazan por ``_`` en el
            nombre del archivo descargado.
        lat: Latitud central en grados decimales. Default: 4.71.
        lng: Longitud central en grados decimales. Default: -74.07.
        radius_km: Radio de cobertura. Valores válidos: 8.23, 21.94, 35.85.

    Returns:
        Response con Content-Type ``text/csv; charset=utf-8-sig`` y header
        ``Content-Disposition: attachment`` para descarga directa.

    Raises:
        ValueError: Si radius_km no es válido → HTTP 400.
    """
    engine: GeoEngine = request.app.state.geo_engine
    settings = request.app.state.settings
    result = engine.calculate_coverage(lat, lng, radius_km)

    raw = result["total_value"]
    final_value = max(raw, settings.val_min)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["nombre", "lat", "lng", "radio_km", "valor_total_cop", "poblacion"])
    writer.writerow([
        name,
        lat,
        lng,
        radius_km,
        final_value,
        result["population_covered"],
    ])

    # \ufeff = BOM UTF-8 — Excel en español lo necesita para abrir correctamente
    content = "\ufeff" + buf.getvalue()

    return Response(
        content=content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": (
            f'attachment; filename="{name.replace(" ", "_").replace("/", "-")}'
            f'_export_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.csv"'
        )},
    )


@app.get("/health")
def health():
    """Verificar el estado operativo del servicio.

    Endpoint de health check para monitoreo, Docker healthcheck y
    load balancers. Retorna 200 OK si el proceso está en ejecución.
    No verifica el estado del GeoEngine ni la disponibilidad del GeoJSON.

    Returns:
        JSON con ``{"status": "ok", "service": "geosight"}``.
    """
    return {"status": "ok", "service": "geosight"}


# ---------------------------------------------------------------------------
# Manejadores de errores
# ---------------------------------------------------------------------------
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.warning("Peticion invalida: %s", exc)
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception):
    logger.error("Error inesperado: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500, content={"error": "Error interno del servidor"}
    )
