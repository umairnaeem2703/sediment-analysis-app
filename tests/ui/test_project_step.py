import json
import tkinter as tk

import pytest

from src.services.project import Project
from src.ui.steps.project_step import ProjectStep
from src.ui.wizard import Wizard


@pytest.fixture()
def errors(monkeypatch):
    shown = []
    monkeypatch.setattr("src.ui.steps.project_step.show_error", lambda title, message: shown.append((title, message)))
    return shown


@pytest.fixture()
def make_wizard(tk_root):
    tops = []

    def make():
        top = tk.Toplevel(tk_root)
        tops.append(top)
        step = ProjectStep()
        wizard = Wizard(top, [step])
        wizard.frame.pack(fill="both", expand=True)
        return wizard, step

    yield make
    for top in tops:
        top.destroy()


def test_w_m1_01_creating_a_project_writes_project_json_and_completes_the_step(make_wizard, tmp_path, errors):
    wizard, step = make_wizard()
    assert not step.is_complete()

    step.create_project(str(tmp_path / "region"), "Sakarya Region")

    assert errors == []
    assert step.is_complete()
    assert wizard.project.name == "Sakarya Region"
    data = json.loads((tmp_path / "region" / "project.json").read_text(encoding="utf-8"))
    assert data["name"] == "Sakarya Region"
    assert "Sakarya Region" in step.summary_var.get()


def test_w_m1_01_a_saved_project_reopens_with_the_same_state(make_wizard, tmp_path, errors):
    first, first_step = make_wizard()
    first_step.create_project(str(tmp_path / "region"), "Sakarya Region")
    first.project.add_dam("Çubuk 1").commissioning_year = 1965
    first.project.save()

    second, second_step = make_wizard()
    second_step.open_project(str(tmp_path / "region"))

    assert errors == []
    assert second.project == first.project
    assert second_step.name_var.get() == "Sakarya Region"
    assert second_step.folder_var.get() == str(tmp_path / "region")
    assert "1 dam(s)" in second_step.summary_var.get()
    assert second_step.is_complete()


def test_w_m1_01_creating_over_an_existing_project_is_refused_with_a_message(make_wizard, tmp_path, errors):
    Project.new(tmp_path / "region", "Existing")
    wizard, step = make_wizard()

    step.create_project(str(tmp_path / "region"), "Another")

    assert wizard.project is None
    assert len(errors) == 1
    assert "already contains a project" in errors[0][1]


@pytest.mark.parametrize(("folder", "name"), [("", "x"), ("some-folder", ""), ("  ", "  ")])
def test_w_m1_01_folder_and_name_are_both_required(make_wizard, errors, folder, name):
    wizard, step = make_wizard()

    step.create_project(folder, name)

    assert wizard.project is None
    assert len(errors) == 1
    assert "folder" in errors[0][1] and "name" in errors[0][1]


def test_w_m1_01_opening_a_folder_that_is_not_a_project_names_the_problem(make_wizard, tmp_path, errors):
    wizard, step = make_wizard()

    step.open_project(str(tmp_path))

    assert wizard.project is None
    assert "project.json" in errors[0][1]


def test_w_m1_01_a_newer_project_file_is_refused(make_wizard, tmp_path, errors):
    project = Project.new(tmp_path / "region", "x")
    path = project.folder / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = 99
    path.write_text(json.dumps(data), encoding="utf-8")
    wizard, step = make_wizard()

    step.open_project(str(project.folder))

    assert wizard.project is None
    assert "newer version" in errors[0][1]


def test_w_x_01_nothing_is_loaded_until_the_user_chooses_a_project(make_wizard, errors):
    wizard, step = make_wizard()

    assert wizard.project is None
    assert step.name_var.get() == "" and step.folder_var.get() == ""
    assert errors == []
