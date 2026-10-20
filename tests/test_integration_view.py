"""
Tests for IntegrationView (src/ui/integration_view.py).

All tests:
  - Pass DataFrames directly to execute_integration() — no file-dialogs.
  - Patch show_warning / show_error / show_info so no Tk messageboxes block.
  - Use a synthetic bathymetry with volumes large enough to cover test sediment values.
"""
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from app import SedimentApp
from src.utils.paths import read_table, resource_path


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_with_root(tk_root):
    window = tk.Toplevel(tk_root)
    app = SedimentApp(window)
    yield app
    window.destroy()


@pytest.fixture()
def phase2_df():
    return pd.DataFrame({"Suspended_Volume_m3": [185_754.26]})


@pytest.fixture()
def phase3_df():
    return pd.DataFrame({
        "Year": [2012, 2013, 2014],
        "Bedload_Volume_m3": [0.0, 114.14, 0.0],
    })


@pytest.fixture()
def bathy_df():
    """
    Synthetic bathymetry with volumes large enough to bracket the test sediment values
    (Total_Volume_m3 ~ 185 754 – 185 868 m³).
    """
    return pd.DataFrame({
        "Volume_m3": [0.0, 100_000.0, 200_000.0, 300_000.0],
        "Elevation_m": [900.0, 950.0, 1000.0, 1050.0],
    })


# Patch target shared by all tests that call execute_integration
_UI_PATCH = {
    "show_warning": "src.ui.integration_view.show_warning",
    "show_error": "src.ui.integration_view.show_error",
    "show_info": "src.ui.integration_view.show_info",
}


# ---------------------------------------------------------------------------
# 1. master_yield.csv ingestion via _ensure_phase2_volume
# ---------------------------------------------------------------------------

def test_ensure_phase2_volume_from_master_yield(app_with_root):
    """_ensure_phase2_volume turns master_yield (Area + Slope cols) into Suspended_Volume_m3."""
    master = read_table(resource_path("inputs", "master_yield.csv"))
    app_with_root.zonal_file_var.set(str(resource_path("inputs", "raw_zonal_means.csv")))
    result = app_with_root.integration_view._ensure_phase2_volume(master)
    assert "Suspended_Volume_m3" in result.columns
    assert len(result) == 1
    assert float(result["Suspended_Volume_m3"].iloc[0]) > 0


def test_ensure_phase2_volume_requires_zonal_file(app_with_root):
    master = read_table(resource_path("inputs", "master_yield.csv"))
    app_with_root.zonal_file_var.set("")
    with pytest.raises(ValueError, match="Zonal Statistics CSV"):
        app_with_root.integration_view._ensure_phase2_volume(master)


def test_ensure_phase2_volume_unmatched_subbasin_raises(app_with_root, tmp_path):
    zonal = tmp_path / "zonal.csv"
    pd.DataFrame({"Sub-basin": ["Other Alt Havzası"], "MEAN": [2.0]}).to_csv(zonal, index=False)
    app_with_root.zonal_file_var.set(str(zonal))
    raw = pd.DataFrame({"Sub-basin Name": ["Missing Alt Havzası"], "Area": [100.0], "Slope": [0.05]})
    with pytest.raises(ValueError, match="Missing Alt Havzası"):
        app_with_root.integration_view._ensure_phase2_volume(raw)


def test_ensure_phase2_volume_accepts_turkish_headers(app_with_root, tmp_path):
    zonal = tmp_path / "zonal.csv"
    pd.DataFrame({"Alt Havza": ["Çine Alt Havzası"], "MEAN": [2.5]}).to_csv(zonal, index=False, encoding="utf-8-sig")
    app_with_root.zonal_file_var.set(str(zonal))
    raw = pd.DataFrame({"Alt Havza Adı": ["Çine Alt Havzası"], "Alan (km2)": [850.0], "Eğim": [0.025]})
    result = app_with_root.integration_view._ensure_phase2_volume(raw)
    assert float(result["Suspended_Volume_m3"].iloc[0]) > 0


def test_ensure_phase2_volume_passthrough_when_column_present(app_with_root, phase2_df):
    """When Suspended_Volume_m3 already exists the DataFrame is returned unchanged."""
    result = app_with_root.integration_view._ensure_phase2_volume(phase2_df)
    assert "Suspended_Volume_m3" in result.columns
    assert float(result["Suspended_Volume_m3"].iloc[0]) == pytest.approx(185_754.26)


