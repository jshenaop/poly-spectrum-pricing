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
**Estado:** ⏳ Pendiente (solo-lectura en `app/main.py`)  
**Fix propuesto para el equipo principal:**
```python
from pydantic import BaseModel, Field, field_validator

class AssignmentRequest(BaseModel):
    name: str
    lat: float = Field(..., ge=-4.23, le=13.39)   # Colombia lat range
    lng: float = Field(..., ge=-81.73, le=-66.87) # Colombia lng range
    radius_km: float = Field(..., gt=0, le=200)

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not -4.23 <= v <= 13.39:
            raise ValueError(f"Latitud {v} fuera del rango de Colombia (-4.23 a 13.39)")
        return v

    @field_validator("lng")
    @classmethod
    def validate_lng(cls, v: float) -> float:
        if not -81.73 <= v <= -66.87:
            raise ValueError(f"Longitud {v} fuera del rango de Colombia (-81.73 a -66.87)")
        return v
```
> ⚠️ Requiere cambiar `Form(...)` en el endpoint `/assignments` a un `Body` con el schema `AssignmentRequest`, o mantener `Form` y hacer la validación inline utilizando esos rangos.

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
- [ ] Equipo principal implementa F-05 (validación Pydantic lat/lng) en `app/main.py`
- [ ] Configurar TLS en `nginx.prod.conf` con las rutas reales de certificados (Certbot / Let's Encrypt)
- [ ] PR `fix/security-audit` → `develop` aprobado y mergeado
