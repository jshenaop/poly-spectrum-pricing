import csv
import io
import logging
import os
import re
from datetime import datetime
from contextlib import asynccontextmanager

import folium
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator, model_validator

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
    logger.info("Iniciando GeoEngine...")
    app.state.settings = settings
    app.state.geo_engine = GeoEngine()
    yield
    logger.info("GeoSight cerrando.")


# ---------------------------------------------------------------------------
# Aplicacion
# ---------------------------------------------------------------------------
_env = os.getenv("GEOSIGHT_ENV", "development")
_is_dev = _env.lower() != "production"

app = FastAPI(
    title="GeoSight",
    version="2.1.0",
    description=(
        "Plataforma geoespacial de la ANE para valoración de cobertura "
        "radioeléctrica por polígono. Calcula COP/MHz/Año con fórmula v1.1 "
        "(polígonos completos + parciales ponderados por área). "
        "Soporta múltiples puntos con radio individual y deduplicación."
    ),
    lifespan=lifespan,
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
)

# CORS: allowlist explicita via GEOSIGHT_CORS_ORIGINS (comma-separated)
_cors_raw = os.getenv("GEOSIGHT_CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
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


# Colombia bounding box (EPSG:4686)
_COL_LAT_MIN, _COL_LAT_MAX = -4.23, 13.39
_COL_LNG_MIN, _COL_LNG_MAX = -81.73, -66.87


class PointInput(BaseModel):
    lat: float
    lng: float
    radius_km: float

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not _COL_LAT_MIN <= v <= _COL_LAT_MAX:
            raise ValueError(
                f"Latitud {v} fuera del rango de Colombia ({_COL_LAT_MIN} a {_COL_LAT_MAX})"
            )
        return v

    @field_validator("lng")
    @classmethod
    def validate_lng(cls, v: float) -> float:
        if not _COL_LNG_MIN <= v <= _COL_LNG_MAX:
            raise ValueError(
                f"Longitud {v} fuera del rango de Colombia ({_COL_LNG_MIN} a {_COL_LNG_MAX})"
            )
        return v


class MultiAssignmentRequest(BaseModel):
    points: list[PointInput] = Field(max_length=50)


class MultiAssignmentResponse(BaseModel):
    points_count: int
    raw_total: float
    deduplication_adjustment: float
    total: float
    population_covered: int
    polygon_count: int
    min_applied: bool
    map_html: str
    geojson: dict | None


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


def _build_multi_map(points: list[PointInput], result: dict) -> str:
    """Genera un mapa Folium para multiples puntos con zona de solapamiento."""
    center_lat = sum(p.lat for p in points) / len(points)
    center_lng = sum(p.lng for p in points) / len(points)
    m = folium.Map(location=[center_lat, center_lng], zoom_start=11)

    colors = ["#1B7A4A", "#1A4A7A", "#7A1A4A"]

    for i, pt in enumerate(points):
        color = colors[i % len(colors)]
        folium.Circle(
            location=[pt.lat, pt.lng],
            radius=pt.radius_km * 1000,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.06,
            tooltip=f"Punto {i + 1}: ({pt.lat:.5f}, {pt.lng:.5f}) — {pt.radius_km} km",
        ).add_to(m)
        folium.Marker(
            location=[pt.lat, pt.lng],
            tooltip=f"Punto {i + 1}",
        ).add_to(m)

    if result.get("polygons_geojson"):
        folium.GeoJson(
            result["polygons_geojson"],
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

    if result.get("overlap_geojson"):
        folium.GeoJson(
            result["overlap_geojson"],
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


def _build_overlap_map(
    points: list[PointInput],
    coverage_geojson: dict | None,
    overlap_geojson: dict | None,
) -> str:
    """Genera un mapa Folium para la vista de un proponente en el traslape."""
    center_lat = sum(p.lat for p in points) / len(points)
    center_lng = sum(p.lng for p in points) / len(points)
    m = folium.Map(location=[center_lat, center_lng], zoom_start=12, tiles="cartodbpositron")

    for pt in points:
        folium.Circle(
            location=[pt.lat, pt.lng],
            radius=pt.radius_km * 1000,
            color="#1B7A4A",
            fill=True,
            fill_color="#28A745",
            fill_opacity=0.08,
            tooltip=f"Radio: {pt.radius_km} km",
        ).add_to(m)

    if coverage_geojson:
        folium.GeoJson(
            coverage_geojson,
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

    if overlap_geojson:
        folium.GeoJson(
            overlap_geojson,
            style_function=lambda _: {
                "fillColor": "#555555",
                "color": "#333333",
                "weight": 2,
                "fillOpacity": 0.6,
                "opacity": 0.8,
            },
            tooltip="Zona de traslape",
        ).add_to(m)

    for i, pt in enumerate(points):
        label = f"({pt.lat:.5f}, {pt.lng:.5f})" if len(points) == 1 else f"Punto {i + 1} ({pt.lat:.5f}, {pt.lng:.5f})"
        folium.Marker(
            location=[pt.lat, pt.lng],
            tooltip=label,
        ).add_to(m)

    return m._repr_html_()


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Sirve la interfaz web principal de GeoSight."""
    return templates.TemplateResponse(request, "index.html")


@app.get("/overlap", response_class=HTMLResponse)
def overlap_page(request: Request):
    """Sirve la página de cálculo de traslape entre proponentes."""
    settings = request.app.state.settings
    return templates.TemplateResponse(
        request, "overlap.html", {"max_points": settings.max_points},
    )


def _handle_assignment(
    request: Request,
    lat: float,
    lng: float,
    radius_km: float,
    allowed_radii: list[float] | None = None,
) -> AssignmentResponse:
    """Logica compartida para /assignments (v1) y /v2/assignments."""
    if not _COL_LAT_MIN <= lat <= _COL_LAT_MAX:
        raise ValueError(
            f"Latitud {lat} fuera del rango de Colombia ({_COL_LAT_MIN} a {_COL_LAT_MAX})"
        )
    if not _COL_LNG_MIN <= lng <= _COL_LNG_MAX:
        raise ValueError(
            f"Longitud {lng} fuera del rango de Colombia ({_COL_LNG_MIN} a {_COL_LNG_MAX})"
        )

    engine: GeoEngine = request.app.state.geo_engine
    settings = request.app.state.settings
    result = engine.calculate_coverage(lat, lng, radius_km, allowed_radii=allowed_radii)

    raw = result["total_value"]
    final = max(raw, settings.val_min)
    min_applied = raw < settings.val_min

    return AssignmentResponse(
        value=final,
        population=result["population_covered"],
        map_html=_build_map(lat, lng, radius_km, result.get("polygons_geojson")),
        min_applied=min_applied,
    )


@app.post("/v1/assignments", response_model=AssignmentResponse)
def create_assignment(
    request: Request,
    name: str = Form(default="Sin nombre", max_length=100),
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
    return _handle_assignment(request, lat, lng, radius_km)


def _handle_multi_assignment(
    request: Request,
    body: MultiAssignmentRequest,
    allowed_radii: list[float] | None = None,
) -> MultiAssignmentResponse:
    """Logica compartida para /assignments/multi (v1) y /v2/assignments/multi."""
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
        allowed_radii=allowed_radii,
    )

    map_html = _build_multi_map(body.points, multi)

    return MultiAssignmentResponse(
        points_count=multi["points_count"],
        raw_total=multi["raw_total"],
        deduplication_adjustment=multi["deduplication_adjustment"],
        total=multi["total_value"],
        population_covered=multi["population_covered"],
        polygon_count=multi["polygon_count"],
        min_applied=multi["min_applied"],
        map_html=map_html,
        geojson=multi.get("polygons_geojson"),
    )


@app.post("/v1/assignments/multi", response_model=MultiAssignmentResponse)
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
    return _handle_multi_assignment(request, body)


@app.get("/map", response_class=HTMLResponse)
def get_map(
    lat: float = Query(default=4.71, ge=_COL_LAT_MIN, le=_COL_LAT_MAX),
    lng: float = Query(default=-74.07, ge=_COL_LNG_MIN, le=_COL_LNG_MAX),
    radius_km: float = Query(default=8.2, gt=0, le=40.0),
):
    """Generar mapa Folium con círculo de cobertura sin ejecutar cálculo."""
    return HTMLResponse(_build_map(lat, lng, radius_km))


def _handle_export_csv(
    request: Request,
    name: str,
    lat: float,
    lng: float,
    radius_km: float,
    allowed_radii: list[float] | None = None,
) -> Response:
    """Logica compartida para /export/csv (v1) y /v2/export/csv."""
    if not _COL_LAT_MIN <= lat <= _COL_LAT_MAX:
        raise ValueError(
            f"Latitud {lat} fuera del rango de Colombia ({_COL_LAT_MIN} a {_COL_LAT_MAX})"
        )
    if not _COL_LNG_MIN <= lng <= _COL_LNG_MAX:
        raise ValueError(
            f"Longitud {lng} fuera del rango de Colombia ({_COL_LNG_MIN} a {_COL_LNG_MAX})"
        )

    engine: GeoEngine = request.app.state.geo_engine
    settings = request.app.state.settings
    result = engine.calculate_coverage(lat, lng, radius_km, allowed_radii=allowed_radii)

    raw = result["total_value"]
    final_value = max(raw, settings.val_min)

    _CSV_FORMULA_CHARS = ("=", "+", "-", "@", "\t", "\r")
    safe_name = f"'{name}" if name.startswith(_CSV_FORMULA_CHARS) else name

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["nombre", "lat", "lng", "radio_km", "valor_total_cop", "poblacion"])
    writer.writerow([
        safe_name,
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
            'attachment; filename="{}_export_{}.csv"'.format(
                re.sub(r"[^\w\-]", "_", name)[:64],
                datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
            )
        )},
    )


@app.get("/v1/export/csv")
def export_csv(
    request: Request,
    name: str = Query(default="Sin nombre", max_length=100),
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
    return _handle_export_csv(request, name, lat, lng, radius_km)


# ---------------------------------------------------------------------------
# Rutas V2 — radios actualizados [8.2, 21.9, 35.8]
# ---------------------------------------------------------------------------
_V2_RADII = GeoEngine.VALID_RADII_V2


@app.post("/v2/assignments", response_model=AssignmentResponse)
def create_assignment_v2(
    request: Request,
    name: str = Form(default="Sin nombre", max_length=100),
    lat: float = Form(...),
    lng: float = Form(...),
    radius_km: float = Form(...),
):
    """Calcular cobertura con radios v2 (8.2 / 21.9 / 35.8 km)."""
    return _handle_assignment(request, lat, lng, radius_km, allowed_radii=_V2_RADII)


@app.post("/v2/assignments/multi", response_model=MultiAssignmentResponse)
def create_multi_assignment_v2(request: Request, body: MultiAssignmentRequest):
    """Calcular cobertura multi-punto con radios v2 y deduplicacion."""
    return _handle_multi_assignment(request, body, allowed_radii=_V2_RADII)


@app.get("/v2/export/csv")
def export_csv_v2(
    request: Request,
    name: str = Query(default="Sin nombre", max_length=100),
    lat: float = 4.71,
    lng: float = -74.07,
    radius_km: float = 8.2,
):
    """Exportar resultado CSV con radios v2."""
    return _handle_export_csv(request, name, lat, lng, radius_km, allowed_radii=_V2_RADII)


class CoverageMetrics(BaseModel):
    value: float
    population: int
    polygon_count: int


class ProponentView(BaseModel):
    coverage: CoverageMetrics
    overlap: CoverageMetrics
    map_html: str


class OverlapRequest(BaseModel):
    point_a: PointInput | None = None
    point_b: PointInput | None = None
    points_a: list[PointInput] | None = Field(default=None, max_length=50)
    points_b: list[PointInput] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def resolve_points(self) -> "OverlapRequest":
        for side, singular, plural in [
            ("A", self.point_a, self.points_a),
            ("B", self.point_b, self.points_b),
        ]:
            if singular is not None and plural is not None:
                raise ValueError(
                    f"Proponente {side}: envíe point_{side.lower()} o "
                    f"points_{side.lower()}, no ambos"
                )
            if singular is None and plural is None:
                raise ValueError(
                    f"Proponente {side}: debe enviar point_{side.lower()} o "
                    f"points_{side.lower()}"
                )
            if plural is not None and len(plural) == 0:
                raise ValueError(
                    f"Proponente {side}: la lista de puntos no puede estar vacía"
                )
        if self.point_a is not None:
            self.points_a = [self.point_a]
        if self.point_b is not None:
            self.points_b = [self.point_b]
        return self


class OverlapResponse(BaseModel):
    overlap_exists: bool
    overlap: CoverageMetrics
    view_a: ProponentView
    view_b: ProponentView


@app.post("/v2/overlap", response_model=OverlapResponse)
def calculate_overlap(request: Request, body: OverlapRequest):
    """Calcular el valor del traslape entre dos proponentes.

    Genera dos vistas independientes: cada proponente ve su cobertura
    y la zona de traslape en gris oscuro, sin ver las coordenadas del otro.
    Acepta punto unico (point_a/point_b) o multiples coordenadas
    (points_a/points_b) por proponente.
    """
    engine: GeoEngine = request.app.state.geo_engine
    settings = request.app.state.settings

    for side_label, pts in [("A", body.points_a), ("B", body.points_b)]:
        if len(pts) > settings.max_points:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Proponente {side_label}: máximo {settings.max_points} "
                    f"coordenadas permitidas. Recibidas: {len(pts)}."
                ),
            )

    pts_a_dicts = [p.model_dump() for p in body.points_a]
    pts_b_dicts = [p.model_dump() for p in body.points_b]

    if len(body.points_a) == 1:
        p = body.points_a[0]
        cov_a = engine.calculate_coverage(
            p.lat, p.lng, p.radius_km, allowed_radii=_V2_RADII,
        )
    else:
        multi_a = engine.calculate_multi_coverage(
            pts_a_dicts, val_min=0, allowed_radii=_V2_RADII,
        )
        cov_a = {
            "total_value": multi_a["raw_total"],
            "population_covered": multi_a["population_covered"],
            "polygon_count": multi_a["polygon_count"],
            "polygons_geojson": multi_a.get("polygons_geojson"),
        }

    if len(body.points_b) == 1:
        p = body.points_b[0]
        cov_b = engine.calculate_coverage(
            p.lat, p.lng, p.radius_km, allowed_radii=_V2_RADII,
        )
    else:
        multi_b = engine.calculate_multi_coverage(
            pts_b_dicts, val_min=0, allowed_radii=_V2_RADII,
        )
        cov_b = {
            "total_value": multi_b["raw_total"],
            "population_covered": multi_b["population_covered"],
            "polygon_count": multi_b["polygon_count"],
            "polygons_geojson": multi_b.get("polygons_geojson"),
        }

    overlap = engine.calculate_overlap_coverage(
        pts_a_dicts, pts_b_dicts, allowed_radii=_V2_RADII,
    )

    overlap_value = overlap["value"]
    if overlap["overlap_exists"]:
        overlap_value = max(overlap_value, settings.val_min)

    overlap_metrics = CoverageMetrics(
        value=overlap_value,
        population=overlap["population"],
        polygon_count=overlap["polygon_count"],
    )

    metrics_a = CoverageMetrics(
        value=max(cov_a["total_value"], settings.val_min),
        population=cov_a["population_covered"],
        polygon_count=cov_a["polygon_count"],
    )
    metrics_b = CoverageMetrics(
        value=max(cov_b["total_value"], settings.val_min),
        population=cov_b["population_covered"],
        polygon_count=cov_b["polygon_count"],
    )

    map_a = _build_overlap_map(
        body.points_a,
        cov_a.get("polygons_geojson"),
        overlap.get("overlap_geojson"),
    )
    map_b = _build_overlap_map(
        body.points_b,
        cov_b.get("polygons_geojson"),
        overlap.get("overlap_geojson"),
    )

    return OverlapResponse(
        overlap_exists=overlap["overlap_exists"],
        overlap=overlap_metrics,
        view_a=ProponentView(
            coverage=metrics_a, overlap=overlap_metrics, map_html=map_a,
        ),
        view_b=ProponentView(
            coverage=metrics_b, overlap=overlap_metrics, map_html=map_b,
        ),
    )


class ComparePointInput(BaseModel):
    lat: float
    lng: float
    ring: int  # 1, 2, o 3

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not _COL_LAT_MIN <= v <= _COL_LAT_MAX:
            raise ValueError(
                f"Latitud {v} fuera del rango de Colombia ({_COL_LAT_MIN} a {_COL_LAT_MAX})"
            )
        return v

    @field_validator("lng")
    @classmethod
    def validate_lng(cls, v: float) -> float:
        if not _COL_LNG_MIN <= v <= _COL_LNG_MAX:
            raise ValueError(
                f"Longitud {v} fuera del rango de Colombia ({_COL_LNG_MIN} a {_COL_LNG_MAX})"
            )
        return v

    @field_validator("ring")
    @classmethod
    def validate_ring(cls, v: int) -> int:
        if v not in (1, 2, 3):
            raise ValueError(f"Anillo invalido: {v}. Valores permitidos: 1, 2, 3")
        return v


class CompareRequest(BaseModel):
    points: list[ComparePointInput] = Field(max_length=50)


_RING_TO_V1 = {1: 8.23, 2: 21.94, 3: 35.85}
_RING_TO_V2 = {1: 8.2, 2: 21.9, 3: 35.8}


@app.post("/v2/compare")
def compare_v1_v2(request: Request, body: CompareRequest):
    """Comparar resultados v1 vs v2 para una lista de puntos.

    Recibe puntos con numero de anillo (1, 2, 3) y retorna el calculo
    con radios v1 y v2 lado a lado, incluyendo deltas.
    """
    engine: GeoEngine = request.app.state.geo_engine
    settings = request.app.state.settings

    if len(body.points) > settings.max_points:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Máximo {settings.max_points} puntos permitidos. "
                f"Recibidos: {len(body.points)}."
            ),
        )

    comparisons = []

    for pt in body.points:
        r_v1 = _RING_TO_V1[pt.ring]
        r_v2 = _RING_TO_V2[pt.ring]

        res_v1 = engine.calculate_coverage(pt.lat, pt.lng, r_v1)
        res_v2 = engine.calculate_coverage(pt.lat, pt.lng, r_v2, allowed_radii=_V2_RADII)

        comparisons.append({
            "lat": pt.lat,
            "lng": pt.lng,
            "ring": pt.ring,
            "v1": {
                "radius_km": r_v1,
                "total": res_v1["total_value"],
                "population": res_v1["population_covered"],
                "polygons": res_v1["polygon_count"],
            },
            "v2": {
                "radius_km": r_v2,
                "total": res_v2["total_value"],
                "population": res_v2["population_covered"],
                "polygons": res_v2["polygon_count"],
            },
            "delta_total": res_v2["total_value"] - res_v1["total_value"],
            "delta_population": res_v2["population_covered"] - res_v1["population_covered"],
            "delta_polygons": res_v2["polygon_count"] - res_v1["polygon_count"],
        })

    return {"comparisons": comparisons}


@app.get("/health")
def health(request: Request):
    engine = getattr(request.app.state, "geo_engine", None)
    if engine is None or engine._gdf is None:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "service": "geosight"},
        )
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
