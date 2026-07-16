# Reporte de Auditoría de Seguridad — GeoSight Platform
**Fecha:** 2026-03-05 | **Branch:** `fix/security-audit` → PR → `develop`

---

## Hallazgos y Estado

### 🔴 F-01 — CSP ausente en `nginx.prod.conf`
**Impacto:** Alto — sin `Content-Security-Policy` la plataforma es vulnerable a XSS e inyección de recursos externos no autorizados.  
**Estado:** ✅ Resuelto  
**Fix:** Agregado header `Content-Security-Policy` en `nginx.prod.conf` con política ajustada al stack (Folium, Google Fonts, OpenStreetMap, unpkg/jsDelivr).

---

### 🔴 F-02 — HSTS ausente en `nginx.prod.conf`
**Impacto:** Alto — sin `Strict-Transport-Security` los navegadores pueden ser degradados a HTTP mediante ataques MITM (SSL stripping).  
**Estado:** ✅ Resuelto  
**Fix:** Agregado `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` en `nginx.prod.conf`. Además se agregó bloque `server` en puerto 80 que redirige todo el tráfico HTTP → HTTPS (301).

---

### 🔴 F-03 — Sin rate limiting en `POST /assignments`
**Impacto:** Alto — el endpoint ejecuta cálculos geoespaciales costosos. Sin throttling, un atacante puede agotar la CPU del servidor con un bombardeo de peticiones.  
**Estado:** ✅ Resuelto  
**Fix:**  
- `nginx.prod.conf`: zona `assignments` → **5 req/min** por IP, `burst=3 nodelay`, HTTP 429 en exceso.
- `nginx.conf` (dev): zona `assignments_dev` → **20 req/min** por IP, `burst=10`, para detectar problemas antes de prod.

---

### 🟡 F-04 — Sin rate limiting general en NGINX (dev & prod)
**Impacto:** Medio — rutas como `/map` y `/export/csv` también invocan el motor geo. Sin rate limit global se pueden usar para amplificar ataques.  
**Estado:** ✅ Resuelto  
**Fix:**  
- `nginx.prod.conf`: zona `general` → **10 req/s**, `burst=20`.
- `nginx.conf` (dev): zona `general_dev` → **30 req/s**, `burst=50`.

---

### 🟡 F-05 — Sin validación lat/lng en `app/main.py`
**Impacto:** Medio — la API acepta coordenadas fuera de Colombia. Puede derivar en resultados incorrectos o consultas inesperadas al motor geo.  
**Estado:** ✅ Resuelto  
**Fix:**
- `PointInput` (multi-punto): `field_validator` en Pydantic para lat (-4.23 a 13.39) y lng (-81.73 a -66.87).
- `POST /assignments` (punto único): validación inline con los mismos rangos al inicio del endpoint.
- Coordenadas fuera de Colombia retornan HTTP 400 (single) o HTTP 422 (multi, via Pydantic).

---

---

### 🟡 F-10 — Sin rate limiting en `POST /assignments/multi`
**Impacto:** Medio — el endpoint multi-punto ejecuta múltiples cálculos geoespaciales + unión geométrica. Sin throttling dedicado, solo el rate limit general lo protege.  
**Estado:** ✅ Resuelto  
**Fix:**
- `nginx.prod.conf`: bloque `location = /assignments/multi` con zona `assignments` (5 req/min, burst=3).
- `nginx.conf` (dev): bloque `location = /assignments/multi` con zona `assignments_dev` (20 req/min, burst=10).

---

## Validaciones — Sin acción requerida

| # | Ítem | Resultado |
|---|------|-----------|
| F-06 | `app/data/` mount en Docker | ✅ Montado `:ro` en ambos compose files |
| F-07 | `.env` en `.gitignore` | ✅ Cubierto por `.env` y `.env.*` en `.gitignore` |
| F-08 | API Key Anthropic en logs | ✅ El logger no registra variables de entorno; `ANTHROPIC_API_KEY` nunca aparece en stdout/stderr |
| F-09 | CORS en producción | ✅ `allow_origins=[]` cuando `GEOSIGHT_ENV=production` |

