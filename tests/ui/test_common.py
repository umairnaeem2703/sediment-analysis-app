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


def test_w_m3_01_hovering_a_point_of_the_trend_chart_shows_the_year_and_both_values():
    import pandas as pd
    from matplotlib.backend_bases import LocationEvent, MouseEvent
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    from src.core.wilcock import WATER_YEAR_COLUMN
    from src.services.bedload import FLOW_M3_S, MASS_T
    from src.services.reporting import bedload_trend_figure

    table = pd.DataFrame(
        {WATER_YEAR_COLUMN: [1991, 1992, 1993], FLOW_M3_S: [1.04, 2.64, 2.35], MASS_T: [0, 628345.4, 47000]}
    )
    canvas = FigureCanvasAgg(bedload_trend_figure(table))
    canvas.draw()
    common.add_point_readout(canvas)
    note = canvas.figure.axes[-1].texts[-1]
    mass_line = canvas.figure.axes[1].get_lines()[0]
    x, y = mass_line.get_transform().transform((1992, 628345.4))

    MouseEvent("motion_notify_event", canvas, x + 3, y - 3)._process()
    assert note.get_visible()
    assert note.get_text().splitlines() == [
        "Water Year (Oct–Sep): 1992",
        "Annual Mean Flow (m³/s): 2.64",
        "Annual Bed Load (t/yr): 628,345",
    ]

    MouseEvent("motion_notify_event", canvas, x + 40, y - 40)._process()
    assert not note.get_visible()
    MouseEvent("motion_notify_event", canvas, x, y)._process()
    LocationEvent("figure_leave_event", canvas, x, y)._process()
    assert not note.get_visible()
