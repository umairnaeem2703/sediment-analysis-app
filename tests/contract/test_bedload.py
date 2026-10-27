"""C-M3-01 to C-M3-04: the bedload service's contract with its inputs, its project copies and its output file
(FR-M3-01, FR-M3-02, FR-M3-04, FR-M3-05, FR-X-01 to FR-X-03)."""

import re

import pandas as pd
import pytest

from src.core.wilcock import WATER_YEAR_COLUMN
from src.services.bedload import (
    VALUE_COLUMNS,
    FlowSeries,
    apply_flow_settings,
    compute_bedload,
    compute_dam_bedload,
    import_flow,
    import_fractions,
    load_flow,
    load_fractions,
    validate_flow_settings,
    write_bedload_csv,
)
from src.services.project import Project
from tests.flows import dsi_table, sample_values
from tests.samples import SAMPLE_FRACTIONS, write_fractions_with_wrong_tau_ri

FRACTIONS = load_fractions(SAMPLE_FRACTIONS).data[["di", "Fi"]]  # no tau_ri or bi column, so nothing to cross-check
GOOD_FRACTIONS = "di,Fi\n0.004,0.1\n0.01,0.2\n0.02,0.35\n0.032,0.25\n0.05,0.1\n"


def _write(folder, name, text, encoding="utf-8"):
    path = folder / name
    path.write_bytes(text.encode(encoding))
    return path


def _daily(*flows, dates=None, **extra):
    dates = dates or [f"{day:02d}/01/2000" for day in range(1, len(flows) + 1)]
    return pd.DataFrame({"Date": dates, "Flow Q (m3/s)": list(flows), **extra})


def _compute(frame, source="flow.csv"):
    return compute_bedload(FlowSeries(frame, False, []), FRACTIONS, source)


# --- C-M3-01: a daily series ------------------------------------------------------------------


@pytest.mark.parametrize("flow_header", ["Flow Q (m3/s)", "Flow Q (m³/s)", "FLOW Q (M³/S)"])
@pytest.mark.parametrize("date_header", ["Date", "DATE"])
def test_c_m3_01_the_date_and_flow_labels_are_found_whatever_their_case_and_superscript(
    tmp_path, date_header, flow_header
):
    path = _write(tmp_path, "flow.csv", f"{date_header},{flow_header}\n01/01/2000,10\n02/01/2000,20\n")

    result = compute_bedload(load_flow(path, 0.6, 0), FRACTIONS, path.name)

    assert list(result.table["Year"]) == [2000]
    assert result.table[VALUE_COLUMNS[0]].iloc[0] == 15.0


def test_c_m3_01_iso_dates_are_accepted():
    result = _compute(_daily(10.0, 20.0, dates=["2000-01-01", "2000-01-02"]))

    assert list(result.table["Year"]) == [2000]


def test_c_m3_01_a_daily_file_is_read_as_it_is_and_is_not_flagged_synthetic(tmp_path):
    path = _write(tmp_path, "flow.csv", "Date,Flow Q (m3/s)\n01/01/2000,10\n02/01/2000,20\n")

    series = load_flow(path, 0.6, 0)

    assert not series.synthetic and series.notes == []
    assert list(series.daily["Flow Q (m3/s)"]) == [10, 20]


def test_c_m3_01_a_semicolon_file_loads(tmp_path):
    path = _write(tmp_path, "flow.csv", "Date;Flow Q (m3/s)\n01/01/2000;1.5\n02/01/2000;2.5\n", encoding="cp1254")

    result = compute_bedload(load_flow(path, 0.6, 0), FRACTIONS, path.name)

    assert result.table[VALUE_COLUMNS[0]].iloc[0] == 2.0


def test_c_m3_01_a_table_without_date_and_flow_columns_is_an_error_naming_the_file():
    with pytest.raises(ValueError, match=r"^flow\.csv: .*Date.*Flow"):
        _compute(pd.DataFrame({"Day": ["01/01/2000"], "Q": [1.0]}))


def test_c_m3_01_a_missing_file_is_an_error_naming_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="nothing.csv"):
        load_flow(tmp_path / "nothing.csv", 0.6, 0)


# --- C-M3-02: a DSİ monthly table -------------------------------------------------------------


def _monthly_file(folder, name="monthly.csv", **kwargs):
    path = folder / name
    dsi_table(sample_values(), **kwargs).to_csv(path, index=False, encoding="utf-8")
    return path


