import json
import tkinter as tk

import pytest

from src.ui.steps.dam_step import DamStep
from src.ui.steps.project_step import ProjectStep
from src.ui.steps.regional_step import RegionalStep
from src.ui.wizard import Wizard
from src.utils.paths import resource_path
from tests.ui.fakes import FakeStep

SAMPLE_BASINS = resource_path("inputs", "master_yield.csv")
SAMPLE_ZONAL = resource_path("inputs", "raw_zonal_means.csv")
CUBUK_1_SHEET = resource_path("inputs", "bathymetry", "cubuk_1_bathymetry.csv")
ONE_DAM_TABLE = (
    "Dam Name,Basin Name,Sub-basin Name,Drainage Area (km2),Main Waterway Slope\n"
    "Çubuk 1,Sakarya,Ankara Alt Havzası,834.7,0.09\n"
)


@pytest.fixture()
def errors(monkeypatch):
    shown = []
    monkeypatch.setattr("src.ui.steps.dam_step.show_error", lambda t, m: shown.append((t, m)))
    monkeypatch.setattr("src.ui.steps.project_step.show_error", lambda t, m: shown.append((t, m)))
    return shown


@pytest.fixture()
def app(tk_root, tmp_path, errors):
    top = tk.Toplevel(tk_root)
    project_step, regional_step, dam_step, later = ProjectStep(), RegionalStep(), DamStep(), FakeStep("Later")
    wizard = Wizard(top, [project_step, regional_step, dam_step, later])
    wizard.frame.pack(fill="both", expand=True)
    project_step.create_project(str(tmp_path / "project"), "Region")
    wizard.go_to(1)
    regional_step.import_basin_table(str(SAMPLE_BASINS))
    regional_step.import_zonal_means(str(SAMPLE_ZONAL))
    regional_step.import_dam_sheets([str(CUBUK_1_SHEET)])  # only Çubuk 1 gets a sheet
    wizard.go_to(2)
    yield wizard, dam_step, later, tmp_path
    top.destroy()


def _fill(step, commissioning="", analysis="", efficiency="100", h_min=""):
    step.commissioning_var.set(commissioning)
    step.analysis_var.set(analysis)
    step.efficiency_var.set(efficiency)
    step.h_min_var.set(h_min)


def test_w_m1_03_the_dams_of_the_table_are_listed_and_nothing_is_selected(app):
    wizard, step, _, _ = app

    assert list(step.dam_list.get(0, tk.END)) == ["Kavşakkaya", "Çubuk 1", "Çubuk 2"]
    assert step.selected is None
    assert not step.is_complete()


def test_w_m1_03_selecting_a_dam_shows_its_sub_basins_sheet_and_settings(app):
    wizard, step, _, _ = app

    step.select_dam("cubuk_1")

    rows = [step.sub_basin_tree.item(i, "values") for i in step.sub_basin_tree.get_children()]
    assert [(r[0], str(r[1]), str(r[2])) for r in rows] == [("Ankara Alt Havzası", "834.7", "0.09")]
    sheet = step.sheet_var.get()
    assert "908.6" in sheet and "5.6" in sheet and "888" in sheet
    assert step.efficiency_var.get() == "100"
    assert step.commissioning_var.get() == ""


def test_w_m1_03_the_list_selection_drives_the_view(app):
    wizard, step, _, _ = app

    top = wizard.frame.winfo_toplevel()
    top.update()  # Tk only delivers generated events to mapped windows
    step.dam_list.selection_set(1)
    step.dam_list.event_generate("<<ListboxSelect>>")
    top.update()

    assert step.selected.slug == "cubuk_1"


def test_w_m1_03_using_a_dam_saves_its_settings_and_completes_the_step(app):
    wizard, step, _, _ = app
    step.select_dam("cubuk_1")
    _fill(step, commissioning="1965", analysis="2025", efficiency="85,5", h_min="892.5")

    step.use_dam()

    assert step.is_complete()
    dam = wizard.project.dams[1]
    assert (dam.commissioning_year, dam.analysis_year, dam.trap_efficiency_pct, dam.h_min_m) == (
        1965,
        2025,
        85.5,
        892.5,
    )
    saved = json.loads((wizard.project.folder / "project.json").read_text(encoding="utf-8"))
    assert saved["dams"][1]["trap_efficiency_pct"] == 85.5
    wizard.refresh()
    assert not wizard.next_button.instate(["disabled"])


def test_w_m1_03_a_dam_without_a_sheet_cannot_be_used(app, errors):
    wizard, step, _, _ = app
    step.select_dam("kavsakkaya")

    assert "no sheet" in step.sheet_var.get().lower()
    step.use_dam()

    assert not step.is_complete()
    assert len(errors) == 1 and "Kavşakkaya" in errors[0][1] and "step 2" in errors[0][1]


def test_w_m1_03_invalid_settings_are_listed_and_nothing_changes(app, errors):
    wizard, step, _, _ = app
    step.select_dam("cubuk_1")
    _fill(step, commissioning="65", efficiency="150")

    step.use_dam()

    assert not step.is_complete()
    assert len(errors) == 1
    assert "Commissioning year" in errors[0][1] and "Trap efficiency" in errors[0][1]
    assert wizard.project.dams[1].trap_efficiency_pct == 100.0


def test_w_m1_03_using_a_dam_without_selecting_one_asks_for_a_choice(app, errors):
    wizard, step, _, _ = app

    step.use_dam()

    assert len(errors) == 1 and "Select a dam" in errors[0][1]


def test_w_x_02_choosing_a_different_dam_resets_later_steps(app):
    wizard, step, later, _ = app
    step.select_dam("cubuk_1")
    step.use_dam()
    later.done = True
    wizard.refresh()

    step.select_dam("cubuk_2")

    assert not step.is_complete()
    assert later.done is False
    assert "Later" in wizard.notice_var.get()


def test_w_x_02_changing_a_setting_resets_later_steps_but_repeating_it_does_not(app):
    wizard, step, later, _ = app
    step.select_dam("cubuk_1")
    _fill(step, commissioning="1965")
    step.use_dam()
    later.done = True
    resets = later.resets

    step.use_dam()  # nothing changed
    assert later.done is True and later.resets == resets

    _fill(step, commissioning="1970")
    step.use_dam()
    assert later.done is False


def test_w_x_02_editing_regional_data_clears_the_chosen_dam(app):
    wizard, step, _, _ = app
    step.select_dam("cubuk_1")
    step.use_dam()
    assert step.is_complete()

    wizard.steps[1].commit_edit(1, "Main Waterway Slope", "0.1")

    assert not step.is_complete()


def test_w_m1_03_sheet_cross_check_warnings_are_shown(app):
    wizard, step, _, _ = app
    wizard.steps[1].commit_edit(1, "Drainage Area (km2)", "999")
    wizard.steps[1].import_zonal_means(str(SAMPLE_ZONAL))
    wizard.go_to(2)

    step.select_dam("cubuk_1")

    assert "drainage area" in step.warning_var.get()


def test_w_m1_03_the_list_follows_the_dams_of_the_project(app):
    wizard, step, _, tmp_path = app
    step.select_dam("cubuk_1")
    table = tmp_path / "one.csv"
    table.write_bytes(ONE_DAM_TABLE.encode("utf-8-sig"))
    wizard.steps[1].import_basin_table(str(table))
    wizard.go_to(2)

    assert list(step.dam_list.get(0, tk.END)) == ["Çubuk 1"]
