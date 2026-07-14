# CLAUDE.md — GeoSight Platform (Polygon Spectrum Pricing)

Archivo de memoria persistente para Claude Code.
Lee esto al inicio de cada sesión antes de tocar cualquier código.

---

## Contexto del Proyecto

**Nombre:** GeoSight — Plataforma de análisis geoespacial para valoración de cobertura.
**Archivo de datos:** `app/data/n6_1k_aniop_ipm.geojson` — NUNCA en Git (ver .gitignore).
**Stack:** Python 3.11 + FastAPI + GeoPandas + Folium + HTMX + Docker.
**Restricción:** NO usar Streamlit. La UI se construye con HTMX sobre FastAPI.

---

## Fórmula de Valoración v1.2 — NUNCA CAMBIAR

```python
import math
valor_total = 0
for p in candidatos_que_intersectan_circulo:
    if p.within(circulo):
        personas_pond = p["personas"]
    else:
        ratio = p.intersection(circulo).area / p.area
        personas_pond = math.ceil(ratio * p["personas"])
    valor_total += p["cop_ipm_mhz_hab_anio"] * personas_pond

# Piso mínimo (GEOSIGHT_VAL_MIN)
valor_final = max(valor_total, VAL_MIN)
```

- Polígono **completamente dentro**: 100% de su población.
- Polígono **parcialmente dentro**: `ceil(area_solapada / area_total × personas)`.
- Solo toca el borde (contacto puntual/lineal): contribuye 0 (área ≈ 0).
- Completamente fuera: excluido.
- **Piso mínimo**: si `valor_total < GEOSIGHT_VAL_MIN`, se usa `GEOSIGHT_VAL_MIN` como valor final y se marca `min_applied=True`.

---

## Radios Permitidos

### v1 (endpoints `/v1/assignments`, `/v1/assignments/multi`, `/v1/export/csv`)

| Radio nombre | Metros |
|-------------|--------|
| 8.23 km     | 8230   |
| 21.94 km    | 21940  |
| 35.85 km    | 35850  |

### v2 (endpoints `/v2/assignments`, `/v2/assignments/multi`, `/v2/export/csv`)

| Radio nombre | Metros |
|-------------|--------|
| 8.2 km      | 8200   |
| 21.9 km     | 21900  |
| 35.8 km     | 35800  |

No agregar ni modificar radios sin decisión explícita.

---

## Colores del Mapa

| Elemento               | Color     | Opacidad |
|------------------------|-----------|----------|
| Cobertura (fill)       | `#28A745` | `fill_opacity=0.08` (single) / `0.2` (multi) |
| Bordes                 | `#1B7A4A` | — |
| Polígono completo      | `#28A745` | `fillOpacity=0.25` |
| Polígono parcial       | `#28A745` | `fillOpacity=0.5` |
| Pre-header background  | `#3366CC` (`--blue-primary`) | — |

---

## Decisión de Base de Datos

- **< 50 000 polígonos:** JSON en memoria + índice STRtree (GeoPandas/Shapely).
- **> 50 000 polígonos:** PostGIS en Docker local.
- **NUNCA Supabase:** latencia de red innecesaria para uso interno.

---

## Repositorio

```
git@github.com:jshenaop/poly-spectrum-pricing.git
```

**Branching:**
```
feature/*   ← desarrollo activo
    ↓  PR
 develop    ← validación y tests
    ↓  PR (solo cuando develop es estable)
   main     ← tag de release (vX.Y.Z)
```

**Reglas:**
1. Todo desarrollo nuevo ocurre en `feature/*` (creada desde `develop`).
2. PR de `feature/*` → `develop` para integrar y validar.
3. PR de `develop` → `main` solo cuando el conjunto de features del milestone está completo y los tests pasan.
4. Cada merge a `main` lleva un tag anotado de release (`vX.Y.Z`).
5. Nunca commitear directamente a `develop` ni a `main`.

---

## Entornos

| Entorno     | Config                                        |
|-------------|-----------------------------------------------|
| development | `.env` + `docker-compose.override.yml` (hot-reload) |
| production  | `.env.production` + `docker-compose.production.yml` |

---

## Protocolo Multi-PC

**Al cerrar sesión:**
1. Pedir a Claude: "Documenta estado actual en CLAUDE.md"
2. `git add -A && git commit -m "wip: <descripcion breve>"`
3. `git push`

**Al abrir sesión en otro PC:**
1. `git pull --all`
2. Recrear worktrees necesarios (ver Comandos Frecuentes)
3. `docker compose up -d`
4. Leer este archivo antes de continuar

