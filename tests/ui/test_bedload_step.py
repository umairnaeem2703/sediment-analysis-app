import threading
import tkinter as tk

import pytest

from src.services.bedload import VALUE_COLUMNS
from src.ui.steps import bedload_step
from src.ui.steps.bedload_step import BedloadStep
from src.ui.steps.dam_step import DamStep
from src.ui.steps.project_step import ProjectStep
from src.ui.steps.regional_step import RegionalStep
from src.ui.steps.suspended_step import SuspendedStep
from src.ui.wizard import Wizard
from src.utils.paths import resource_path
from tests.samples import SAMPLE_BASINS, SAMPLE_FRACTIONS, SAMPLE_ZONAL, sample_flow, write_fractions_with_wrong_tau_ri
from tests.ui.fakes import FakeStep
from tests.ui.helpers import wait_until

CUBUK_1_SHEET = resource_path("inputs", "bathymetry", "cubuk_1_bathymetry.csv")


@pytest.fixture()
def errors(monkeypatch):
    shown = []
    for module in ("suspended_step", "dam_step", "project_step", "bedload_step"):
        monkeypatch.setattr(f"src.ui.steps.{module}.show_error", lambda t, m: shown.append((t, m)))
    return shown


@pytest.fixture()
def warnings_shown(monkeypatch):
    shown = []
    monkeypatch.setattr(bedload_step, "show_warning", lambda t, m: shown.append((t, m)))
    return shown


@pytest.fixture()
def app(tk_root, tmp_path, errors, warnings_shown):
    """The wizard at step 3 with the sample tables imported and only Çubuk 1 holding a sheet."""
    top = tk.Toplevel(tk_root)
    project_step, regional_step, dam_step = ProjectStep(), RegionalStep(), DamStep()
    suspended, step, later = SuspendedStep(dam_step), BedloadStep(dam_step), FakeStep("Later")
    wizard = Wizard(top, [project_step, regional_step, dam_step, suspended, step, later])
    wizard.frame.pack(fill="both", expand=True)
    project_step.create_project(str(tmp_path / "project"), "Region")
    wizard.go_to(1)
    regional_step.import_basin_table(str(SAMPLE_BASINS))
    regional_step.import_zonal_means(str(SAMPLE_ZONAL))
    regional_step.import_dam_sheets([str(CUBUK_1_SHEET)])
    wizard.go_to(2)
    yield wizard, step, later, top, tmp_path
    top.destroy()


def _reach_step(wizard, top):
    """Choose Çubuk 1, compute its suspended sediment and open the bedload step."""
    dam_step, suspended = wizard.steps[2], wizard.steps[3]
    dam_step.select_dam("cubuk_1")
    dam_step.use_dam()
    assert wizard.go_to(3)
    suspended.compute()
    wait_until(top, lambda: not wizard.busy)
    assert wizard.go_to(4)


def _inputs(step):
    step.use_flow_file(str(sample_flow("cubuk_1")))
    step.use_fractions_file(str(SAMPLE_FRACTIONS))


def _compute(wizard, step, top):
    step.compute()
    wait_until(top, lambda: not wizard.busy)


def _rows(step):
    return [step.tree.item(iid, "values") for iid in step.tree.get_children()]


def test_w_m3_01_the_step_is_locked_until_the_suspended_sediment_is_computed(app):
    wizard, step, _, _, _ = app

    assert not wizard.can_enter(4)
    assert not step.is_complete()


def test_w_m3_01_the_chosen_files_are_listed_by_the_name_of_the_project_copy(app):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    assert "none chosen" in step.flow_var.get() and "none chosen" in step.fractions_var.get()

    _inputs(step)

    assert step.flow_var.get() == "Flow file: cubuk_1_flow.csv"
    assert step.fractions_var.get() == "Grain fractions: fractions.csv"
    assert (step.sigma_var.get(), step.seed_var.get()) == ("0.6", "0")


def test_w_m3_01_compute_fills_the_table_the_chart_and_the_synthetic_flag(app):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)
    assert not step.is_complete() and not _rows(step)

    _compute(wizard, step, top)

    assert step.is_complete()
    rows = _rows(step)
    assert len(rows) == 39 and rows[0][0] == "1974" and rows[-1][0] == "2012"
    assert step.tree.heading("year")["text"] == "Water year"
    assert "Mean bedload" in step.summary_var.get() and "39 water year(s)" in step.summary_var.get()
    assert "Synthetic daily flow" in step.flag_var.get() and "seed 0" in step.flag_var.get()
    assert step._canvas is not None and step._canvas.get_tk_widget().winfo_exists()
    wizard.refresh()
    assert not wizard.next_button.instate(["disabled"])


def test_w_m3_01_the_sample_fractions_show_no_warning(app, warnings_shown):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)

    _compute(wizard, step, top)

    assert warnings_shown == [] and step.warning_var.get() == ""


