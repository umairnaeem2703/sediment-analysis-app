from pathlib import Path

import numpy as np
import pandas as pd

from paths import load_raster_matrix, resource_path
from rusle_engine import HA_PER_KM2, SpatialProcessor, YieldCalculator


def test_digitize_20_is_class_4():
    processor = SpatialProcessor()
    classified = processor.classify_5_classes(np.array([[20.0]]))
    assert classified[0, 0] == 4


def test_class_5_is_strictly_above_20():
    processor = SpatialProcessor()
    classified = processor.classify_5_classes(np.array([[20.0001, 21.0]]))
    assert classified.tolist() == [[5, 5]]


def test_fixture_matrix_classification_and_lut_shape():
    raster = load_raster_matrix(resource_path("inputs", "test_raster_matrix.csv"))
    processor = SpatialProcessor()
    classes = processor.classify_5_classes(raster)
    rgb = processor.apply_5_class_colormap(raster)
    assert raster.shape == (5, 5)
    assert classes[3, 3] == 4  # 20.0
    assert rgb.shape == (5, 5, 3)
    assert rgb.dtype == np.uint8


def test_cem_sio_uses_decimal_slope_not_percent():
    calc = YieldCalculator()
    slope = 0.015
    expected = 1.0 / (2.05823 + 0.02816 * slope**2)
    percent_form = 1.0 / (2.05823 + 0.02816 * (slope * 100.0) ** 2)
    assert np.isclose(calc.calculate_cem_sio(slope), expected)
    assert not np.isclose(calc.calculate_cem_sio(slope), percent_form)


def test_gross_mass_uses_hectares():
    calc = YieldCalculator()
    mean = 2.0
    area_km2 = 1.5
    metrics = calc.calculate_metrics(mean, area_km2, slope=0.015)
    assert metrics["area_ha"] == area_km2 * HA_PER_KM2
    assert np.isclose(metrics["gross_mass_t"], mean * area_km2 * HA_PER_KM2)


def test_rgb_tiff_export(tmp_path: Path):
    processor = SpatialProcessor()
    rgb = processor.apply_5_class_colormap(np.array([[0.5, 21.0], [20.0, 9.0]]))
    dest = tmp_path / "map.tif"
    processor.export_rgb_tiff(rgb, str(dest))
    assert dest.exists()
    assert dest.stat().st_size > 0


def test_phase2_schema():
    df = YieldCalculator().to_phase2_handoff(2020, 123.4)
    assert list(df.columns) == ["Year", "Suspended_Volume_m3"]
    assert df.iloc[0]["Year"] == 2020
