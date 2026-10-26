"""P-M4-02 and P-M4-03: integration, accumulation and projection of the sample dams (FR-M4-03 to FR-M4-05)."""

from pathlib import Path

import pandas as pd
import pytest

from src.core.projection import EXCEEDED, YEAR
from src.services.bedload import VOLUME_M3, compute_dam_bedload
from src.services.integration import compute_dam_integration, write_integration_csv, write_projection_csv
from src.services.reservoir import compute_dam_curve
from src.services.suspended import compute_suspended
from tests.samples import SAMPLE_ANALYSIS_YEAR, SAMPLE_COMMISSIONING_YEAR, sample_integration_inputs

BENCHMARKS = Path(__file__).parents[1] / "benchmarks"
SAMPLE_DAMS = ["kavsakkaya", "cubuk_1", "cubuk_2"]


def _parts(data, slug):
    """The suspended, bedload and curve results of one dam, and the dam."""
    dam = next(dam for dam in data.project.dams if dam.slug == slug)
    suspended = compute_suspended(data.sub_basins(dam), data.zonal)
    bedload = compute_dam_bedload(data.project, dam)
    curve = compute_dam_curve(data.dam_sheet(dam).data, dam)
    return suspended, bedload, curve, dam


def _result(data, slug):
    suspended, bedload, curve, dam = _parts(data, slug)
    return compute_dam_integration(suspended, bedload, curve, dam)


# --- P-M4-02: annual totals and elevations ----------------------------------------------------


def test_p_m4_02_each_sample_dam_has_its_own_totals(tmp_path):
    data = sample_integration_inputs(tmp_path / "project")

    means = {slug: _result(data, slug).annual["Total_hm3"].mean() for slug in SAMPLE_DAMS}

    assert len(set(means.values())) == 3 and all(mean > 0 for mean in means.values())


def test_p_m4_02_each_water_year_total_is_te_times_suspended_plus_bedload(tmp_path):
    data = sample_integration_inputs(tmp_path / "project")
    data.project.dams[1].trap_efficiency_pct = 80.0
    suspended, bedload, curve, dam = _parts(data, "cubuk_1")

    result = compute_dam_integration(suspended, bedload, curve, dam)

    expected = 0.8 * (suspended.total_volume_m3 + bedload.table[VOLUME_M3]) / 1e6
    assert list(result.annual["Water_Year"]) == list(range(1974, 2013))
    assert list(result.annual["Total_hm3"]) == pytest.approx(list(expected), rel=1e-12)


def test_p_m4_02_the_elevation_of_a_year_is_read_from_the_curve(tmp_path):
    data = sample_integration_inputs(tmp_path / "project")
    _, _, curve, _ = _parts(data, "kavsakkaya")
    result = _result(data, "kavsakkaya")

    expected = [curve.curve.elevation(volume) for volume in result.annual["Total_hm3"]]

    assert list(result.annual["Elevation_m"]) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("slug", SAMPLE_DAMS)
def test_p_m4_02_integration_csv_matches_the_golden(tmp_path, slug):
    data = sample_integration_inputs(tmp_path / "project")

    path = write_integration_csv(_result(data, slug), tmp_path)

    written = pd.read_csv(path, encoding="utf-8-sig")
    golden = pd.read_csv(BENCHMARKS / f"integration_{slug}.csv", encoding="utf-8-sig")
    pd.testing.assert_frame_equal(written, golden, check_exact=False, rtol=1e-9, atol=0)


# --- P-M4-03: accumulation, projection and lifespan -------------------------------------------


def test_p_m4_03_the_accumulation_counts_the_years_before_the_analysis_year(tmp_path):
    data = sample_integration_inputs(tmp_path / "project")

    result = _result(data, "cubuk_2")

    table, record = result.accumulation, set(result.annual["Water_Year"])
    years = list(range(SAMPLE_COMMISSIONING_YEAR, SAMPLE_ANALYSIS_YEAR))
    assert list(table["Year"]) == years
    assert list(table["In_Record"]) == [int(year in record) for year in years]
    outside = sum(year not in record for year in years)
    assert outside > 0 and any(f"{outside} year(s)" in warning for warning in result.warnings)


def test_p_m4_03_the_accumulation_is_the_record_years_plus_the_mean_for_the_rest(tmp_path):
    data = sample_integration_inputs(tmp_path / "project")
    result = _result(data, "kavsakkaya")
    totals = result.annual.set_index("Water_Year")["Total_hm3"]
    years = range(SAMPLE_COMMISSIONING_YEAR, SAMPLE_ANALYSIS_YEAR)

    expected = sum(totals.get(year, totals.mean()) for year in years)

    assert result.accumulated_hm3 == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("slug", SAMPLE_DAMS)
def test_p_m4_03_the_lifespans_are_consistent_with_the_accumulation_and_ordered_by_rate(tmp_path, slug):
    result = _result(sample_integration_inputs(tmp_path / "project"), slug)

    statuses = {lifespan.status for lifespan in result.lifespans.values()}
    if result.accumulated_hm3 >= result.dead_vol_hm3:
        assert statuses == {EXCEEDED} and result.exceeded_year is not None
    else:
        assert statuses == {YEAR} and result.exceeded_year is None
        years = {name: lifespan.year for name, lifespan in result.lifespans.items()}
        assert years["Max"] <= years["Mean"] <= years["Min"]
        assert min(years.values()) > SAMPLE_ANALYSIS_YEAR


@pytest.mark.parametrize("slug", SAMPLE_DAMS)
def test_p_m4_03_projection_csv_matches_the_golden(tmp_path, slug):
    data = sample_integration_inputs(tmp_path / "project")

    path = write_projection_csv(_result(data, slug), tmp_path)

    written = pd.read_csv(path, encoding="utf-8-sig")
    golden = pd.read_csv(BENCHMARKS / f"projection_{slug}.csv", encoding="utf-8-sig")
    pd.testing.assert_frame_equal(written, golden, check_exact=False, rtol=1e-9, atol=0)
