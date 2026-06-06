# -*- coding: utf-8 -*-
"""
抖音单视频下载器 - PyQt6 桌面界面

支持:
  - 视频 (下载最高画质 mp4)
  - 图集 (下载原图 jpg)
  - 实况图 (下载图片 + 关联视频)
  - 自动创建文件夹: 作者（描述）

用法:
    python single_gui.py
"""

import sys
import re
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Claude/
PROJECT_DIR = Path(__file__).resolve().parent  # douyin_downloader/
for p in (str(PROJECT_ROOT), str(PROJECT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QProgressBar, QLabel, QFileDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPalette, QColor

import requests

# ============================================================
# 路径配置
# ============================================================
BOOTSTRAP_JS = PROJECT_DIR / "sign-server" / "bootstrap.js"
COOKIE_FILE = PROJECT_DIR / "data" / "Cookie.txt"
OUTPUT_DIR = PROJECT_DIR / "output"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36 "
    "SLBrowser/9.0.8.5161 SLBChan/111 SLBVPV/64-bit"
)


# ============================================================
# 工具函数
# ============================================================
def clean_name(name: str, max_len: int = 50) -> str:
    if not name:
        return "untitled"
    name = re.sub(r'[\\/:*?"<>|\x00-\x1F\x7F\n\r\t]', '', name)
    name = re.sub(r'[​-‏ - ﻿ -‏]', '', name)
    name = name.strip().rstrip('. ')
    if len(name) > max_len:
        name = name[:max_len].strip().rstrip('. ')
    return name or "untitled"


def pick_best_video_url(vdata: dict) -> str:
    def _first(urls):
        for u in (urls or []):
            if u and ".mp3" not in u:
                return u
        return ""
    bit_rates = vdata.get("bit_rate") or []
    if bit_rates:
        best = max(bit_rates, key=lambda b: b.get("bit_rate", 0))
        url = _first((best.get("play_addr") or {}).get("url_list") or [])
        if url:
            return url
    url = _first((vdata.get("download_addr") or {}).get("url_list") or [])
    return url or _first((vdata.get("play_addr") or {}).get("url_list") or [])


# ============================================================
# 下载线程
# ============================================================
class DownloadThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, raw_text: str, save_dir: str):
        super().__init__()
        self.raw_text = raw_text
        self.save_dir = Path(save_dir)

    def run(self):
        try:
            # 1. 解析视频ID
            self.log_signal.emit("[>>] 解析链接...")
            aweme_id = self._resolve_video_id(self.raw_text)
            self.log_signal.emit(f"[OK] 视频ID: {aweme_id}")

            # 2. 加载Cookie
            cookie = ""
            if COOKIE_FILE.exists():
                cookie = COOKIE_FILE.read_text(encoding='utf-8').strip()
                self.log_signal.emit(f"[OK] Cookie 已加载 ({len(cookie)}字符)")
            else:
                self.log_signal.emit("[WARN] Cookie.txt 不存在")

            # 3. 获取视频数据
            self.log_signal.emit("[>>] 获取数据 (启动浏览器, 约15秒)...")
            aweme = self._fetch_video_data(aweme_id, cookie)

            desc = aweme.get("desc", "") or aweme_id
            author = aweme.get("author", {}).get("nickname", "")
            self.log_signal.emit(f"  作者: {author}")
            self.log_signal.emit(f"  描述: {desc[:60]}")

            # 4. 创建文件夹并下载
            self._download_aweme(aweme)

        except Exception as e:
            self.log_signal.emit(f"[ERROR] {e}")
            self.finished_signal.emit(False, str(e))

    def _resolve_video_id(self, raw: str) -> str:
        for pat in [
            r'https?://v\.douyin\.com/[A-Za-z0-9_\-/]+',
            r'https?://(?:www\.)?douyin\.com/(?:video|note)/(\d+)',
        ]:
            m = re.search(pat, raw)
            if m:
                url = m.group(0)
                break
        else:
            raise ValueError("未识别到抖音链接")

        m = re.search(r'/(?:video|note)/(\d+)', url)
        if m:
            return m.group(1)

        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        r = s.get(url, allow_redirects=True, timeout=15, stream=True)
        r.close()
        m = re.search(r'/(?:video|note)/(\d+)', r.url)
        if m:
            return m.group(1)
        raise ValueError(f"无法解析: {r.url}")

    def _fetch_video_data(self, aweme_id: str, cookie: str) -> dict:
        result = subprocess.run(
            ["node", str(BOOTSTRAP_JS), aweme_id, cookie],
            capture_output=True, text=True, timeout=120,
            cwd=str(BOOTSTRAP_JS.parent),
            encoding='utf-8', errors='replace',
        )
        data = json.loads(result.stdout.strip())
        if '_error' in data:
            raise RuntimeError(data['_error'])
        return data.get('aweme_detail', {})

    def _download_aweme(self, aweme: dict):
        """根据作品类型自动处理：视频 / 图集 / 实况图"""
        desc = aweme.get("desc", "") or aweme.get("aweme_id", "untitled")
        author = aweme.get("author", {}).get("nickname", "")
        video = aweme.get("video")
        images = aweme.get("images") or []

        # 文件夹: 作者（描述）
        safe_author = clean_name(author, 20)
        safe_desc = clean_name(desc, 40)
        folder_name = f"{safe_author}（{safe_desc}）"
        post_dir = self.save_dir / folder_name
        post_dir.mkdir(parents=True, exist_ok=True)

        stats = {"video": 0, "image": 0, "fail": 0}

        # --- 视频 ---
        if video:
            url = pick_best_video_url(video)
            if url:
                self.log_signal.emit(f"[视频]")
                if self._download(url, post_dir / "video.mp4"):
                    stats["video"] += 1
                else:
                    stats["fail"] += 1

        # --- 图集 ---
        if images:
            for j, img in enumerate(images):
                img_urls = img.get("url_list", [])
                img_url = ""
                for u in img_urls:
                    if 'jpeg' in u.lower() or 'jpg' in u.lower():
                        img_url = u
                        break
                if not img_url:
                    img_url = img_urls[0] if img_urls else ""
                if not img_url:
                    continue

                is_live = img.get('live_photo_type', 0) == 1
                live_tag = '_实况' if is_live else ''

                self.log_signal.emit(f"[图集 {j+1}/{len(images)}{' 实况' if is_live else ''}]")
                if self._download(img_url, post_dir / f"{j+1:02d}{live_tag}.jpg"):
                    stats["image"] += 1
                else:
                    stats["fail"] += 1

                # 实况图: 下载关联视频
                if is_live:
                    lv = img.get('video') or {}
                    live_url = pick_best_video_url(lv)
                    if live_url:
                        self.log_signal.emit(f"[实况视频 {j+1}]")
                        if self._download(live_url, post_dir / f"{j+1:02d}{live_tag}.mp4"):
                            stats["video"] += 1
                        else:
                            stats["fail"] += 1

        # --- 保存描述 ---
        (post_dir / "desc.txt").write_text(desc, encoding='utf-8')

        msg = f"完成! {author} - 视频:{stats['video']} 图片:{stats['image']}"
        self.log_signal.emit(f"===== {msg} =====")
        self.finished_signal.emit(True, msg)

    def _download(self, url: str, path: Path) -> bool:
        if path.exists():
            self.log_signal.emit(f"  [SKIP] {path.name}")
            self.progress_signal.emit(100)
            return True
        headers = {"User-Agent": UA, "Referer": "https://www.douyin.com/"}
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=120)
            r.raise_for_status()
            total = int(r.headers.get('content-length', 0))
            dl = 0
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
                    dl += len(chunk)
                    if total > 0:
                        self.progress_signal.emit(dl * 100 // total)
            mb = dl / 1024 / 1024
            self.log_signal.emit(f"  [OK] {path.name} ({mb:.1f}MB)")
            self.progress_signal.emit(100)
            return True
        except Exception as e:
            self.log_signal.emit(f"  [FAIL] {e}")
            if path.exists():
                path.unlink()
            return False


# ============================================================
# 样式 (对齐 main_gui.py)
# ============================================================
STYLE = """
QMainWindow, QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
}
QLineEdit {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 14px;
    selection-background-color: #e94560;
}
QLineEdit:focus {
    border: 1px solid #e94560;
}
QPushButton {
    background-color: #e94560;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #ff6b81;
}
QPushButton#secondaryBtn {
    background-color: #0f3460;
}
QPushButton#secondaryBtn:hover {
    background-color: #1a4a7a;
}
QPushButton:disabled {
    background-color: #333;
    color: #666;
}
QTextEdit {
    background-color: #0d1117;
    color: #8b949e;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 6px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}
QProgressBar {
    background-color: #16213e;
    border: 1px solid #0f3460;
    border-radius: 4px;
    height: 10px;
    text-align: center;
    font-size: 10px;
}
QProgressBar::chunk {
    background-color: #e94560;
    border-radius: 3px;
}
QLabel {
    color: #8b949e;
    font-size: 13px;
}
"""


# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("抖音单视频下载")
        self.resize(750, 550)
        self.setMinimumSize(550, 400)
        self.setStyleSheet(STYLE)

        self.thread = None
        self.output_path = OUTPUT_DIR

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("抖音单视频下载")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #e94560; padding: 4px 0;")
        layout.addWidget(title)

        # URL 输入
        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴分享链接或视频URL... 支持视频/图集/实况图")
        self.url_input.returnPressed.connect(self._start_download)
        url_row.addWidget(self.url_input)

        self.dl_btn = QPushButton("下载")
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.clicked.connect(self._start_download)
        url_row.addWidget(self.dl_btn)
        layout.addLayout(url_row)

        # 保存路径
        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        path_row.addWidget(QLabel("保存路径"))
        self.path_input = QLineEdit()
        self.path_input.setText(str(OUTPUT_DIR))
        path_row.addWidget(self.path_input)

        self.browse_btn = QPushButton("浏览")
        self.browse_btn.setObjectName("secondaryBtn")
        self.browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(self.browse_btn)
        layout.addLayout(path_row)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # 日志
        layout.addWidget(QLabel("日志"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("下载日志...")
        layout.addWidget(self.log_view, 1)

        # 状态栏
        self.status = QLabel("就绪 — 依赖 data/Cookie.txt")
        self.status.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.status)

        if COOKIE_FILE.exists():
            self.status.setText(f"[OK] Cookie 就绪 ({COOKIE_FILE.stat().st_size} bytes)")
        else:
            self.status.setText("[WARN] Cookie.txt 不存在")

    def _browse_path(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", str(self.output_path))
        if folder:
            self.path_input.setText(folder)
            self.output_path = Path(folder)

    def _start_download(self):
        text = self.url_input.text().strip()
        if not text:
            self._log("[ERROR] 请输入链接")
            return

        save_dir = Path(self.path_input.text().strip()) if self.path_input.text().strip() else OUTPUT_DIR

        self.dl_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.log_view.clear()

        self.thread = DownloadThread(text, str(save_dir))
        self.thread.log_signal.connect(self._log)
        self.thread.progress_signal.connect(self._update_progress)
        self.thread.finished_signal.connect(self._on_finished)
        self.thread.start()

    def _log(self, msg):
        self.log_view.append(msg)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _update_progress(self, pct):
        self.progress.setValue(pct)

    def _on_finished(self, ok, message):
        self.dl_btn.setEnabled(True)
        self.status.setText(message)
        if ok:
            self.progress.setValue(100)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

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
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
