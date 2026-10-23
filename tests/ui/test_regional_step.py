import tkinter as tk

import pytest

from src.services.project import Project
from src.ui.steps.project_step import ProjectStep
from src.ui.steps.regional_step import RegionalStep
from src.ui.wizard import Wizard
from src.utils.paths import resource_path
from tests.ui.test_wizard_shell import FakeStep

HEADER = "Dam Name,Basin Name,Sub-basin Name,Drainage Area (km2),Main Waterway Slope"
SAMPLE_BASINS = resource_path("inputs", "master_yield.csv")
SAMPLE_ZONAL = resource_path("inputs", "raw_zonal_means.csv")
SAMPLE_SHEETS = [
    resource_path("inputs", "bathymetry", f"{s}_bathymetry.csv") for s in ("kavsakkaya", "cubuk_1", "cubuk_2")
]


@pytest.fixture()
def dialogs(monkeypatch):
    shown = {"error": [], "warning": []}
    monkeypatch.setattr("src.ui.steps.regional_step.show_error", lambda t, m: shown["error"].append((t, m)))
    monkeypatch.setattr("src.ui.steps.regional_step.show_warning", lambda t, m: shown["warning"].append((t, m)))
    monkeypatch.setattr("src.ui.steps.project_step.show_error", lambda t, m: shown["error"].append((t, m)))
    return shown


@pytest.fixture()
def app(tk_root, tmp_path, dialogs):
    top = tk.Toplevel(tk_root)
    project_step, regional_step, later = ProjectStep(), RegionalStep(), FakeStep("Later")
    wizard = Wizard(top, [project_step, regional_step, later])
    wizard.frame.pack(fill="both", expand=True)
    project_step.create_project(str(tmp_path / "project"), "Region")
    wizard.go_to(1)
    yield wizard, regional_step, later, tmp_path
    top.destroy()


def _csv(tmp_path, name, *rows):
    path = tmp_path / name
    path.write_bytes(("\n".join([HEADER, *rows]) + "\n").encode("utf-8-sig"))
    return path


def _flagged(step):
    return [iid for iid in step.tree.get_children() if "invalid" in step.tree.item(iid, "tags")]


def test_w_x_01_the_step_starts_empty_and_nothing_is_loaded(app):
    wizard, step, _, _ = app

    assert step.tree.get_children() == ()
    assert not step.is_complete()
    assert "not imported" in step.status_vars["basin"].get()
    assert "not imported" in step.status_vars["zonal"].get()


def test_w_m1_02_importing_the_sample_table_fills_the_grid_and_creates_the_dams(app, dialogs):
    wizard, step, _, _ = app

    step.import_basin_table(str(SAMPLE_BASINS))

    assert [step.tree.set(iid, "Dam Name") for iid in step.tree.get_children()] == ["Kavşakkaya", "Çubuk 1", "Çubuk 2"]
    assert _flagged(step) == []
    assert step.problem_list.size() == 0
    assert "valid" in step.status_vars["basin"].get() and "3 dam(s)" in step.status_vars["basin"].get()
    assert [d.slug for d in wizard.project.dams] == ["kavsakkaya", "cubuk_1", "cubuk_2"]
    assert dialogs["error"] == []


def test_w_m1_02_the_step_completes_with_a_valid_table_and_zonal_means_and_next_opens(app):
    wizard, step, later, _ = app
    step.import_basin_table(str(SAMPLE_BASINS))
    assert not step.is_complete()

    step.import_zonal_means(str(SAMPLE_ZONAL))

    assert step.is_complete()
    assert "6 sub-basin" in step.status_vars["zonal"].get()
    assert not wizard.next_button.instate(["disabled"])
    wizard.next()
    assert wizard.current == 2


def test_w_m1_02_invalid_cells_are_flagged_and_the_step_stays_incomplete(app):
    wizard, step, _, tmp_path = app

    step.import_basin_table(str(_csv(tmp_path, "bad.csv", "A,B,S1,10,0.1", "A,B,S2,-1,steep")))

    assert _flagged(step) == ["1"]
    assert step.tree.set("1", "Drainage Area (km2)") == "⚠ -1"
    assert step.tree.set("1", "Main Waterway Slope") == "⚠ steep"
    assert step.tree.set("1", "Dam Name") == "A"  # only the invalid cells carry the marker
    assert step.problem_list.size() == 2
    assert "row 3" in step.problem_list.get(0)
    assert "problem" in step.status_vars["basin"].get()
    step.import_zonal_means(str(SAMPLE_ZONAL))
    assert not step.is_complete()
    assert wizard.project.dams == []