def test_w_m3_01_the_fractions_cross_check_is_shown_when_they_are_chosen_and_with_the_result(app, warnings_shown):
    wizard, step, _, top, tmp_path = app
    _reach_step(wizard, top)
    step.use_flow_file(str(sample_flow("cubuk_1")))

    step.use_fractions_file(str(write_fractions_with_wrong_tau_ri(tmp_path)))

    assert len(warnings_shown) == 1 and "fractional_parameters.csv" in warnings_shown[0][1]
    _compute(wizard, step, top)
    assert step.warning_var.get().count("tau_ri") == 5


def test_w_m3_01_the_columns_ignored_in_a_flow_file_are_shown_when_it_is_chosen(app, warnings_shown):
    wizard, step, _, top, tmp_path = app
    _reach_step(wizard, top)
    flow = tmp_path / "daily.csv"
    flow.write_text("Date,Flow Q (m3/s),Station\n01/01/2010,10,A\n02/01/2010,20,A\n", encoding="utf-8")

    step.use_flow_file(str(flow))

    assert len(warnings_shown) == 1 and "ignored column(s) Station" in warnings_shown[0][1]


def test_w_m3_01_the_calculation_runs_off_the_tk_thread(app, monkeypatch):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)
    seen = {}
    real = bedload_step.compute_dam_bedload

    def spy(*args, **kwargs):
        seen["thread"] = threading.get_ident()
        return real(*args, **kwargs)

    monkeypatch.setattr(bedload_step, "compute_dam_bedload", spy)

    step.compute()
    assert wizard.busy and wizard.status_var.get()
    wait_until(top, lambda: not wizard.busy)

    assert seen["thread"] != threading.get_ident()
    assert step.is_complete()


def test_x_01_computing_without_a_flow_file_is_an_error_naming_the_dam(app, errors):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    step.use_fractions_file(str(SAMPLE_FRACTIONS))

    _compute(wizard, step, top)

    assert not step.is_complete() and not _rows(step)
    assert len(errors) == 1 and "No flow file has been chosen for Çubuk 1" in errors[0][1]


def test_x_01_computing_without_fractions_is_an_error_naming_them(app, errors):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    step.use_flow_file(str(sample_flow("cubuk_1")))

    _compute(wizard, step, top)

    assert not step.is_complete()
    assert len(errors) == 1 and "No grain fractions file has been chosen" in errors[0][1]


def test_w_m3_01_a_file_that_cannot_be_used_is_refused_and_named(app, errors):
    wizard, step, _, top, tmp_path = app
    _reach_step(wizard, top)
    bad = tmp_path / "bad_fractions.csv"
    bad.write_text("di,Fi\n0.004,0.5\n", encoding="utf-8")

    step.use_fractions_file(str(bad))

    assert len(errors) == 1 and "bad_fractions.csv" in errors[0][1]
    assert "none chosen" in step.fractions_var.get()


def test_w_m3_01_a_flow_file_without_the_expected_columns_is_refused_when_it_is_chosen(app, errors):
    wizard, step, _, top, tmp_path = app
    _reach_step(wizard, top)
    flow = tmp_path / "wrong.csv"
    flow.write_text("Day,Q\n01/01/2000,1\n", encoding="utf-8")

    step.use_flow_file(str(flow))

    assert len(errors) == 1 and "wrong.csv" in errors[0][1] and "Date" in errors[0][1]
    assert "none chosen" in step.flow_var.get() and wizard.project.dams[1].flow.path is None


def test_w_m3_01_a_project_copy_that_has_gone_bad_is_reported_when_computing(app, errors):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)
    copy = wizard.project.folder / wizard.project.dams[1].flow.path
    copy.write_text("Day,Q\n01/01/2000,1\n", encoding="utf-8")

    _compute(wizard, step, top)

    assert not step.is_complete()
    assert len(errors) == 1 and "cubuk_1_flow.csv" in errors[0][1] and "Date" in errors[0][1]


def test_w_m3_01_a_daily_flow_can_be_chosen_while_sigma_and_seed_hold_invalid_text(app, errors):
    wizard, step, _, top, tmp_path = app
    _reach_step(wizard, top)
    daily = tmp_path / "daily.csv"
    daily.write_text("Date,Flow Q (m3/s)\n01/01/2000,10\n02/01/2000,20\n", encoding="utf-8")
    step.seed_var.set("x")

    step.use_flow_file(str(daily))

    assert errors == [] and step.flow_var.get() == "Flow file: cubuk_1_flow.csv"


def test_w_m3_01_computing_while_busy_neither_stores_the_settings_nor_clears_anything(app):
    wizard, step, later, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)
    _compute(wizard, step, top)
    later.done = True
    step.sigma_var.set("0.4")
    wizard.busy = True

    step.compute()
    wizard.busy = False

    assert wizard.project.dams[1].flow.sigma == 0.6 and later.done is True


