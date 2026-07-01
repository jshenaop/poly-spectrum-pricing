# GeoSight — Referencia de API v1.2

Documentación de la API REST de la plataforma de valoración de cobertura radioeléctrica.

---

## Documentación interactiva

FastAPI genera automáticamente dos interfaces de documentación en tiempo real:

| Visor | URL |
|:---|:---|
| Swagger UI | `http://localhost/docs` |
| ReDoc | `http://localhost/redoc` |
| Spec OpenAPI (JSON) | `http://localhost/openapi.json` |

El archivo estático completo está en [`docs/openapi.yaml`](openapi.yaml).

---

## URL Base

| Entorno | URL Base | Nota |
|:---|:---|:---|
| Desarrollo (NGINX) | `http://localhost` | Puerto 80, proxy a Uvicorn |
| Desarrollo directo | `http://localhost:8000` | Uvicorn sin NGINX |
| Producción | `https://<dominio>` | HTTPS enforced, HSTS habilitado |

---

## Autenticación

La API **no requiere autenticación** en la versión actual. Todos los endpoints son públicos.

> Las variables `GEOSIGHT_USER` y `GEOSIGHT_PASSWORD` en `.env.example` son marcadores de posición para una implementación futura.

---

## Inicio rápido

Calcular la cobertura para Bogotá con radio 8.23 km:

```bash
curl -X POST http://localhost/assignments \
  -d "name=Zona%20Norte&lat=4.71099&lng=-74.07209&radius_km=8.23"
```

**Respuesta esperada:**

```json
{
  "value": 125430000.50,
  "population": 85420,
  "map_html": "<!DOCTYPE html>...",
  "min_applied": false
}
```

Calcular cobertura para múltiples puntos con deduplicación:

```bash
curl -X POST http://localhost/assignments/multi \
  -H "Content-Type: application/json" \
  -d '{"points": [
    {"lat": 4.71099, "lng": -74.07209, "radius_km": 8.23},
    {"lat": 4.72000, "lng": -74.08000, "radius_km": 21.94}
  ]}'
```

Descargar el resultado como CSV:

```bash
curl "http://localhost/export/csv?name=Zona+Norte&lat=4.71099&lng=-74.07209&radius_km=8.23" \
  -o reporte.csv
```

---

## Índice de endpoints

| Método | Ruta | Resumen | Auth |
|:---:|:---|:---|:---:|
| `GET` | `/` | Interfaz web principal (HTMX + Jinja2) | No |
| `POST` | `/assignments` | Calcular cobertura para un punto — valor, población y mapa | No |
| `POST` | `/assignments/multi` | Calcular cobertura para múltiples puntos con deduplicación | No |
| `GET` | `/map` | Mapa Folium sin cálculo (previsualización) | No |
| `GET` | `/export/csv` | Exportar resultado de cobertura como CSV | No |
| `POST` | `/v2/overlap` | Calcular traslape entre dos proponentes | No |
| `GET` | `/overlap` | Interfaz web de traslape | No |
| `GET` | `/health` | Health check del servicio | No |

---

## Detalle de endpoints

### `POST /assignments`

Calcula la valoración geoespacial para un punto y radio dados.

**Content-Type de la solicitud:** `application/x-www-form-urlencoded`

**Parámetros (form data):**

| Campo | Tipo | Requerido | Descripción |
|:---|:---:|:---:|:---|
| `name` | `string` | ✓ | Nombre del proyecto o asignación |
| `lat` | `float` | ✓ | Latitud en grados decimales (EPSG:4686), mínimo 5 decimales |
| `lng` | `float` | ✓ | Longitud en grados decimales (EPSG:4686), mínimo 5 decimales |
| `radius_km` | `float` | ✓ | Radio de cobertura. Valores válidos: `8.23`, `21.94`, `35.85` |

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
| `population` | `int` | Personas cubiertas (ponderadas para polígonos parciales) |
| `map_html` | `string` | HTML del mapa Folium — inyectar en `<div>` vía HTMX |
| `min_applied` | `bool` | `true` si se aplicó el valor piso (`GEOSIGHT_VAL_MIN`) |

