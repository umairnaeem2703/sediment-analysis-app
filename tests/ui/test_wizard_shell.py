import threading
import time
import tkinter as tk
from tkinter import ttk

import pytest

from src.ui.steps.base import Step
from src.ui.wizard import Wizard


class FakeStep(Step):
    def __init__(self, title):
        super().__init__()
        self.title = title
        self.done = False
        self.resets = 0
        self.shown = 0

    def build(self, frame):
        ttk.Label(frame, text=self.title).pack()

    def on_show(self):
        self.shown += 1

    def is_complete(self):
        return self.done

    def reset(self):
        self.done = False
        self.resets += 1


@pytest.fixture()
def shell(tk_root):
    top = tk.Toplevel(tk_root)
    steps = [FakeStep("One"), FakeStep("Two"), FakeStep("Three")]
    wizard = Wizard(top, steps)
    wizard.frame.pack(fill="both", expand=True)
    top.update_idletasks()
    yield wizard, steps, top
    top.destroy()


def _enabled(button):
    return not button.instate(["disabled"])


def _wait_until(top, condition, timeout=5.0):
    # Worker threads may only call into Tk while the main thread is inside mainloop(), as in the app.
    deadline = time.monotonic() + timeout

    def poll():
        if condition() or time.monotonic() > deadline:
            top.quit()
        else:
            top.after(10, poll)

    top.after(10, poll)
    top.mainloop()
    assert condition(), "timed out waiting for the background task"


def test_w_x_02_next_needs_a_complete_step_and_later_steps_stay_locked(shell):
    wizard, steps, _ = shell

    assert wizard.current == 0
    assert not _enabled(wizard.next_button)
    assert not _enabled(wizard.back_button)
    assert wizard.can_enter(0) and not wizard.can_enter(1) and not wizard.can_enter(2)
    assert wizard.go_to(2) is False

    steps[0].done = True
    wizard.refresh()

    assert _enabled(wizard.next_button)
    assert wizard.can_enter(1) and not wizard.can_enter(2)
    wizard.next()
    assert wizard.current == 1
    assert steps[1].shown == 1
    assert _enabled(wizard.back_button)
    assert not _enabled(wizard.next_button)


def test_w_x_02_completed_steps_can_be_revisited_from_the_list(shell):
    wizard, steps, _ = shell
    steps[0].done = steps[1].done = True
    wizard.refresh()
    wizard.go_to(2)

    wizard.step_list.selection_set("0")
    wizard.step_list.event_generate("<<TreeviewSelect>>")

    assert wizard.current == 0
    wizard.back()
    assert wizard.current == 0


def test_w_x_02_editing_a_step_resets_every_later_step_and_says_so(shell):
    wizard, steps, _ = shell
    steps[0].done = steps[1].done = True
    wizard.refresh()
    wizard.go_to(1)

    wizard.invalidate_after(0, "The basin table changed.")

    assert [s.resets for s in steps] == [0, 1, 1]
    assert [s.done for s in steps] == [True, False, False]
    assert wizard.current == 0
    assert "The basin table changed." in wizard.notice_var.get()
    assert "Two" in wizard.notice_var.get()
    assert "Three" not in wizard.notice_var.get()  # only steps that held a result are named
    assert not wizard.can_enter(2)


def test_w_x_02_no_notice_when_nothing_later_was_complete(shell):
    wizard, steps, _ = shell
    steps[0].done = True

    wizard.invalidate_after(0, "Changed.")

    assert wizard.notice_var.get() == ""


def test_w_x_02_the_step_list_marks_done_and_locked_steps(shell):
    wizard, steps, _ = shell
    steps[0].done = True
    wizard.refresh()

    texts = [wizard.step_list.item(str(i), "text") for i in range(3)]

    assert texts[0].startswith("✓") and "1. One" in texts[0]
    assert "2. Two" in texts[1] and not texts[1].startswith("✓")
    assert "locked" in wizard.step_list.item("2", "tags")


def test_w_x_03_tasks_run_off_the_tk_thread_and_navigation_is_disabled_meanwhile(shell):
    wizard, steps, top = shell
    steps[0].done = True
    wizard.refresh()
    main_thread = threading.get_ident()
    seen = {}
    release = threading.Event()

    def task():
        seen["task_thread"] = threading.get_ident()
        release.wait(timeout=5)
        return 42

    def on_done(result, error):
        seen.update(result=result, error=error, done_thread=threading.get_ident())

    wizard.run_task(task, on_done, "Working")
    assert not _enabled(wizard.next_button)
    assert not _enabled(wizard.back_button)
    assert wizard.status_var.get() == "Working"
    assert wizard.go_to(1) is False

    release.set()
    _wait_until(top, lambda: "result" in seen)

    assert seen["task_thread"] != main_thread
    assert seen["done_thread"] == main_thread
    assert seen["result"] == 42 and seen["error"] is None
    assert _enabled(wizard.next_button)
    assert wizard.status_var.get() == ""


def test_w_x_03_a_failing_task_reports_its_error_and_unlocks_navigation(shell):
    wizard, _, top = shell
    seen = {}

    def task():
        raise ValueError("bad input")

    wizard.run_task(task, lambda result, error: seen.update(result=result, error=error))
    _wait_until(top, lambda: "error" in seen)

    assert seen["result"] is None
    assert str(seen["error"]) == "bad input"
    assert not wizard.busy


def test_w_x_02_syncing_the_list_selection_does_not_trigger_endless_refreshes(shell):
    wizard, _, top = shell
    calls = []
    original = wizard.refresh

    def counting_refresh():
        calls.append(1)
        if len(calls) <= 50:  # cap, so a regression fails here instead of hanging
            original()

    wizard.refresh = counting_refresh
    wizard.refresh()
    for _ in range(20):
        top.update()

    assert len(calls) == 1
