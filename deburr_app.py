#!/usr/bin/env python3
import sys

from PySide6.QtWidgets import QApplication

from fc_deburr.ui.main_window import MainWindow


def main():
    application = QApplication.instance() or QApplication(sys.argv)
    feature_path = sys.argv[1] if len(sys.argv) > 1 else None
    window = MainWindow(feature_path=feature_path)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
