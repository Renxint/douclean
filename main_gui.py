# -*- coding: utf-8 -*-
"""
抖音下载器 - PyQt6 桌面界面入口

运行:
    python main_gui.py
"""

import sys
from pathlib import Path

# 将项目根目录和本项目目录加入 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Claude/
PROJECT_DIR = Path(__file__).resolve().parent  # douyin_downloader/
for p in (str(PROJECT_ROOT), str(PROJECT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor

from src.gui import MainWindow, OUTPUT_ROOT


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # 暗色调色板
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(26, 26, 46))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(224, 224, 224))
    palette.setColor(QPalette.ColorRole.Base, QColor(22, 33, 62))
    palette.setColor(QPalette.ColorRole.Text, QColor(224, 224, 224))
    palette.setColor(QPalette.ColorRole.Button, QColor(233, 69, 96))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(233, 69, 96))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    window = MainWindow()
    window.show()

    # 检查 Cookie
    from pathlib import Path
    cookie_file = Path(__file__).resolve().parent / "data" / "Cookie.txt"
    if cookie_file.exists():
        cookie_len = len(cookie_file.read_text(encoding='utf-8').strip())
        window.status.setText(f"[OK] Cookie 已就绪 ({cookie_len} 字符) — 直连模式")
    else:
        window.status.setText("[警告] Cookie.txt 不存在 — 请放入 data/Cookie.txt")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
