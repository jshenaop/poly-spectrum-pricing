# GeoSight — SRS Changelog

## Referencia de documentos

| Documento | Rol |
|:---|:---|
| `GeoSight_SRS_v3.2_SecurityAgent.docx` | Especificación de requisitos inicial (referencia congelada) |
| `API.md` | Referencia API REST viva — siempre refleja la versión en producción |
| `openapi.yaml` | Especificación OpenAPI 3.1 viva — fuente de verdad para integración |
| `GeoSight_Guia_Prompts_v1.1.html` | Guía interactiva de prompts para Claude Code + Antigravity |

---

## v1.1 — 2026-03-18 (versión actual)

Cambios respecto al SRS v3.2:

### Fórmula de valoración
- **SRS v3.2:** Solo polígonos completamente dentro del círculo (`within`-only)
- **v1.1:** Polígonos parciales incluidos con ponderación por área solapada:
  ```python
  personas_ponderadas = math.ceil(area_solapada / area_total × personas)
  ```

### Radios de cobertura
| SRS v3.2 | v1.1 |
|:---:|:---:|
| 4.6 km | 8.23 km |
| 12.02 km | 21.94 km |
| 19.64 km | 35.85 km |

### API
- Nuevo endpoint: `GET /health` — health check para Docker y load balancers
- Nuevo endpoint: `GET /docs` — Swagger UI (FastAPI nativo)
- Nuevo endpoint: `GET /redoc` — ReDoc (FastAPI nativo)
- CSV filename ahora incluye timestamp ISO: `{nombre}_export_YYYY-MM-DD_HH-MM-SS.csv`
- Documentación OpenAPI 3.1 estática en `docs/openapi.yaml`

### CI/CD
- GitHub Actions pipeline en `.github/workflows/tests.yml`
- Cobertura mínima: 70% (`--cov-fail-under=70`)
- Docker imagen incluye `tests/` para ejecución en CI sin volumen montado

### UI
- Favicon MinTIC: `app/static/img/favicon.png`
- Pre-header color → `--blue-dark: #004884`
- Badge de versión → `V1.1`
- Polígonos parciales diferenciados visualmente (`fillOpacity: 0.5`)

---

## v1.0 — 2026-03-05 (lanzamiento inicial)

- Implementación base del SRS v3.2
- Fórmula `within`-only
- Radios: 4.6 km · 12.02 km · 19.64 km
