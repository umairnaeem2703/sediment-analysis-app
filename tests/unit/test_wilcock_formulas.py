"""U-M3-02 to U-M3-05: the Wilcock & Crowe formulas against the hand calculations (FR-M3-02 to FR-M3-04, B3.2)."""

import numpy as np
import pandas as pd
import pytest

from src.core.wilcock import PHI_BREAK, WATER_YEAR_COLUMN, FractionalModel, TimeSeriesAggregator
from src.utils.paths import read_table, resource_path
from tests.oracle import bedload_annual, bedload_series, bedload_tau_ri, bedload_transport, bedload_wstar

REL = 1e-9
SAMPLE = [row for row in bedload_tau_ri() if row["Fi"] != ""]  # the five sample fractions
COMPUTED_TAU_RI = [row["tau_ri_Pa"] for row in SAMPLE]
COMPUTED_EXPONENT = [row["b_i"] for row in SAMPLE]
TRANSPORT = bedload_transport()
HYDROLOGIST_FILE = read_table(resource_path("inputs", "fractional_parameters.csv"))  # the hydrologist's tau_ri, in Pa
OFF_COLUMN = [value * 1.5 for value in COMPUTED_TAU_RI]  # a column that disagrees with the formula everywhere


def close(expected):
    """Equal to 1e-9 relative, with no absolute allowance: the transport rates go down to 1e-14."""
    return pytest.approx(expected, rel=REL, abs=0)


def _fractions(**supplied) -> pd.DataFrame:
    frame = pd.DataFrame({"di": [row["di_m"] for row in SAMPLE], "Fi": [row["Fi"] for row in SAMPLE]})
    return frame.assign(**supplied)


def _model(**supplied) -> FractionalModel:
    model = FractionalModel()
    model.load_fractional_parameters(_fractions(**supplied))
    return model


# --- U-M3-02: grain fractions (FR-M3-02, D36) ------------------------------------------------------


def test_u_m3_02_tau_ri_and_the_exponent_are_computed_from_the_formula():
    model = _model()

    assert [fraction["tau_ri"] for fraction in model.fractions] == close(COMPUTED_TAU_RI)
    assert [fraction["bi"] for fraction in model.fractions] == close(COMPUTED_EXPONENT)
    assert model.warnings == []


def test_u_m3_02_tau_ri_reproduces_the_hydrologists_sample_file():
    file_tau_ri = pd.to_numeric(HYDROLOGIST_FILE["tau_ri"]).to_numpy(dtype=float)
    file_exponent = pd.to_numeric(HYDROLOGIST_FILE["bi"]).to_numpy(dtype=float)
    model = _model()

    # The file is rounded to 3 significant digits (1.18 for 1.1836), so the match is to its rounding, not to 1e-9.
    assert [fraction["tau_ri"] for fraction in model.fractions] == pytest.approx(list(file_tau_ri), rel=5e-3)
    assert [fraction["bi"] for fraction in model.fractions] == pytest.approx(list(file_exponent), abs=5e-4)
    assert model.warnings == []


def test_u_m3_02_the_sample_file_loaded_whole_gives_no_cross_check_warning():
    model = FractionalModel()
    model.load_fractional_parameters(HYDROLOGIST_FILE)

    assert model.warnings == []
    assert [fraction["tau_ri"] for fraction in model.fractions] == close(COMPUTED_TAU_RI)


def test_u_m3_02_a_supplied_tau_ri_is_cross_checked_and_never_used():
    model = _model(tau_ri=OFF_COLUMN)

    assert [fraction["tau_ri"] for fraction in model.fractions] == close(COMPUTED_TAU_RI)
    assert len(model.warnings) == len(SAMPLE)
    assert all("tau_ri" in warning for warning in model.warnings)


def test_u_m3_02_supplied_values_within_one_percent_give_no_warning():
    model = _model(
        tau_ri=[value * 1.009 for value in COMPUTED_TAU_RI], bi=[value * 0.991 for value in COMPUTED_EXPONENT]
    )

    assert model.warnings == []


def test_u_m3_02_a_supplied_exponent_more_than_one_percent_off_is_warned():
    model = _model(bi=[value * 1.02 for value in COMPUTED_EXPONENT])

    assert len(model.warnings) == len(SAMPLE)
    assert all("bi" in warning for warning in model.warnings)
    assert [fraction["bi"] for fraction in model.fractions] == close(COMPUTED_EXPONENT)


def test_u_m3_02_a_blank_supplied_value_is_not_cross_checked():
    blanks = [np.nan] * len(SAMPLE)

    assert _model(tau_ri=blanks, bi=blanks).warnings == []


def test_u_m3_02_the_warnings_of_an_earlier_load_do_not_carry_over():
    model = _model(tau_ri=[1.0] * len(SAMPLE))
    assert model.warnings

    model.load_fractional_parameters(_fractions())

    assert model.warnings == []