def test_c_m3_02_a_monthly_table_is_detected_converted_and_flagged_synthetic(tmp_path):
    values = sample_values()
    path = _monthly_file(tmp_path)

    series = load_flow(path, 0.6, 3)

    assert series.synthetic
    assert len(series.notes) == 1 and "0.6" in series.notes[0] and "seed 3" in series.notes[0]
    assert list(series.daily.columns) == ["Date", "Flow Q (m3/s)", WATER_YEAR_COLUMN]
    volume_hm3 = (series.daily["Flow Q (m3/s)"] * 86_400).sum() / 1e6
    assert volume_hm3 == pytest.approx(sum(sum(months) for months in values.values()), rel=1e-12)


def test_c_m3_02_the_flag_reaches_the_result_and_the_years_are_water_years(tmp_path):
    series = load_flow(_monthly_file(tmp_path), 0.6, 0)

    result = compute_bedload(series, FRACTIONS, "monthly.csv")

    assert result.synthetic and result.notes == series.notes
    assert result.year_column == WATER_YEAR_COLUMN
    assert list(result.table[WATER_YEAR_COLUMN]) == [1974, 1975]


def test_c_m3_02_the_same_sigma_and_seed_give_the_same_series_and_another_seed_does_not(tmp_path):
    path = _monthly_file(tmp_path)

    first, again, other = load_flow(path, 0.6, 1), load_flow(path, 0.6, 1), load_flow(path, 0.6, 2)

    pd.testing.assert_frame_equal(first.daily, again.daily)
    assert not first.daily["Flow Q (m3/s)"].equals(other.daily["Flow Q (m3/s)"])


def test_c_m3_02_a_malformed_monthly_table_is_an_error_naming_the_file_and_the_month(tmp_path):
    path = tmp_path / "broken.csv"
    dsi_table(sample_values()).drop(columns=["Şubat"]).to_csv(path, index=False, encoding="utf-8")

    with pytest.raises(ValueError, match=r"^broken\.csv: .*Şubat"):
        load_flow(path, 0.6, 0)


# --- C-M3-03: the grain fractions -------------------------------------------------------------


def test_c_m3_03_the_sample_file_loads_and_its_tau_ri_column_agrees_with_the_formula():
    loaded = load_fractions(SAMPLE_FRACTIONS)

    assert list(loaded.data["di"]) == [0.004, 0.01, 0.02, 0.032, 0.05]
    assert list(loaded.data.columns) == ["di", "Fi", "bi", "tau_ri"]
    assert loaded.warnings == []  # the hydrologist's tau_ri is the formula's, to the file's rounding (D50)


def test_c_m3_03_a_tau_ri_column_that_disagrees_with_the_formula_is_warned_with_the_file(tmp_path):
    loaded = load_fractions(write_fractions_with_wrong_tau_ri(tmp_path))

    assert len(loaded.warnings) == 5
    assert all(warning.startswith("fractional_parameters.csv: ") and "tau_ri" in warning for warning in loaded.warnings)


def test_c_m3_03_only_di_and_fi_are_needed_and_then_there_is_nothing_to_warn_about(tmp_path):
    loaded = load_fractions(_write(tmp_path, "fractions.csv", GOOD_FRACTIONS))

    assert list(loaded.data.columns) == ["di", "Fi"] and loaded.warnings == []


def test_c_m3_03_a_semicolon_file_with_blank_lines_loads(tmp_path):
    text = "di;Fi\n0.004;0.1\n;\n0.01;0.2\n0.02;0.35\n0.032;0.25\n0.05;0.1\n"

    loaded = load_fractions(_write(tmp_path, "fractions.csv", text, encoding="cp1254"))

    assert list(loaded.data["Fi"]) == [0.1, 0.2, 0.35, 0.25, 0.1]


def test_c_m3_03_a_missing_column_is_an_error_naming_the_file_and_the_column(tmp_path):
    path = _write(tmp_path, "fractions.csv", "di,share\n0.004,1\n")

    with pytest.raises(
        ValueError, match=r"^fractions\.csv: required column\(s\) not found: Fi\. Columns present: di, share"
    ):
        load_fractions(path)


