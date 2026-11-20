import tkinter as tk

import pytest

from src.ui.steps import reservoir_step
from src.ui.steps.dam_step import DamStep
from src.ui.steps.project_step import ProjectStep
from src.ui.steps.regional_step import RegionalStep
from src.ui.steps.reservoir_step import ReservoirStep
from src.ui.wizard import Wizard
from tests.samples import SAMPLE_BASINS, SAMPLE_H_MIN, SAMPLE_ZONAL, sample_curve
from tests.ui.fakes import FakeStep


@pytest.fixture()
def errors(monkeypatch):
    shown = []
    for module in ("dam_step", "project_step", "reservoir_step"):
        monkeypatch.setattr(f"src.ui.steps.{module}.show_error", lambda t, m: shown.append((t, m)))
    return shown


@pytest.fixture()
def warnings(monkeypatch):
    shown = []
    monkeypatch.setattr("src.ui.steps.reservoir_step.show_warning", lambda t, m: shown.append((t, m)))
    return shown


@pytest.fixture()
def app(tk_root, tmp_path, errors):
    """The wizard at step 3 with the sample tables imported. The suspended and bedload steps are stand-ins: the curve
    does not use their results."""
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
    wizard.go_to(2)
    yield wizard, step, later, tmp_path
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


def _generated(wizard, step):
    _reach_step(wizard)
    step.use_curve_file(str(sample_curve("kavsakkaya")))
    step.h_min_var.set(str(SAMPLE_H_MIN["kavsakkaya"]))
    step.generate()


def _rows(step):
    return [step.tree.item(iid, "values") for iid in step.tree.get_children()]


def test_w_m4_01_the_step_is_locked_until_the_earlier_steps_are_complete(app):
    wizard, step, _, _ = app

    assert not wizard.can_enter(5) and not step.is_complete()


def test_w_m4_01_the_step_names_the_dam_and_that_no_curve_sheet_is_chosen(app):
    wizard, step, _, _ = app
    _reach_step(wizard)

    assert "Kavşakkaya" in step.dam_var.get() and step.curve_file_var.get() == "Curve sheet: none chosen"
    assert not step.is_complete() and not _rows(step)


def test_x_01_generating_without_a_curve_sheet_says_where_to_import_it(app, errors):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.h_min_var.set("1080")

    step.generate()

    assert not step.is_complete() and len(errors) == 1 and "no reservoir curve sheet" in errors[0][1]


def test_w_m4_01_the_imported_sheet_is_named_and_kept_on_the_dam(app):
    wizard, step, _, _ = app
    _reach_step(wizard)

    step.use_curve_file(str(sample_curve("kavsakkaya")))

    assert step.curve_file_var.get() == "Curve sheet: kavsakkaya_curve.csv"
    assert wizard.project.dams[0].curve_sheet == "inputs/curves/kavsakkaya_curve.csv"


def test_w_m4_01_generate_fills_the_table_the_chart_and_the_summary(app):
    wizard, step, _, _ = app

    _generated(wizard, step)

    assert step.is_complete()
    rows = _rows(step)
    assert len(rows) == 69 and rows[0] == ("1055.00", "0.014", "0.028") and rows[-1][0] == "1124.00"
    summary = step.summary_var.get()
    assert summary == "Dead volume 4.69 hm³ below Hmin 1071.99 m. Hbed 1055 m, Hcrest 1124 m, Vmax 96.52 hm³."
    assert wizard.project.dams[0].h_min_m == 1071.99
    assert step._canvas is not None and step._canvas.get_tk_widget().winfo_exists()
    assert step.warning_var.get() == ""
    wizard.refresh()
    assert not wizard.next_button.instate(["disabled"])