---

### `POST /assignments/multi`

Calcula la cobertura para múltiples puntos, cada uno con su propio radio. Los polígonos solapados entre círculos se cuentan exactamente una vez mediante unión geométrica (deduplicación).

**Content-Type de la solicitud:** `application/json`

**Body:**

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
| `points` | `array` | ✓ | Lista de puntos (máximo `GEOSIGHT_MAX_POINTS`, default 10) |
| `points[].lat` | `float` | ✓ | Latitud en grados decimales (EPSG:4686) |
| `points[].lng` | `float` | ✓ | Longitud en grados decimales (EPSG:4686) |
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
  "geojson": null
}
```

| Campo | Tipo | Descripción |
|:---|:---:|:---|
| `points_count` | `int` | Número de puntos procesados |
| `raw_total` | `float` | Suma de valores individuales (antes de deduplicación) |
| `deduplication_adjustment` | `float` | Valor restado por polígonos contados en múltiples círculos |
| `total` | `float` | Valor final COP/MHz/Año deduplicado |
| `population_covered` | `int` | Personas cubiertas por la unión de todos los círculos |
| `polygon_count` | `int` | Polígonos evaluados en la unión |
| `min_applied` | `bool` | `true` si se aplicó el valor piso |
| `map_html` | `string` | HTML del mapa con todos los círculos y zona de solapamiento (púrpura) |
| `geojson` | `object\|null` | GeoJSON de los polígonos cubiertos, o `null` si no hay resultados |

**Algoritmo de deduplicación:**
1. Cada punto se proyecta a EPSG:3116 y se crea un buffer circular con su radio individual.
2. Se construye la unión geométrica de todos los buffers.
3. Se evalúan los polígonos contra la unión — cada polígono se cuenta exactamente una vez.
4. `deduplication_adjustment` = suma de valores individuales − valor de la unión.

---

### `POST /v2/overlap`

Calcula el valor del traslape geográfico entre dos proponentes (A y B). Cada proponente puede tener una o múltiples coordenadas. Retorna dos vistas independientes: cada proponente ve su propia cobertura y la zona de traslape en gris oscuro, sin acceso a las coordenadas del otro.

**Content-Type de la solicitud:** `application/json`

**Formato punto único (legacy):**

```json
{
  "point_a": {"lat": 5.73, "lng": -73.05, "radius_km": 8.2},
  "point_b": {"lat": 5.77, "lng": -73.02, "radius_km": 8.2}
}
```

**Formato multi-coordenada:**

```json
{
  "points_a": [
    {"lat": 5.73, "lng": -73.05, "radius_km": 8.2},
    {"lat": 5.74, "lng": -73.06, "radius_km": 21.9}
  ],
  "points_b": [
    {"lat": 5.77, "lng": -73.02, "radius_km": 8.2}
  ]
}
```

| Campo | Tipo | Requerido | Descripción |
|:---|:---:|:---:|:---|
| `point_a` | `object` | * | Coordenada única del proponente A (formato legacy) |
| `point_b` | `object` | * | Coordenada única del proponente B (formato legacy) |
| `points_a` | `array` | * | Lista de coordenadas del proponente A (máximo `GEOSIGHT_MAX_POINTS`) |
| `points_b` | `array` | * | Lista de coordenadas del proponente B (máximo `GEOSIGHT_MAX_POINTS`) |
| `*.lat` | `float` | ✓ | Latitud (Colombia: -4.23 a 13.39) |
| `*.lng` | `float` | ✓ | Longitud (Colombia: -81.73 a -66.87) |
| `*.radius_km` | `float` | ✓ | Radio v2: `8.2`, `21.9`, `35.8` |

\* Debe enviarse exactamente uno de (`point_a`, `points_a`) y uno de (`point_b`, `points_b`). No ambos, no ninguno.

**Respuesta `200 OK`:**

```json
{
  "overlap_exists": true,
  "overlap": {
    "value": 350000.0,
    "population": 6200,
    "polygon_count": 45
  },
  "view_a": {
    "coverage": {"value": 1090526.0, "population": 18759, "polygon_count": 245},
    "overlap": {"value": 350000.0, "population": 6200, "polygon_count": 45},
    "map_html": "<html>..."
  },
  "view_b": {
    "coverage": {"value": 980000.0, "population": 16500, "polygon_count": 230},
    "overlap": {"value": 350000.0, "population": 6200, "polygon_count": 45},
    "map_html": "<html>..."
  }
}
```

| Campo | Tipo | Descripción |
|:---|:---:|:---|
| `overlap_exists` | `bool` | `false` si las coberturas no se intersectan |
| `overlap` | `object` | Métricas del traslape (unión_A ∩ unión_B) |
| `view_a` | `object` | Vista para el proponente A (cobertura + traslape + mapa) |
| `view_b` | `object` | Vista para el proponente B (cobertura + traslape + mapa) |
| `*.coverage` | `object` | Métricas de la cobertura total del proponente (unión de todos sus buffers) |
| `*.map_html` | `string` | Mapa Folium con cobertura propia (verde) y traslape (gris oscuro) |

Se aplica `GEOSIGHT_VAL_MIN` como piso al valor del traslape.

**Algoritmo multi-coordenada:**
1. Para cada proponente, se construye la unión geométrica de sus buffers circulares.
2. Se calcula la intersección: `union(A) ∩ union(B)`.
3. Se evalúan los polígonos del grid contra la intersección.
4. Cada proponente ve su cobertura total (unión) y el traslape, pero nunca las coordenadas del otro.

---

### `GET /map`

Retorna un mapa Folium con el círculo de cobertura dibujado. No ejecuta ningún cálculo geoespacial.

**Parámetros (query string):**

| Parámetro | Tipo | Default | Descripción |
|:---|:---:|:---:|:---|
| `lat` | `float` | `4.71` | Latitud central |
| `lng` | `float` | `-74.07` | Longitud central |
| `radius_km` | `float` | `8.23` | Radio del círculo a dibujar |

**Respuesta:** HTML del mapa (`text/html`, `200 OK`)

---

### `GET /export/csv`

Calcula la cobertura y retorna el resultado como archivo CSV descargable.

El archivo incluye BOM UTF-8 para compatibilidad con Excel en español.
El nombre del archivo tiene formato: `{nombre}_export_YYYY-MM-DD_HH-MM-SS.csv`

**Parámetros (query string):**

| Parámetro | Tipo | Default | Descripción |
|:---|:---:|:---:|:---|
| `name` | `string` | `"Sin nombre"` | Nombre del proyecto |
| `lat` | `float` | `4.71` | Latitud central |
| `lng` | `float` | `-74.07` | Longitud central |
| `radius_km` | `float` | `8.23` | Radio de cobertura |

**Columnas del CSV:** `nombre`, `lat`, `lng`, `radio_km`, `valor_total_cop`, `poblacion`

---

### `GET /health`

```bash
curl http://localhost/health
# → {"status": "ok", "service": "geosight"}
```

---

## Referencia de errores

| Código | Causa | Respuesta |
|:---:|:---|:---|
| `400` | Radio no permitido o error de lógica de negocio | `{"error": "Radio invalido: X km. Valores permitidos: [8.23, 21.94, 35.85]"}` |
| `422` | Parámetro faltante o tipo incorrecto (validación FastAPI) | `{"detail": [...]}` |
| `429` | Límite de tasa excedido (gestionado por NGINX) | HTML de NGINX |
| `500` | Error interno inesperado del servidor | `{"error": "Error interno del servidor"}` |

---

## Límites de tasa (Rate Limiting)

Gestionados por NGINX — la aplicación FastAPI no los aplica directamente.

### Desarrollo (`nginx/nginx.conf`)

| Endpoint | Límite | Burst |
|:---|:---:|:---:|
| `POST /assignments` | 20 solicitudes/minuto | 10 |
| `POST /assignments/multi` | 20 solicitudes/minuto | 10 |
| `POST /v2/overlap` | 20 solicitudes/minuto | 3 |
| Todos los demás | 30 solicitudes/segundo | 50 |

### Producción (`nginx/nginx.prod.conf`)

| Endpoint | Límite | Burst |
|:---|:---:|:---:|
| `POST /assignments` | 5 solicitudes/minuto | 3 |
| `POST /assignments/multi` | 5 solicitudes/minuto | 3 |
| `POST /v2/overlap` | 5 solicitudes/minuto | 3 |
| Todos los demás | 10 solicitudes/segundo | 20 |

Cuando se supera el límite: **HTTP 429 Too Many Requests**.

---

## Cabeceras de seguridad (Producción)

Aplicadas por NGINX en `nginx/nginx.prod.conf`:

| Cabecera | Valor |
|:---|:---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` |
| `X-Frame-Options` | `SAMEORIGIN` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net; ...` |

---

## CORS

| Entorno | Configuración |
|:---|:---|
| `development` | `allow_origins=["*"]` — permisivo |
| `production` | `allow_origins=[]` — sin CORS externo |

Métodos permitidos en ambos entornos: `GET`, `POST`.

---

## Fórmula de valoración v1.1

```
Valor licencia = valor_total × MHz × años_vigencia
```

Donde `valor_total` (retornado por `POST /assignments`) se calcula como:

```
valor_total = Σ (cop_ipm_mhz_hab_anio × personas_ponderadas)
```

| Condición del polígono | Personas ponderadas |
|:---|:---|
| Completamente dentro del círculo | `personas` (100%) |
| Intersección parcial con el borde | `ceil(área_solapada / área_total × personas)` |
| Solo toca el borde (área ≈ 0) | 0 |
| Completamente fuera | Excluido |

---

## Changelog

### v2.1 — 2026-06-30
- `POST /v2/overlap` ahora acepta múltiples coordenadas por proponente (`points_a`/`points_b`)
- Formato legacy (`point_a`/`point_b`) sigue funcionando — backward compatible
- Máximo `GEOSIGHT_MAX_POINTS` (default 10) coordenadas por proponente
- UI de traslape con formulario dinámico: agregar/eliminar coordenadas por proponente
- Mapa muestra múltiples círculos y markers por proponente
- Nuevo helper `_build_union_buffer()` en GeoEngine elimina duplicación de código

### v2.0 — 2026-06-30
- Nuevo endpoint `POST /v2/overlap` — cálculo de traslape entre dos proponentes
- Vistas independientes por proponente: cobertura propia + zona de traslape (gris oscuro)
- Página `GET /overlap` con formulario para proponentes A y B, tabs de mapa
- Mapas de traslape con tiles CartoDB Light para mejor contraste
- Rate limiting para `/v2/overlap` en NGINX (dev: burst=3, prod: burst=3)

### v1.2 — 2026-04-10
- Nuevo endpoint `POST /assignments/multi` — múltiples puntos con radio individual
- Deduplicación por unión geométrica (polígonos solapados se cuentan una vez)
- Campos `population_covered` y `polygon_count` añadidos a la respuesta multi
- Campo `min_applied` añadido a la respuesta de `POST /assignments`
- Mapa multi-punto con zona de solapamiento en púrpura y tooltips en polígonos
- UI: sidebar 420px, selector de radio por punto, herencia de valores entre puntos

### v1.1 — 2026-03-18
- Fórmula extendida a polígonos parciales con ponderación por área (`math.ceil`)
- Radios actualizados: `8.23 km · 21.94 km · 35.85 km`
- Nombre del archivo CSV con timestamp ISO
- Campo `polygons_geojson` añadido a la respuesta interna del GeoEngine

### v1.0 — 2026-03-05
- Lanzamiento inicial
- Fórmula `within`-only (solo polígonos completamente dentro del círculo)
- Radios: `4.6 km · 12.02 km · 19.64 km`