def test_c_m3_03_a_cell_that_is_not_a_number_is_an_error_naming_the_file_and_the_row(tmp_path):
    path = _write(tmp_path, "fractions.csv", "di,Fi\n0.004,0.5\n0.01,half\n")

    with pytest.raises(ValueError, match=r"(?s)fractions\.csv.*row 3: 'Fi' must be a number, found 'half'"):
        load_fractions(path)


def test_c_m3_03_fractions_that_do_not_sum_to_one_are_an_error_naming_the_file(tmp_path):
    path = _write(tmp_path, "fractions.csv", "di,Fi\n0.004,0.5\n0.01,0.3\n")

    with pytest.raises(ValueError, match=r"^fractions\.csv: Fi fractions must sum to ~1\.0 \(got 0\.8000\)"):
        load_fractions(path)


def test_c_m3_03_a_grain_size_of_zero_is_an_error_naming_the_file(tmp_path):
    path = _write(tmp_path, "fractions.csv", "di,Fi\n0,0.5\n0.01,0.5\n")

    with pytest.raises(ValueError, match=r"^fractions\.csv: .*di"):
        load_fractions(path)


def test_c_m3_03_a_supplied_exponent_that_is_off_by_more_than_one_percent_is_warned_with_the_file(tmp_path):
    path = _write(tmp_path, "fractions.csv", "di,Fi,bi\n0.02,1.0,0.5\n")

    loaded = load_fractions(path)

    assert len(loaded.warnings) == 1 and loaded.warnings[0].startswith("fractions.csv: ") and "bi" in loaded.warnings[0]


def test_c_m3_03_a_file_without_data_rows_is_an_error(tmp_path):
    with pytest.raises(ValueError, match=r"fractions\.csv"):
        load_fractions(_write(tmp_path, "fractions.csv", "di,Fi\n"))


# --- C-M3-04: the annual summary --------------------------------------------------------------


def test_c_m3_04_the_table_has_the_year_key_then_the_value_columns():
    result = _compute(_daily(10.0, 20.0))

    assert list(result.table.columns) == ["Year", *VALUE_COLUMNS]
    assert VALUE_COLUMNS == ["Mean_Flow_m3_s", "Mean_Qb_m2_s", "Volume_m3_yr", "Mass_t_yr"]


def test_c_m3_04_a_water_year_column_makes_the_years_water_years():
    flow = _daily(10.0, 80.0, dates=["30/09/2010", "01/10/2010"], **{WATER_YEAR_COLUMN: [2010, 2011]})

    water = _compute(flow)
    calendar = _compute(flow.drop(columns=[WATER_YEAR_COLUMN]))

    assert water.year_column == WATER_YEAR_COLUMN and list(water.table[WATER_YEAR_COLUMN]) == [2010, 2011]
    assert calendar.year_column == "Year" and list(calendar.table["Year"]) == [2010]


def test_c_m3_04_rows_with_a_bad_date_or_flow_are_dropped_and_counted_in_the_warnings():
    frame = pd.DataFrame(
        {
            "Date": ["01/01/2000", "02/01/2000", "not a date", "04/01/2000"],
            "Flow Q (m3/s)": [10.0, None, 30.0, 20.0],
        }
    )

    result = _compute(frame)

    assert result.table[VALUE_COLUMNS[0]].iloc[0] == 15.0
    assert len(result.warnings) == 1
    assert result.warnings[0].startswith("flow.csv: ")
    assert "1 row(s) with missing" in result.warnings[0] and "1 row(s) with unparseable" in result.warnings[0]


def test_c_m3_04_a_clean_series_has_no_warnings():
    assert _compute(_daily(5.0)).warnings == []


def test_c_m3_04_a_negative_flow_is_an_error_naming_the_file_and_the_date():
    with pytest.raises(
        ValueError, match=r"^flow\.csv: Flow values must not be negative \(first offending dates: 2000-01-02"
    ):
        _compute(_daily(5.0, -1.0))


def test_c_m3_04_a_series_with_no_valid_row_is_an_error_naming_the_file():
    with pytest.raises(ValueError, match=r"^flow\.csv: .*no rows"):
        _compute(pd.DataFrame({"Date": ["x", "y"], "Flow Q (m3/s)": [None, None]}))


def test_c_m3_04_summarising_leaves_the_input_table_unchanged():
    frame = _daily(10.0, 20.0)
    before = frame.copy()

    _compute(frame)

    pd.testing.assert_frame_equal(frame, before)