def test_w_m3_01_choosing_a_file_while_the_calculation_runs_is_refused_and_changes_nothing(app, errors):
    wizard, step, _, top, tmp_path = app
    _reach_step(wizard, top)
    _inputs(step)
    other = tmp_path / "other_fractions.csv"
    other.write_text("di,Fi\n0.004,0.5\n0.05,0.5\n", encoding="utf-8")
    flow_before, fractions_before = wizard.project.dams[1].flow.path, wizard.project.inputs["fractions"]
    wizard.busy = True

    step.use_fractions_file(str(other))
    step.use_flow_file(str(sample_flow("cubuk_1")))
    wizard.busy = False

    assert len(errors) == 2 and all("calculation" in message for _, message in errors)
    assert (wizard.project.dams[1].flow.path, wizard.project.inputs["fractions"]) == (flow_before, fractions_before)
    assert "other_fractions" not in (tmp_path / "project" / "inputs" / "fractions.csv").read_text(encoding="utf-8")


def test_w_m3_01_editing_sigma_while_the_calculation_runs_is_not_lost_and_the_result_is_not_current(app):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)

    step.compute()
    step.sigma_var.set("0.4")  # typed while the worker thread is busy
    wait_until(top, lambda: not wizard.busy)

    assert step.sigma_var.get() == "0.4" and step.result is not None
    assert not step.is_complete()


def test_w_m3_01_invalid_sigma_or_seed_is_refused_and_nothing_is_computed(app, errors):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)
    step.sigma_var.set("-2")

    _compute(wizard, step, top)

    assert not step.is_complete() and not wizard.busy
    assert len(errors) == 1 and "Sigma" in errors[0][1]


def test_w_m3_01_a_high_sigma_is_warned_under_the_result(app):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)
    step.sigma_var.set("2")

    _compute(wizard, step, top)

    assert step.is_complete() and "Sigma 2 is above 1.5" in step.warning_var.get()


def test_w_x_02_choosing_other_fractions_clears_the_result_and_later_steps(app):
    wizard, step, later, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)
    _compute(wizard, step, top)
    later.done = True
    wizard.refresh()

    step.use_fractions_file(str(SAMPLE_FRACTIONS))

    assert not step.is_complete() and not _rows(step) and step.summary_var.get() == ""
    assert step._canvas is None
    assert later.done is False
    assert "Later" in wizard.notice_var.get()


def test_w_x_02_editing_sigma_un_completes_the_step_and_computing_stores_it_and_clears_later_steps(app):
    wizard, step, later, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)
    _compute(wizard, step, top)
    first = list(step.result.table["Volume_m3_yr"])
    later.done = True

    step.sigma_var.set("0.3")

    assert not step.is_complete()
    _compute(wizard, step, top)
    assert step.is_complete() and later.done is False
    assert wizard.project.dams[1].flow.sigma == 0.3 and "σ=0.3" in step.flag_var.get()
    assert list(step.result.table["Volume_m3_yr"]) != first


def test_w_x_02_choosing_a_different_dam_clears_the_result(app):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)
    _compute(wizard, step, top)

    wizard.steps[2].select_dam("cubuk_2")

    assert not step.is_complete() and not _rows(step) and step._canvas is None


def test_w_x_02_editing_the_basin_table_clears_the_result(app):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)
    _compute(wizard, step, top)

    wizard.steps[1].commit_edit(1, "Main Waterway Slope", "0.1")

    assert not step.is_complete() and not _rows(step)


def test_w_m3_01_each_dam_keeps_its_own_flow_file_and_settings(app):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)
    step.sigma_var.set("0.9")
    step.seed_var.set("4")
    _compute(wizard, step, top)

    cubuk_1, cubuk_2 = wizard.project.dams[1], wizard.project.dams[2]

    assert (cubuk_1.flow.sigma, cubuk_1.flow.seed) == (0.9, 4) and cubuk_1.flow.path == "inputs/flow/cubuk_1_flow.csv"
    assert cubuk_2.flow.path is None and (cubuk_2.flow.sigma, cubuk_2.flow.seed) == (0.6, 0)


def test_w_m3_01_the_grid_shows_exactly_the_columns_the_service_returns():
    assert [key for key, *_ in bedload_step.GRID_COLUMNS[1:]] == VALUE_COLUMNS


def test_w_m3_03_the_lag_1_phi_starts_at_zero_and_is_refused_when_invalid(app, errors):
    wizard, step, _, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)
    assert step.phi_var.get() == "0"

    step.phi_var.set("1")
    _compute(wizard, step, top)

    assert not step.is_complete() and errors and "Lag-1 phi" in errors[-1][1]


def test_w_x_02_editing_phi_un_completes_the_step_and_computing_stores_it_and_changes_the_result(app):
    wizard, step, later, top, _ = app
    _reach_step(wizard, top)
    _inputs(step)
    _compute(wizard, step, top)
    first = list(step.result.table["Volume_m3_yr"])
    later.done = True

    step.phi_var.set("0.8")

    assert not step.is_complete()
    _compute(wizard, step, top)
    assert step.is_complete() and later.done is False
    assert wizard.project.dams[1].flow.phi == 0.8 and "φ=0.8" in step.flag_var.get()
    assert list(step.result.table["Volume_m3_yr"]) != first
