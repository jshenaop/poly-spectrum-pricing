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

## Fórmula de Valoración v2.1 — NUNCA CAMBIAR

```
valor_total = sum(cop_ipm_mhz_hab_anio * personas)
```

- Los polígonos cuentan **COMPLETOS** si hay cualquier intersección con el círculo.
- **NO** ponderar por porcentaje de área solapada.
- Cada polígono aporta su valor íntegro o cero — no hay valores parciales.

---

## Radios Permitidos

| Radio nombre | Metros |
|-------------|--------|
| 4.6 km      | 4600   |
| 12.02 km    | 12020  |
| 19.64 km    | 19640  |

Estos son los únicos tres radios válidos. No agregar ni modificar sin decisión explícita.

---

## Colores del Mapa

| Elemento   | Color   | Opacidad |
|------------|---------|----------|
| Cobertura (fill) | `#28A745` | `fill_opacity=0.2` |
| Bordes     | `#1B7A4A` | — |

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
main (estable, siempre deployable)
  └── develop
        └── feature/*
```

PRs van de `feature/*` → `develop`. Merge a `main` solo cuando develop es estable.

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
docker compose exec app pytest tests/ -v --cov=app

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
- **[agregar futuras decisiones con fecha ISO YYYY-MM-DD]**
