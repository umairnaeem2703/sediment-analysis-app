"""C-X-07: the results of one dam are kept together, for that dam only (FR-X-04)."""

import pytest

from src.services.dam_run import BEDLOAD, CURVE, INTEGRATION, STAGES, SUSPENDED, DamRun
from src.services.project import Dam


@pytest.fixture()
def run():
    return DamRun(Dam(name="Çubuk 1", slug="cubuk_1"))


def test_c_x_07_a_new_run_holds_no_result(run):
    assert [run.get(stage) for stage in STAGES] == [None] * 4
    assert run.suspended is run.bedload is run.curve is run.integration is None


def test_c_x_07_a_result_is_kept_by_its_stage_and_none_removes_it(run):
    marker = object()

    run.set(BEDLOAD, marker)
    assert run.bedload is marker and run.suspended is None

    run.set(BEDLOAD, None)
    assert run.bedload is None
    run.set(BEDLOAD, None)  # removing what is not there is not an error


def test_c_x_07_an_unknown_stage_is_refused(run):
    with pytest.raises(KeyError):
        run.set("report", object())


def test_c_x_07_a_missing_result_is_an_error_naming_it_and_the_dam(run):
    run.set(SUSPENDED, object())

    with pytest.raises(ValueError, match="Compute the bedload, reservoir curve of Çubuk 1 first"):
        run.require(SUSPENDED, BEDLOAD, CURVE)
    run.require(SUSPENDED)


def test_c_x_07_the_four_results_come_out_in_the_order_of_the_report(run):
    parts = [object() for _ in STAGES]
    with pytest.raises(ValueError, match="integration and projection"):
        run.results()

    for stage, part in zip(STAGES, parts, strict=True):
        run.set(stage, part)

    assert run.results() == tuple(parts) and STAGES[-1] == INTEGRATION


def test_c_x_07_reading_an_unknown_stage_is_refused_like_setting_one(run):
    with pytest.raises(KeyError):
        run.get("report")