def test_c_m3_04_the_fractions_warnings_come_with_the_result_and_name_their_file(tmp_path):
    result = compute_bedload(
        FlowSeries(_daily(5.0), False, []),
        load_fractions(write_fractions_with_wrong_tau_ri(tmp_path)).data,
        "flow.csv",
        "fractional_parameters.csv",
    )

    assert len(result.warnings) == 5 and all(w.startswith("fractional_parameters.csv: ") for w in result.warnings)


# --- the project's copies, settings and the output file ----------------------------------------


@pytest.fixture()
def project(tmp_path):
    project = Project.new(tmp_path / "project", "Region")
    project.add_dam("Alpha")
    return project


def test_c_m3_01_importing_a_flow_copies_it_into_the_project_and_leaves_the_original_alone(project, tmp_path):
    source = _write(tmp_path, "mine.csv", "Date,Flow Q (m3/s)\n01/01/2000,10\n")
    before = source.read_bytes()
    dam = project.dams[0]

    import_flow(project, dam, source, 0.8, 5)

    assert source.read_bytes() == before
    assert dam.flow.path == "inputs/flow/alpha_flow.csv" and (project.folder / dam.flow.path).read_bytes() == before
    assert (dam.flow.sigma, dam.flow.seed) == (0.8, 5)
    reopened = Project.open(project.folder)
    assert reopened.dams[0].flow == dam.flow


def test_c_m3_01_a_new_flow_replaces_the_old_copy(project, tmp_path):
    dam = project.dams[0]
    import_flow(project, dam, _write(tmp_path, "one.csv", "Date,Flow Q (m3/s)\n01/01/2000,10\n"), 0.6, 0)
    old = project.folder / dam.flow.path
    xlsx = tmp_path / "two.xlsx"
    pd.DataFrame({"Date": ["01/01/2000"], "Flow Q (m3/s)": [10.0]}).to_excel(xlsx, index=False)

    import_flow(project, dam, xlsx, 0.6, 0)

    assert dam.flow.path == "inputs/flow/alpha_flow.xlsx" and not old.exists()


@pytest.mark.parametrize(
    ("name", "text", "named"),
    [
        ("wrong.csv", "Day,Q\n01/01/2000,1\n", "Date"),
        ("negative.csv", "Date,Flow Q (m3/s)\n01/01/2000,-1\n", "negative"),
        ("blank.csv", "Date,Flow Q (m3/s)\nx,\n", "no rows"),
    ],
)
def test_c_m3_01_a_daily_file_that_cannot_be_summarised_is_refused_and_the_old_copy_is_kept(
    project, tmp_path, name, text, named
):
    dam = project.dams[0]
    import_flow(project, dam, _write(tmp_path, "good.csv", "Date,Flow Q (m3/s)\n01/01/2000,10\n"), 0.6, 0)
    copy = project.folder / dam.flow.path
    kept = copy.read_bytes()

    with pytest.raises(ValueError, match=rf"^{re.escape(name)}: .*{named}"):
        import_flow(project, dam, _write(tmp_path, name, text), 0.8, 5)

    assert dam.flow.path == "inputs/flow/alpha_flow.csv" and (dam.flow.sigma, dam.flow.seed) == (0.6, 0)
    assert copy.read_bytes() == kept
    assert Project.open(project.folder).dams[0].flow == dam.flow


def _failing_save():
    raise OSError("disk full")


def test_c_m3_02_a_failed_save_leaves_the_dam_and_the_old_flow_copy_as_they_were(project, tmp_path, monkeypatch):
    dam = project.dams[0]
    import_flow(project, dam, _write(tmp_path, "one.csv", "Date,Flow Q (m3/s)\n01/01/2000,10\n"), 0.6, 0)
    before, old_copy = dam.flow, project.folder / dam.flow.path
    xlsx = tmp_path / "two.xlsx"
    pd.DataFrame({"Date": ["01/01/2000"], "Flow Q (m3/s)": [10.0]}).to_excel(xlsx, index=False)
    monkeypatch.setattr(project, "save", _failing_save)

    with pytest.raises(OSError, match="disk full"):
        import_flow(project, dam, xlsx, 0.8, 5)

    assert dam.flow == before and old_copy.exists()


