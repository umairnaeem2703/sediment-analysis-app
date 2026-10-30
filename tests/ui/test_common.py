import tkinter as tk

from src.ui import common
from src.utils.log import attach_project_log


def test_x_nfr_04_an_error_in_a_tk_callback_is_logged_and_shown_not_lost_on_the_console(tk_root, tmp_path, monkeypatch):
    path = attach_project_log(tmp_path)
    shown = []
    monkeypatch.setattr(common.messagebox, "showerror", lambda title, message: shown.append((title, message)))
    original = tk_root.report_callback_exception
    common.install_error_handler(tk_root)

    def broken():
        raise KeyError("callback")

    try:
        tk_root.after(0, broken)
        tk_root.update()
    finally:
        tk_root.report_callback_exception = original

    assert len(shown) == 1 and shown[0][0] == "Unexpected error" and "KeyError" in shown[0][1]
    assert "KeyError: 'callback'" in path.read_text(encoding="utf-8")


def test_x_nfr_04_every_error_dialog_is_also_in_the_log(tmp_path, monkeypatch):
    path = attach_project_log(tmp_path)
    monkeypatch.setattr(common.messagebox, "showerror", lambda title, message: None)

    common.show_error("Flow file", "no such column")

    assert "WARNING Flow file: no such column" in path.read_text(encoding="utf-8")


def test_x_nfr_04_opening_a_project_starts_its_log(tk_root, tmp_path):
    from src.ui.steps.project_step import ProjectStep
    from src.ui.wizard import Wizard

    top = tk.Toplevel(tk_root)
    try:
        project_step = ProjectStep()
        Wizard(top, [project_step])
        project_step.create_project(str(tmp_path / "project"), "Region")
        log = tmp_path / "project" / "logs" / "app.log"
        assert log.is_file() and "Project Region opened" in log.read_text(encoding="utf-8")
    finally:
        top.destroy()


def test_x_nfr_04_every_warning_dialog_is_also_in_the_log(tmp_path, monkeypatch):
    path = attach_project_log(tmp_path)
    monkeypatch.setattr(common.messagebox, "showwarning", lambda title, message: None)

    common.show_warning("Grain fractions", "the supplied tau_ri differs")

    assert "WARNING Grain fractions: the supplied tau_ri differs" in path.read_text(encoding="utf-8")


def test_x_nfr_04_without_a_project_log_the_dialog_says_the_traceback_was_not_saved():
    message = common.unexpected_message(ZeroDivisionError("boom"))

    assert "Unexpected ZeroDivisionError: boom" in message and "not saved" in message and "console" not in message
