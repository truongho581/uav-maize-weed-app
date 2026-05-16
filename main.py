"""
main.py — File chạy chính của phần mềm Phân tích Sinh trưởng Cây trồng UAV
Chạy: python main.py
"""

import sys

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from phan_tich_ui import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("UAV Crop Analysis")
    app.setOrganizationName("UAV Research Group")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))

    win = MainWindow()
    win.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
