"""X-NFR-04: errors and progress are logged, and an unexpected error leaves a traceback in the project folder (B5)."""

import logging

import pytest

from src.utils import log
from src.utils.log import LOG_DIR, LOG_NAME, attach_project_log, configure, detach_project_log, get_logger, log_file


@pytest.fixture()
def logger():
    log = get_logger()
    log.setLevel(logging.INFO)
    yield log
    detach_project_log()


def test_x_nfr_04_the_log_goes_to_a_file_in_the_project_folder(tmp_path, logger):
    path = attach_project_log(tmp_path)

    logger.info("hello %s", "dam")
    detach_project_log()

    assert path == tmp_path / LOG_DIR / LOG_NAME
    assert "INFO hello dam" in path.read_text(encoding="utf-8")


def test_x_nfr_04_a_traceback_is_written_to_the_file(tmp_path, logger):
    path = attach_project_log(tmp_path)

    try:
        raise ZeroDivisionError("boom")
    except ZeroDivisionError as exc:
        logger.error("A background task failed.", exc_info=exc)
    detach_project_log()

    text = path.read_text(encoding="utf-8")
    assert "ZeroDivisionError: boom" in text and "Traceback" in text


def test_x_nfr_04_a_second_project_takes_over_the_file_and_the_first_stays_unwritten(tmp_path, logger):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir(), second.mkdir()
    first_path = attach_project_log(first)
    logger.info("one")
    second_path = attach_project_log(second)
    logger.info("two")
    detach_project_log()

    assert "one" in first_path.read_text(encoding="utf-8") and "two" not in first_path.read_text(encoding="utf-8")
    assert "two" in second_path.read_text(encoding="utf-8") and log_file() is None


def test_x_nfr_04_a_folder_that_cannot_hold_a_log_gives_no_file_and_no_error(tmp_path, logger):
    (tmp_path / LOG_DIR).write_text("in the way", encoding="utf-8")  # a file where the folder should be

    assert attach_project_log(tmp_path) is None and log_file() is None


def test_x_nfr_04_the_file_rolls_over_instead_of_growing_without_a_limit(tmp_path, logger, monkeypatch):
    monkeypatch.setattr(log, "MAX_BYTES", 300)
    path = attach_project_log(tmp_path)

    for number in range(30):
        logger.info("a line that is long enough to fill the file after a few of them, number %d", number)
    detach_project_log()

    assert path.with_name("app.log.1").is_file() and path.stat().st_size <= 300 + 200


def test_x_nfr_04_configure_adds_one_console_handler_however_often_it_is_called(logger):
    def consoles():
        return [handler for handler in logger.handlers if type(handler) is logging.StreamHandler]

    for handler in consoles():
        logger.removeHandler(handler)
    propagate = logger.propagate
    try:
        configure()
        configure()
        assert len(consoles()) == 1 and logger.propagate is False
    finally:
        for handler in consoles():
            logger.removeHandler(handler)
        logger.propagate = propagate