def test_c_m3_03_a_failed_save_leaves_the_fractions_and_the_old_copy_as_they_were(project, tmp_path, monkeypatch):
    import_fractions(project, SAMPLE_FRACTIONS)
    old_copy = project.folder / project.inputs["fractions"]
    xlsx = tmp_path / "fractions.xlsx"
    pd.read_csv(SAMPLE_FRACTIONS)[["di", "Fi"]].to_excel(xlsx, index=False)
    monkeypatch.setattr(project, "save", _failing_save)

    with pytest.raises(OSError, match="disk full"):
        import_fractions(project, xlsx)

    assert project.inputs["fractions"] == "inputs/fractions.csv" and old_copy.exists()


def test_c_m3_02_a_flow_file_that_cannot_be_used_is_refused_and_nothing_is_copied(project, tmp_path):
    broken = tmp_path / "broken.csv"
    dsi_table(sample_values()).drop(columns=["Şubat"]).to_csv(broken, index=False, encoding="utf-8")

    with pytest.raises(ValueError, match="broken.csv"):
        import_flow(project, project.dams[0], broken, 0.6, 0)

    assert project.dams[0].flow.path is None and not (project.folder / "inputs" / "flow").exists()


def test_c_m3_03_importing_fractions_copies_them_and_returns_the_cross_check(project, tmp_path):
    source = write_fractions_with_wrong_tau_ri(tmp_path)

    loaded = import_fractions(project, source)

    assert project.inputs["fractions"] == "inputs/fractions.csv"
    assert (project.folder / "inputs" / "fractions.csv").read_bytes() == source.read_bytes()
    assert len(loaded.warnings) == 5
    assert Project.open(project.folder).inputs["fractions"] == "inputs/fractions.csv"


def test_c_m3_03_fractions_that_cannot_be_used_are_refused_and_nothing_is_copied(project, tmp_path):
    bad = _write(tmp_path, "bad.csv", "di,Fi\n0.004,0.5\n")

    with pytest.raises(ValueError, match="bad.csv"):
        import_fractions(project, bad)

    assert project.inputs["fractions"] is None and not (project.folder / "inputs" / "fractions.csv").exists()


def test_c_m3_03_the_new_fractions_replace_the_old_copy(project, tmp_path):
    import_fractions(project, SAMPLE_FRACTIONS)
    old = project.folder / project.inputs["fractions"]
    xlsx = tmp_path / "fractions.xlsx"
    pd.read_csv(SAMPLE_FRACTIONS)[["di", "Fi"]].to_excel(xlsx, index=False)

    import_fractions(project, xlsx)

    assert project.inputs["fractions"] == "inputs/fractions.xlsx" and not old.exists()


def test_c_m3_02_the_settings_are_validated_stored_and_reported_as_changed_or_not(project):
    dam = project.dams[0]

    assert apply_flow_settings(project, dam, "0.8", "7") is True
    assert (dam.flow.sigma, dam.flow.seed) == (0.8, 7)
    assert Project.open(project.folder).dams[0].flow.sigma == 0.8
    assert apply_flow_settings(project, dam, "0.8", " 7 ") is False


@pytest.mark.parametrize(
    ("sigma", "seed", "named"),
    [("-1", "0", "Sigma"), ("x", "0", "Sigma"), ("0.6", "1.5", "Seed"), ("0.6", "-3", "Seed")],
)
def test_c_m3_02_invalid_settings_are_refused_naming_the_field_and_change_nothing(project, sigma, seed, named):
    dam = project.dams[0]

    with pytest.raises(ValueError, match=named):
        apply_flow_settings(project, dam, sigma, seed)

    assert (dam.flow.sigma, dam.flow.seed) == (0.6, 0)


def test_c_m3_02_every_problem_with_the_settings_is_listed_at_once():
    with pytest.raises(ValueError) as error:
        validate_flow_settings("-1", "x")

    assert "Sigma" in str(error.value) and "Seed" in str(error.value)


def test_x_01_a_missing_flow_is_an_error_naming_the_dam(project):
    import_fractions(project, SAMPLE_FRACTIONS)

    with pytest.raises(ValueError, match="No flow file has been chosen for Alpha"):
        compute_dam_bedload(project, project.dams[0])


def test_x_01_missing_fractions_are_an_error_naming_them(project, tmp_path):
    import_flow(project, project.dams[0], _write(tmp_path, "flow.csv", "Date,Flow Q (m3/s)\n01/01/2000,10\n"), 0.6, 0)

    with pytest.raises(ValueError, match="No grain fractions file has been chosen"):
        compute_dam_bedload(project, project.dams[0])


