# -*- coding: utf-8 -*-
"""
抖音下载器 - PyQt6 桌面界面
双击运行或: python douyin_gui.py
"""
import sys, os, re, time, json
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QProgressBar, QLabel, QSplitter, QFrame, QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon

from douyin_downloader import (
    parse_sec_user_id, clean_filename, pick_best_url,
    get_ext_from_url, OUTPUT_ROOT, PAGE_DELAY,
)

# ============ 路径工具 ============
def get_base_dir():
    """获取项目根目录 (兼容 PyInstaller 打包)"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent

BASE_DIR = get_base_dir()
SIGN_SERVER_DIR = BASE_DIR / "sign-server"

# ============ 下载线程 ============
class DownloadThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)  # current, total
    finished_signal = pyqtSignal(dict)       # stats

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        url = self.url.strip()
        self.log_signal.emit("[>>] Parsing URL...")

        try:
            sec_id = parse_sec_user_id(url)
        except Exception as e:
            self.log_signal.emit(f"[ERROR] {e}")
            return

        self.log_signal.emit(f"[OK] User: {sec_id[:24]}...")

        # 检查签名服务
        import requests
        try:
            r = requests.get("http://localhost:8765/health", timeout=5)
            if r.json().get("status") != "ok":
                self.log_signal.emit("[ERROR] Sign server not ready!")
                return
        except:
            self.log_signal.emit("[ERROR] Sign server not running! Run: cd sign-server && npm start")
            return

        from douyin_api import DouyinAPI
        api = DouyinAPI()

        self.log_signal.emit("[>>] Fetching posts (paginated)...")
        all_posts = []
        cursor = 0
        author_name = ""
        page = 0
        while page < 50:
            page += 1
            data = api.get_user_posts(sec_id, max_cursor=cursor, count=18)
            aweme_list = data.get("aweme_list", [])
            if not aweme_list:
                break
            all_posts.extend(aweme_list)
            if not author_name and aweme_list:
                author_name = aweme_list[0].get("author", {}).get("nickname", "")
            if not data.get("has_more", 0):
                break
            cursor = data.get("max_cursor", 0)
            time.sleep(PAGE_DELAY)

        total = len(all_posts)
        self.log_signal.emit(f"[OK] {total} posts | Author: {author_name}")

        safe_author = clean_filename(author_name, 20) if author_name else sec_id[:8]
        out_dir = OUTPUT_ROOT / safe_author
        out_dir.mkdir(parents=True, exist_ok=True)

        tracker_path = out_dir / ".downloaded.json"
        tracker = {}
        if tracker_path.exists():
            try: tracker = json.loads(tracker_path.read_text(encoding='utf-8'))
            except: pass

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0.0.0 Safari/537.36',
            'Referer': 'https://www.douyin.com/',
        }

        stats = {"video": 0, "image": 0, "music": 0, "skip": 0, "fail": 0}

        for i, post in enumerate(all_posts):
            aweme_id = post.get("aweme_id", "")
            desc = clean_filename(post.get("desc", "")) or aweme_id
            folder_name = f"{i+1:03d}_{desc}"
            post_dir = out_dir / folder_name

            self.progress_signal.emit(i + 1, total)

            if aweme_id in tracker:
                stats["skip"] += 1
                continue

            post_dir.mkdir(parents=True, exist_ok=True)
            self.log_signal.emit(f"[{i+1}/{total}] {desc[:40]}")

            has_video = bool(post.get("video"))
            has_images = bool(post.get("images"))
            has_real_video = False

            # 视频
            if has_video:
                vdata = post["video"]
                da_urls = (vdata.get("download_addr") or {}).get("url_list") or []
                pa_urls = (vdata.get("play_addr") or {}).get("url_list") or []
                raw = (da_urls[0] if da_urls else None) or (pa_urls[0] if pa_urls else None)
                if raw and ".mp3" not in raw.lower():
                    has_real_video = True
                    ok = self._download(raw, post_dir / "video.mp4", headers)
                    if ok: stats["video"] += 1
                    else: stats["fail"] += 1

            # 音乐
            if not has_real_video:
                music = post.get("music") or {}
                mp = music.get("play_url")
                mp_urls = (mp.get("url_list") if isinstance(mp, dict) else
                           [mp] if isinstance(mp, str) and mp else [])
                if mp_urls:
                    ok = self._download(mp_urls[0], post_dir / "music.mp3", headers)
                    if ok: stats["music"] += 1
                    else: stats["fail"] += 1

            # 图片
            if has_images:
                for j, img in enumerate(post["images"]):
                    img_urls = img.get("url_list", [])
                    img_url = pick_best_url(img_urls, "jpeg") or pick_best_url(img_urls, "jpg")
                    if img_url:
                        ext = get_ext_from_url(img_url, ".jpg")
                        ok = self._download(img_url, post_dir / f"{j+1:02d}{ext}", headers)
                        if ok: stats["image"] += 1
                        else: stats["fail"] += 1

            tracker[aweme_id] = {"desc": desc, "folder": folder_name,
                                 "time": time.strftime("%Y-%m-%d %H:%M:%S")}

        tracker_path.write_text(json.dumps(tracker, ensure_ascii=False, indent=2), encoding='utf-8')
        self.log_signal.emit(f"===== DONE =====")
        self.log_signal.emit(f"Video:{stats['video']} Image:{stats['image']} Music:{stats['music']} Skip:{stats['skip']} Fail:{stats['fail']}")
        self.log_signal.emit(f"Folder: {out_dir}")
        self.finished_signal.emit(stats)

    def _download(self, url, path, headers):
        import requests
        if path.exists():
            return True
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            r.raise_for_status()
            with open(path, 'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return True
        except Exception as e:
            self.log_signal.emit(f"  ! FAIL: {e}")
            if path.exists():
                path.unlink()
            return False


# ============ 主窗口 ============
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
QPushButton:pressed {
    background-color: #c23152;
}
QPushButton#secondaryBtn {
    background-color: #0f3460;
}
QPushButton#secondaryBtn:hover {
    background-color: #1a4a7a;
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
QListWidget {
    background-color: #16213e;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 4px;
    font-size: 13px;
    outline: none;
}
QListWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
}
QListWidget::item:selected {
    background-color: #e94560;
}
QListWidget::item:hover {
    background-color: #0f3460;
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
QSplitter::handle {
    background-color: #0f3460;
    width: 1px;
}
QFrame#separator {
    background-color: #0f3460;
    max-height: 1px;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Douyin Downloader")
        self.resize(900, 650)
        self.setMinimumSize(700, 500)
        self.setStyleSheet(STYLE)

        self.thread = None
        self.out_dir = OUTPUT_ROOT

        self._build_ui()
        self._refresh_users()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # ---- 标题 ----
        title = QLabel("Douyin User Downloader")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #e94560; padding: 4px 0;")
        layout.addWidget(title)

        # ---- URL 输入行 ----
        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.douyin.com/user/MS4wLjAB...")
        self.url_input.returnPressed.connect(self._start_download)
        url_row.addWidget(self.url_input)

        self.dl_btn = QPushButton("Download")
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.clicked.connect(self._start_download)
        url_row.addWidget(self.dl_btn)
        layout.addLayout(url_row)

        # ---- 进度条 ----
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # ---- 主体: 日志 + 用户列表 ----
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧: 日志
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Log"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Download log will appear here...")
        left_layout.addWidget(self.log_view)
        splitter.addWidget(left)

        # 右侧: 用户列表
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Downloaded"))
        self.user_list = QListWidget()
        self.user_list.currentItemChanged.connect(self._on_user_select)
        right_layout.addWidget(self.user_list)

        self.open_btn = QPushButton("Open Folder")
        self.open_btn.setObjectName("secondaryBtn")
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.clicked.connect(self._open_folder)
        right_layout.addWidget(self.open_btn)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("secondaryBtn")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh_users)
        right_layout.addWidget(self.refresh_btn)

        splitter.addWidget(right)
        splitter.setSizes([550, 300])
        layout.addWidget(splitter, 1)

        # ---- 状态栏 ----
        self.status = QLabel("Check sign server: http://localhost:8765/health")
        self.status.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.status)

    # ============ 逻辑 ============

    def _start_download(self):
        url = self.url_input.text().strip()
        if not url:
            self._log("[ERROR] Please enter a URL")
            return

        self.dl_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.log_view.clear()
        self._log("[>>] Starting...")

        self.thread = DownloadThread(url)
        self.thread.log_signal.connect(self._log)
        self.thread.progress_signal.connect(self._update_progress)
        self.thread.finished_signal.connect(self._on_finished)
        self.thread.start()

    def _log(self, msg):
        self.log_view.append(msg)
        # 自动滚到底部
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _update_progress(self, current, total):
        self.progress.setMaximum(total)
        self.progress.setValue(current)

    def _on_finished(self, stats):
        self.dl_btn.setEnabled(True)
        if stats.get("video", 0) + stats.get("image", 0) > 0:
            self.progress.setValue(self.progress.maximum())
        self._refresh_users()
        self.status.setText(f"Done! Video:{stats.get('video',0)} Image:{stats.get('image',0)} Music:{stats.get('music',0)}")

    def _refresh_users(self):
        self.user_list.clear()
        if not self.out_dir.exists():
            return
        for d in sorted(self.out_dir.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            tracker = d / ".downloaded.json"
            posts = 0
            if tracker.exists():
                try: posts = len(json.loads(tracker.read_text(encoding='utf-8')))
                except: pass
            files = sum(1 for _ in d.rglob("*") if _.is_file() and _.name != ".downloaded.json")
            item = QListWidgetItem(f"{d.name}  [{posts} posts, {files} files]")
            item.setData(Qt.ItemDataRole.UserRole, str(d))
            self.user_list.addItem(item)

    def _on_user_select(self, current, previous):
        pass

    def _open_folder(self):
        item = self.user_list.currentItem()
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and Path(path).exists():
                os.startfile(path)


# ============ 入口 ============
import subprocess

_sign_server_process = None


def start_sign_server():
    """启动签名服务"""
    global _sign_server_process
    import requests

    # Already running?
    try:
        r = requests.get("http://localhost:8765/health", timeout=2)
        if r.json().get("status") == "ok":
            return True
    except:
        pass

    server_js = SIGN_SERVER_DIR / "puppeteer-server.js"
    if not server_js.exists():
        return False

    try:
        _sign_server_process = subprocess.Popen(
            ["node", str(server_js)],
            cwd=str(SIGN_SERVER_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
        )
        # Wait up to 60 seconds for server
        for _ in range(60):
            time.sleep(1)
            try:
                r = requests.get("http://localhost:8765/health", timeout=2)
                if r.json().get("status") == "ok":
                    return True
            except:
                pass
        return False
    except FileNotFoundError:
        return False


def stop_sign_server():
    """停止签名服务"""
    global _sign_server_process
    if _sign_server_process:
        _sign_server_process.terminate()
        _sign_server_process = None


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

    # 启动签名服务
    window.status.setText("Starting sign server...")
    QApplication.processEvents()
    if start_sign_server():
        window.status.setText("[OK] Sign server running on localhost:8765")
    else:
        window.status.setText("[WARN] Sign server failed. Install Node.js and run: cd sign-server && npm install && node puppeteer-server.js")

    window._refresh_users()

    exit_code = app.exec()
    stop_sign_server()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