---

## Comandos Frecuentes

```bash
# Levantar entorno de desarrollo
docker compose up -d --build

# Correr tests con cobertura
docker compose run --rm app pytest tests/ -v --cov=app

# Ver worktrees activos
git worktree list

# Crear worktree para una feature
git worktree add ../geosight-[feat] feature/[feat]

# Eliminar worktree cuando termina
git worktree remove ../geosight-[feat]
```

---

## Versión Activa

| Versión | Tag Git | Estado | Rama |
|---------|---------|--------|------|
| v1.1.1  | `v1.1.1` @ `244cc58` | **Cerrada / Estable** | — |
| v1.2.0  | — | **Cerrada / Estable** | — |
| v2.0.0  | `v2.0.0` | **Cerrada / Estable** | — |
| v2.1.0  | `v2.1.0` | **Estable** | `main` |

**v2.1.0 — Features:**
- Endpoint `POST /v2/overlap`: análisis de traslape geográfico entre dos proponentes.
- Soporte multi-coordenada por proponente (hasta `GEOSIGHT_MAX_POINTS` puntos cada uno).
- UI de traslape en `/overlap` con formularios dinámicos, vistas A/B y métricas de coincidencia.
- `_build_union_buffer()` extraído como helper reutilizable.
- Tests de integración para overlap (single-point, multi-point, no-overlap, radios inválidos).

**v2.0.0 — Features:**
- API versionada: endpoints v1 (`/v1/*`) y v2 (`/v2/*`) conviven.
- Radios v2: 8.2 / 21.9 / 35.8 km (reemplazan 8.23 / 21.94 / 35.85 km en UI).
- Endpoint `/v2/compare`: comparación lado a lado v1 vs v2.
- UI apunta a endpoints v2 con radios actualizados.
- Fix Dockerfile para Debian Trixie (`libgdal36`, `libgeos-c1t64`).
- Dependencia `python-multipart` agregada para FastAPI Form.

---

## Historial de Decisiones

- **2026-03-05:** Repo GitHub creado ANTES que el código local (paso 01 del setup).
- **2026-03-05:** README.md creado en paso 03, antes del primer push.
- **2026-03-05:** Estructura de directorios creada (app/, tests/, .agents/, docs/).
- **2026-03-05:** .gitignore extendido con exclusiones GeoSight (*.geojson, app/data/).
- **2026-03-05:** Regla de conteo cambiada: `intersects` → `within`. Solo polígonos completamente dentro del círculo cuentan (v2.2).
- **2026-03-18:** Refactor v1.1 — radios actualizados (8.23/21.94/35.85 km), fórmula extendida a polígonos parciales con ponderación por área (math.ceil), etiqueta UI → V1.1, pre-header links eliminados (fondo → `--blue-dark`), CSV con timestamp ISO en filename, cards de métricas en layout vertical.
- **2026-04-09:** v1.1.1 cerrada — tag re-creado en `244cc58` (favicon + OpenAPI 3.1 + documentación completa). develop sincronizado con main. Branch `refactor/geosight-v1.1` eliminada. Inicio de v1.2.0 en `feature/multi-lat-lng`.
- **2026-06-17:** v2.0.0 — API versionada (`/v1/*`, `/v2/*`), radios v2 (8.2/21.9/35.8 km), endpoint `/v2/compare`, UI migrada a v2, fix Dockerfile Debian Trixie, `python-multipart` agregado. Branch `feature/v2-radii` mergeada y eliminada.
- **2026-06-30:** Producción (ANE, `172.23.90.131`) actualizada `GEOSIGHT_MAX_POINTS=5` → `10` en `.env` + `docker compose down && up -d`. No requirió cambio de código (la variable se lee desde el entorno en `app/config.py`, default 5). Validado con `curl` a `https://tramites.ane.gov.co/valoracion/v2/assignments/multi` con 10 puntos → `HTTP 200`. Nota: los resultados de prod y local difieren levemente (prod `total`≈$41.3M / `population`=735.979 vs local ≈$40.4M / 728.502, mismo `polygon_count`=4499), lo que sugiere que el dataset GeoJSON difiere entre entornos — pendiente verificar sincronización de `app/data/n6_1k_aniop_ipm.geojson`.
- **2026-07-13:** v2.1.0 — Endpoint `POST /v2/overlap` con soporte multi-coordenada por proponente, UI de traslape en `/overlap` con formularios dinámicos y vistas A/B, helper `_build_union_buffer()` extraído, tests de integración para overlap. Tag `v2.1.0` creado en `main`.