---

## Archivos Modificados
| Archivo | Cambio |
|---------|--------|
| `nginx/nginx.prod.conf` | HSTS, CSP, rate limiting, TLS redirect |
| `nginx/nginx.conf` | Rate limiting para paridad con prod |

## Próximos pasos
- [x] ~~Equipo principal implementa F-05 (validación Pydantic lat/lng) en `app/main.py`~~ — Resuelto v1.2
- [x] ~~Rate limiting para `/assignments/multi`~~ — Resuelto v1.2
- [ ] Configurar TLS en `nginx.prod.conf` con las rutas reales de certificados (Certbot / Let's Encrypt)
- [x] ~~PR `fix/security-audit` → `develop` aprobado y mergeado~~

---

## Auditoría Post-v2.1.0 — Julio 2026

**Fecha:** 2026-07-16 | **Alcance:** Revisión completa post-desarrollo de `/v2/overlap` y multi-coordenada

### 🔴 F-11 — `/v2/compare` sin límite de puntos (DoS)
**Impacto:** Crítico — cada punto ejecuta 2 `calculate_coverage()`. Sin `max_points` check, un body de 10 MB puede forzar ~400K evaluaciones de grilla.
**Estado:** ✅ Resuelto
**Fix:** Agregada verificación `len(body.points) > settings.max_points` al inicio de `compare_v1_v2()` en `app/main.py`.

---

### 🔴 F-12 — CSV Formula Injection (CWE-1236)
**Impacto:** Crítico — campo `name` se escribía sin sanitizar en CSV con BOM UTF-8 (Excel). Un `name` como `=cmd|'/c calc'!A1` ejecuta fórmulas/DDE.
**Estado:** ✅ Resuelto
**Fix:** Prefijo `'` de neutralización si `name` empieza con `=`, `+`, `-`, `@`, `\t`, `\r` en `_handle_export_csv()`.

---

### 🔴 F-13 — Listas Pydantic sin cap en esquema
**Impacto:** Crítico — `points`, `points_a`, `points_b` sin `Field(max_length=...)` permitían que Pydantic parseara arrays enormes antes de la verificación `max_points`.
**Estado:** ✅ Resuelto
**Fix:** `Field(max_length=50)` en `MultiAssignmentRequest`, `OverlapRequest`, y `CompareRequest`.

---

### 🟡 F-14 — OpenAPI/Docs expuestos sin autenticación
**Impacto:** Alto — `/docs`, `/redoc`, `/openapi.json` accesibles en producción, exponiendo esquemas y lógica de negocio.
**Estado:** ✅ Resuelto
**Fix:** `docs_url`/`redoc_url`/`openapi_url` condicionados a `GEOSIGHT_ENV != production` (pasan `None` en prod).

---

### 🟡 F-15 — Host Header Injection en redirect HTTP→HTTPS
**Impacto:** Alto — `return 301 https://$host$request_uri;` reflejaba el header `Host` del atacante → open redirect / cache poisoning.
**Estado:** ✅ Resuelto
**Fix:** Agregado `server_name tramites.ane.gov.co` en ambos bloques server, redirect usa `$server_name`, y bloque `default_server` retorna 444 para hosts desconocidos.

---

### 🟡 F-16 — Iframe sandbox `allow-scripts allow-same-origin`
**Impacto:** Alto (defensa en profundidad) — la combinación permite que contenido del iframe escape el sandbox.
**Estado:** ✅ Resuelto
**Fix:** Removido `allow-same-origin` en `index.html` y `overlap.html`. Mapas Folium verificados funcionando sin esa directiva.

---

### 🟢 F-17 — `'unsafe-inline'` en CSP `script-src`
**Impacto:** Medio — debilita CSP contra XSS inyectado.
**Estado:** ⚠️ Riesgo aceptado
**Razón:** Folium genera `<script>` inline en `map_html`; eliminar `unsafe-inline` rompe los mapas. Documentado con comentario en `nginx.prod.conf`.

---

### 🟢 F-18 — Supply chain: Trivy Action pinned a `@master`
**Impacto:** Medio — branch mutable, un compromiso upstream ejecutaría código en CI.
**Estado:** ✅ Resuelto
**Fix:** Pineado a `aquasecurity/trivy-action@0.28.0` en `.github/workflows/security.yml`.

---

### 🟢 F-19 — Sin `permissions:` explícito en workflows
**Impacto:** Medio — `GITHUB_TOKEN` con permisos amplios por defecto.
**Estado:** ✅ Resuelto
**Fix:** Agregado `permissions: { contents: read }` en `tests.yml` y `security.yml`.

---

### 🟢 F-20 — Healthcheck no verifica GeoEngine
**Impacto:** Bajo — `/health` retornaba 200 incluso si GeoJSON no cargó (degraded mode silencioso).
**Estado:** ✅ Resuelto
**Fix:** `/health` ahora verifica `geo_engine._gdf is not None`, retorna 503 `{"status": "degraded"}` si no.

---

### 🟢 F-21 — `name` en `Form(...)` sin `max_length` y no usado
**Impacto:** Bajo — `name` sin límite de tamaño, parseado y descartado.
**Estado:** ✅ Resuelto
**Fix:** `name: str = Form(default="Sin nombre", max_length=100)` en `/v1/assignments` y `/v2/assignments`.

---

### 🟢 F-22 — CORS doc/code drift
**Impacto:** Bajo — `docs/API.md` describía branching por `GEOSIGHT_ENV` que no existe en el código.
**Estado:** ✅ Resuelto
**Fix:** Documentación corregida para reflejar que CORS depende exclusivamente de `GEOSIGHT_CORS_ORIGINS`.

---

### Archivos modificados (Auditoría Julio 2026)

| Archivo | Cambio |
|---------|--------|
| `app/main.py` | F-11, F-12, F-13, F-14, F-20, F-21 |
| `app/templates/index.html` | F-16 |
| `app/templates/overlap.html` | F-16 |
| `nginx/nginx.prod.conf` | F-15, F-17 |
| `.github/workflows/security.yml` | F-18, F-19 |
| `.github/workflows/tests.yml` | F-19 |
| `docs/API.md` | F-22 |

---

## Remediación de Vulnerabilidades Trivy — Abril 2026

**Escaneo:** 359 vulnerabilidades (3 CRITICAL, 77 HIGH, 279 MEDIUM)

### Acciones ejecutadas

| Fase | Acción | Estado |
|---|---|---|
| **FASE 1** | Nginx 1.25-alpine → 1.27-alpine (resuelve 3 CRITICAL + 17 HIGH) | ✅ |
| **FASE 2** | Python deps: FastAPI ≥0.115, geopandas ≥1.1.2, Jinja2 ≥3.1.6 | ✅ |
| **FASE 3** | Multi-stage Dockerfile (elimina ~50% vulns OS-level de -dev packages) | ✅ |
| **FASE 4** | CI/CD Trivy scan en `.github/workflows/security.yml` | ✅ |

### Archivos modificados
| Archivo | Cambio |
|---|---|
| `docker-compose.yml` | nginx:1.25-alpine → 1.27-alpine |
| `docker-compose.production.yml` | nginx:1.25-alpine → 1.27-alpine |
| `requirements.txt` | FastAPI ≥0.115, geopandas ≥1.1.2, Jinja2 ≥3.1.6 |
| `Dockerfile` | Multi-stage build (builder + runtime), apt-get upgrade |
| `.github/workflows/security.yml` | Trivy CRITICAL+HIGH gate, escaneo semanal |