@pytest.mark.parametrize("missing", ["di", "Fi"])
def test_u_m3_02_di_and_fi_are_required(missing):
    with pytest.raises(KeyError, match=missing):
        FractionalModel().load_fractional_parameters(_fractions().drop(columns=[missing]))


def test_u_m3_02_di_must_be_above_zero():
    frame = _fractions()
    frame.loc[0, "di"] = 0.0

    with pytest.raises(ValueError, match="di"):
        FractionalModel().load_fractional_parameters(frame)


def test_u_m3_02_fi_must_sum_to_one_within_0_02():
    FractionalModel().load_fractional_parameters(_fractions().assign(Fi=lambda f: f["Fi"] * 1.019))

    with pytest.raises(ValueError, match="sum"):
        FractionalModel().load_fractional_parameters(_fractions().assign(Fi=lambda f: f["Fi"] * 1.03))


def test_u_m3_02_fi_must_not_be_negative_even_when_the_sum_is_one():
    frame = _fractions()
    frame["Fi"] = [0.6, -0.1, 0.35, 0.15, 0.0]
    assert frame["Fi"].sum() == pytest.approx(1.0)

    with pytest.raises(ValueError, match="Fi"):
        FractionalModel().load_fractional_parameters(frame)


def test_u_m3_02_a_text_or_blank_di_is_an_error():
    frame = _fractions().astype(object)
    frame.loc[1, "di"] = "coarse"

    with pytest.raises(ValueError, match="non-numeric"):
        FractionalModel().load_fractional_parameters(frame)


# --- U-M3-03: dimensionless transport W* (FR-M3-03, D35) -------------------------------------------


@pytest.mark.parametrize("row", bedload_wstar(), ids=lambda row: f"phi={row['Phi']:g}")
def test_u_m3_03_wstar_matches_the_hand_calculation(row):
    assert FractionalModel().calculate_dimensionless_transport(row["Phi"]) == close(row["W_star"])


def test_u_m3_03_wstar_is_continuous_at_the_break():
    model = FractionalModel()
    below = model.calculate_dimensionless_transport(float(np.nextafter(PHI_BREAK, 0.0)))
    at = model.calculate_dimensionless_transport(PHI_BREAK)

    # The published coefficients are rounded, so the branches meet to 4.2e-4 and not to 1e-6 (D47). Today's code
    # (no square root) jumps from 0.0190 to 0.1059.
    assert abs(at - below) / at < 1e-3


# --- U-M3-04: hydraulics and unit-width transport (FR-M3-03) ---------------------------------------


@pytest.mark.parametrize("row", TRANSPORT, ids=lambda row: f"Q={row['Flow_m3_s']:g}")
def test_u_m3_04_shear_stress_and_shear_velocity_match_the_hand_calculation(row):
    tau, u_star = FractionalModel().calculate_hydraulics(row["Flow_m3_s"])

    assert tau == close(row["Tau_Pa"])
    assert u_star == close(row["U_star_m_s"])


def test_u_m3_04_transport_series_matches_the_hand_calculation():
    got = _model().compute_transport_series([row["Flow_m3_s"] for row in TRANSPORT])

    assert list(got) == close([row["Qb_m2_s"] for row in TRANSPORT])


def test_u_m3_04_a_supplied_tau_ri_does_not_change_the_transport():
    flows = [row["Flow_m3_s"] for row in TRANSPORT]

    with_column = _model(tau_ri=OFF_COLUMN).compute_transport_series(flows)

    assert list(with_column) == close([row["Qb_m2_s"] for row in TRANSPORT])


# --- U-M3-05: annual summary (FR-M3-04) ------------------------------------------------------------


def _series(with_water_year: bool) -> pd.DataFrame:
    rows = bedload_series()
    frame = pd.DataFrame({"Date": [row["Date"] for row in rows], "Flow": [row["Flow"] for row in rows]})
    if with_water_year:
        frame[WATER_YEAR_COLUMN] = [int(row["Water_Year"]) for row in rows]
    return frame


@pytest.mark.parametrize("grouping", ["calendar", "water"])
def test_u_m3_05_the_annual_summary_matches_the_hand_calculation(grouping):
    expected = [row for row in bedload_annual() if row["Grouping"] == grouping]

    summary = TimeSeriesAggregator(_model()).process_annual_averages(_series(grouping == "water"))

    assert summary.index.name == (WATER_YEAR_COLUMN if grouping == "water" else "Year")
    assert [int(key) for key in summary.index] == [int(row["Key"]) for row in expected]
    assert list(summary["Annual_Average_Flow"]) == close([row["Mean_Flow_m3_s"] for row in expected])
    assert list(summary["Average_Rate_m2_s"]) == close([row["Mean_Qb_m2_s"] for row in expected])
    assert list(summary["Annual_Total_Bedload_m3_yr"]) == close([row["Volume_m3_yr"] for row in expected])
    assert list(summary["Annual_Average_Bed_Load_metric_tons_yr"]) == close([row["Mass_t_yr"] for row in expected])
