"""Tests for app/config.py — env var validation and GeoJSON startup checks."""
from pathlib import Path
import pytest
from app.config import load_settings


def test_defaults_are_correct(monkeypatch, tmp_path):
    monkeypatch.delenv("GEOSIGHT_GRID_DATA", raising=False)
    monkeypatch.setenv("GEOSIGHT_DATA_PATH", str(tmp_path))
    monkeypatch.delenv("GEOSIGHT_VAL_MIN", raising=False)
    monkeypatch.delenv("GEOSIGHT_MAX_POINTS", raising=False)
    monkeypatch.delenv("GEOSIGHT_LOG_LEVEL", raising=False)
    monkeypatch.delenv("GEOSIGHT_ENV", raising=False)

    s = load_settings()
    assert s.grid_data == "n6_1k_aniop_ipm.geojson"
    assert s.data_path == tmp_path.resolve()
    assert s.val_min == 0
    assert s.max_points == 5
    assert s.log_level == "INFO"
    assert s.env == "development"


def test_val_min_must_be_non_negative(monkeypatch):
    monkeypatch.setenv("GEOSIGHT_VAL_MIN", "-1")
    with pytest.raises(SystemExit):
        load_settings()


def test_val_min_must_be_integer(monkeypatch):
    monkeypatch.setenv("GEOSIGHT_VAL_MIN", "abc")
    with pytest.raises(SystemExit):
        load_settings()


def test_max_points_must_be_positive(monkeypatch):
    monkeypatch.setenv("GEOSIGHT_MAX_POINTS", "0")
    with pytest.raises(SystemExit):
        load_settings()


def test_grid_data_no_path_separator_forward_slash(monkeypatch):
    monkeypatch.setenv("GEOSIGHT_GRID_DATA", "some/dir/file.geojson")
    with pytest.raises(SystemExit):
        load_settings()


def test_grid_data_no_path_separator_backslash(monkeypatch):
    monkeypatch.setenv("GEOSIGHT_GRID_DATA", "some\\file.geojson")
    with pytest.raises(SystemExit):
        load_settings()


def test_val_min_zero_is_valid(monkeypatch):
    monkeypatch.setenv("GEOSIGHT_VAL_MIN", "0")
    s = load_settings()
    assert s.val_min == 0


def test_custom_values_parsed_correctly(monkeypatch):
    monkeypatch.setenv("GEOSIGHT_GRID_DATA", "my_grid_v2.geojson")
    monkeypatch.setenv("GEOSIGHT_VAL_MIN", "500000")
    monkeypatch.setenv("GEOSIGHT_MAX_POINTS", "3")
    s = load_settings()
    assert s.grid_data == "my_grid_v2.geojson"
    assert s.val_min == 500000
    assert s.max_points == 3
