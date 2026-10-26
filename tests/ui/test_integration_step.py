import tkinter as tk

import pytest

from src.ui.steps import integration_step
from src.ui.steps.bedload_step import BedloadStep
from src.ui.steps.dam_step import DamStep
from src.ui.steps.integration_step import IntegrationStep
from src.ui.steps.project_step import ProjectStep
from src.ui.steps.regional_step import RegionalStep
from src.ui.steps.reservoir_step import ReservoirStep
from src.ui.steps.suspended_step import SuspendedStep
from src.ui.wizard import Wizard
from tests.samples import SAMPLE_BASINS, SAMPLE_FRACTIONS, SAMPLE_ZONAL, sample_flow, sample_sheet
from tests.ui.fakes import FakeStep
from tests.ui.helpers import wait_until

SLUGS = ("kavsakkaya", "cubuk_1", "cubuk_2")


@pytest.fixture()
def errors(monkeypatch):
    shown = []
    for module in ("suspended_step", "dam_step", "project_step", "bedload_step", "reservoir_step", "integration_step"):
        monkeypatch.setattr(f"src.ui.steps.{module}.show_error", lambda t, m: shown.append((t, m)))
    return shown


@pytest.fixture()
def app(tk_root, tmp_path, errors):
    """The wizard at step 3 with the sample tables and the three dam sheets imported, and one more step after step 7."""
    top = tk.Toplevel(tk_root)
    project_step, regional_step, dam_step = ProjectStep(), RegionalStep(), DamStep()
    suspended, bedload, reservoir = SuspendedStep(dam_step), BedloadStep(dam_step), ReservoirStep(dam_step)
    step, later = IntegrationStep(dam_step, suspended, bedload, reservoir), FakeStep("Later")
    wizard = Wizard(top, [project_step, regional_step, dam_step, suspended, bedload, reservoir, step, later])
    wizard.frame.pack(fill="both", expand=True)
    project_step.create_project(str(tmp_path / "project"), "Region")
    wizard.go_to(1)
    regional_step.import_basin_table(str(SAMPLE_BASINS))
    regional_step.import_zonal_means(str(SAMPLE_ZONAL))
    regional_step.import_dam_sheets([str(sample_sheet(slug)) for slug in SLUGS])
    wizard.go_to(2)
    yield wizard, step, later, top
    top.destroy()


def _reach_step(wizard, top, slug="cubuk_1", commissioning="1990", analysis="2020"):
    """Choose a dam, compute steps 4 to 6 for it and open the integration step."""
    dam_step, suspended, bedload, reservoir = wizard.steps[2:6]
    dam_step.select_dam(slug)
    dam_step.commissioning_var.set(commissioning)
    dam_step.analysis_var.set(analysis)
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


def _rows(tree):
    return [tree.item(iid, "values") for iid in tree.get_children()]


def test_w_m4_02_the_step_is_locked_until_the_curve_is_generated(app):
    wizard, step, _, _ = app

    assert not wizard.can_enter(6) and not step.is_complete()


def test_w_m4_02_compute_fills_the_tables_the_summary_and_the_chart(app):
    wizard, step, _, top = app
    _reach_step(wizard, top)
    assert not step.is_complete() and not _rows(step.annual_tree)

    step.compute()

    assert step.is_complete()
    annual = _rows(step.annual_tree)
    assert len(annual) == 39 and annual[0][0] == "1974" and annual[-1][0] == "2012"
    assert step.annual_tree.heading("year")["text"] == "Water year"
    projection = _rows(step.projection_tree)
    assert len(projection) == 101 and projection[0][0] == "2020" and projection[-1][0] == "2120"
    summary = step.summary_var.get()
    assert "Accumulation to date" in summary and "1990" in summary and "2019" in summary and "Hmin" in summary
    assert step._canvas is not None and step._canvas.get_tk_widget().winfo_exists()
    wizard.refresh()
    assert not wizard.next_button.instate(["disabled"])


def test_w_m4_02_the_lifespan_of_each_rate_is_stated(app):
    wizard, step, _, top = app
    _reach_step(wizard, top)

    step.compute()

    text = step.lifespan_var.get()
    assert [name for name in ("mean", "min", "max") if f"{name} rate" in text.lower()] == ["mean", "min", "max"]
    assert "already exceeded in" in text  # Çubuk 1 holds 0.32 hm³ of dead volume, filled long before 2020


def test_w_m4_02_years_outside_the_record_are_warned_about(app):
    wizard, step, _, top = app
    _reach_step(wizard, top)

    step.compute()

    assert "7 year(s)" in step.warning_var.get()


def test_x_01_without_a_commissioning_year_computing_is_an_error_that_says_where_to_enter_it(app, errors):
    wizard, step, _, top = app
    _reach_step(wizard, top, commissioning="")

    step.compute()

    assert not step.is_complete() and not _rows(step.annual_tree)
    assert len(errors) == 1 and "commissioning year" in errors[0][1] and "step 3" in errors[0][1]


def test_w_x_02_changing_the_curve_clears_the_result_and_the_later_steps(app):
    wizard, step, later, top = app
    _reach_step(wizard, top)
    step.compute()
    later.done = True
    reservoir = wizard.steps[5]
    wizard.go_to(5)
    reservoir.shape_var.set("lake")

    reservoir.generate()

    assert not step.is_complete() and not _rows(step.annual_tree) and step._canvas is None
    assert step.summary_var.get() == "" and later.done is False


def test_w_x_02_generating_the_same_curve_again_keeps_the_result(app):
    wizard, step, _, top = app
    _reach_step(wizard, top)
    step.compute()
    wizard.go_to(5)

    wizard.steps[5].generate()

    assert step.is_complete()


def test_w_x_02_choosing_a_different_dam_clears_the_result(app):
    wizard, step, _, top = app
    _reach_step(wizard, top)
    step.compute()

    wizard.steps[2].select_dam("cubuk_2")

    assert not step.is_complete() and not _rows(step.annual_tree) and step._canvas is None


def test_w_x_02_editing_the_basin_table_clears_the_result(app):
    wizard, step, _, top = app
    _reach_step(wizard, top)
    step.compute()

    wizard.steps[1].commit_edit(1, "Main Waterway Slope", "0.1")

    assert not step.is_complete() and not _rows(step.projection_tree)


def test_w_m4_02_computing_again_replaces_the_tables(app):
    wizard, step, _, top = app
    _reach_step(wizard, top)
    step.compute()

    step.compute()

    assert len(_rows(step.annual_tree)) == 39 and len(_rows(step.projection_tree)) == 101


def test_w_m4_02_the_grids_show_the_columns_the_service_returns():
    assert [key for key, *_ in integration_step.ANNUAL_COLUMNS[1:]] == [
        "Suspended_hm3",
        "Bedload_hm3",
        "Total_hm3",
        "Elevation_m",
    ]
    assert [key for key, *_ in integration_step.PROJECTION_COLUMNS] == [
        "Year",
        "Cumulative_Mean_hm3",
        "Cumulative_Min_hm3",
        "Cumulative_Max_hm3",
        "Elevation_Mean_m",
        "Elevation_Min_m",
        "Elevation_Max_m",
    ]
