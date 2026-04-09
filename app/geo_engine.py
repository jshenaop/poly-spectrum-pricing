import math
import logging

import folium
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

logger = logging.getLogger(__name__)

METRIC_CRS = "EPSG:3116"  # MAGNA-SIRGAS / Colombia Bogota (metros)
SOURCE_CRS = "EPSG:4686"  # MAGNA-SIRGAS geografico (grados)


class GeoEngine:
    """Motor de analisis geoespacial para valoracion de cobertura.

    Carga el GeoJSON de poligonos una sola vez al inicializar y construye
    un indice espacial STRtree para consultas eficientes. Las queries
    posteriores se resuelven enteramente en memoria.
    """

    VALID_RADII = [8.23, 21.94, 35.85]  # km — unicos radios validos

    def __init__(self):
        self._gdf = None      # GeoDataFrame proyectado a METRIC_CRS
        self._sindex = None   # STRtree sobre geometrias proyectadas
        self._load_data()

    def _load_data(self):
        """Carga el GeoJSON desde GEOSIGHT_DATA_PATH/GEOSIGHT_GRID_DATA y construye el indice espacial."""
        from app.config import load_settings
        settings = load_settings()
        geojson = settings.data_path / settings.grid_data

        if not geojson.exists():
            logger.warning("Archivo de datos no encontrado: %s", geojson)
            return

        try:
            gdf = gpd.read_file(geojson).to_crs(METRIC_CRS)
            self._gdf = gdf
            self._sindex = gdf.sindex
            logger.info("GeoEngine listo: %d poligonos cargados", len(gdf))
        except Exception as exc:
            logger.error("Error al cargar GeoJSON: %s", exc)

    def calculate_coverage(self, lat: float, lng: float, radius_km: float) -> dict:
        """Calcula el valor total de cobertura para un punto y radio dados.

        Formula: valor_total = sum(cop_ipm_mhz_hab_anio * personas)
        Los poligonos cuentan COMPLETOS si hay cualquier interseccion con el
        buffer circular. No se pondera por porcentaje de area solapada.

        Args:
            lat: Latitud del punto central en grados (EPSG:4686).
            lng: Longitud del punto central en grados (EPSG:4686).
            radius_km: Radio de cobertura en kilometros. Debe ser uno de VALID_RADII.

        Returns:
            dict con las claves:
                - total_value (float): Suma de cop_ipm_mhz_hab_anio * personas.
                - population_covered (int): Suma de personas en poligonos cubiertos.
                - polygon_count (int): Numero de poligonos que intersectan el buffer.

        Raises:
            ValueError: Si radius_km no es uno de los radios permitidos.
        """
        if radius_km not in self.VALID_RADII:
            raise ValueError(
                f"Radio invalido: {radius_km} km. "
                f"Valores permitidos: {self.VALID_RADII}"
            )

        if self._gdf is None:
            logger.warning("GeoEngine sin datos — retornando resultado vacio")
            return {"total_value": 0.0, "population_covered": 0, "polygon_count": 0}

        # Proyectar punto de consulta al CRS metrico y crear buffer en metros
        point_m = (
            gpd.GeoSeries([Point(lng, lat)], crs=SOURCE_CRS)
            .to_crs(METRIC_CRS)
            .iloc[0]
        )
        buffer = point_m.buffer(radius_km * 1000)

        # Pre-filtrado rapido con STRtree (puede incluir falsos positivos)
        candidatos_idx = self._sindex.query(buffer, predicate="intersects")
        candidatos = self._gdf.iloc[candidatos_idx]

        mask_within = candidatos.geometry.within(buffer)
        full_polys = candidatos[mask_within]
        partial_polys = candidatos[~mask_within]

        # Poligonos completos — 100% de contribucion
        full_value = float(
            (full_polys["cop_ipm_mhz_hab_anio"] * full_polys["personas"]).sum()
        )
        full_pop = int(full_polys["personas"].sum())

        # Poligonos parciales — ponderados por area solapada, poblacion redondeada arriba
        partial_value = 0.0
        partial_pop = 0
        for _, row in partial_polys.iterrows():
            intersection = row.geometry.intersection(buffer)
            if intersection.is_empty or row.geometry.area == 0:
                continue
            overlap_ratio = intersection.area / row.geometry.area
            weighted_pop = math.ceil(overlap_ratio * row["personas"])
            partial_value += row["cop_ipm_mhz_hab_anio"] * weighted_pop
            partial_pop += weighted_pop

        total_value = full_value + partial_value
        population_covered = full_pop + partial_pop
        polygon_count = len(full_polys) + len(partial_polys)

        # Construir GeoJSON con marca is_partial para el renderizador del mapa
        full_export = full_polys[["geometry", "personas", "cop_ipm_mhz_hab_anio"]].copy()
        full_export["is_partial"] = False
        partial_export = partial_polys[["geometry", "personas", "cop_ipm_mhz_hab_anio"]].copy()
        partial_export["is_partial"] = True

        all_polys = gpd.GeoDataFrame(
            pd.concat([full_export, partial_export], ignore_index=True),
            crs=METRIC_CRS,
        )
        polys_wgs84 = all_polys.to_crs("EPSG:4326")
        polygons_geojson = polys_wgs84.__geo_interface__ if polygon_count > 0 else None

        return {
            "total_value": total_value,
            "population_covered": population_covered,
            "polygon_count": polygon_count,
            "polygons_geojson": polygons_geojson,
        }

    def calculate_multi_coverage(
        self,
        points: list[dict],
        radii: list[float] | None = None,
        val_min: int = 0,
    ) -> dict:
        """Calcula cobertura para multiples puntos con deduplicacion por union.

        Para cada radio, construye la union de todos los buffers y consulta
        el grid una sola vez. Los poligonos solapados entre circulos se cuentan
        exactamente una vez (deduplicacion natural por geometria de union).

        Args:
            points: Lista de dicts con claves 'lat' y 'lng'.
            radii:  Radios a evaluar (km). Por defecto: VALID_RADII (los 3).
            val_min: Piso minimo de valor total (GEOSIGHT_VAL_MIN).

        Returns:
            dict con:
                - points_count (int)
                - results_by_radius (list[dict]): uno por radio, cada uno con:
                    radius_km, raw_total, total_value, population_covered,
                    polygon_count, min_applied, deduplication_adjustment,
                    polygons_geojson, overlap_geojson
        """
        if radii is None:
            radii = self.VALID_RADII

        results_by_radius = []

        for radius_km in radii:
            if radius_km not in self.VALID_RADII:
                raise ValueError(
                    f"Radio invalido: {radius_km} km. "
                    f"Valores permitidos: {self.VALID_RADII}"
                )

            if self._gdf is None:
                results_by_radius.append({
                    "radius_km": radius_km,
                    "raw_total": 0.0,
                    "total_value": 0.0,
                    "population_covered": 0,
                    "polygon_count": 0,
                    "min_applied": False,
                    "deduplication_adjustment": 0.0,
                    "polygons_geojson": None,
                    "overlap_geojson": None,
                })
                continue

            # Proyectar cada punto y construir su buffer para este radio
            buffers = []
            for pt in points:
                point_m = (
                    gpd.GeoSeries([Point(pt["lng"], pt["lat"])], crs=SOURCE_CRS)
                    .to_crs(METRIC_CRS)
                    .iloc[0]
                )
                buffers.append(point_m.buffer(radius_km * 1000))

            union_buffer = buffers[0]
            for b in buffers[1:]:
                union_buffer = union_buffer.union(b)

            # Consultar grid contra la union — cada poligono evaluado una vez
            candidatos_idx = self._sindex.query(union_buffer, predicate="intersects")
            candidatos = self._gdf.iloc[candidatos_idx]

            mask_within = candidatos.geometry.within(union_buffer)
            full_polys = candidatos[mask_within]
            partial_polys = candidatos[~mask_within]

            full_value = float(
                (full_polys["cop_ipm_mhz_hab_anio"] * full_polys["personas"]).sum()
            )
            full_pop = int(full_polys["personas"].sum())

            partial_value = 0.0
            partial_pop = 0
            for _, row in partial_polys.iterrows():
                intersection = row.geometry.intersection(union_buffer)
                if intersection.is_empty or row.geometry.area == 0:
                    continue
                overlap_ratio = intersection.area / row.geometry.area
                weighted_pop = math.ceil(overlap_ratio * row["personas"])
                partial_value += row["cop_ipm_mhz_hab_anio"] * weighted_pop
                partial_pop += weighted_pop

            raw_total = full_value + partial_value
            population_covered = full_pop + partial_pop
            polygon_count = len(full_polys) + len(partial_polys)

            # Calcular ajuste de deduplicacion vs suma de individuales
            individual_sum = 0.0
            for pt in points:
                try:
                    r = self.calculate_coverage(pt["lat"], pt["lng"], radius_km)
                    individual_sum += r["total_value"]
                except ValueError:
                    pass
            deduplication_adjustment = individual_sum - raw_total

            # Zona de solapamiento (interseccion de todos los buffers individuales)
            overlap_geojson = None
            if len(buffers) > 1:
                overlap_geom = buffers[0]
                for b in buffers[1:]:
                    overlap_geom = overlap_geom.intersection(b)
                if not overlap_geom.is_empty:
                    overlap_gs = gpd.GeoSeries([overlap_geom], crs=METRIC_CRS).to_crs("EPSG:4326")
                    overlap_geojson = overlap_gs.__geo_interface__

            # GeoJSON de poligonos para el mapa
            full_export = full_polys[["geometry", "personas", "cop_ipm_mhz_hab_anio"]].copy()
            full_export["is_partial"] = False
            partial_export = partial_polys[["geometry", "personas", "cop_ipm_mhz_hab_anio"]].copy()
            partial_export["is_partial"] = True
            all_polys = gpd.GeoDataFrame(
                pd.concat([full_export, partial_export], ignore_index=True),
                crs=METRIC_CRS,
            )
            polygons_geojson = (
                all_polys.to_crs("EPSG:4326").__geo_interface__ if polygon_count > 0 else None
            )

            final_value = max(raw_total, val_min)
            min_applied = raw_total < val_min

            results_by_radius.append({
                "radius_km": radius_km,
                "raw_total": raw_total,
                "total_value": final_value,
                "population_covered": population_covered,
                "polygon_count": polygon_count,
                "min_applied": min_applied,
                "deduplication_adjustment": deduplication_adjustment,
                "polygons_geojson": polygons_geojson,
                "overlap_geojson": overlap_geojson,
            })

        return {
            "points_count": len(points),
            "results_by_radius": results_by_radius,
        }

    def generate_map(self, assignments: list[dict]) -> str:
        """Genera un mapa Folium con todas las asignaciones superpuestas.

        Args:
            assignments: Lista de dicts con claves:
                nombre (str), lat (float), lng (float),
                radius_km (float), total_value (float), population_covered (int).

        Returns:
            HTML del mapa como string (m._repr_html_()).
            Si assignments esta vacio, retorna mapa centrado en Bogota.
        """
        if assignments:
            center_lat = sum(a["lat"] for a in assignments) / len(assignments)
            center_lng = sum(a["lng"] for a in assignments) / len(assignments)
        else:
            center_lat, center_lng = 4.711, -74.072  # Bogota

        m = folium.Map(
            location=[center_lat, center_lng],
            zoom_start=10,
            tiles="CartoDB dark_matter",
        )

        for a in assignments:
            lat = a["lat"]
            lng = a["lng"]
            nombre = a.get("nombre", "Sin nombre")
            radius_km = a["radius_km"]
            valor = a.get("total_value", 0.0)
            poblacion = a.get("population_covered", 0)

            # Formato COP: punto como separador de miles
            valor_cop = f"${valor:,.0f}".replace(",", ".")

            popup_html = f"""
            <div style="font-family:system-ui,sans-serif;padding:10px 12px;
                        min-width:230px;max-width:280px;">
              <h4 style="margin:0 0 10px;color:#28A745;font-size:14px;
                         border-bottom:1px solid #333;padding-bottom:6px;">
                {nombre}
              </h4>
              <table style="width:100%;border-collapse:collapse;font-size:13px;
                            color:#e0e0e0;">
                <tr>
                  <td style="padding:4px 0;color:#aaa;">Radio</td>
                  <td style="text-align:right;font-weight:600;">{radius_km} km</td>
                </tr>
                <tr>
                  <td style="padding:4px 0;color:#aaa;">Valor COP</td>
                  <td style="text-align:right;font-weight:600;color:#28A745;">
                    {valor_cop}
                  </td>
                </tr>
                <tr>
                  <td style="padding:4px 0;color:#aaa;">Poblacion</td>
                  <td style="text-align:right;font-weight:600;">
                    {poblacion:,}
                  </td>
                </tr>
              </table>
            </div>
            """

            folium.Circle(
                location=[lat, lng],
                radius=radius_km * 1000,
                color="#1B7A4A",
                fill=True,
                fill_color="#28A745",
                fill_opacity=0.2,
                tooltip=folium.Tooltip(nombre, sticky=False),
                popup=folium.Popup(popup_html, max_width=290),
            ).add_to(m)

            # Marcador central con pin azul oscuro
            folium.Marker(
                location=[lat, lng],
                tooltip=nombre,
                icon=folium.DivIcon(
                    html=(
                        '<div style="width:14px;height:14px;background:#1A3C5E;'
                        "border-radius:50%;border:2px solid #fff;"
                        'box-shadow:0 1px 4px rgba(0,0,0,.6);"></div>'
                    ),
                    icon_size=(14, 14),
                    icon_anchor=(7, 7),
                ),
            ).add_to(m)

        if assignments:
            total_global = sum(a.get("total_value", 0) for a in assignments)
            total_cop = f"${total_global:,.0f}".replace(",", ".")
            def _cop(v: float) -> str:
                return f"${v:,.0f}".replace(",", ".")

            filas = "".join(
                f"""<tr>
                  <td style="padding:4px 8px;border-bottom:1px solid #2a2a2a;
                             max-width:120px;overflow:hidden;text-overflow:ellipsis;
                             white-space:nowrap;" title="{a.get('nombre','')}">
                    {a.get('nombre', '—')}
                  </td>
                  <td style="padding:4px 8px;border-bottom:1px solid #2a2a2a;
                             text-align:center;">{a['radius_km']} km</td>
                  <td style="padding:4px 8px;border-bottom:1px solid #2a2a2a;
                             text-align:right;color:#28A745;font-weight:600;">
                    {_cop(a.get('total_value', 0))}
                  </td>
                </tr>"""
                for a in assignments
            )
            # Tabla-leyenda inyectada como elemento HTML en el mapa
            legend = f"""
            <div id="gs-legend" style="
              position:fixed;bottom:24px;right:16px;z-index:9999;
              background:rgba(18,18,18,.92);border:1px solid #2d2d2d;
              border-radius:8px;padding:14px 0 6px;min-width:340px;
              box-shadow:0 4px 16px rgba(0,0,0,.5);
              font-family:system-ui,sans-serif;font-size:12px;color:#e0e0e0;">
              <div style="padding:0 14px 10px;font-weight:700;font-size:13px;
                          color:#28A745;border-bottom:1px solid #2a2a2a;">
                Resumen de asignaciones
              </div>
              <table style="width:100%;border-collapse:collapse;">
                <thead>
                  <tr style="color:#888;font-size:11px;">
                    <th style="padding:6px 8px;text-align:left;font-weight:500;">
                      Nombre
                    </th>
                    <th style="padding:6px 8px;text-align:center;font-weight:500;">
                      Radio
                    </th>
                    <th style="padding:6px 8px;text-align:right;font-weight:500;">
                      Valor COP
                    </th>
                  </tr>
                </thead>
                <tbody>{filas}</tbody>
              </table>
              <div style="padding:8px 14px 4px;text-align:right;
                          border-top:1px solid #2a2a2a;margin-top:4px;">
                <span style="color:#888;font-size:11px;">Total&nbsp;</span>
                <span style="color:#28A745;font-weight:700;font-size:13px;">
                  {total_cop}
                </span>
              </div>
            </div>
            """
            m.get_root().html.add_child(folium.Element(legend))

        return m._repr_html_()
