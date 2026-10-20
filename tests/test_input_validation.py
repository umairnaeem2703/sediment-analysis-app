import tkinter as tk

import numpy as np
import pandas as pd
import pytest

from app import SedimentApp
from src.core.rusle import ZonalMatcher
from src.core.wilcock import FractionalModel, TimeSeriesAggregator
from src.utils.paths import read_table, resource_path


def _aggregator():
    model = FractionalModel()
    model.load_fractional_parameters(read_table(resource_path("inputs", "fractional_parameters.csv")))
    return TimeSeriesAggregator(model)


# --- read_table: decimal commas -------------------------------------------------

def test_read_table_semicolon_decimal_comma(tmp_path):
    path = tmp_path / "flow.csv"
    path.write_text("Date;Flow;Station\n01/01/2000;1,76;Göksu\n02/01/2000;2,5;Çoruh\n", encoding="utf-8-sig")
    df = read_table(str(path))
    assert df["Flow"].tolist() == [1.76, 2.5]
    assert df["Station"].tolist() == ["Göksu", "Çoruh"]
    assert df["Date"].tolist() == ["01/01/2000", "02/01/2000"]


def test_read_table_dot_decimal_unchanged(tmp_path):
    path = tmp_path / "flow.csv"
    path.write_text("Date,Flow\n01/01/2000,1.76\n", encoding="utf-8-sig")
    assert read_table(str(path))["Flow"].tolist() == [1.76]


# --- Wilcock flow headers and validation ----------------------------------------

@pytest.mark.parametrize("flow_header", ["Flow", "Flow Q (m3/s)", "Flow Q (m³/s)", "FLOW Q (M³/S)", "Debi"])
def test_flow_header_variants_accepted(flow_header):
    df = pd.DataFrame({"Date": ["01/01/2000", "02/01/2000"], flow_header: [10.0, 20.0]})
    summary = _aggregator().process_annual_averages(df)
    assert summary.loc[2000, "Annual_Average_Flow"] == 15.0


def test_bad_flow_and_date_rows_are_dropped_and_reported():
    df = pd.DataFrame(
        {
            "Date": ["01/01/2000", "02/01/2000", "not a date", "04/01/2000"],
            "Flow": [10.0, None, 30.0, 20.0],
        }
    )
    agg = _aggregator()
    summary = agg.process_annual_averages(df)
    assert summary.loc[2000, "Annual_Average_Flow"] == 15.0
    assert len(agg.warnings) == 1
    assert "1 row(s) with missing" in agg.warnings[0]
    assert "1 row(s) with unparseable" in agg.warnings[0]


def test_clean_flow_table_has_no_warnings():
    df = pd.DataFrame({"Date": ["01/01/2000"], "Flow": [5.0]})
    agg = _aggregator()
    agg.process_annual_averages(df)
    assert agg.warnings == []


def test_negative_flow_raises():
    df = pd.DataFrame({"Date": ["01/01/2000", "02/01/2000"], "Flow": [5.0, -1.0]})
    with pytest.raises(ValueError, match="negative"):
        _aggregator().process_annual_averages(df)


def test_all_invalid_rows_raises():
    df = pd.DataFrame({"Date": ["x", "y"], "Flow": [None, None]})
    with pytest.raises(ValueError, match="no rows"):
        _aggregator().process_annual_averages(df)


# --- Zonal matching ------------------------------------------------------------

def test_short_key_does_not_match_longer_number():
    lookup = {"112": 9.0}
    assert ZonalMatcher.resolve_zonal_mean(lookup, "12") is None


def test_ambiguous_loose_match_is_unmatched():
    lookup = {"3a": 1.0, "3b": 2.0}
    match = ZonalMatcher.resolve_zonal_match(lookup, "Sub-basin 3")
    assert match.value is None
    assert match.method == "ambiguous"
    assert match.candidates == ["3a", "3b"]
    assert ZonalMatcher.resolve_zonal_mean(lookup, "Sub-basin 3") is None


def test_unique_loose_match_is_flagged():
    lookup = {"3a": 1.0, "7": 2.0}
    match = ZonalMatcher.resolve_zonal_match(lookup, "Sub-basin 3")
    assert match.value == 1.0
    assert match.method == "loose"


def test_exact_match_is_flagged_exact():
    lookup = {"3": 1.5}
    assert ZonalMatcher.resolve_zonal_match(lookup, "Subbasin 3").method == "exact"


# --- Basin grid: Year is not used in the RUSLE tab --------------------------------

def _grid_app(tk_root, basin_csv):
    root = tk.Toplevel(tk_root)
    app = SedimentApp(root)
    app.rusle_view._populate_basin_tree(str(basin_csv))
    return root, app


