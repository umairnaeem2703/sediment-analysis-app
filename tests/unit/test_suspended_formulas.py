"""U-M2-02, U-M2-03, and the service's per-sub-basin table against the hand calculations (FR-M2-02, B3.1)."""

import pandas as pd
import pytest

from src.core.rusle import YieldCalculator
from src.services.regional import AREA, DAM, SLOPE, SUBBASIN
from src.services.suspended import compute_suspended
from tests.oracle import suspended_cases

CASES = suspended_cases()
NAMES = {1: "Alfa", 2: "Bravo", 3: "Charlie", 4: "Delta", 5: "Echo", 6: "Foxtrot", 7: "Golf"}
REL = 1e-9


def _metrics(case):
    return YieldCalculator().calculate_metrics(case["Zonal_Mean_t_ha_yr"], case["Area_km2"], case["Slope_m_per_m"])


@pytest.mark.parametrize("number", CASES)
def test_u_m2_02_sios_and_gross_mass_match_the_hand_calculation(number):
    case, got = CASES[number], _metrics(CASES[number])

    assert got["gross_mass_t"] == pytest.approx(case["Gross_Mass_t"], rel=REL)
    assert got["usda_scs_sio"] == pytest.approx(case["SIO_USDA_SCS"], rel=REL)
    assert got["cem_sio"] == pytest.approx(case["SIO_CEM"], rel=REL)
    assert got["avg_sio"] == pytest.approx(case["SIO_Average"], rel=REL)


@pytest.mark.parametrize("number", CASES)
def test_u_m2_03_yield_mass_volume_and_specific_yield_match_the_hand_calculation(number):
    case, got = CASES[number], _metrics(CASES[number])

    assert got["yield_mass_t"] == pytest.approx(case["Yield_Mass_t"], rel=REL)
    assert got["volume_m3"] == pytest.approx(case["Volume_m3"], rel=REL)
    assert got["specific_yield_m3_km2"] == pytest.approx(case["Specific_Yield_m3_km2"], rel=REL)


def test_u_m2_03_the_service_table_reports_every_hand_calculated_column_per_sub_basin():
    basins = pd.DataFrame(
        {DAM: "Test Dam", SUBBASIN: [NAMES[n] for n in CASES], AREA: [c["Area_km2"] for c in CASES.values()]}
        | {SLOPE: [c["Slope_m_per_m"] for c in CASES.values()]}
    )
    zonal = pd.DataFrame({SUBBASIN: list(NAMES.values()), "MEAN": [c["Zonal_Mean_t_ha_yr"] for c in CASES.values()]})

    result = compute_suspended(basins, zonal)

    assert list(result.table[SUBBASIN]) == [NAMES[n] for n in CASES]
    for column in (
        "Zonal_Mean_t_ha_yr",
        "Area_km2",
        "Slope_m_per_m",
        "Gross_Mass_t",
        "SIO_USDA_SCS",
        "SIO_CEM",
        "SIO_Average",
        "Yield_Mass_t",
        "Volume_m3",
        "Specific_Yield_m3_km2",
    ):
        assert list(result.table[column]) == pytest.approx([c[column] for c in CASES.values()], rel=REL)
    assert result.total_volume_m3 == pytest.approx(sum(c["Volume_m3"] for c in CASES.values()), rel=REL)
    assert result.warnings == []
