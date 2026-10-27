"""C-M4-01: the curve inputs of one dam, their texts, their storage in the project and the curve service (FR-M4-01,
FR-M4-02)."""

import json

import pandas as pd
import pytest

from src.services.project import CurveOverrides, Project
from src.services.regional import DamSheet
from src.services.reservoir import (
    CSV_NAME,
    CurveInputs,
    apply_curve_settings,
    compute_curve,
    compute_dam_curve,
    curve_inputs,
    parse_table_step,
    sheet_differences,
    validate_curve_entries,
    write_reservoir_csv,
)


def _sheet(**changes) -> DamSheet:
    values = {
        "name": "Kavşakkaya",
        "bed_elev_m": 1063.0,
        "crest_elev_m": 1124.0,
        "max_elev_m": 1122.3,
        "active_vol_hm3": 74.1,
        "max_vol_hm3": 80.8,
        "drainage_area_km2": 309.2,
    }
    return DamSheet(**{**values, **changes})


def _entered(**changes):
    values = {
        "bed_elev_m": "1063",
        "h_min_m": "",
        "max_elev_m": "1122.3",
        "crest_elev_m": "1124",
        "active_vol_hm3": "74.1",
        "max_vol_hm3": "80.8",
        "shape_class": "foothill",
    }
    return {**values, **changes}


@pytest.fixture()
def project(tmp_path):
    project = Project.new(tmp_path / "project", "Region")
    project.add_dam("Kavşakkaya")
    project.save()
    return project


# --- the inputs -------------------------------------------------------------------------------


def test_c_m4_01_the_inputs_are_prefilled_from_the_dam_sheet(project):
    dam = project.dams[0]

    inputs = curve_inputs(_sheet(), dam)

    assert inputs == CurveInputs(1063.0, None, 1122.3, 1124.0, 74.1, 80.8, None)


def test_c_m4_01_hmin_and_the_shape_class_come_from_the_dam(project):
    dam = project.dams[0]
    dam.h_min_m, dam.shape_class = 1090.0, "hill"

    inputs = curve_inputs(_sheet(), dam)

    assert inputs.h_min_m == 1090.0 and inputs.shape_class == "hill"


def test_c_m4_01_an_edited_value_wins_over_the_sheet(project):
    dam = project.dams[0]
    dam.curve = CurveOverrides(max_elev_m=1121.0, max_vol_hm3=79.0)

    inputs = curve_inputs(_sheet(), dam)

    assert (inputs.max_elev_m, inputs.max_vol_hm3) == (1121.0, 79.0)
    assert (inputs.bed_elev_m, inputs.crest_elev_m, inputs.active_vol_hm3) == (1063.0, 1124.0, 74.1)


def test_c_m4_01_the_differences_from_the_sheet_are_listed(project):
    dam = project.dams[0]
    assert sheet_differences(_sheet(), curve_inputs(_sheet(), dam)) == []
    dam.curve = CurveOverrides(max_elev_m=1121.0)

    differences = sheet_differences(_sheet(), curve_inputs(_sheet(), dam))

    assert len(differences) == 1
    assert "Hmax" in differences[0] and "1121" in differences[0] and "1122.3" in differences[0]


# --- the texts --------------------------------------------------------------------------------


def test_c_m4_01_entered_texts_become_numbers():
    inputs = validate_curve_entries(**_entered(max_elev_m=" 1122.3 ", h_min_m="1090", shape_class="hill"))

    assert inputs == CurveInputs(1063.0, 1090.0, 1122.3, 1124.0, 74.1, 80.8, "hill")


def test_c_m4_01_a_blank_hmin_or_shape_class_is_none_when_the_other_is_given():
    assert validate_curve_entries(**_entered(h_min_m="1090", shape_class="")).shape_class is None
    assert validate_curve_entries(**_entered()).h_min_m is None


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"bed_elev_m": ""}, "Hbed"),
        ({"max_elev_m": "high"}, "Hmax"),
        ({"crest_elev_m": "nan"}, "Hcrest"),
        ({"active_vol_hm3": "x"}, "Vactive"),
        ({"max_vol_hm3": "-"}, "Vmax"),
        ({"h_min_m": "low"}, "Hmin"),
        ({"shape_class": "mountain"}, "mountain"),
        ({"shape_class": ""}, "Hmin or a shape class"),  # neither is given
        ({"h_min_m": "1060"}, "Hmin"),  # below the bed
        ({"crest_elev_m": "1100"}, "Hcrest"),  # below Hmax
        ({"active_vol_hm3": "90"}, "Vactive"),  # above Vmax
    ],
)
def test_c_m4_01_an_invalid_entry_is_refused_and_named(changes, expected):
    with pytest.raises(ValueError, match="not valid") as caught:
        validate_curve_entries(**_entered(**changes))

    assert expected in str(caught.value)


