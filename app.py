import sys
from pathlib import Path
import os

os.chdir(Path(__file__).resolve().parent)
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Qnumber")
    app.setOrganizationName("QnumberLab")

    win = MainWindow()
    win.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())