def test_w_m1_02_editing_a_cell_saves_the_project_copy_and_clears_the_flag(app):
    wizard, step, _, tmp_path = app
    step.import_basin_table(str(_csv(tmp_path, "bad.csv", "A,B,S1,10,0.1", "A,B,S2,-1,0.2")))

    step.commit_edit(1, "Drainage Area (km2)", "25")

    assert _flagged(step) == []
    assert step.problem_list.size() == 0
    copy = wizard.project.folder / "inputs" / "basins.csv"
    assert "25" in copy.read_text(encoding="utf-8-sig")
    assert [d.slug for d in wizard.project.dams] == ["a"]


def test_w_x_02_editing_the_grid_resets_later_steps_and_names_them(app):
    wizard, step, later, tmp_path = app
    step.import_basin_table(str(SAMPLE_BASINS))
    step.import_zonal_means(str(SAMPLE_ZONAL))
    later.done = True
    wizard.refresh()

    step.commit_edit(0, "Main Waterway Slope", "0.24")

    assert later.resets >= 1 and later.done is False
    assert "Later" in wizard.notice_var.get()
    assert step.is_complete()


def test_w_x_02_an_edit_that_changes_nothing_resets_nothing(app):
    wizard, step, later, _ = app
    step.import_basin_table(str(SAMPLE_BASINS))
    step.import_zonal_means(str(SAMPLE_ZONAL))
    later.done = True
    resets = later.resets

    step.commit_edit(0, "Main Waterway Slope", "0.23")

    assert later.resets == resets and later.done is True


def test_w_m1_02_dams_that_leave_the_table_are_named_in_the_notice(app):
    wizard, step, _, tmp_path = app
    step.import_basin_table(str(SAMPLE_BASINS))

    step.import_basin_table(str(_csv(tmp_path, "one.csv", "Çubuk 1,Sakarya,Ankara Alt Havzası,834.7,0.09")))

    assert "Kavşakkaya" in wizard.notice_var.get() and "Çubuk 2" in wizard.notice_var.get()


def test_w_m1_02_an_unreadable_or_incomplete_table_shows_an_error_and_changes_nothing(app, dialogs):
    wizard, step, _, tmp_path = app
    step.import_basin_table(str(SAMPLE_BASINS))
    bad = tmp_path / "nocols.csv"
    bad.write_text("Dam Name,Basin Name\nA,B\n", encoding="utf-8")

    step.import_basin_table(str(bad))

    assert len(dialogs["error"]) == 1 and "required column" in dialogs["error"][0][1]
    assert len(step.tree.get_children()) == 3  # the earlier valid table is still shown


def test_w_m1_02_dam_sheets_are_matched_and_counted(app, dialogs):
    wizard, step, _, tmp_path = app
    step.import_basin_table(str(SAMPLE_BASINS))
    stranger = tmp_path / "stranger.csv"
    stranger.write_text(
        SAMPLE_SHEETS[1].read_text(encoding="utf-8-sig").replace("Çubuk 1", "Sariyar"), encoding="utf-8"
    )

    step.import_dam_sheets([str(p) for p in SAMPLE_SHEETS[:2]] + [str(stranger)])

    assert "2 of 3" in step.status_vars["sheets"].get()
    assert len(dialogs["error"]) == 1 and "Sariyar" in dialogs["error"][0][1]


def test_w_m1_02_dam_sheet_warnings_are_shown(app, dialogs):
    wizard, step, _, tmp_path = app
    step.import_basin_table(str(SAMPLE_BASINS))
    off = tmp_path / "off.csv"
    off.write_text(SAMPLE_SHEETS[1].read_text(encoding="utf-8-sig").replace("834.7", "999"), encoding="utf-8")

    step.import_dam_sheets([str(off)])

    assert len(dialogs["warning"]) == 1 and "drainage area" in dialogs["warning"][0][1]


def test_w_m1_02_zonal_warnings_are_shown(app, dialogs):
    wizard, step, _, tmp_path = app
    z = tmp_path / "z.csv"
    z.write_text("Sub-basin,MEAN\nA,1.5\nB,\n", encoding="utf-8")

    step.import_zonal_means(str(z))

    assert len(dialogs["warning"]) == 1 and "skipped 1 row(s)" in dialogs["warning"][0][1]