def test_c_m4_01_every_problem_is_listed_at_once():
    with pytest.raises(ValueError) as caught:
        validate_curve_entries(**_entered(bed_elev_m="", max_elev_m="x", crest_elev_m="y"))

    assert str(caught.value).count("\n- ") == 3


# --- storing them -----------------------------------------------------------------------------


def test_c_m4_01_values_equal_to_the_sheet_are_not_stored_as_edits(project):
    dam = project.dams[0]

    changed = apply_curve_settings(project, dam, _sheet(), **_entered(max_elev_m="1122.3"))

    assert changed and dam.shape_class == "foothill"  # the shape class was new
    assert dam.curve == CurveOverrides() and dam.h_min_m is None


def test_c_m4_01_an_edited_value_is_stored_and_survives_reopening(project):
    dam = project.dams[0]

    changed = apply_curve_settings(project, dam, _sheet(), **_entered(max_elev_m="1121", h_min_m="1090"))

    assert changed
    reopened = Project.open(project.folder).dams[0]
    assert reopened.curve == CurveOverrides(max_elev_m=1121.0)
    assert reopened.h_min_m == 1090.0 and reopened.shape_class == "foothill"


def test_c_m4_01_entering_the_sheet_value_again_drops_the_edit(project):
    dam = project.dams[0]
    apply_curve_settings(project, dam, _sheet(), **_entered(max_elev_m="1121"))

    changed = apply_curve_settings(project, dam, _sheet(), **_entered(max_elev_m="1122.3"))

    assert changed and dam.curve == CurveOverrides()


def test_c_m4_01_nothing_is_reported_changed_when_nothing_changed(project):
    dam = project.dams[0]
    apply_curve_settings(project, dam, _sheet(), **_entered(max_elev_m="1121", h_min_m="1090"))

    assert not apply_curve_settings(project, dam, _sheet(), **_entered(max_elev_m="1121", h_min_m="1090"))


def test_c_m4_01_changing_only_the_shape_class_is_a_change(project):
    dam = project.dams[0]
    apply_curve_settings(project, dam, _sheet(), **_entered())

    assert apply_curve_settings(project, dam, _sheet(), **_entered(shape_class="hill"))
    assert dam.shape_class == "hill"


def test_c_m4_01_a_sheet_value_with_more_digits_than_the_field_shows_is_not_an_edit(project):
    dam = project.dams[0]
    sheet = _sheet(max_vol_hm3=80.80000000000001, bed_elev_m=1063.0000000000002)

    apply_curve_settings(project, dam, sheet, **_entered())  # the fields show 12 digits: 80.8 and 1063

    assert dam.curve == CurveOverrides()
    assert sheet_differences(sheet, validate_curve_entries(**_entered())) == []


def test_c_m4_01_a_new_shape_class_is_kept_but_does_not_change_the_curve_while_hmin_is_given(project):
    dam = project.dams[0]
    apply_curve_settings(project, dam, _sheet(), **_entered(h_min_m="1090", shape_class="foothill"))

    changed = apply_curve_settings(project, dam, _sheet(), **_entered(h_min_m="1090", shape_class="hill"))

    assert not changed and dam.shape_class == "hill"
    assert Project.open(project.folder).dams[0].shape_class == "hill"


def test_c_m4_01_a_blank_shape_class_is_kept_as_none_when_hmin_is_given(project):
    dam = project.dams[0]

    apply_curve_settings(project, dam, _sheet(), **_entered(h_min_m="1090", shape_class=""))

    assert dam.shape_class is None and dam.h_min_m == 1090.0


def test_c_m4_01_invalid_entries_change_nothing(project):
    dam = project.dams[0]
    apply_curve_settings(project, dam, _sheet(), **_entered(max_elev_m="1121"))
    saved = (project.folder / "project.json").read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="Hmax"):
        apply_curve_settings(project, dam, _sheet(), **_entered(max_elev_m="x", shape_class="hill"))

    assert dam.curve.max_elev_m == 1121.0 and dam.shape_class == "foothill"
    assert (project.folder / "project.json").read_text(encoding="utf-8") == saved