def test_w_m4_01_an_invalid_curve_sheet_is_refused_and_named(app, errors, tmp_path):
    wizard, step, _, _ = app
    _reach_step(wizard)
    bad = tmp_path / "bad.csv"
    bad.write_text("Elevation (m),Volume (hm3),Surface Area (km2)\n100,5,1\n110,5,2\n", encoding="utf-8")

    step.use_curve_file(str(bad))

    assert len(errors) == 1 and "row 3: the volume 5 hm³" in errors[0][1]
    assert wizard.project.dams[0].curve_sheet is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "Hmin (m) must be a number, found an empty cell"),
        ("1071,99", "Hmin (m) must be a number, found '1071,99'"),
        ("1124", "Hmin (1124 m) must lie above Hbed (1055 m) and below Hcrest (1124 m)"),
    ],
)
def test_w_m4_01_an_hmin_that_is_not_a_level_inside_the_curve_is_refused(app, errors, text, expected):
    wizard, step, _, _ = app
    _reach_step(wizard)
    step.use_curve_file(str(sample_curve("kavsakkaya")))
    step.h_min_var.set(text)

    step.generate()

    assert not step.is_complete() and not _rows(step) and wizard.project.dams[0].h_min_m is None
    assert len(errors) == 1 and errors[0][0] == "Reservoir curve" and expected in errors[0][1]


def test_w_m4_01_editing_hmin_un_completes_the_step(app):
    wizard, step, _, _ = app
    _generated(wizard, step)

    step.h_min_var.set("1080")

    assert not step.is_complete()
    step.h_min_var.set(str(SAMPLE_H_MIN["kavsakkaya"]))
    assert step.is_complete()


def test_w_x_02_a_new_hmin_clears_the_later_steps(app):
    wizard, step, later, _ = app
    _generated(wizard, step)
    later.done = True

    step.h_min_var.set("1080")
    step.generate()

    assert step.is_complete() and later.done is False and "Hmin changed" in wizard.notice_var.get()
    assert wizard.project.dams[0].h_min_m == 1080.0


def test_w_m4_01_the_kept_hmin_is_shown_when_the_dam_is_chosen_again(app):
    wizard, step, _, _ = app
    _generated(wizard, step)
    wizard.steps[2].select_dam("cubuk_2")
    wizard.steps[2].use_dam()
    wizard.steps[2].select_dam("kavsakkaya")
    wizard.steps[2].use_dam()

    assert step.h_min_var.get() == "1071.99"


def test_w_m4_01_the_warnings_of_the_sheet_are_shown(app, warnings, tmp_path):
    wizard, step, _, _ = app
    _reach_step(wizard)
    noted = tmp_path / "noted.csv"
    text = sample_curve("kavsakkaya").read_text(encoding="utf-8").splitlines()
    noted.write_text("\n".join([text[0] + ",Note", *(line + ",x" for line in text[1:])]) + "\n", encoding="utf-8")

    step.use_curve_file(str(noted))
    step.h_min_var.set("1080")
    step.generate()

    assert len(warnings) == 1 and "Note" in warnings[0][1]
    assert step.is_complete() and "Note" in step.warning_var.get()


def test_w_x_02_replacing_the_curve_sheet_clears_the_curve_and_the_later_steps(app):
    wizard, step, later, _ = app
    _generated(wizard, step)
    later.done = True

    step.use_curve_file(str(sample_curve("kavsakkaya")))

    assert not step.is_complete() and not _rows(step) and later.done is False
    assert "Later" in wizard.notice_var.get()


def test_w_x_02_generating_again_keeps_the_later_steps(app):
    wizard, step, later, _ = app
    _generated(wizard, step)
    later.done = True

    step.generate()

    assert later.done is True and step.is_complete()


def test_w_x_02_choosing_a_different_dam_clears_the_curve_and_shows_that_dams_sheet(app):
    wizard, step, _, _ = app
    _generated(wizard, step)

    wizard.steps[2].select_dam("cubuk_2")

    assert not step.is_complete() and not _rows(step) and step._canvas is None and step.summary_var.get() == ""
    wizard.steps[2].use_dam()
    for fake in wizard.steps[3:5]:
        fake.done = True
    assert wizard.go_to(5)
    assert "Çubuk 2" in step.dam_var.get() and step.curve_file_var.get() == "Curve sheet: none chosen"


def test_w_x_02_editing_the_basin_table_clears_the_curve(app):
    wizard, step, _, _ = app
    _generated(wizard, step)

    wizard.steps[1].commit_edit(1, "Main Waterway Slope", "0.1")

    assert not step.is_complete() and not _rows(step)


def test_w_m4_01_the_grid_shows_the_columns_of_the_curve_table():
    assert [key for key, *_ in reservoir_step.GRID_COLUMNS] == ["Elevation_m", "Volume_hm3", "Area_km2"]
