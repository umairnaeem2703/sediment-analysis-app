import datetime

import pytest

from src.services.dam_settings import apply_dam_settings, validate_dam_settings
from src.services.project import Project

THIS_YEAR = datetime.date.today().year


def _valid(**overrides):
    values = {"commissioning_year": "1965", "analysis_year": "2025", "trap_efficiency_pct": "80", "h_min_m": "892.5"}
    values.update(overrides)
    return values


def test_c_m1_09_valid_settings_are_converted():
    assert validate_dam_settings(**_valid()) == {
        "commissioning_year": 1965,
        "analysis_year": 2025,
        "trap_efficiency_pct": 80.0,
        "h_min_m": 892.5,
    }


def test_c_m1_09_the_optional_fields_may_be_blank():
    values = validate_dam_settings(commissioning_year="", analysis_year="  ", trap_efficiency_pct="100", h_min_m="")

    assert values == {
        "commissioning_year": None,
        "analysis_year": None,  # None means the current year
        "trap_efficiency_pct": 100.0,
        "h_min_m": None,
    }


@pytest.mark.parametrize(
    ("overrides", "converted"),
    [
        ({"commissioning_year": "1965.0"}, ("commissioning_year", 1965)),
        ({"trap_efficiency_pct": "87.5"}, ("trap_efficiency_pct", 87.5)),
        ({"h_min_m": "892.5"}, ("h_min_m", 892.5)),
        ({"trap_efficiency_pct": "100"}, ("trap_efficiency_pct", 100.0)),
        ({"trap_efficiency_pct": "0.5"}, ("trap_efficiency_pct", 0.5)),
    ],
)
def test_c_m1_09_decimal_points_and_whole_number_years_are_accepted(overrides, converted):
    key, expected = converted

    assert validate_dam_settings(**_valid(**overrides))[key] == expected


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"trap_efficiency_pct": "0"}, "Trap efficiency"),
        ({"trap_efficiency_pct": "100.1"}, "Trap efficiency"),
        ({"trap_efficiency_pct": "-5"}, "Trap efficiency"),
        ({"trap_efficiency_pct": ""}, "Trap efficiency"),
        ({"trap_efficiency_pct": "high"}, "'high'"),
        ({"commissioning_year": "1965.5"}, "Commissioning year"),
        ({"commissioning_year": "abc"}, "'abc'"),
        ({"commissioning_year": "65"}, "four-digit"),
        ({"analysis_year": "2k25"}, "Analysis year"),
        ({"analysis_year": "1960"}, "before the commissioning year"),
        ({"commissioning_year": str(THIS_YEAR + 1), "analysis_year": ""}, "before the commissioning year"),
        ({"h_min_m": "low"}, "Minimum operating level"),
    ],
)
def test_c_m1_09_invalid_settings_are_refused_with_the_field_named(overrides, fragment):
    with pytest.raises(ValueError) as error:
        validate_dam_settings(**_valid(**overrides))

    assert fragment in str(error.value)


def test_c_m1_09_every_problem_is_listed():
    with pytest.raises(ValueError) as error:
        validate_dam_settings(commissioning_year="x", analysis_year="y", trap_efficiency_pct="0", h_min_m="z")

    message = str(error.value)
    for field in ("Commissioning year", "Analysis year", "Trap efficiency", "Minimum operating level"):
        assert field in message


def test_c_m1_09_a_blank_analysis_year_means_the_current_year():
    values = validate_dam_settings(**_valid(commissioning_year=str(THIS_YEAR), analysis_year=""))

    assert values["analysis_year"] is None


def test_c_m1_09_applying_settings_saves_them_and_a_refusal_changes_nothing(tmp_path):
    project = Project.new(tmp_path / "p", "x")
    dam = project.add_dam("Çubuk 1")

    apply_dam_settings(project, dam, **_valid())

    reopened = Project.open(project.folder).dams[0]
    assert (reopened.commissioning_year, reopened.analysis_year) == (1965, 2025)
    assert (reopened.trap_efficiency_pct, reopened.h_min_m) == (80.0, 892.5)

    with pytest.raises(ValueError):
        apply_dam_settings(project, dam, **_valid(trap_efficiency_pct="500", commissioning_year="1900"))

    assert (dam.commissioning_year, dam.trap_efficiency_pct) == (1965, 80.0)
    assert Project.open(project.folder).dams[0].trap_efficiency_pct == 80.0


# --- review follow-ups -------------------------------------------------------------------------


@pytest.mark.parametrize("year", ["2e3", "1e3", "0x7d0", "20 25", "٢٠٢٥"])
def test_c_m1_09_years_must_be_plain_digits(year):
    with pytest.raises(ValueError, match="four-digit"):
        validate_dam_settings(**_valid(commissioning_year=year))


def test_c_m1_09_a_failed_save_leaves_the_dam_as_it_was(tmp_path, monkeypatch):
    project = Project.new(tmp_path / "p", "x")
    dam = project.add_dam("Çubuk 1")
    apply_dam_settings(project, dam, **_valid())

    def locked():
        raise PermissionError("project.json is open in another program")

    monkeypatch.setattr(project, "save", locked)
    with pytest.raises(PermissionError):
        apply_dam_settings(project, dam, **_valid(trap_efficiency_pct="50"))

    assert dam.trap_efficiency_pct == 80.0