def test_ensure_phase2_volume_from_volume_m3_yr_field(app_with_root):
    df = pd.DataFrame({"Volume_m3_yr": [99_000.0]})
    result = app_with_root.integration_view._ensure_phase2_volume(df)
    assert "Volume_m3_yr" in result.columns


# ---------------------------------------------------------------------------
# 2. execute_integration – merged DataFrame columns & values
# ---------------------------------------------------------------------------

def test_execute_integration_produces_merged_df(app_with_root, phase2_df, phase3_df, bathy_df):
    with patch(_UI_PATCH["show_warning"]), patch(_UI_PATCH["show_error"]):
        app_with_root.integration_view.execute_integration(
            df_p2=phase2_df, df_p3=phase3_df, df_bathy=bathy_df
        )
    merged = app_with_root.final_merged_df

    assert merged is not None and not merged.empty
    assert "Year" in merged.columns
    assert "Suspended_Volume_m3" in merged.columns
    assert "Bedload_Volume_m3" in merged.columns
    assert "Total_Volume_m3" in merged.columns
    assert "Interpolated_Elevation_m" in merged.columns

    for _, row in merged.iterrows():
        assert row["Total_Volume_m3"] == pytest.approx(
            row["Suspended_Volume_m3"] + row["Bedload_Volume_m3"], rel=1e-6
        )


def test_execute_integration_no_bathy_gives_nan_elevation(app_with_root, phase2_df, phase3_df):
    from src.ui.integration_view import IntegrationView
    with patch(_UI_PATCH["show_warning"]), patch(_UI_PATCH["show_error"]):
        app_with_root.integration_view.execute_integration(
            df_p2=phase2_df, df_p3=phase3_df, df_bathy=IntegrationView._NO_BATHY
        )
    merged = app_with_root.final_merged_df
    assert merged is not None
    assert "Interpolated_Elevation_m" in merged.columns
    assert merged["Interpolated_Elevation_m"].isna().all()


def test_execute_integration_elevation_values_within_bathy_range(app_with_root, phase2_df, phase3_df, bathy_df):
    with patch(_UI_PATCH["show_warning"]), patch(_UI_PATCH["show_error"]):
        app_with_root.integration_view.execute_integration(
            df_p2=phase2_df, df_p3=phase3_df, df_bathy=bathy_df
        )
    merged = app_with_root.final_merged_df
    elevations = merged["Interpolated_Elevation_m"].dropna()
    # All elevations should be clamped or within [900, 1050]
    assert (elevations >= 900.0).all()
    assert (elevations <= 1050.0).all()


# ---------------------------------------------------------------------------
# 3. Formatted summary display
# ---------------------------------------------------------------------------

def test_summary_text_has_best_and_worst_case_headers(app_with_root, phase2_df, phase3_df):
    from src.ui.integration_view import IntegrationView
    with patch(_UI_PATCH["show_warning"]), patch(_UI_PATCH["show_error"]):
        app_with_root.integration_view.execute_integration(
            df_p2=phase2_df, df_p3=phase3_df, df_bathy=IntegrationView._NO_BATHY
        )
    text = app_with_root.integration_view.results_text.get("1.0", tk.END)

    assert "Minimum Sediment Year (Best Case):" in text
    assert "Maximum Sediment Year (Worst Case):" in text


def test_summary_text_shows_year_volume_elevation(app_with_root, phase2_df, phase3_df, bathy_df):
    with patch(_UI_PATCH["show_warning"]), patch(_UI_PATCH["show_error"]):
        app_with_root.integration_view.execute_integration(
            df_p2=phase2_df, df_p3=phase3_df, df_bathy=bathy_df
        )
    text = app_with_root.integration_view.results_text.get("1.0", tk.END)

    assert "2012" in text or "2014" in text  # best case (min bedload ≈ 0)
    assert "2013" in text                    # worst case (max bedload)
    assert "Total Volume:" in text
    assert "Interpolated Water Elevation:" in text


