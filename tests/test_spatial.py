import numpy as np

from src.core.rusle import HA_PER_KM2, YieldCalculator


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


def test_zonal_matcher_normalization_and_aliases():
    from src.core.rusle import ZonalMatcher

    assert ZonalMatcher.normalize_subbasin_name("Subbasin_12") == "12"
    assert ZonalMatcher.normalize_subbasin_name("SB-5") == "5"
    assert ZonalMatcher.normalize_subbasin_name("Basin 3A") == "3a"
    assert ZonalMatcher.normalize_subbasin_name(4.0) == "4"

    aliases = ZonalMatcher.get_subbasin_aliases("Subbasin 12")
    assert "12" in aliases


def test_zonal_matcher_build_lookup_and_resolution():
    import pandas as pd
    from src.core.rusle import ZonalMatcher

    df = pd.DataFrame(
        {
            "Subbasin Name": ["Subbasin 1", "Subbasin 2", "SB-3"],
            "MEAN": [1.25, 3.40, 2.10],
        }
    )
    lookup = ZonalMatcher.build_lookup(df)
    assert ZonalMatcher.resolve_zonal_mean(lookup, "1") == 1.25
    assert ZonalMatcher.resolve_zonal_mean(lookup, "Subbasin 2") == 3.40
    assert ZonalMatcher.resolve_zonal_mean(lookup, "Sub-basin 3") == 2.10
    assert ZonalMatcher.resolve_zonal_mean(lookup, "Unknown") is None

