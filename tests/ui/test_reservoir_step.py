import tkinter as tk

import pytest

from src.ui.steps import reservoir_step
from src.ui.steps.dam_step import DamStep
from src.ui.steps.project_step import ProjectStep
from src.ui.steps.regional_step import RegionalStep
from src.ui.steps.reservoir_step import ReservoirStep
from src.ui.wizard import Wizard
from tests.samples import SAMPLE_BASINS, SAMPLE_ZONAL, sample_sheet
from tests.ui.fakes import FakeStep

SLUGS = ("kavsakkaya", "cubuk_1", "cubuk_2")


@pytest.fixture()
def errors(monkeypatch):
    shown = []
    for module in ("dam_step", "project_step", "reservoir_step"):
        monkeypatch.setattr(f"src.ui.steps.{module}.show_error", lambda t, m: shown.append((t, m)))
    return shown


@pytest.fixture()
def app(tk_root, tmp_path, errors):
    """The wizard at step 3 with the sample tables and the three dam sheets imported. The suspended and bedload
    steps are stand-ins: the curve does not use their results."""
    top = tk.Toplevel(tk_root)
    project_step, regional_step, dam_step = ProjectStep(), RegionalStep(), DamStep()
    suspended, bedload, step, later = (
        FakeStep("Suspended"),
        FakeStep("Bedload"),
        ReservoirStep(dam_step),
        FakeStep("Later"),
    )
    wizard = Wizard(top, [project_step, regional_step, dam_step, suspended, bedload, step, later])
    wizard.frame.pack(fill="both", expand=True)
    project_step.create_project(str(tmp_path / "project"), "Region")
    wizard.go_to(1)
    regional_step.import_basin_table(str(SAMPLE_BASINS))
    regional_step.import_zonal_means(str(SAMPLE_ZONAL))
    regional_step.import_dam_sheets([str(sample_sheet(slug)) for slug in SLUGS])
    wizard.go_to(2)
    yield wizard, step, later, top
    top.destroy()


def _reach_step(wizard, slug="kavsakkaya"):
    """Choose a dam and open the curve step."""
    dam_step = wizard.steps[2]
    dam_step.select_dam(slug)
    dam_step.use_dam()
    for fake in wizard.steps[3:5]:
        fake.done = True
    wizard.refresh()
    assert wizard.go_to(5)


def _rows(step):
    return [step.tree.item(iid, "values") for iid in step.tree.get_children()]


def _fields(step):
    return [
        variable.get()
        for variable in (
            step.bed_var,
            step.h_min_var,
            step.max_elev_var,
            step.crest_var,
            step.active_var,
            step.max_vol_var,
            step.shape_var,
        )
    ]


def test_w_m4_01_the_step_is_locked_until_the_earlier_steps_are_complete(app):
    wizard, step, _, _ = app

    assert not wizard.can_enter(5) and not step.is_complete()


def test_w_m4_01_the_fields_are_prefilled_from_the_dam_sheet(app):
    wizard, step, _, _ = app
    _reach_step(wizard)

    assert _fields(step) == ["1063", "", "1122.3", "1124", "74.1", "80.8", ""]
    assert not step.is_complete() and not _rows(step)
    assert "Kavşakkaya" in step.dam_var.get()


def test_w_m4_01_the_shape_classes_are_offered(app):
    wizard, step, _, _ = app
    _reach_step(wizard)

    assert list(step.shape_box["values"]) == ["gorge", "hill", "foothill", "lake"]


def test_w_m4_01_generate_fills_the_table_the_chart_and_the_summary(app):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.shape_var.set("foothill")

    step.generate()

    assert step.is_complete()
    rows = _rows(step)
    assert len(rows) == 123 and rows[0] == ("1063.0", "0.000", "0.000") and rows[-1][0] == "1124.0"
    summary = step.summary_var.get()
    assert "m = 3.00" in summary and "1088.86" in summary and "shape class" in summary and "6.70" in summary
    assert step._canvas is not None and step._canvas.get_tk_widget().winfo_exists()
    assert step.warning_var.get() == ""
    wizard.refresh()
    assert not wizard.next_button.instate(["disabled"])


def test_w_m4_01_the_chosen_shape_class_is_kept_on_the_dam(app):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.shape_var.set("foothill")

    step.generate()

    assert wizard.project.dams[0].shape_class == "foothill"


def test_x_01_generating_without_hmin_or_a_shape_class_says_what_to_enter(app, errors):
    wizard, step, _, _ = app
    _reach_step(wizard)

    step.generate()

    assert not step.is_complete() and not _rows(step)
    assert len(errors) == 1 and "Hmin or a shape class" in errors[0][1]


def test_w_m4_01_an_invalid_entry_is_refused_and_named_and_the_old_curve_stays(app, errors):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.shape_var.set("foothill")
    step.generate()
    step.crest_var.set("1100")

    step.generate()

    assert len(errors) == 1 and "Hcrest" in errors[0][1]
    assert len(_rows(step)) == 123 and not step.is_complete()  # the fields no longer show what the curve was made with


def test_w_m4_01_a_given_hmin_is_used_kept_and_shown_in_step_3(app):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.h_min_var.set("1090")

    step.generate()

    assert "Hmin 1090" in step.summary_var.get() and "m = 3.16" in step.summary_var.get()
    assert wizard.project.dams[0].h_min_m == 1090.0
    dam_step = wizard.steps[2]
    assert dam_step.h_min_var.get() == "1090" and dam_step.is_complete()
    assert wizard.steps[3].done and wizard.steps[4].done  # Hmin does not reset the steps before the curve


