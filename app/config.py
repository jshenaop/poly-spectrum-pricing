"""Centralized configuration and startup validation for GeoSight.

All environment variables are parsed and validated here. Invalid values
produce a descriptive error and halt startup (SystemExit) rather than
causing silent runtime failures.
"""
import os
import sys
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Settings:
    grid_data: str    # GEOSIGHT_GRID_DATA — GeoJSON filename (no path separators)
    data_path: Path   # GEOSIGHT_DATA_PATH — directory containing the grid file
    val_min: int      # GEOSIGHT_VAL_MIN   — minimum spectrum value floor (>= 0)
    max_points: int   # GEOSIGHT_MAX_POINTS — max (lat,lng) pairs per request (>= 1)
    log_level: str
    env: str


def load_settings() -> Settings:
    """Parse and validate all GeoSight environment variables.

    Raises SystemExit with a descriptive message if any value is invalid.
    """
    grid_data = os.getenv("GEOSIGHT_GRID_DATA", "n6_1k_aniop_ipm.geojson")
    if "/" in grid_data or "\\" in grid_data:
        sys.exit(
            f"[GeoSight] GEOSIGHT_GRID_DATA must be a filename only (no path separators). "
            f"Got: '{grid_data}'. Use GEOSIGHT_DATA_PATH for the directory."
        )

    data_path = Path(os.getenv("GEOSIGHT_DATA_PATH", "./app/data")).resolve()
    if not data_path.is_dir():
        sys.exit(
            f"[GeoSight] GEOSIGHT_DATA_PATH '{data_path}' does not exist or is not a directory."
        )

    raw_val_min = os.getenv("GEOSIGHT_VAL_MIN", "0")
    try:
        val_min = int(raw_val_min)
        if val_min < 0:
            raise ValueError
    except ValueError:
        sys.exit(
            f"[GeoSight] GEOSIGHT_VAL_MIN must be a non-negative integer. Got: '{raw_val_min}'."
        )

    raw_max_points = os.getenv("GEOSIGHT_MAX_POINTS", "5")
    try:
        max_points = int(raw_max_points)
        if max_points < 1:
            raise ValueError
    except ValueError:
        sys.exit(
            f"[GeoSight] GEOSIGHT_MAX_POINTS must be a positive integer (>= 1). Got: '{raw_max_points}'."
        )

    return Settings(
        grid_data=grid_data,
        data_path=data_path,
        val_min=val_min,
        max_points=max_points,
        log_level=os.getenv("GEOSIGHT_LOG_LEVEL", "INFO").upper(),
        env=os.getenv("GEOSIGHT_ENV", "development"),
    )
