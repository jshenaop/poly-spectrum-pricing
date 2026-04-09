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

## Fórmula de Valoración v1.1 — NUNCA CAMBIAR

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
```

- Polígono **completamente dentro**: 100% de su población.
- Polígono **parcialmente dentro**: `ceil(area_solapada / area_total × personas)`.
- Solo toca el borde (contacto puntual/lineal): contribuye 0 (área ≈ 0).
- Completamente fuera: excluido.

---

## Radios Permitidos

| Radio nombre | Metros |
|-------------|--------|
| 8.23 km     | 8230   |
| 21.94 km    | 21940  |
| 35.85 km    | 35850  |

Estos son los únicos tres radios válidos. No agregar ni modificar sin decisión explícita.

---

## Colores del Mapa

| Elemento               | Color     | Opacidad |
|------------------------|-----------|----------|
| Cobertura (fill)       | `#28A745` | `fill_opacity=0.08` (single) / `0.2` (multi) |
| Bordes                 | `#1B7A4A` | — |
| Polígono completo      | `#28A745` | `fillOpacity=0.25` |
| Polígono parcial       | `#28A745` | `fillOpacity=0.5` |
| Pre-header background  | `#004884` (`--blue-dark`) | — |

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

## Historial de Decisiones

- **2026-03-05:** Repo GitHub creado ANTES que el código local (paso 01 del setup).
- **2026-03-05:** README.md creado en paso 03, antes del primer push.
- **2026-03-05:** Estructura de directorios creada (app/, tests/, .agents/, docs/).
- **2026-03-05:** .gitignore extendido con exclusiones GeoSight (*.geojson, app/data/).
- **2026-03-05:** Regla de conteo cambiada: `intersects` → `within`. Solo polígonos completamente dentro del círculo cuentan (v2.2).
- **2026-03-18:** Refactor v1.1 — radios actualizados (8.23/21.94/35.85 km), fórmula extendida a polígonos parciales con ponderación por área (math.ceil), etiqueta UI → V1.1, pre-header links eliminados (fondo → `--blue-dark`), CSV con timestamp ISO en filename, cards de métricas en layout vertical.
