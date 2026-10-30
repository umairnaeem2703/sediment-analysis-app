import tkinter as tk

import pytest

from src.ui.steps.bedload_step import BedloadStep
from src.ui.steps.dam_step import DamStep
from src.ui.steps.integration_step import IntegrationStep
from src.ui.steps.project_step import ProjectStep
from src.ui.steps.regional_step import RegionalStep
from src.ui.steps.report_step import ReportStep
from src.ui.steps.reservoir_step import ReservoirStep
from src.ui.steps.suspended_step import SuspendedStep
from src.ui.wizard import Wizard
from tests.samples import SAMPLE_BASINS, SAMPLE_FRACTIONS, SAMPLE_ZONAL, sample_flow, sample_sheet
from tests.ui.helpers import wait_until

SLUGS = ("kavsakkaya", "cubuk_1", "cubuk_2")


@pytest.fixture()
def errors(monkeypatch):
    shown = []
    for module in (
        "suspended_step",
        "dam_step",
        "project_step",
        "bedload_step",
        "reservoir_step",
        "integration_step",
        "report_step",
    ):
        monkeypatch.setattr(f"src.ui.steps.{module}.show_error", lambda t, m: shown.append((t, m)))
    return shown


@pytest.fixture()
def app(tk_root, tmp_path, errors):
    """The wizard at step 3 with the sample tables and the three dam sheets imported, and all eight steps."""
    top = tk.Toplevel(tk_root)
    project_step, regional_step, dam_step = ProjectStep(), RegionalStep(), DamStep()
    suspended, bedload, reservoir = SuspendedStep(dam_step), BedloadStep(dam_step), ReservoirStep(dam_step)
    integration = IntegrationStep(dam_step)
    report = ReportStep(dam_step)
    wizard = Wizard(top, [project_step, regional_step, dam_step, suspended, bedload, reservoir, integration, report])
    wizard.frame.pack(fill="both", expand=True)
    project_step.create_project(str(tmp_path / "project"), "Region")
    wizard.go_to(1)
    regional_step.import_basin_table(str(SAMPLE_BASINS))
    regional_step.import_zonal_means(str(SAMPLE_ZONAL))
    regional_step.import_dam_sheets([str(sample_sheet(slug)) for slug in SLUGS])
    wizard.go_to(2)
    yield wizard, report, top
    top.destroy()


def _reach_integration(wizard, top, slug="cubuk_1"):
    """Choose a dam and compute steps 4 to 6; step 7 is left for the test to compute."""
    dam_step, suspended, bedload, reservoir = wizard.steps[2:6]
    dam_step.select_dam(slug)
    dam_step.commissioning_var.set("1990")
    dam_step.analysis_var.set("2020")
    dam_step.use_dam()
    assert wizard.go_to(3)
    suspended.compute()
    wait_until(top, lambda: not wizard.busy)
    assert wizard.go_to(4)
    bedload.use_flow_file(str(sample_flow(slug)))
    bedload.use_fractions_file(str(SAMPLE_FRACTIONS))
    bedload.compute()
    wait_until(top, lambda: not wizard.busy)
    assert wizard.go_to(5)
    reservoir.shape_var.set("hill")
    reservoir.generate()
    assert wizard.go_to(6)


def _reach_report(wizard, top, slug="cubuk_1"):
    _reach_integration(wizard, top, slug)
    wizard.steps[6].compute()
    assert wizard.go_to(7)


def _run_folders(wizard):
    return sorted(path.name for path in (wizard.project.folder / "outputs").iterdir())


def test_w_m5_01_the_step_is_locked_until_the_integration_is_computed(app):
    wizard, report, top = app
    _reach_integration(wizard, top)

    assert not wizard.can_enter(7) and not report.is_complete()
    wizard.steps[6].compute()
    assert wizard.can_enter(7)


def test_w_m5_01_the_step_shows_the_minimum_and_maximum_years_before_exporting(app):
    wizard, report, top = app
    _reach_report(wizard, top)
    lowest, highest = wizard.steps[6].result.extremes

    text = report.extremes_var.get()

    assert f"Minimum: {lowest.year}" in text and f"Maximum: {highest.year}" in text
    assert f"{lowest.total_hm3:.4f} hm³" in text and f"{highest.elevation_m:.2f} m" in text
    assert not report.is_complete() and report.files_var.get() == ""


def test_w_m5_01_the_step_shows_the_warnings_of_every_phase(app):
    wizard, report, top = app
    _reach_report(wizard, top)

    assert "7 year(s)" in report.warning_var.get()  # the integration's, for the years outside the record


def test_w_m5_01_export_writes_the_run_folder_and_lists_its_files(app):
    wizard, report, top = app
    _reach_report(wizard, top)

    report.export()
    wait_until(top, lambda: not wizard.busy)

    assert report.is_complete()
    (folder,) = _run_folders(wizard)
    assert folder.startswith("cubuk_1_")
    listed = report.files_var.get().splitlines()
    assert len(listed) == 11 and all(folder in line for line in listed)
    assert any(line.endswith("results.xlsx") for line in listed) and any(line.endswith("run.json") for line in listed)
    assert folder in report.folder_var.get()


def test_w_m5_01_exporting_twice_makes_two_run_folders(app):
    wizard, report, top = app
    _reach_report(wizard, top)

    report.export()
    wait_until(top, lambda: not wizard.busy)
    report.export()
    wait_until(top, lambda: not wizard.busy)

    assert len(_run_folders(wizard)) == 2


def test_w_m5_01_a_failed_export_is_reported_and_leaves_the_step_open(app, errors):
    wizard, report, top = app
    _reach_report(wizard, top)
    dam = wizard.steps[2].chosen
    (wizard.project.folder / dam.flow.path).unlink()

    report.export()
    wait_until(top, lambda: not wizard.busy)

    assert not report.is_complete() and report.files_var.get() == ""
    assert len(errors) == 1 and "cubuk_1_flow" in errors[0][1]


def test_w_x_02_choosing_a_different_dam_clears_the_export(app):
    wizard, report, top = app
    _reach_report(wizard, top)
    report.export()
    wait_until(top, lambda: not wizard.busy)

    wizard.steps[2].select_dam("cubuk_2")

    assert not report.is_complete() and report.files_var.get() == "" and report.extremes_var.get() == ""


def test_w_x_02_a_changed_integration_clears_the_export(app):
    wizard, report, top = app
    _reach_report(wizard, top)
    report.export()
    wait_until(top, lambda: not wizard.busy)
    integration = wizard.steps[6]
    wizard.go_to(6)
    integration.years_var.set("50")

    integration.compute()

    assert not report.is_complete() and report.files_var.get() == ""


def test_w_x_02_computing_the_same_integration_again_keeps_the_export(app):
    wizard, report, top = app
    _reach_report(wizard, top)
    report.export()
    wait_until(top, lambda: not wizard.busy)
    wizard.go_to(6)

    wizard.steps[6].compute()

    assert report.is_complete()
