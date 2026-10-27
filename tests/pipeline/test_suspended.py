"""P-M2-01, P-M2-02: the suspended pipeline over the project's dams (FR-M2-03, FR-M2-04)."""

from pathlib import Path

import pandas as pd
import pytest

from src.services.suspended import compute_suspended, write_suspended_csv
from tests.oracle import suspended_cases
from tests.samples import sample_regional

BENCHMARKS = Path(__file__).parents[1] / "benchmarks"
CASES = suspended_cases()
SAMPLE_DAMS = {"kavsakkaya": 1, "cubuk_1": 2, "cubuk_2": 3}  # dam slug -> the oracle case with its numbers
HEADER = "Dam Name,Basin Name,Sub-basin Name,Drainage Area (km2),Main Waterway Slope\n"


def _result(data, dam):
    return compute_suspended(data.sub_basins(dam), data.zonal, "raw_zonal_means.csv")


def test_p_m2_01_each_sample_dam_has_its_own_total(tmp_path):
    data = sample_regional(tmp_path / "project")

    totals = {dam.slug: _result(data, dam).total_volume_m3 for dam in data.project.dams}

    assert list(totals) == list(SAMPLE_DAMS)
    for slug, case in SAMPLE_DAMS.items():
        assert totals[slug] == pytest.approx(CASES[case]["Volume_m3"], rel=1e-9)
    assert len(set(totals.values())) == 3


def test_p_m2_01_a_dam_totals_only_its_own_sub_basins(tmp_path):
    # A dam with two sub-basins next to a dam with one: the totals must not mix.
    rows = [
        ("Alpha", "Delta Alt Havzası", CASES[4]),
        ("Alpha", "Echo Alt Havzası", CASES[5]),
        ("Beta", "Foxtrot Alt Havzası", CASES[6]),
    ]
    table = tmp_path / "basins.csv"
    table.write_text(
        HEADER + "".join(f"{d},Basin,{s},{c['Area_km2']},{c['Slope_m_per_m']}\n" for d, s, c in rows), encoding="utf-8"
    )
    zonal = tmp_path / "zonal.csv"
    zonal.write_text(
        "Sub-basin Name,MEAN\n" + "".join(f"{s},{c['Zonal_Mean_t_ha_yr']}\n" for _, s, c in rows), encoding="utf-8"
    )
    data = sample_regional(tmp_path / "project")
    data.import_basin_table(table)
    data.import_zonal_means(zonal)

    totals = {dam.slug: _result(data, dam).total_volume_m3 for dam in data.project.dams}

    assert totals["alpha"] == pytest.approx(CASES[4]["Volume_m3"] + CASES[5]["Volume_m3"], rel=1e-9)
    assert totals["beta"] == pytest.approx(CASES[6]["Volume_m3"], rel=1e-9)


@pytest.mark.parametrize("slug", SAMPLE_DAMS)
def test_p_m2_02_suspended_csv_matches_the_golden(tmp_path, slug):
    data = sample_regional(tmp_path / "project")
    dam = next(dam for dam in data.project.dams if dam.slug == slug)

    path = write_suspended_csv(_result(data, dam), tmp_path)

    written = pd.read_csv(path, encoding="utf-8-sig")
    golden = pd.read_csv(BENCHMARKS / f"suspended_{slug}.csv", encoding="utf-8-sig")
    pd.testing.assert_frame_equal(written, golden, check_exact=False, rtol=1e-9, atol=0)


def test_p_m2_01_the_whole_three_dam_table_can_not_be_totalled_as_one_dam(tmp_path):
    data = sample_regional(tmp_path / "project")

    with pytest.raises(ValueError, match="one dam at a time"):
        compute_suspended(data.basin_table, data.zonal, "raw_zonal_means.csv")
