import tkinter as tk
from src.ui import SedimentApp


def main():
    root = tk.Tk()
    app = SedimentApp(root)  # noqa: F841 (keeps a reference to the controller)
    root.mainloop()


if __name__ == "__main__":
    main()
