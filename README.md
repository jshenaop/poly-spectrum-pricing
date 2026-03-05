# GeoSight Platform — Polygon Spectrum Pricing

<div align="center">

[![Tests](https://github.com/jshenaop/poly-spectrum-pricing/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/jshenaop/poly-spectrum-pricing/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-24+-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![GeoPandas](https://img.shields.io/badge/GeoPandas-0.14-139C5A?logo=pandas&logoColor=white)](https://geopandas.org/)
[![Claude Code](https://img.shields.io/badge/Claude_Code-AI_Dev-D97706?logo=anthropic&logoColor=white)](https://docs.anthropic.com/claude-code)
[![Coverage](https://img.shields.io/badge/coverage-70%25_min-brightgreen)](https://github.com/jshenaop/poly-spectrum-pricing/actions)
[![License](https://img.shields.io/badge/License-Private-red)](#)

**Plataforma de análisis geoespacial para visualización de cobertura y valoración por área.**  
Consulta polígonos colombianos, calcula valoración por intersección y genera mapas interactivos.

[Instalación](#instalación-rápida) · [API](#api-reference) · [Multi-PC](#workflow-multi-pc) · [Claude Code](#desarrollo-con-claude-code)

</div>

---

## ¿Qué hace GeoSight?

| Función | Descripción |
|:---|:---|
| 🗺️ **Visualización interactiva** | Mapas Folium con círculos de cobertura sobre cartografía oscura |
| 📐 **Radios de cobertura** | Tres radios seleccionables: 4.6 km · 12.02 km · 19.64 km |
| 💰 **Valoración geoespacial** | `valor = Σ (cop_ipm_mhz_hab_anio × personas)` por polígono intersectado |
| 📊 **Reporte ejecutivo** | Costo Total (COP) y Población Cubierta por asignación |
| 📥 **Exportación** | Mapa como HTML embebible · Reporte como CSV con formato COP |

---

## Stack

```
Backend      →  Python 3.11 + FastAPI + Uvicorn
Geoespacial  →  GeoPandas 0.14 + Shapely 2.0 (índice STRtree)
Mapas        →  Folium 0.16 (Leaflet.js)
Frontend     →  HTMX 1.9 + Jinja2
Datos        →  n6_1k_aniop_ipm.geojson  (local, fuera de Git)
Containers   →  Docker 24 + Docker Compose v2
CI/CD        →  GitHub Actions
AI Dev       →  Claude Code  (CLAUDE.md como memoria del proyecto)
```

---

## Prerrequisitos

```bash
docker --version        # 24.x o superior
docker compose version  # 2.x o superior
git --version           # 2.x o superior
claude --version        # Claude Code — docs.anthropic.com/claude-code
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
# Editar .env: agregar ANTHROPIC_API_KEY y verificar GEOSIGHT_DATA_PATH
```

### 3 — Agregar datos geoespaciales

> Los datos **no están en el repositorio** — viven fuera de Git por seguridad y tamaño.

```bash
mkdir -p app/data
cp /ruta/a/n6_1k_aniop_ipm.geojson app/data/
ls app/data/   # verificar
```

### 4 — Levantar

```bash
docker compose up -d --build
```

### 5 — Verificar

```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

Abre **http://localhost:8000** 🎉

---

## Estructura del Proyecto

```
poly-spectrum-pricing/
├── app/
│   ├── main.py              # FastAPI — endpoints y startup de GeoEngine
│   ├── geo_engine.py        # Motor de valoración con STRtree
│   ├── data/                # ← GeoJSON aquí  (NO en Git)
│   │   └── n6_1k_aniop_ipm.geojson
│   ├── templates/
│   │   └── index.html       # UI con HTMX
│   └── static/
├── tests/
│   ├── fixtures/            # Datos de prueba mínimos  (sí en Git)
│   │   └── test_polygons.json
│   ├── test_geo_engine.py
│   ├── test_api.py
│   └── test_export.py
├── .agents/
│   └── worktrees.txt        # Estado de worktrees activos entre PCs
├── .github/
│   └── workflows/
│       └── tests.yml        # CI: pytest + cobertura mínima 70%
├── .env.example             # Plantilla de variables (sin valores reales)
├── CLAUDE.md                # Memoria del proyecto para Claude Code
├── Dockerfile
├── docker-compose.yml
├── docker-compose.production.yml
└── requirements.txt
```

---

## Variables de Entorno

```bash
# ── Core ──────────────────────────────────────────────────────
GEOSIGHT_ENV=development          # development | staging | production
GEOSIGHT_DATA_PATH=./app/data     # ruta al directorio de datos GeoJSON
GEOSIGHT_PORT=8000
GEOSIGHT_LOG_LEVEL=INFO           # DEBUG | INFO | WARNING | ERROR

# ── Auth (opcional) ───────────────────────────────────────────
GEOSIGHT_USER=
GEOSIGHT_PASSWORD=

# ── Claude Code ───────────────────────────────────────────────
ANTHROPIC_API_KEY=                # api.anthropic.com
```

```bash
# Development  (hot-reload automático vía docker-compose.override.yml)
docker compose up -d --build

# Production  (4 workers, sin hot-reload)
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
```

---

## Formato de los Datos

Estructura esperada de `n6_1k_aniop_ipm.geojson`:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[lng, lat], [lng, lat], "..."]]
      },
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
| `personas` | `int` | Población del polígono — puede ser `0` |

---

## Fórmula de Valoración

```python
# v2.1 — no modificar sin actualizar el SRS
valor_total = sum(
    row["cop_ipm_mhz_hab_anio"] * row["personas"]
    for row in polygons_that_intersect_circle
)
```

> **Regla de intersección:** un polígono cuenta **completo** ante cualquier intersección con el círculo. No se pondera por porcentaje de área solapada.

| Radio | Metros |
|:---:|:---:|
| 4.6 km | 4 600 m |
| 12.02 km | 12 020 m |
| 19.64 km | 19 640 m |

---

## API Reference

| Método | Endpoint | Descripción |
|:---:|:---|:---|
| `GET` | `/` | Interfaz web principal |
| `POST` | `/assignments` | Calcular cobertura para una asignación |
| `GET` | `/map` | HTML del mapa actual |
| `GET` | `/export/csv` | Descargar reporte en CSV |
| `GET` | `/health` | Health check |

### POST `/assignments`

```bash
curl -X POST http://localhost:8000/assignments \
  -H "Content-Type: application/json" \
  -d '{"name": "Zona Norte", "lat": 4.7109, "lng": -74.0721, "radius_km": 12.02}'
```

```json
{
  "value": 125430000.50,
  "population": 85420,
  "polygon_count": 34,
  "map_html": "..."
}
```

---

## Tests

```bash
# Todos los tests
docker compose exec app pytest tests/ -v

# Con reporte de cobertura
docker compose exec app pytest tests/ --cov=app --cov-report=term-missing

# Fallar si cobertura < 70%
docker compose exec app pytest tests/ --cov=app --cov-fail-under=70
```

> **Cobertura mínima requerida:** 70% — enforced en CI.

---

## Arquitectura de Datos

```
Fuente      →  n6_1k_aniop_ipm.geojson  (local, fuera de Git)
Motor       →  GeoEngine + STRtree  (construido al startup, una sola vez)
Umbral      →  JSON + STRtree  para datasets < 50 000 polígonos
Migración   →  PostGIS en Docker  si dataset supera 50 000 polígonos
```

---

## Desarrollo con Claude Code

Este proyecto usa [Claude Code](https://docs.anthropic.com/claude-code) como asistente de desarrollo.  
`CLAUDE.md` contiene el contexto completo — fórmulas, convenciones y protocolo multi-PC.

```bash
cd poly-spectrum-pricing
claude   # Lee CLAUDE.md automáticamente
```

**Comandos frecuentes:**

```bash
docker compose up -d --build                               # levantar
docker compose exec app pytest tests/ -v --cov=app         # tests
docker compose logs -f app                                 # logs
git worktree list                                          # worktrees activos
git worktree add ../poly-spectrum-[feat] feature/[feat]         # nuevo worktree
```

---

## Workflow Multi-PC

### Cerrar — PC A

```bash
# 1. En Claude Code: "Documenta en CLAUDE.md el estado y el siguiente paso."
git add . && git commit -m "wip: [estado actual]" && git push

git worktree list > .agents/worktrees.txt
git add .agents/ && git commit -m "meta: save worktree state" && git push

docker compose down
```

### Abrir — PC B

```bash
git pull --all
cat .agents/worktrees.txt
git worktree add ../poly-spectrum-[feat] feature/[feat]
docker compose up -d --build
claude
```

Prompt de retoma:
```
Lee el CLAUDE.md y dime en qué estaba trabajando y cuál es el siguiente paso.
Después corre: pytest tests/ -v
```

---

## Contribuir

```bash
# Worktree (recomendado para features)
git worktree add ../poly-spectrum-[feat] feature/[feat]
cd ../poly-spectrum-[feat] && claude

# Branch clásica
git checkout -b feature/[feat] develop
```

1. Tests: `pytest tests/ --cov=app --cov-fail-under=70`
2. Actualiza `CLAUDE.md` con las decisiones tomadas
3. PR hacia `develop`

---

## Documentación

| Archivo | Descripción |
|:---|:---|
| [`CLAUDE.md`](./CLAUDE.md) | Memoria del proyecto — reglas, fórmulas, protocolo multi-PC |
| `docs/GeoSight_SRS_v3.docx` | Software Requirements Specification v3.0 |
| `docs/GeoSight_Guia_Prompts.html` | Guía interactiva de prompts por fase |

---

<div align="center">
<sub>GeoSight Platform — Polygon Spectrum Pricing · v1.0 · Built with <a href="https://docs.anthropic.com/claude-code">Claude Code</a></sub>
</div>
