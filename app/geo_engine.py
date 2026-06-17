import math
import logging

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

    VALID_RADII = [8.23, 21.94, 35.85]  # km — radios v1
    VALID_RADII_V2 = [8.2, 21.9, 35.8]  # km — radios v2

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

    def calculate_coverage(
        self,
        lat: float,
        lng: float,
        radius_km: float,
        allowed_radii: list[float] | None = None,
    ) -> dict:
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
        radii = allowed_radii or self.VALID_RADII
        if radius_km not in radii:
            raise ValueError(
                f"Radio invalido: {radius_km} km. "
                f"Valores permitidos: {radii}"
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
        val_min: int = 0,
        allowed_radii: list[float] | None = None,
    ) -> dict:
        """Calcula cobertura para multiples puntos con deduplicacion por union.

        Cada punto lleva su propio radio. Se construye la union de todos los
        buffers y se consulta el grid una sola vez. Los poligonos solapados
        entre circulos se cuentan exactamente una vez (deduplicacion natural).

        Args:
            points: Lista de dicts con claves 'lat', 'lng' y 'radius_km'.
            val_min: Piso minimo de valor total (GEOSIGHT_VAL_MIN).

        Returns:
            dict con: points_count, raw_total, total_value, population_covered,
            polygon_count, min_applied, deduplication_adjustment,
            polygons_geojson, overlap_geojson.
        """
        empty_result = {
            "points_count": len(points),
            "raw_total": 0.0,
            "total_value": 0.0,
            "population_covered": 0,
            "polygon_count": 0,
            "min_applied": False,
            "deduplication_adjustment": 0.0,
            "polygons_geojson": None,
            "overlap_geojson": None,
        }

        # Validar radios
        radii = allowed_radii or self.VALID_RADII
        for pt in points:
            radius_km = pt["radius_km"]
            if radius_km not in radii:
                raise ValueError(
                    f"Radio invalido: {radius_km} km. "
                    f"Valores permitidos: {radii}"
                )

        if self._gdf is None:
            return empty_result

        # Proyectar cada punto y construir su buffer con su propio radio
        buffers = []
        for pt in points:
            point_m = (
                gpd.GeoSeries([Point(pt["lng"], pt["lat"])], crs=SOURCE_CRS)
                .to_crs(METRIC_CRS)
                .iloc[0]
            )
            buffers.append(point_m.buffer(pt["radius_km"] * 1000))

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

        # Ajuste de deduplicacion: suma individual - valor union
        individual_sum = 0.0
        for pt in points:
            try:
                r = self.calculate_coverage(pt["lat"], pt["lng"], pt["radius_km"], allowed_radii=radii)
                individual_sum += r["total_value"]
            except ValueError:
                pass
        deduplication_adjustment = individual_sum - raw_total

        # Zona de solapamiento (interseccion de todos los buffers)
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

        return {
            "points_count": len(points),
            "raw_total": raw_total,
            "total_value": final_value,
            "population_covered": population_covered,
            "polygon_count": polygon_count,
            "min_applied": min_applied,
            "deduplication_adjustment": deduplication_adjustment,
            "polygons_geojson": polygons_geojson,
            "overlap_geojson": overlap_geojson,
        }
