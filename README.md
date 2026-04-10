# GeoSight — Valoración de Espectro por Polígono

<div align="center">

[![Tests](https://github.com/jshenaop/poly-spectrum-pricing/actions/workflows/tests.yml/badge.svg)](https://github.com/jshenaop/poly-spectrum-pricing/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-24+-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![GeoPandas](https://img.shields.io/badge/GeoPandas-1.x-139C5A?logo=pandas&logoColor=white)](https://geopandas.org/)
[![License](https://img.shields.io/badge/Licencia-Privada-red)](#)

**Plataforma geoespacial de la Agencia Nacional del Espectro (ANE) para valoración de cobertura radioeléctrica por polígono.**
Calcula el valor `COP/MHz/Año` sobre polígonos completamente cubiertos por un radio seleccionado y genera mapas interactivos.

[Instalación](#instalación-rápida) · [API](#api-reference) · [Fórmula](#fórmula-de-valoración) · [Multi-PC](#workflow-multi-pc)

</div>

---

## ¿Qué hace GeoSight?

| Función | Descripción |
|:---|:---|
| **Consulta geoespacial** | Calcula el valor de cobertura para un punto y radio dados |
| **Multi-punto** | Hasta 5 coordenadas con radio individual, deduplicación por unión geométrica |
| **Radios de cobertura** | Tres radios seleccionables por punto: 8.23 km · 21.94 km · 35.85 km |
| **Valoración COP/MHz/Año** | `valor = Σ (cop_ipm_mhz_hab_anio × personas_ponderadas)` — polígonos completos al 100%, parciales por área solapada |
| **Mapa interactivo** | Folium con círculos de cobertura, polígonos cubiertos y zona de solapamiento |
| **Exportación CSV** | Reporte con BOM UTF-8 (compatible con Excel en español) |
| **UI institucional** | Interfaz govco Kit UI 9.2 con logos ANE · Responsive (desktop + móvil) |

---

## Stack

```
Backend      →  Python 3.11 + FastAPI 0.115 + Uvicorn
Geoespacial  →  GeoPandas 1.x + Shapely 2.0 (índice STRtree)
Mapas        →  Folium 0.16 (Leaflet.js)
Frontend     →  HTMX 1.9 + Jinja2 + Montserrat (govco Kit UI 9.2)
Datos        →  n6_1k_aniop_ipm.geojson  (local, fuera de Git)
Contenedores →  Docker 24 + Docker Compose v2 + NGINX 1.27
CI/CD        →  GitHub Actions + Trivy (escaneo de vulnerabilidades)
```

---

## Prerrequisitos

```bash
docker --version        # 24.x o superior
docker compose version  # 2.x o superior
git --version           # 2.x o superior
```

---

## Instalación rápida

### 1 — Clonar

```bash
git clone git@github.com:jshenaop/poly-spectrum-pricing.git
cd poly-spectrum-pricing
```

### 2 — Configurar entorno

```bash
cp .env.example .env
# Editar .env: verificar GEOSIGHT_DATA_PATH
```

### 3 — Agregar datos geoespaciales

> Los datos **no están en el repositorio** — viven fuera de Git por seguridad y tamaño.

```bash
mkdir -p app/data
cp /ruta/a/n6_1k_aniop_ipm.geojson app/data/
```

### 4 — Levantar

```bash
docker compose up -d --build
```

### 5 — Verificar

```bash
curl http://localhost/health
# → {"status": "ok", "service": "geosight"}
```

Abre **http://localhost**

---

## Estructura del Proyecto

```
poly-spectrum-pricing/
├── app/
│   ├── main.py              # FastAPI — endpoints, lifespan, GeoEngine singleton
│   ├── geo_engine.py        # Motor de valoración con STRtree
│   ├── config.py            # Settings dataclass + load_settings()
│   ├── data/                # ← GeoJSON aquí  (NO en Git)
│   │   └── n6_1k_aniop_ipm.geojson
│   ├── templates/
│   │   └── index.html       # UI HTMX — govco Kit UI 9.2 — responsive
│   └── static/
│       └── img/             # Logos ANE y gov.co
├── tests/
│   ├── fixtures/
│   │   └── n6_1k_aniop_ipm.geojson  # 3 polígonos de prueba (en Git)
│   ├── test_config.py
│   ├── test_geo_engine.py
│   └── test_routes.py
├── nginx/
│   ├── nginx.conf           # Dev: proxy + static files
│   └── nginx.prod.conf      # Prod: gzip + security headers
├── .github/
│   └── workflows/
│       ├── tests.yml        # CI: build + pytest + cobertura mínima 70%
│       └── security.yml     # Trivy: escaneo semanal de vulnerabilidades
├── .env.example
├── CLAUDE.md                # Memoria del proyecto para Claude Code
├── Dockerfile
├── docker-compose.yml
├── docker-compose.production.yml
└── requirements.txt
```

---

## Variables de Entorno

```bash
GEOSIGHT_ENV=development          # development | production
GEOSIGHT_DATA_PATH=./app/data     # ruta al directorio con el GeoJSON
GEOSIGHT_GRID_DATA=n6_1k_aniop_ipm.geojson  # nombre del archivo GeoJSON (sin ruta)
GEOSIGHT_LOG_LEVEL=INFO           # DEBUG | INFO | WARNING | ERROR
GEOSIGHT_VAL_MIN=0                # valor piso COP/MHz/Año (0 = sin piso)
GEOSIGHT_MAX_POINTS=5             # máximo de coordenadas en /assignments/multi
GEOSIGHT_PORT=8000                # puerto de Uvicorn
```

```bash
# Development  (hot-reload via docker-compose.override.yml)
docker compose up -d --build

# Production  (4 workers, NGINX con gzip y security headers)
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
```

---

## Formato de los Datos

Estructura esperada de `n6_1k_aniop_ipm.geojson`:

```json
{
  "type": "FeatureCollection",
  "crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:EPSG::4686" } },
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Polygon", "coordinates": [[...]] },
      "properties": {
        "cop_ipm_mhz_hab_anio": 12500.50,
        "personas": 45230
      }
    }
  ]
}
```

| Campo | Tipo | Descripción |
|:---|:---:|:---|
| `cop_ipm_mhz_hab_anio` | `float` | Costo en COP · MHz · habitante · año |
| `personas` | `int` | Población del polígono |

**CRS nativo:** EPSG:4686 (MAGNA-SIRGAS geográfico).
**CRS de trabajo:** EPSG:3116 (MAGNA-SIRGAS / Colombia Bogotá, metros) — proyección automática al cargar.

---

## Fórmula de Valoración

```python
# v1.2 — polígonos completos + parciales con ponderación por área + piso mínimo
import math

valor_total = 0
for poligono in candidatos_que_intersectan_circulo:
    if poligono.within(circulo):                          # completamente dentro
        personas_pond = poligono["personas"]
    else:                                                 # intersección parcial
        ratio = poligono.intersection(circulo).area / poligono.area
        personas_pond = math.ceil(ratio * poligono["personas"])
    valor_total += poligono["cop_ipm_mhz_hab_anio"] * personas_pond

# Piso mínimo (GEOSIGHT_VAL_MIN)
valor_final = max(valor_total, VAL_MIN)
```

| Condición | Acción |
|:---|:---|
| Polígono completamente dentro del círculo | 100% de su población |
| Polígono con intersección parcial (borde) | `ceil(área_solapada / área_total × personas)` |
| Solo toca el borde (contacto puntual/lineal) | Contribuye 0 (área de intersección ≈ 0) |
| Completamente fuera | Excluido |
| `valor_total < GEOSIGHT_VAL_MIN` | Se usa `VAL_MIN` como valor final (`min_applied=true`) |

**El resultado es la valoración base. Para obtener el valor total de la licencia:**

```
Valor licencia = valor_total × MHz × años_de_vigencia
```

| Radio | Metros |
|:---:|:---:|
| 8.23 km | 8 230 m |
| 21.94 km | 21 940 m |
| 35.85 km | 35 850 m |

---

## API Reference

Base URL: `http://localhost` (NGINX en puerto 80)

### Endpoints

| Método | Endpoint | Descripción |
|:---:|:---|:---|
| `GET` | `/` | Interfaz web principal |
| `POST` | `/assignments` | Calcular cobertura para un punto — valor, población y mapa |
| `POST` | `/assignments/multi` | Calcular cobertura para múltiples puntos con deduplicación |
| `GET` | `/map` | HTML del mapa Folium para las coordenadas indicadas |
| `GET` | `/export/csv` | Descargar reporte en CSV (UTF-8 BOM para Excel) |
| `GET` | `/health` | Health check |

---

### `POST /assignments`

Calcula la valoración geoespacial para un punto y radio. Acepta `application/x-www-form-urlencoded`.

**Parámetros (form data):**

| Campo | Tipo | Requerido | Descripción |
|:---|:---:|:---:|:---|
| `name` | `string` | ✓ | Nombre del proyecto |
| `lat` | `float` | ✓ | Latitud en grados (EPSG:4686), mínimo 5 decimales |
| `lng` | `float` | ✓ | Longitud en grados (EPSG:4686), mínimo 5 decimales |
| `radius_km` | `float` | ✓ | Radio de cobertura. Valores válidos: `8.23`, `21.94`, `35.85` |

**Ejemplo:**

```bash
curl -X POST http://localhost/assignments \
  -d "name=Zona%20Norte&lat=4.71099&lng=-74.07209&radius_km=8.23"
```

**Respuesta `200 OK`:**

```json
{
  "value": 125430000.50,
  "population": 85420,
  "map_html": "<!DOCTYPE html>...",
  "min_applied": false
}
```

| Campo | Tipo | Descripción |
|:---|:---:|:---|
| `value` | `float` | Valoración base COP/MHz/Año (o piso mínimo si aplica) |
| `population` | `int` | Suma de personas en polígonos cubiertos |
| `map_html` | `string` | HTML completo del mapa Folium (inyectar en `div`) |
| `min_applied` | `bool` | `true` si se aplicó el valor piso (`GEOSIGHT_VAL_MIN`) |

**Errores:**

| Código | Causa |
|:---:|:---|
| `400` | Radio no permitido (`{"error": "Radio invalido: ..."}`) |
| `422` | Parámetro faltante o tipo incorrecto |
| `500` | Error interno del servidor |

---

### `POST /assignments/multi`

Calcula la cobertura para múltiples puntos, cada uno con su propio radio. Los polígonos solapados entre círculos se cuentan exactamente una vez (deduplicación por unión geométrica). Acepta `application/json`.

**Body (JSON):**

```json
{
  "points": [
    {"lat": 4.71099, "lng": -74.07209, "radius_km": 8.23},
    {"lat": 4.72000, "lng": -74.08000, "radius_km": 21.94}
  ]
}
```

| Campo | Tipo | Requerido | Descripción |
|:---|:---:|:---:|:---|
| `points` | `array` | ✓ | Lista de puntos (máximo configurado por `GEOSIGHT_MAX_POINTS`, default 5) |
| `points[].lat` | `float` | ✓ | Latitud (EPSG:4686) |
| `points[].lng` | `float` | ✓ | Longitud (EPSG:4686) |
| `points[].radius_km` | `float` | ✓ | Radio individual. Valores válidos: `8.23`, `21.94`, `35.85` |

**Respuesta `200 OK`:**

```json
{
  "points_count": 2,
  "raw_total": 250860000.00,
  "deduplication_adjustment": 12500.50,
  "total": 250847499.50,
  "population_covered": 170840,
  "polygon_count": 45,
  "min_applied": false,
  "map_html": "<!DOCTYPE html>...",
  "geojson": { "type": "FeatureCollection", "..." }
}
```

| Campo | Tipo | Descripción |
|:---|:---:|:---|
| `points_count` | `int` | Número de puntos procesados |
| `raw_total` | `float` | Suma de valores individuales (antes de deduplicación) |
| `deduplication_adjustment` | `float` | Valor restado por polígonos contados en múltiples círculos |
| `total` | `float` | Valor final COP/MHz/Año (deduplicado, con piso si aplica) |
| `population_covered` | `int` | Personas cubiertas por la unión de todos los círculos |
| `polygon_count` | `int` | Polígonos evaluados en la unión |
| `min_applied` | `bool` | `true` si se aplicó el valor piso |
| `map_html` | `string` | HTML del mapa Folium con todos los círculos y zona de solapamiento |
| `geojson` | `object\|null` | GeoJSON de los polígonos cubiertos |

**Errores:**

| Código | Causa |
|:---:|:---|
| `422` | Número de puntos supera `GEOSIGHT_MAX_POINTS` o parámetros inválidos |
| `400` | Radio no permitido en alguno de los puntos |
| `500` | Error interno del servidor |

---

### `GET /map`

Devuelve el HTML del mapa Folium sin polígonos de resultado (mapa inicial).

| Parámetro | Tipo | Default | Descripción |
|:---|:---:|:---:|:---|
| `lat` | `float` | `4.71` | Latitud central |
| `lng` | `float` | `-74.07` | Longitud central |
| `radius_km` | `float` | `8.23` | Radio del círculo |

```bash
curl "http://localhost/map?lat=4.71099&lng=-74.07209&radius_km=21.94"
```

---

### `GET /export/csv`

Descarga el resultado de cobertura como archivo CSV con BOM UTF-8 (compatible con Excel en español).

| Parámetro | Tipo | Default |
|:---|:---:|:---:|
| `name` | `string` | `"Sin nombre"` |
| `lat` | `float` | `4.71` |
| `lng` | `float` | `-74.07` |
| `radius_km` | `float` | `8.23` |

```bash
curl "http://localhost/export/csv?name=Zona+Norte&lat=4.71099&lng=-74.07209&radius_km=8.23" \
  -o reporte.csv
```

El nombre del archivo descargado incluye un timestamp ISO: `Zona_Norte_export_2026-03-18_14-32-07.csv`

**Columnas del CSV:** `nombre`, `lat`, `lng`, `radio_km`, `valor_total_cop`, `poblacion`

---

### `GET /health`

```bash
curl http://localhost/health
# → {"status": "ok", "service": "geosight"}
```

---

## Tests

```bash
# Todos los tests
docker compose run --rm app pytest tests/ -v

# Con reporte de cobertura
docker compose run --rm app pytest tests/ --cov=app --cov-report=term-missing

# Fallar si cobertura < 70%
docker compose run --rm app pytest tests/ --cov=app --cov-fail-under=70
```

**Cobertura mínima requerida:** 70% — enforced en CI.

**Datos de prueba:** `tests/fixtures/n6_1k_aniop_ipm.geojson` — 3 polígonos cerca de Bogotá con resultado conocido. El fixture usa el mismo nombre del archivo real para que `GEOSIGHT_DATA_PATH=tests/fixtures` funcione sin modificar `GeoEngine`.

---

## Arquitectura de Datos

```
Fuente       →  n6_1k_aniop_ipm.geojson  (local, NO en Git)
Carga        →  Una sola vez al startup (lifespan FastAPI)
Índice       →  STRtree (GeoPandas/Shapely 2) — pre-filtrado rápido
Filtro       →  within() → 100%  |  intersects() → ceil(ratio × personas)
Umbral       →  < 50 000 polígonos: JSON en memoria + STRtree
Migración    →  > 50 000 polígonos: PostGIS en Docker local
```

---

## Workflow Multi-PC

### Cerrar — PC A

```bash
git add -A && git commit -m "wip: [estado actual]" && git push
docker compose down
```

### Abrir — PC B

```bash
git pull --all
docker compose up -d --build
```

Prompt de retoma en Claude Code:
```
Lee el CLAUDE.md y dime en qué estaba trabajando y cuál es el siguiente paso.
```

---

## Contribuir

Flujo de branches:

```
main  (estable, siempre deployable)
  └── develop
        └── feature/*
```

```bash
git checkout -b feature/nombre develop
# ... cambios ...
pytest tests/ --cov=app --cov-fail-under=70
# PR hacia develop
```

---

<div align="center">
<sub>GeoSight V1.2 · Agencia Nacional del Espectro · República de Colombia · Built with <a href="https://docs.anthropic.com/claude-code">Claude Code</a></sub>
</div>
