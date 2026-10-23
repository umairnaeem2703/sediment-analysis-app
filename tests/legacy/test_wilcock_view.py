"""
Tests for WilcockView (src/ui/wilcock_view.py): summary-table formatting and DSI settings.

Show* dialogs are patched so no Tk messageboxes block. execute_wc_analysis is run with a
synchronous stand-in for run_in_background and a no-op graph render.
"""

import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from src.core.monthly_flow_preprocessor import DEFAULT_SEED, DEFAULT_SIGMA
from src.core.wilcock import WATER_YEAR_COLUMN
from src.ui.wilcock_view import WilcockView, _parse_dsi_settings
from src.utils.paths import resource_path

DAILY_FLOW = ("inputs", "daily_flow_data.csv")
DSI_FLOW = ("inputs", "dam_flow_data", "cubuk_1_flow.csv")


@pytest.fixture()
def wc_view(tk_root):
    window = tk.Toplevel(tk_root)
    notebook = ttk.Notebook(window)
    notebook.pack()
    app = SimpleNamespace(annual_summary=None, root=window)
    yield WilcockView(notebook, app)
    window.destroy()


def _summary():
    return pd.DataFrame(
        {
            "Annual_Average_Flow": [12.3456789],
            "Annual_Average_Bed_Load_metric_tons_yr": [2703286.1234],
        },
        index=pd.Index([1981], name="Year"),
    )


def _run_inline(root, task, on_complete):
    try:
        result, error = task(), None
    except Exception as exc:
        result, error = None, exc
    on_complete(result, error)


def _run_analysis(wc_view, flow_parts, sigma="0.6", seed="0"):
    """Run execute_wc_analysis synchronously; return (annual summaries, show_error mock)."""
    summaries = []
    wc_view.app.set_wilcock_results = lambda summary, phase3: summaries.append(summary)
    wc_view._render_wc_graph = lambda: None
    wc_view.flow_file_var.set(str(resource_path(*flow_parts)))
    wc_view.frac_file_var.set(str(resource_path("inputs", "fractional_parameters.csv")))
    wc_view.sigma_var.set(sigma)
    wc_view.seed_var.set(seed)
    with (
        patch("src.ui.wilcock_view.run_in_background", _run_inline),
        patch("src.ui.wilcock_view.show_error") as show_error,
        patch("src.ui.wilcock_view.show_warning"),
    ):
        wc_view.execute_wc_analysis()
    return summaries, show_error


def test_summary_table_formats_flow_and_bedload(wc_view):
    wc_view.app.annual_summary = _summary()
    with patch("src.ui.wilcock_view.show_error") as show_error:
        wc_view.display_wc_summary_table()
    assert not show_error.called

    tree = next(w for w in wc_view.wc_graph_frame.winfo_children() if isinstance(w, ttk.Treeview))
    (item,) = tree.get_children()
    assert list(tree["columns"]) == [
        "Year",
        "Annual Average Flow (m3/s)",
        "Annual Average Bed Load (metric tons/year)",
    ]
    assert [str(v) for v in tree.item(item, "values")] == ["1981", "12.3457", "2,703,286.12"]


def test_summary_table_shows_water_year_heading(wc_view):
    wc_view.app.annual_summary = _summary().rename_axis(WATER_YEAR_COLUMN)
    with patch("src.ui.wilcock_view.show_error"):
        wc_view.display_wc_summary_table()

    tree = next(w for w in wc_view.wc_graph_frame.winfo_children() if isinstance(w, ttk.Treeview))
    (item,) = tree.get_children()
    assert tree.heading(WATER_YEAR_COLUMN, "text") == "Water Year (Oct–Sep)"
    assert str(tree.item(item, "values")[0]) == "1981"


def test_dsi_settings_default_to_preprocessor_defaults():
    assert _parse_dsi_settings(str(DEFAULT_SIGMA), str(DEFAULT_SEED)) == (DEFAULT_SIGMA, DEFAULT_SEED)


@pytest.mark.parametrize("sigma", ["0.4", "0,4", " 0,4 "], ids=["point", "comma", "padded-comma"])
def test_dsi_settings_accept_decimal_comma(sigma):
    assert _parse_dsi_settings(sigma, "7") == (0.4, 7)


@pytest.mark.parametrize(
    "sigma, seed",
    [("abc", "0"), ("-0.5", "0"), ("nan", "0"), ("0.6", "-1"), ("0.6", "1.5")],
    ids=["text-sigma", "negative-sigma", "nan-sigma", "negative-seed", "fractional-seed"],
)
def test_dsi_settings_reject_invalid_fields(sigma, seed):
    with pytest.raises(ValueError, match="seed"):
        _parse_dsi_settings(sigma, seed)


def test_invalid_dsi_settings_do_not_block_daily_flow_run(wc_view):
    summaries, show_error = _run_analysis(wc_view, DAILY_FLOW, sigma="abc")
    assert not show_error.called
    assert len(summaries) == 1


def test_invalid_dsi_settings_are_reported_for_dsi_file(wc_view):
    summaries, show_error = _run_analysis(wc_view, DSI_FLOW, sigma="abc")
    assert summaries == []
    assert show_error.called
    assert "σ" in show_error.call_args[0][1]


def test_dsi_run_accepts_decimal_comma_sigma(wc_view):
    comma, comma_error = _run_analysis(wc_view, DSI_FLOW, sigma="0,6")
    point, _ = _run_analysis(wc_view, DSI_FLOW, sigma="0.6")
    assert not comma_error.called
    pd.testing.assert_frame_equal(comma[0], point[0])
    assert comma[0].index.name == WATER_YEAR_COLUMN