def test_c_m3_04_the_project_copies_are_what_is_computed(project, tmp_path):
    source = _write(tmp_path, "mine.csv", "Date,Flow Q (m3/s)\n01/01/2000,10\n02/01/2000,20\n")
    import_flow(project, project.dams[0], source, 0.6, 0)
    import_fractions(project, write_fractions_with_wrong_tau_ri(tmp_path))
    source.unlink()  # the project must not depend on the original

    result = compute_dam_bedload(project, project.dams[0])

    assert result.table[VALUE_COLUMNS[0]].iloc[0] == 15.0
    assert not result.synthetic
    assert result.warnings and all(
        warning.startswith("fractions.csv: ") for warning in result.warnings
    )  # the copy's name, not the original's


def test_c_m3_04_an_error_in_the_project_copy_names_the_copy(project, tmp_path):
    import_flow(project, project.dams[0], _write(tmp_path, "mine.csv", "Date,Flow Q (m3/s)\n01/01/2000,10\n"), 0.6, 0)
    import_fractions(project, SAMPLE_FRACTIONS)
    (project.folder / project.dams[0].flow.path).write_text("Date,Flow Q (m3/s)\n01/01/2000,-4\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"^alpha_flow\.csv: Flow values must not be negative"):
        compute_dam_bedload(project, project.dams[0])


def test_c_m3_04_the_csv_holds_the_table_and_nothing_else(tmp_path):
    result = _compute(_daily(10.0, 20.0, dates=["01/01/2000", "01/01/2001"]))

    path = write_bedload_csv(result, tmp_path)

    assert path.name == "bedload.csv" and path.read_bytes().startswith(b"\xef\xbb\xbf")
    written = pd.read_csv(path, encoding="utf-8-sig")
    assert list(written.columns) == ["Year", *VALUE_COLUMNS]
    assert list(written["Year"]) == [2000, 2001]


def test_c_m3_02_the_lag_1_phi_changes_the_series_keeps_the_volume_and_is_reported(tmp_path):
    path = _monthly_file(tmp_path)

    independent, persistent = load_flow(path, 0.6, 1), load_flow(path, 0.6, 1, 0.8)

    assert not persistent.daily["Flow Q (m3/s)"].equals(independent.daily["Flow Q (m3/s)"])
    assert persistent.daily["Flow Q (m3/s)"].sum() == pytest.approx(independent.daily["Flow Q (m3/s)"].sum(), rel=1e-12)
    assert "AR(1)" in persistent.notes[0] and "φ=0.8" in persistent.notes[0]
    assert "AR(1)" not in independent.notes[0]


def test_c_m3_02_phi_is_validated_stored_and_reported_as_changed_or_not(project):
    dam = project.dams[0]

    assert apply_flow_settings(project, dam, "0.6", "0", "0.8") is True
    assert dam.flow.phi == 0.8 and Project.open(project.folder).dams[0].flow.phi == 0.8
    assert apply_flow_settings(project, dam, "0.6", "0", " 0.8 ") is False
    assert validate_flow_settings("0.6", "0") == (0.6, 0, 0.0)


@pytest.mark.parametrize("phi", ["-0.1", "1", "1.5", "x", ""])
def test_c_m3_02_an_invalid_phi_is_refused_naming_the_field_and_changes_nothing(project, phi):
    dam = project.dams[0]

    with pytest.raises(ValueError, match="Lag-1 phi"):
        apply_flow_settings(project, dam, "0.9", "5", phi)

    assert (dam.flow.sigma, dam.flow.seed, dam.flow.phi) == (0.6, 0, 0.0)


def test_c_m3_02_the_import_and_the_dams_computation_use_the_stored_phi(project, tmp_path):
    dam = project.dams[0]
    path = _monthly_file(tmp_path)
    import_fractions(project, SAMPLE_FRACTIONS)
    import_flow(project, dam, path, 0.6, 0, 0.0)
    flat = compute_dam_bedload(project, dam)

    import_flow(project, dam, path, 0.6, 0, 0.8)
    persistent = compute_dam_bedload(project, dam)

    assert dam.flow.phi == 0.8
    assert list(persistent.table["Volume_m3_yr"]) != list(flat.table["Volume_m3_yr"])
    assert "φ=0.8" in persistent.notes[0]