def _basin_frame(**extra):
    return pd.DataFrame(
        {
            "Basin Name": ["B1", "B2"],
            "Sub-basin Name": ["S1", "S2"],
            "Area": [12.0, 8.0],
            "Main Waterway Slope": [0.02, 0.03],
            **extra,
        }
    )


def test_year_less_basin_table_loads_five_columns(tk_root, tmp_path):
    basin_csv = tmp_path / "basins.csv"
    _basin_frame().to_csv(basin_csv, index=False)
    root, app = _grid_app(tk_root, basin_csv)
    try:
        assert list(app.basin_tree["columns"]) == ["dam", "basin", "subbasin", "area", "slope"]
        rows = app.rusle_view._iter_basin_rows()
        assert [(r.basin, r.subbasin, r.area_km2, r.slope) for r in rows] == [
            ("B1", "S1", 12.0, 0.02),
            ("B2", "S2", 8.0, 0.03),
        ]
    finally:
        root.destroy()


@pytest.mark.parametrize("years, expect_warning", [([2005, 2006], True), ([2005, 2005], False)])
def test_multi_year_basin_file_warns(tk_root, tmp_path, monkeypatch, years, expect_warning):
    warnings = []
    monkeypatch.setattr("src.ui.rusle_view.show_warning", lambda title, message: warnings.append(message))
    basin_csv = tmp_path / "basins.csv"
    _basin_frame(Year=years).to_csv(basin_csv, index=False)
    root, app = _grid_app(tk_root, basin_csv)
    try:
        assert len(app.basin_tree.get_children()) == 2
        assert bool(warnings) is expect_warning
    finally:
        root.destroy()


def test_bundled_master_yield_runs_without_year(tk_root, monkeypatch, tmp_path):
    errors = []
    monkeypatch.setattr("src.ui.rusle_view.show_error", lambda title, message: errors.append(message))
    monkeypatch.setattr("src.ui.rusle_view.show_warning", lambda title, message: None)
    monkeypatch.chdir(tmp_path)
    root = tk.Toplevel(tk_root)
    try:
        app = SedimentApp(root)
        app.rusle_view._populate_basin_tree(str(resource_path("inputs", "master_yield.csv")))
        app.rusle_view.zonal_file_var.set(str(resource_path("inputs", "raw_zonal_means.csv")))
        app.rusle_view.execute_rusle_analysis()

        assert errors == []
        rows = len(app.basin_tree.get_children())
        assert len(app.results_tree.get_children()) == rows > 0
        assert list(app.phase2_df.columns) == ["Suspended_Volume_m3"]
        assert np.isclose(app.phase2_df["Suspended_Volume_m3"].iloc[0], app.rusle_results_df["volume_m3"].sum())
        assert not (tmp_path / "exports").exists()
    finally:
        root.destroy()


def test_results_tree_error_is_reported_not_swallowed(tk_root, monkeypatch):
    errors = []
    monkeypatch.setattr("src.ui.rusle_view.show_error", lambda title, message: errors.append(message))
    monkeypatch.setattr("src.ui.rusle_view.show_warning", lambda title, message: None)

    def boom(self):
        raise RuntimeError("render failed")

    monkeypatch.setattr("src.ui.rusle_view.RusleView._render_results_tree", boom)
    root = tk.Toplevel(tk_root)
    try:
        app = SedimentApp(root)
        app.rusle_view._populate_basin_tree(str(resource_path("inputs", "master_yield.csv")))
        app.rusle_view.zonal_file_var.set(str(resource_path("inputs", "raw_zonal_means.csv")))
        app.rusle_view.execute_rusle_analysis()
        assert errors == ["render failed"]
    finally:
        root.destroy()


def test_resolve_all_reports_loose_and_unresolved():
    lookup = {"3a": 1.0, "3b": 2.0, "7": 5.0, "ankara": 4.0}
    result = ZonalMatcher.resolve_all(lookup, ["Ankara Alt Havzası", "Sub-basin 3", "Nowhere"])
    assert result.means == [4.0, None, None]
    assert result.loose == {}
    assert len(result.unresolved) == 2
    assert result.unresolved[0].startswith("Sub-basin 3 (ambiguous")
    assert result.unresolved[1] == "Nowhere"
    assert "Nowhere" in str(ZonalMatcher.unresolved_error(lookup, result.unresolved))

    loose = ZonalMatcher.resolve_all({"3a": 1.0, "7": 2.0}, ["Sub-basin 3"])
    assert loose.means == [1.0]
    assert loose.loose == {"Sub-basin 3": "3a"}
    assert loose.unresolved == []
