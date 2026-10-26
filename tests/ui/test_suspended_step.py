import threading
import tkinter as tk

import pytest

from src.services.suspended import OUTPUT_COLUMNS
from src.ui.steps import suspended_step
from src.ui.steps.dam_step import DamStep
from src.ui.steps.project_step import ProjectStep
from src.ui.steps.regional_step import RegionalStep
from src.ui.steps.suspended_step import SuspendedStep
from src.ui.wizard import Wizard
from src.utils.paths import resource_path
from tests.samples import SAMPLE_BASINS, SAMPLE_ZONAL
from tests.ui.fakes import FakeStep
from tests.ui.helpers import wait_until

CUBUK_1_SHEET = resource_path("inputs", "bathymetry", "cubuk_1_bathymetry.csv")
UNRELATED_ZONAL = "Sub-basin,MEAN\nKonya Alt Havzası,1.5\n"


@pytest.fixture()
def errors(monkeypatch):
    shown = []
    for module in ("suspended_step", "dam_step", "project_step"):
        monkeypatch.setattr(f"src.ui.steps.{module}.show_error", lambda t, m: shown.append((t, m)))
    return shown


@pytest.fixture()
def app(tk_root, tmp_path, errors):
    """The wizard at step 3 with the sample tables imported and only Çubuk 1 holding a sheet."""
    top = tk.Toplevel(tk_root)
    project_step, regional_step, dam_step = ProjectStep(), RegionalStep(), DamStep()
    step, later = SuspendedStep(dam_step), FakeStep("Later")
    wizard = Wizard(top, [project_step, regional_step, dam_step, step, later])
    wizard.frame.pack(fill="both", expand=True)
    project_step.create_project(str(tmp_path / "project"), "Region")
    wizard.go_to(1)
    regional_step.import_basin_table(str(SAMPLE_BASINS))
    regional_step.import_zonal_means(str(SAMPLE_ZONAL))
    regional_step.import_dam_sheets([str(CUBUK_1_SHEET)])
    wizard.go_to(2)
    yield wizard, step, later, top, tmp_path
    top.destroy()


def _choose_cubuk_1(wizard):
    dam_step = wizard.steps[2]
    dam_step.select_dam("cubuk_1")
    dam_step.use_dam()
    assert wizard.go_to(3)


def _compute(wizard, step, top):
    step.compute()
    wait_until(top, lambda: not wizard.busy)


def _rows(step):
    return [step.tree.item(iid, "values") for iid in step.tree.get_children()]


def test_w_m2_01_the_step_is_locked_until_the_dam_is_chosen(app):
    wizard, step, _, _, _ = app

    assert not wizard.can_enter(3)
    assert not step.is_complete()


def test_w_m2_01_compute_fills_the_grid_and_the_total_for_the_chosen_dam_only(app):
    wizard, step, _, top, _ = app
    _choose_cubuk_1(wizard)
    assert not step.is_complete() and not _rows(step)

    _compute(wizard, step, top)

    assert step.is_complete()
    rows = _rows(step)
    assert len(rows) == 1 and rows[0][0] == "Ankara Alt Havzası"
    assert "73,705" in step.total_var.get() and "118,933" not in step.total_var.get()
    wizard.refresh()
    assert not wizard.next_button.instate(["disabled"])


def test_w_m2_01_the_calculation_runs_off_the_tk_thread(app, monkeypatch):
    wizard, step, _, top, _ = app
    _choose_cubuk_1(wizard)
    seen = {}
    real = suspended_step.compute_suspended

    def spy(*args, **kwargs):
        seen["thread"] = threading.get_ident()
        return real(*args, **kwargs)

    monkeypatch.setattr(suspended_step, "compute_suspended", spy)

    step.compute()
    assert wizard.busy and wizard.status_var.get()
    wait_until(top, lambda: not wizard.busy)

    assert seen["thread"] != threading.get_ident()
    assert step.is_complete()


def test_w_m2_01_a_sub_basin_without_a_zonal_mean_is_reported_and_nothing_is_shown(app, errors):
    wizard, step, _, top, tmp_path = app
    zonal = tmp_path / "unrelated.csv"
    zonal.write_text(UNRELATED_ZONAL, encoding="utf-8")
    wizard.steps[1].import_zonal_means(str(zonal))
    wizard.go_to(2)
    _choose_cubuk_1(wizard)

    _compute(wizard, step, top)

    assert not step.is_complete() and not _rows(step)
    assert len(errors) == 1 and "Ankara Alt Havzası" in errors[0][1] and "zonal_means.csv" in errors[0][1]


def test_w_x_02_choosing_a_different_dam_clears_the_result_and_later_steps(app):
    wizard, step, later, top, _ = app
    _choose_cubuk_1(wizard)
    _compute(wizard, step, top)
    later.done = True
    wizard.refresh()

    wizard.steps[2].select_dam("cubuk_2")

    assert not step.is_complete() and not _rows(step) and step.total_var.get() == ""
    assert later.done is False
    assert "Suspended" in wizard.notice_var.get()


def test_w_x_02_editing_the_basin_table_clears_the_result(app):
    wizard, step, _, top, _ = app
    _choose_cubuk_1(wizard)
    _compute(wizard, step, top)
    assert step.is_complete()

    wizard.steps[1].commit_edit(1, "Main Waterway Slope", "0.1")

    assert not step.is_complete() and not _rows(step)


def test_w_m2_01_the_grid_shows_exactly_the_columns_the_service_returns():
    assert [key for key, *_ in suspended_step.GRID_COLUMNS] == OUTPUT_COLUMNS
