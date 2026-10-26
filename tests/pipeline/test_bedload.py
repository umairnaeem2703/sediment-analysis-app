"""P-M3-01: the bedload pipeline over the project's dams (FR-M3-01, FR-M3-04, FR-M3-05)."""

from pathlib import Path

import pandas as pd
import pytest

from src.core.wilcock import WATER_YEAR_COLUMN
from src.services.bedload import VALUE_COLUMNS, compute_dam_bedload, import_fractions, write_bedload_csv
from tests.samples import sample_bedload_inputs, write_fractions_with_wrong_tau_ri

BENCHMARKS = Path(__file__).parents[1] / "benchmarks"
SAMPLE_DAMS = ["kavsakkaya", "cubuk_1", "cubuk_2"]


def _result(data, slug):
    dam = next(dam for dam in data.project.dams if dam.slug == slug)
    return compute_dam_bedload(data.project, dam)


def test_p_m3_01_each_sample_dam_has_its_own_bedload(tmp_path):
    data = sample_bedload_inputs(tmp_path / "project")

    means = {slug: _result(data, slug).mean_volume_m3_yr for slug in SAMPLE_DAMS}

    assert len(set(means.values())) == 3
    assert all(mean > 0 for mean in means.values())


def test_p_m3_01_the_sample_dams_are_flagged_synthetic_and_cover_water_years_1974_to_2012(tmp_path):
    data = sample_bedload_inputs(tmp_path / "project")

    for slug in SAMPLE_DAMS:
        result = _result(data, slug)
        assert result.synthetic and len(result.notes) == 1
        assert result.year_column == WATER_YEAR_COLUMN
        assert list(result.table[WATER_YEAR_COLUMN]) == list(range(1974, 2013))
        assert (result.table[VALUE_COLUMNS[2]] >= 0).all()


def test_p_m3_01_the_mass_is_the_volume_times_the_density_of_the_sediment(tmp_path):
    result = _result(sample_bedload_inputs(tmp_path / "project"), "cubuk_1")

    assert list(result.table["Mass_t_yr"]) == pytest.approx(list(result.table["Volume_m3_yr"] * 2.65), rel=1e-12)


def test_p_m3_01_the_fractions_cross_check_reaches_the_result(tmp_path):
    data = sample_bedload_inputs(tmp_path / "project")
    assert _result(data, "cubuk_2").warnings == []  # the sample agrees with the formula (D50)

    import_fractions(data.project, write_fractions_with_wrong_tau_ri(tmp_path))

    warnings = _result(data, "cubuk_2").warnings
    assert len(warnings) == 5 and all("fractions.csv" in warning for warning in warnings)


@pytest.mark.parametrize("slug", SAMPLE_DAMS)
def test_p_m3_01_bedload_csv_matches_the_golden(tmp_path, slug):
    data = sample_bedload_inputs(tmp_path / "project")

    path = write_bedload_csv(_result(data, slug), tmp_path)

    written = pd.read_csv(path, encoding="utf-8-sig")
    golden = pd.read_csv(BENCHMARKS / f"bedload_{slug}.csv", encoding="utf-8-sig")
    pd.testing.assert_frame_equal(written, golden, check_exact=False, rtol=1e-9, atol=0)
