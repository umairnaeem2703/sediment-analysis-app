"""Helpers shared by the wizard tests."""

import time


def wait_until(top, condition, timeout=5.0):
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