def test_w_m4_01_a_changed_value_is_stored_as_an_edit_and_listed_against_the_sheet(app):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.shape_var.set("foothill")
    step.max_elev_var.set("1121")

    step.generate()

    assert wizard.project.dams[0].curve.max_elev_m == 1121.0
    assert "Hmax" in step.edits_var.get() and "1122.3" in step.edits_var.get()


def test_w_m4_01_the_plausibility_warnings_are_shown(app):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.shape_var.set("foothill")
    step.max_elev_var.set("1068")  # 5 m above the bed

    step.generate()

    assert step.is_complete() and "below 10 m" in step.warning_var.get()


def test_w_x_02_editing_a_field_un_completes_the_step(app):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.shape_var.set("foothill")
    step.generate()

    step.active_var.set("70")

    assert not step.is_complete()
    wizard.refresh()
    assert wizard.next_button.instate(["disabled"])


def test_w_x_02_generating_a_changed_curve_clears_the_later_steps(app):
    wizard, step, later, _ = app
    _reach_step(wizard)
    step.shape_var.set("foothill")
    step.generate()
    later.done = True
    step.shape_var.set("hill")

    step.generate()

    assert step.is_complete() and later.done is False
    assert "Later" in wizard.notice_var.get()


def test_w_x_02_generating_the_same_curve_again_keeps_the_later_steps(app):
    wizard, step, later, _ = app
    _reach_step(wizard)
    step.shape_var.set("foothill")
    step.generate()
    later.done = True

    step.generate()

    assert later.done is True and step.is_complete()


def test_w_x_02_choosing_a_different_dam_clears_the_curve_and_loads_that_dams_sheet(app):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.shape_var.set("foothill")
    step.generate()

    wizard.steps[2].select_dam("cubuk_2")

    assert not step.is_complete() and not _rows(step) and step._canvas is None and step.summary_var.get() == ""
    wizard.steps[2].use_dam()
    for fake in wizard.steps[3:5]:
        fake.done = True
    assert wizard.go_to(5)
    assert _fields(step) == ["1110", "", "1115.3", "1117", "22", "22.4", ""]


def test_w_m4_01_an_unreadable_sheet_clears_the_fields_and_says_so(app, errors):
    wizard, step, _, _ = app
    _reach_step(wizard)  # the fields now hold Kavşakkaya's inputs
    dam_step = wizard.steps[2]
    dam_step.select_dam("cubuk_2")
    dam_step.use_dam()
    for fake in wizard.steps[3:5]:
        fake.done = True
    (wizard.project.folder / wizard.project.dams[2].sheet).write_text("Dam Name\n", encoding="utf-8")

    assert wizard.go_to(5)

    assert _fields(step) == [""] * 7 and "cannot be read" in step.edits_var.get()
    step.generate()
    assert len(errors) == 1 and "Reservoir curve" == errors[0][0]


def test_w_x_02_editing_the_basin_table_clears_the_curve(app):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.shape_var.set("foothill")
    step.generate()

    wizard.steps[1].commit_edit(1, "Main Waterway Slope", "0.1")

    assert not step.is_complete() and not _rows(step)


def test_w_m4_01_going_back_and_forth_keeps_what_was_typed(app):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.shape_var.set("hill")
    step.max_elev_var.set("1121")

    wizard.go_to(2)
    wizard.go_to(5)

    assert step.shape_var.get() == "hill" and step.max_elev_var.get() == "1121"


def test_w_m4_01_the_grid_shows_the_columns_of_the_curve_table():
    assert [key for key, *_ in reservoir_step.GRID_COLUMNS] == ["Elevation_m", "Volume_hm3", "Area_km2"]


def test_w_m4_01_the_level_interval_is_offered_and_starts_at_half_a_metre(app):
    wizard, step, _, _ = app
    _reach_step(wizard)

    assert step.step_var.get() == "0.5"


def test_w_m4_01_generate_makes_the_table_at_the_entered_level_interval(app):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.shape_var.set("foothill")
    step.step_var.set("0.25")

    step.generate()

    assert step.is_complete() and len(step.result.table) == 245
    rows = _rows(step)
    assert len(rows) == 245 and rows[0][0] == "1063.0" and rows[-1][0] == "1124.0"


def test_w_m4_01_an_invalid_level_interval_is_refused_before_anything_is_kept_on_the_dam(app, errors):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.shape_var.set("foothill")
    step.step_var.set("0")

    step.generate()

    assert len(errors) == 1 and "level interval" in errors[0][1]
    assert wizard.project.dams[0].shape_class is None and not _rows(step) and not step.is_complete()


def test_w_x_02_changing_the_level_interval_un_completes_the_step_and_keeps_the_later_steps(app):
    wizard, step, later, _ = app
    _reach_step(wizard)
    step.shape_var.set("foothill")
    step.generate()
    later.done = True
    step.step_var.set("0.25")

    assert not step.is_complete()
    wizard.refresh()
    assert wizard.next_button.instate(["disabled"])

    step.generate()

    assert step.is_complete() and later.done is True and len(_rows(step)) == 245
