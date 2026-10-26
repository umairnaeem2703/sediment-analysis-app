"""P-M5-01 to P-M5-03: the run folder, the workbook and run.json of the sample dams (FR-M5-02, FR-M5-03, NFR-04)."""

import datetime
import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from src import __version__
from src.services import run_export
from src.services.project import Project
from src.services.regional_data import RegionalData
from src.services.reservoir import compute_curve, curve_inputs
from src.services.run_export import export_run
from tests.samples import sample_dam_results, sample_integration_inputs

BENCHMARKS = Path(__file__).parents[1] / "benchmarks"
SAMPLE_DAMS = ["kavsakkaya", "cubuk_1", "cubuk_2"]
NOW = datetime.datetime(2026, 10, 26, 14, 30, 5)
SHEETS = ["Inputs", "Suspended", "Bedload", "Annual", "Curve", "Projection", "Extremes", "Warnings"]
FILES = {
    "results.xlsx",
    "run.json",
    "suspended.csv",
    "bedload.csv",
    "reservoir_curve.csv",
    "integration.csv",
    "projection.csv",
    "bedload_trend.png",
    "annual_volume.png",
    "reservoir_curve.png",
    "projection.png",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@pytest.fixture(scope="module")
def shared(tmp_path_factory):
    """The sample project and the results of each sample dam, computed once. Tests export into a copy of the project."""
    folder = tmp_path_factory.mktemp("samples") / "project"
    data = sample_integration_inputs(folder)
    return folder, {slug: sample_dam_results(data, slug)[1:] for slug in SAMPLE_DAMS}


def _copy(shared, tmp_path, slug):
    """A copy of the shared project, with the dam of `slug` in it and the dam's suspended, bedload, curve and
    integration results."""
    folder = tmp_path / "project"
    shutil.copytree(shared[0], folder)
    project = Project.open(folder)
    return project, next(dam for dam in project.dams if dam.slug == slug), *shared[1][slug]


def _run(shared, tmp_path, slug="cubuk_2", now=NOW, input_warnings=()):
    """Export the run of one sample dam; returns the project, the dam with its results, and the export."""
    project, *parts = _copy(shared, tmp_path, slug)
    return project, parts, export_run(project, *parts, input_warnings=input_warnings, now=now)


def _sheet(export, name, **kwargs):
    return pd.read_excel(export.folder / "results.xlsx", sheet_name=name, **kwargs)


def _golden(name, slug):
    return pd.read_csv(BENCHMARKS / f"{name}_{slug}.csv", encoding="utf-8-sig")


# --- P-M5-01: the run folder -----------------------------------------------------------------


def test_p_m5_01_the_run_folder_is_named_for_the_dam_and_the_minute(shared, tmp_path):
    project, _, export = _run(shared, tmp_path)

    assert export.folder == project.folder / "outputs" / "cubuk_2_20261026_1430"
    assert export.folder.is_dir()


def test_p_m5_01_the_folder_holds_the_workbook_the_charts_one_csv_per_phase_and_run_json(shared, tmp_path):
    _, _, export = _run(shared, tmp_path)

    assert {path.name for path in export.folder.iterdir()} == FILES
    assert {path.name for path in export.files} == FILES and all(path.parent == export.folder for path in export.files)


def test_p_m5_01_the_charts_are_png_files(shared, tmp_path):
    _, _, export = _run(shared, tmp_path)

    for name in ("bedload_trend.png", "annual_volume.png", "reservoir_curve.png", "projection.png"):
        assert (export.folder / name).read_bytes()[:8] == PNG_SIGNATURE


@pytest.mark.parametrize(
    "name, golden",
    [
        ("suspended.csv", "suspended"),
        ("bedload.csv", "bedload"),
        ("reservoir_curve.csv", "reservoir"),
        ("integration.csv", "integration"),
        ("projection.csv", "projection"),
    ],
)
@pytest.mark.parametrize("slug", SAMPLE_DAMS)
def test_p_m5_01_each_csv_matches_the_golden_of_its_phase(shared, tmp_path, slug, name, golden):
    _, _, export = _run(shared, tmp_path, slug)

    written = pd.read_csv(export.folder / name, encoding="utf-8-sig")

    pd.testing.assert_frame_equal(written, _golden(golden, slug), check_exact=False, rtol=1e-9, atol=0)


def test_p_m5_01_a_run_never_overwrites_another_run(shared, tmp_path):
    project, *parts = _copy(shared, tmp_path, "cubuk_1")
    first = export_run(project, *parts, now=NOW)
    before = (first.folder / "run.json").read_bytes()

    second = export_run(project, *parts, now=NOW)
    third = export_run(project, *parts, now=NOW)

    assert [first.folder.name, second.folder.name, third.folder.name] == [
        "cubuk_1_20261026_1430",
        "cubuk_1_20261026_1430_2",
        "cubuk_1_20261026_1430_3",
    ]
    assert (first.folder / "run.json").read_bytes() == before


def test_p_m5_01_a_missing_input_is_an_error_naming_it_and_leaves_no_run_folder(shared, tmp_path):
    project, dam, *results = _copy(shared, tmp_path, "cubuk_1")
    (project.folder / dam.flow.path).unlink()

    with pytest.raises(ValueError, match="cubuk_1_flow"):
        export_run(project, dam, *results, now=NOW)

    assert list((project.folder / "outputs").iterdir()) == []


def test_p_m5_01_a_run_that_fails_while_writing_leaves_no_run_folder(shared, tmp_path, monkeypatch):
    project, *parts = _copy(shared, tmp_path, "cubuk_1")

    def disk_full(*_):
        raise OSError("disk full")

    monkeypatch.setattr(run_export, "write_projection", disk_full)  # the last chart

    with pytest.raises(OSError, match="disk full"):
        export_run(project, *parts, now=NOW)

    assert list((project.folder / "outputs").iterdir()) == []


# --- P-M5-02: the workbook --------------------------------------------------------------------


def test_p_m5_02_the_workbook_has_the_eight_sheets_in_order(shared, tmp_path):
    _, _, export = _run(shared, tmp_path)

    assert list(pd.read_excel(export.folder / "results.xlsx", sheet_name=None)) == SHEETS


@pytest.mark.parametrize(
    "sheet, golden",
    [
        ("Suspended", "suspended"),
        ("Bedload", "bedload"),
        ("Curve", "reservoir"),
        ("Annual", "integration"),
        ("Projection", "projection"),
    ],
)
@pytest.mark.parametrize("slug", SAMPLE_DAMS)
def test_p_m5_02_each_result_sheet_matches_the_golden_of_its_phase(shared, tmp_path, slug, sheet, golden):
    _, _, export = _run(shared, tmp_path, slug)

    pd.testing.assert_frame_equal(
        _sheet(export, sheet), _golden(golden, slug), check_exact=False, rtol=1e-9, atol=0, check_dtype=False
    )


def test_p_m5_02_the_extremes_sheet_gives_the_year_total_and_elevation_of_each_extreme(shared, tmp_path):
    _, (_, _, _, _, integration), export = _run(shared, tmp_path)
    annual = integration.annual

    table = _sheet(export, "Extremes", nrows=2)

    assert list(table.columns) == ["Extreme", "Year", "Total_hm3", "Elevation_m"]
    assert list(table["Extreme"]) == ["Minimum", "Maximum"]
    for position, row in ((0, annual.loc[annual["Total_hm3"].idxmin()]), (1, annual.loc[annual["Total_hm3"].idxmax()])):
        assert table["Year"][position] == row["Water_Year"]
        assert table["Total_hm3"][position] == pytest.approx(row["Total_hm3"], rel=1e-12)
        assert table["Elevation_m"][position] == pytest.approx(row["Elevation_m"], rel=1e-12)


def test_p_m5_02_the_extremes_sheet_also_holds_the_accumulation_and_the_lifespans(shared, tmp_path):
    _, (_, _, _, _, integration), export = _run(shared, tmp_path)

    summary = _sheet(export, "Extremes", header=4, usecols="A:C").set_index("Item")

    assert list(summary.columns) == ["Value", "Unit"]
    assert summary.loc["Accumulated to date", "Value"] == pytest.approx(integration.accumulated_hm3, rel=1e-12)
    assert summary.loc["Accumulated to date", "Unit"] == "hm³"
    assert summary.loc["Dead volume", "Value"] == pytest.approx(integration.dead_vol_hm3, rel=1e-12)
    assert summary.loc["Annual total, mean", "Value"] == pytest.approx(integration.rates["Mean"], rel=1e-12)
    for name in ("Mean", "Min", "Max"):
        assert f"Lifespan, {name} rate" in summary.index


def test_p_m5_02_the_lifespan_rows_say_when_the_dead_volume_was_already_exceeded(shared, tmp_path):
    _, (_, _, _, _, integration), export = _run(shared, tmp_path, "cubuk_1")  # filled long before 2020

    summary = _sheet(export, "Extremes", header=4, usecols="A:C").set_index("Item")

    assert integration.exceeded_year is not None
    assert str(integration.exceeded_year) in summary.loc["Lifespan, Mean rate", "Value"]
    assert "exceeded" in summary.loc["Lifespan, Mean rate", "Value"]


def test_p_m5_02_an_exceeded_dead_volume_without_a_year_is_still_stated(shared, tmp_path):
    project, dam, suspended, bedload, curve, integration = _copy(shared, tmp_path, "cubuk_1")

    export = export_run(project, dam, suspended, bedload, curve, integration._replace(exceeded_year=None), now=NOW)

    summary = _sheet(export, "Extremes", header=4, usecols="A:C").set_index("Item")
    assert summary.loc["Lifespan, Mean rate", "Value"] == "Already exceeded"


def test_p_m5_02_the_inputs_sheet_lists_the_parameters_and_the_hashed_files(shared, tmp_path):
    project, (dam, *_), export = _run(shared, tmp_path, "cubuk_1")

    table = _sheet(export, "Inputs")

    assert list(table.columns) == ["Group", "Item", "Value", "Unit", "SHA-256"]
    parameters = table[table["Group"] == "Parameter"].set_index("Item")
    assert parameters.loc["Sigma", "Value"] == dam.flow.sigma
    assert parameters.loc["Trap efficiency", "Unit"] == "%"
    files = table[table["Group"] == "File"].set_index("Item")
    assert set(files.index) == {"basins", "zonal_means", "fractions", "dam_sheet", "flow"}
    flow = (project.folder / dam.flow.path).read_bytes()
    assert files.loc["flow", "SHA-256"] == hashlib.sha256(flow).hexdigest()


def test_p_m5_02_the_warnings_sheet_has_every_warning_with_its_phase(shared, tmp_path):
    _, (_, suspended, bedload, curve, integration), export = _run(
        shared, tmp_path, "cubuk_2", input_warnings=["Dam sheet: area check."]
    )

    table = _sheet(export, "Warnings")

    assert list(table.columns) == ["Phase", "Warning"]
    expected = [("Inputs", "Dam sheet: area check.")]
    for phase, warnings in (
        ("Suspended", suspended.warnings),
        ("Bedload", bedload.warnings),
        ("Reservoir curve", curve.warnings),
        ("Integration", integration.warnings),
    ):
        expected += [(phase, text) for text in warnings]
    assert list(zip(table["Phase"], table["Warning"])) == expected
    assert any(phase == "Integration" for phase, _ in expected)  # cubuk_2 has years outside its record


def test_p_m5_02_a_run_without_warnings_still_has_the_headed_warnings_sheet(shared, tmp_path):
    project, dam, *results = _copy(shared, tmp_path, "kavsakkaya")
    quiet = [result._replace(warnings=[]) for result in results]

    export = export_run(project, dam, *quiet, now=NOW)

    table = _sheet(export, "Warnings")
    assert list(table.columns) == ["Phase", "Warning"] and table.empty


def test_p_m5_02_text_that_starts_with_an_equals_sign_stays_text(shared, tmp_path):
    _, _, export = _run(shared, tmp_path, input_warnings=["=1+1"])

    table = _sheet(export, "Warnings")

    assert table["Warning"][0] == "=1+1"


# --- P-M5-03: run.json ------------------------------------------------------------------------


def _json(export):
    return json.loads((export.folder / "run.json").read_text(encoding="utf-8"))


def _parameters(export):
    return {entry["name"]: entry for entry in _json(export)["parameters"]}


def test_p_m5_03_run_json_names_the_version_the_time_the_project_and_the_dam(shared, tmp_path):
    _, _, export = _run(shared, tmp_path)

    run = _json(export)

    assert run["app_version"] == __version__ == "1.0.0"
    assert run["timestamp"] == "2026-10-26T14:30:05"
    assert run["project"] == "Samples"
    assert run["dam"] == {"name": "Çubuk 2", "slug": "cubuk_2"}


def test_p_m5_03_run_json_gives_the_sha_256_of_every_input(shared, tmp_path):
    project, (dam, *_), export = _run(shared, tmp_path)

    inputs = {entry["role"]: entry for entry in _json(export)["inputs"]}

    assert set(inputs) == {"basins", "zonal_means", "fractions", "dam_sheet", "flow"}
    paths = {**project.inputs, "dam_sheet": dam.sheet, "flow": dam.flow.path}
    for role, entry in inputs.items():
        assert entry["path"] == paths[role]
        assert entry["sha256"] == hashlib.sha256((project.folder / entry["path"]).read_bytes()).hexdigest()


def test_p_m5_03_run_json_records_the_parameters_with_sigma_phi_and_seed(tmp_path):
    data = sample_integration_inputs(tmp_path / "project")
    dam = data.project.dams[1]
    dam.flow.sigma, dam.flow.phi, dam.flow.seed = 0.4, 0.3, 7
    dam.trap_efficiency_pct = 80.0
    _, suspended, bedload, curve, integration = sample_dam_results(data, dam.slug)

    export = export_run(data.project, dam, suspended, bedload, curve, integration, now=NOW)

    parameters = _parameters(export)
    assert (parameters["Sigma"]["value"], parameters["Phi"]["value"], parameters["Seed"]["value"]) == (0.4, 0.3, 7)
    assert parameters["Trap efficiency"] == {"name": "Trap efficiency", "value": 80.0, "unit": "%"}
    assert parameters["Commissioning year"]["value"] == 1990 and parameters["Analysis year"]["value"] == 2020
    assert parameters["Projection length"] == {"name": "Projection length", "value": 100, "unit": "years"}
    assert parameters["Level interval"] == {"name": "Level interval", "value": 0.5, "unit": "m"}
    assert parameters["Exponent m"]["value"] == pytest.approx(curve.curve.exponent)
    for name in ("Hbed", "Hmin", "Hmin of the curve", "Hmax", "Hcrest", "Vactive", "Vmax", "Vdead"):
        assert name in parameters


def test_p_m5_03_run_json_records_the_level_interval_that_was_entered(shared, tmp_path):
    project, dam, suspended, bedload, curve, integration = _copy(shared, tmp_path, "cubuk_1")
    sheet = RegionalData(project).dam_sheet(dam).data
    wide = compute_curve(curve_inputs(sheet, dam), sheet.drainage_area_km2, 1000.0)  # wider than the dam: bed and crest
    assert len(wide.table) == 2

    export = export_run(project, dam, suspended, bedload, wide, integration, now=NOW)

    assert _parameters(export)["Level interval"]["value"] == 1000.0


def test_p_m5_03_run_json_records_hmin_as_entered_apart_from_the_one_of_the_curve(shared, tmp_path):
    project, dam, suspended, bedload, curve, integration = _copy(shared, tmp_path, "cubuk_1")
    without = export_run(project, dam, suspended, bedload, curve, integration, now=NOW)
    dam.h_min_m = 892.5

    entered = export_run(project, dam, suspended, bedload, curve, integration, now=NOW)

    assert _parameters(without)["Hmin"]["value"] is None  # the shape class fixed the curve
    assert _parameters(entered)["Hmin"]["value"] == 892.5
    assert _parameters(entered)["Hmin of the curve"]["value"] == pytest.approx(curve.curve.h_min_m, rel=1e-12)


def test_p_m5_03_run_json_records_the_flags(shared, tmp_path):
    _, _, export = _run(shared, tmp_path, "cubuk_2")

    flags = _json(export)["flags"]

    assert flags == {"synthetic_flow": True, "h_min_given": False, "shape_class": "hill"}


def test_p_m5_03_run_json_has_every_warning_the_workbook_has(shared, tmp_path):
    _, _, export = _run(shared, tmp_path, "cubuk_2", input_warnings=["Dam sheet: area check."])

    warnings = _json(export)["warnings"]
    sheet = _sheet(export, "Warnings")

    assert [(entry["phase"], entry["text"]) for entry in warnings] == list(zip(sheet["Phase"], sheet["Warning"]))
    assert {"phase": "Inputs", "text": "Dam sheet: area check."} in warnings


def test_x_nfr_03_the_same_inputs_give_the_same_run_json_and_workbook_sheets(shared, tmp_path):
    project, *parts = _copy(shared, tmp_path, "kavsakkaya")

    first = export_run(project, *parts, now=NOW)
    second = export_run(project, *parts, now=NOW)

    assert _json(first) == _json(second)
    for sheet in SHEETS:
        pd.testing.assert_frame_equal(_sheet(first, sheet), _sheet(second, sheet))
