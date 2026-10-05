from rusle_engine import HA_PER_KM2, YieldCalculator
import numpy as np


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


def test_phase2_schema():
    df = YieldCalculator().to_phase2_handoff(2020, 123.4)
    assert list(df.columns) == ["Year", "Suspended_Volume_m3"]
    assert df.iloc[0]["Year"] == 2020