def test_c_m4_01_a_failed_save_restores_the_dam(project, monkeypatch):
    dam = project.dams[0]
    apply_curve_settings(project, dam, _sheet(), **_entered(max_elev_m="1121", h_min_m="1090"))

    def refuse():
        raise OSError("disk full")

    monkeypatch.setattr(project, "save", refuse)
    with pytest.raises(OSError, match="disk full"):
        apply_curve_settings(project, dam, _sheet(), **_entered(max_elev_m="1120", h_min_m="", shape_class="hill"))

    assert dam.curve == CurveOverrides(max_elev_m=1121.0)
    assert dam.h_min_m == 1090.0 and dam.shape_class == "foothill"


def test_c_m4_01_a_project_written_before_step_6_opens_without_edits(project):
    path = project.folder / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["dams"][0]["curve"]
    path.write_text(json.dumps(data), encoding="utf-8")

    reopened = Project.open(project.folder)

    assert reopened.dams[0].curve == CurveOverrides()


def test_c_m4_01_an_unknown_edit_field_is_a_malformed_project(project):
    path = project.folder / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["dams"][0]["curve"] = {"depth": 3}
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="malformed"):
        Project.open(project.folder)


# --- the curve --------------------------------------------------------------------------------


def test_c_m4_01_a_curve_from_the_shape_class_derives_hmin():
    result = compute_curve(validate_curve_entries(**_entered()), 309.2)

    assert not result.h_min_given and result.shape_class == "foothill"
    assert result.curve.exponent == 3.0 and result.curve.h_min_m == pytest.approx(1088.86, abs=0.005)
    assert len(result.table) == 123 and result.warnings == []


def test_c_m4_01_a_curve_through_a_given_hmin_ignores_the_shape_class():
    result = compute_curve(validate_curve_entries(**_entered(h_min_m="1090", shape_class="lake")), 309.2)

    assert result.h_min_given and result.shape_class is None
    assert result.curve.exponent == pytest.approx(3.1647, abs=1e-4) and result.curve.h_min_m == pytest.approx(1090.0)


@pytest.mark.parametrize(("text", "step"), [("0.25", 0.25), (" 1 ", 1.0)])
def test_c_m4_01_the_level_interval_is_read_with_a_point(text, step):
    assert parse_table_step(text) == step


@pytest.mark.parametrize("text", ["", "x", "nan", "0", "-0.5", "0,25"])
def test_c_m4_01_a_level_interval_that_is_blank_not_a_number_or_not_above_zero_is_refused(text):
    with pytest.raises(ValueError, match="level interval"):
        parse_table_step(text)


def test_c_m4_01_the_table_is_made_at_the_entered_interval_and_the_curve_does_not_change():
    result = compute_curve(validate_curve_entries(**_entered()), 309.2, 0.25)

    assert len(result.table) == 245
    assert set(result.table["Elevation_m"].diff().dropna()) == {0.25}
    assert result.curve == compute_curve(validate_curve_entries(**_entered()), 309.2).curve


def test_c_m4_01_the_warnings_reach_the_result():
    result = compute_curve(validate_curve_entries(**_entered()), 4.0)  # A(Hmax) = 4.09 km2

    assert len(result.warnings) == 1 and "drainage area" in result.warnings[0]


def test_c_m4_01_a_dam_curve_is_made_from_the_sheet_and_the_dam(project):
    dam = project.dams[0]
    apply_curve_settings(project, dam, _sheet(), **_entered(max_elev_m="1121"))

    result = compute_dam_curve(_sheet(), dam)

    assert result.curve.max_elev_m == 1121.0 and result.shape_class == "foothill"


def test_x_01_a_dam_without_hmin_or_a_shape_class_has_no_curve_and_the_error_says_what_to_enter(project):
    with pytest.raises(ValueError, match="Hmin or a shape class"):
        compute_dam_curve(_sheet(), project.dams[0])


def test_c_m4_01_the_curve_is_written_as_utf8_with_bom_and_unit_named_columns(tmp_path):
    result = compute_curve(validate_curve_entries(**_entered()), 309.2)

    path = write_reservoir_csv(result, tmp_path)

    assert path.name == CSV_NAME == "reservoir_curve.csv"
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    written = pd.read_csv(path, encoding="utf-8-sig")
    assert list(written.columns) == ["Elevation_m", "Volume_hm3", "Area_km2"]
    pd.testing.assert_frame_equal(written, result.table, check_exact=False, rtol=1e-12)