def test_w_m1_01_reopening_the_project_restores_the_step(app, tk_root):
    wizard, step, _, tmp_path = app
    step.import_basin_table(str(SAMPLE_BASINS))
    step.import_zonal_means(str(SAMPLE_ZONAL))

    top = tk.Toplevel(tk_root)
    try:
        other_project, other_step = ProjectStep(), RegionalStep()
        other = Wizard(top, [other_project, other_step])
        other_project.open_project(str(wizard.project.folder))
        other.go_to(1)

        assert other_step.is_complete()
        assert len(other_step.tree.get_children()) == 3
        assert [d.slug for d in other.project.dams] == ["kavsakkaya", "cubuk_1", "cubuk_2"]
    finally:
        top.destroy()


def test_w_m1_01_a_missing_copy_is_reported_in_the_step(app, tk_root):
    wizard, step, _, tmp_path = app
    step.import_basin_table(str(SAMPLE_BASINS))
    (wizard.project.folder / "inputs" / "basins.csv").unlink()

    top = tk.Toplevel(tk_root)
    try:
        other_project, other_step = ProjectStep(), RegionalStep()
        Wizard(top, [other_project, other_step])
        other_project.open_project(str(wizard.project.folder))
        other_step.on_show()

        assert not other_step.is_complete()
        assert other_step.problem_list.size() == 1
        assert "basins.csv" in other_step.problem_list.get(0)
    finally:
        top.destroy()


def test_w_m1_02_choosing_another_project_gives_the_step_that_project(app, tk_root):
    wizard, step, _, tmp_path = app
    step.import_basin_table(str(SAMPLE_BASINS))
    empty = Project.new(tmp_path / "other", "Other")

    wizard.set_project(empty)
    wizard.go_to(1)

    assert step.tree.get_children() == ()
    assert "not imported" in step.status_vars["basin"].get()


def _double_click(widget, x, y):
    # Tk recognises two quick presses as a double-click, so the real binding is exercised.
    for _ in range(2):
        widget.event_generate("<Button-1>", x=x, y=y)
        widget.event_generate("<ButtonRelease-1>", x=x, y=y)


def _double_click_cell(step, top, item, column):
    top.update()
    x, y, width, height = step.tree.bbox(item, column)
    _double_click(step.tree, x + width // 2, y + height // 2)
    top.update()


def test_w_m1_02_double_click_opens_an_editor_and_enter_saves_the_cell(app):
    wizard, step, _, tmp_path = app
    step.import_basin_table(str(_csv(tmp_path, "bad.csv", "A,B,S1,10,0.1", "A,B,S2,-1,0.2")))
    top = wizard.frame.winfo_toplevel()

    _double_click_cell(step, top, "1", "#4")  # the Drainage Area (km2) column
    editor = step._editor
    assert editor is not None and editor.get() == "-1"
    editor.focus_force()
    top.update()
    editor.delete(0, tk.END)
    editor.insert(0, "25")
    editor.event_generate("<Return>")
    top.update()

    assert step._editor is None
    assert _flagged(step) == []
    assert step.tree.set("1", "Drainage Area (km2)") == "25"
    assert "25" in (wizard.project.folder / "inputs" / "basins.csv").read_text(encoding="utf-8-sig")


def test_w_m1_02_escape_leaves_the_cell_alone(app):
    wizard, step, _, tmp_path = app
    step.import_basin_table(str(_csv(tmp_path, "bad.csv", "A,B,S1,10,0.1", "A,B,S2,-1,0.2")))
    top = wizard.frame.winfo_toplevel()

    _double_click_cell(step, top, "1", "#4")
    step._editor.focus_force()
    top.update()
    step._editor.delete(0, tk.END)
    step._editor.insert(0, "25")
    step._editor.event_generate("<Escape>")
    top.update()

    assert step._editor is None
    assert _flagged(step) == ["1"]
    assert wizard.regional.grid.at[1, "Drainage Area (km2)"] == "-1"


def test_w_m1_02_double_clicking_the_header_or_empty_space_does_nothing(app):
    wizard, step, _, _ = app
    step.import_basin_table(str(SAMPLE_BASINS))
    top = wizard.frame.winfo_toplevel()
    top.update()

    _double_click(step.tree, 5, 2)  # the heading row
    top.update()

    assert step._editor is None
