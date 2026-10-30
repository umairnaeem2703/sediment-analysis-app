"""W-X-02: a step keeps its result in the run of the dam in use, and only a step with a stage can (D71)."""

from types import SimpleNamespace

import pytest

from src.services.dam_run import BEDLOAD, DamRun
from src.services.project import Dam
from src.ui.steps.base import Step


class Staged(Step):
    title = "Staged"
    stage = BEDLOAD


class Stageless(Step):
    title = "Stageless"


def _attached(step, run):
    step.wizard = SimpleNamespace(run=run)
    return step


def test_w_x_02_a_result_goes_to_the_run_and_is_read_back_from_it():
    run, marker = DamRun(Dam(name="A", slug="a")), object()
    step = _attached(Staged(), run)

    step.result = marker
    assert run.bedload is marker and step.result is marker

    step.result = None
    assert run.bedload is None and step.result is None


def test_w_x_02_without_a_run_only_no_result_can_be_kept():
    step = _attached(Staged(), None)

    step.result = None
    assert step.result is None
    with pytest.raises(RuntimeError, match="once a dam has been chosen"):
        step.result = object()


def test_w_x_02_a_step_without_a_stage_keeps_no_result_even_when_there_is_a_run():
    step = _attached(Stageless(), DamRun(Dam(name="A", slug="a")))

    step.result = None
    assert step.result is None
    with pytest.raises(RuntimeError, match="Stageless has no result to keep"):
        step.result = object()
