import tkinter as tk
from src.ui import SedimentApp


def main():
    root = tk.Tk()
    app = SedimentApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
