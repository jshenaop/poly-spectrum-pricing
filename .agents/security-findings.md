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
- [ ] PR `fix/security-audit` → `develop` aprobado y mergeado

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