def test_summary_text_worst_case_is_2013(app_with_root, phase2_df, phase3_df, bathy_df):
    """2013 has the largest bedload so must appear as Worst Case."""
    with patch(_UI_PATCH["show_warning"]), patch(_UI_PATCH["show_error"]):
        app_with_root.integration_view.execute_integration(
            df_p2=phase2_df, df_p3=phase3_df, df_bathy=bathy_df
        )
    text = app_with_root.integration_view.results_text.get("1.0", tk.END)

    lines = text.splitlines()
    worst_year = None
    in_worst = False
    for line in lines:
        if "Maximum Sediment Year (Worst Case):" in line:
            in_worst = True
        if in_worst and "Year:" in line and worst_year is None:
            worst_year = line.strip().split("Year:")[-1].strip()
    # Year is rendered as int (e.g. "2013"), compare as int to avoid "2013.0" vs "2013"
    assert int(worst_year) == 2013


def test_summary_text_na_elevation_when_no_bathy(app_with_root, phase2_df, phase3_df):
    from src.ui.integration_view import IntegrationView
    with patch(_UI_PATCH["show_warning"]), patch(_UI_PATCH["show_error"]):
        app_with_root.integration_view.execute_integration(
            df_p2=phase2_df, df_p3=phase3_df, df_bathy=IntegrationView._NO_BATHY
        )
    text = app_with_root.integration_view.results_text.get("1.0", tk.END)
    assert "N/A" in text


# ---------------------------------------------------------------------------
# 4. Export Master Dataset — .xlsx and .csv
# ---------------------------------------------------------------------------

def test_export_master_dataset_to_excel(app_with_root, phase2_df, phase3_df, bathy_df, tmp_path):
    with patch(_UI_PATCH["show_warning"]), patch(_UI_PATCH["show_error"]), \
            patch(_UI_PATCH["show_info"]):
        app_with_root.integration_view.execute_integration(
            df_p2=phase2_df, df_p3=phase3_df, df_bathy=bathy_df
        )

    xlsx_path = str(tmp_path / "master.xlsx")
    with patch(_UI_PATCH["show_info"]):
        result = app_with_root.integration_view.export_master_dataset(save_path=xlsx_path)

    assert result == xlsx_path
    assert Path(xlsx_path).exists()

    exported = pd.read_excel(xlsx_path)
    assert "Year" in exported.columns
    assert "Suspended_Volume_m3" in exported.columns
    assert "Bedload_Volume_m3" in exported.columns
    assert "Total_Volume_m3" in exported.columns
    assert "Interpolated_Elevation_m" in exported.columns
    assert len(exported) == 3


def test_export_master_dataset_to_csv(app_with_root, phase2_df, phase3_df, bathy_df, tmp_path):
    with patch(_UI_PATCH["show_warning"]), patch(_UI_PATCH["show_error"]), \
            patch(_UI_PATCH["show_info"]):
        app_with_root.integration_view.execute_integration(
            df_p2=phase2_df, df_p3=phase3_df, df_bathy=bathy_df
        )

    csv_path = str(tmp_path / "master.csv")
    with patch(_UI_PATCH["show_info"]):
        result = app_with_root.integration_view.export_master_dataset(save_path=csv_path)

    assert result == csv_path
    assert Path(csv_path).exists()

    exported = pd.read_csv(csv_path)
    assert "Year" in exported.columns
    assert "Total_Volume_m3" in exported.columns
    assert len(exported) == 3


def test_export_returns_none_when_no_data(app_with_root):
    app_with_root.final_merged_df = None
    with patch(_UI_PATCH["show_error"]):
        result = app_with_root.integration_view.export_master_dataset(save_path="/tmp/noop.xlsx")
    assert result is None


# ---------------------------------------------------------------------------
# 5. DataFrame handoff from app.phase2_df / app.phase3_df
# ---------------------------------------------------------------------------

def test_execute_integration_uses_app_handoff_dfs(app_with_root):
    app_with_root.phase2_df = pd.DataFrame({"Suspended_Volume_m3": [50_000.0]})
    app_with_root.phase3_df = pd.DataFrame({
        "Year": [2020, 2021],
        "Bedload_Volume_m3": [1_000.0, 3_000.0],
    })
    with patch(_UI_PATCH["show_warning"]), patch(_UI_PATCH["show_error"]):
        app_with_root.integration_view.execute_integration()

    merged = app_with_root.final_merged_df
    assert merged is not None
    assert len(merged) == 2
    assert list(merged["Total_Volume_m3"]) == [51_000.0, 53_000.0]

    text = app_with_root.integration_view.results_text.get("1.0", tk.END)
    assert "2020" in text
    assert "2021" in text
