# -*- coding: utf-8 -*-
"""
抖音下载器 - PyQt6 桌面界面
运行: python main_gui.py
"""

import sys
import os
import time
import json
import threading
from pathlib import Path

# 确保可以导入 shared 库及本项目的 src
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # Claude/
PROJECT_DIR = Path(__file__).resolve().parent.parent  # douyin_downloader/
for p in (str(PROJECT_ROOT), str(PROJECT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QProgressBar, QLabel, QSplitter, QFrame, QMessageBox,
    QComboBox, QFileDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon

from src.downloader import (
    parse_sec_user_id, clean_filename, pick_best_url,
    get_ext_from_url, pick_best_video_url,
    OUTPUT_ROOT, PAGE_DELAY,
)


# ============ 下载线程 ============
class DownloadThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)  # current, total
    finished_signal = pyqtSignal(dict)       # stats
    paused_signal = pyqtSignal(bool)         # True = paused
    total_signal = pyqtSignal(int)           # 真实作品总数 (scroll_user 完成后)

    def __init__(self, url, pending_count_text="全部下载", custom_out_dir=None):
        super().__init__()
        self.url = url
        self.pending_count_text = pending_count_text
        self.custom_out_dir = custom_out_dir
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancelled = False

    def pause(self):
        """暂停下载"""
        self._pause_event.clear()
        self.paused_signal.emit(True)
        self.log_signal.emit("[PAUSED] 下载已暂停")

    def resume(self):
        """继续下载"""
        self._pause_event.set()
        self.paused_signal.emit(False)
        self.log_signal.emit("[RESUMED] 下载已继续")

    def toggle_pause(self):
        """切换暂停/继续"""
        if self._is_paused():
            self.resume()
        else:
            self.pause()

    def _is_paused(self):
        return not self._pause_event.is_set()

    def cancel(self):
        """取消下载"""
        self._cancelled = True
        self._pause_event.set()  # 解除暂停阻塞以便退出
        self.log_signal.emit("[CANCELLED] 正在取消...")

    def _check_cancel(self):
        """检查是否已取消 (在检查点调用)"""
        return self._cancelled

    def _wait_if_paused(self):
        """阻塞直到取消暂停或取消"""
        self._pause_event.wait()

    def run(self):
        url = self.url.strip()
        self.log_signal.emit("[>>] 解析URL...")

        try:
            sec_id = parse_sec_user_id(url)
        except Exception as e:
            self.log_signal.emit(f"[错误] {e}")
            self.finished_signal.emit({"video": 0, "image": 0, "music": 0, "skip": 0, "fail": 0, "cancelled": True})
            return

        self.log_signal.emit(f"[OK] 用户: {sec_id[:24]}...")

        from src.api import DouyinAPI
        # 加载 Cookie (已由主窗口校验，直接读文件)
        cookie_file = Path(__file__).resolve().parent.parent / "data" / "Cookie.txt"
        cookie_str = ""
        if cookie_file.exists():
            cookie_str = cookie_file.read_text(encoding='utf-8').strip()
            self.log_signal.emit(f"[OK] Cookie 已加载 ({len(cookie_str)}字符)")
        else:
            self.log_signal.emit("[WARN] Cookie 未设置")

        api = DouyinAPI(cookie_string=cookie_str)

        # 获取用户简介
        profile = api.get_user_profile(sec_id)

        self.log_signal.emit("[>>] 获取作品列表...")
        all_posts = []
        seen_ids = set()
        cursor = 0
        author_name = profile.get("nickname", "")
        page = 0

        while page < 50:
            if self._check_cancel():
                self.finished_signal.emit({"video": 0, "image": 0, "music": 0, "skip": 0, "fail": 0, "cancelled": True})
                return
            self._wait_if_paused()

            page += 1
            data = api.get_user_posts(sec_id, max_cursor=cursor, count=18)
            aweme_list = data.get("aweme_list", [])
            if not aweme_list:
                self.log_signal.emit(f"[翻页] P{page}: empty, stop")
                break

            new_count = 0
            for post in aweme_list:
                aid = post.get("aweme_id", "")
                if aid not in seen_ids:
                    seen_ids.add(aid)
                    all_posts.append(post)
                    new_count += 1

            if not author_name and aweme_list:
                author_name = aweme_list[0].get("author", {}).get("nickname", "")

            has_more = data.get("has_more", 0)
            new_cursor = data.get("max_cursor", 0)
            self.log_signal.emit(f"[翻页] P{page}: new={new_count}, dup={len(aweme_list)-new_count}, "
                               f"tot={len(all_posts)}, has_more={has_more}, cursor={new_cursor}")

            if not has_more:
                self.log_signal.emit("[翻页] has_more=0, stop")
                break
            if new_count == 0:
                self.log_signal.emit("[翻页] 全是重复, stop")
                break
            cursor = new_cursor
            time.sleep(PAGE_DELAY)

        real_total = len(all_posts)
        self.total_signal.emit(real_total)

        # 解析用户输入数量, 越界自动修正
        count_text = self.pending_count_text.strip()
        max_count = None
        if count_text and not count_text.startswith("全部下载"):
            try:
                max_count = int(count_text)
            except ValueError:
                max_count = None

        if max_count and max_count > real_total:
            self.log_signal.emit(f"[提示] 输入 {max_count} 超过实际 {real_total} 个, 自动修正")
            max_count = real_total

        if max_count:
            all_posts = all_posts[:max_count]

        total = len(all_posts)
        self.log_signal.emit(f"[OK] 作者共 {real_total} 个作品, 本次下载 {total} 个 | 作者: {author_name}")

        safe_author = clean_filename(author_name, 20) if author_name else sec_id[:8]
        out_dir = (self.custom_out_dir or OUTPUT_ROOT) / safe_author
        out_dir.mkdir(parents=True, exist_ok=True)

        # 保存主页信息
        download_date = time.strftime("%Y-%m-%d %H:%M:%S")
        gender_map = {0: "未设置", 1: "男", 2: "女"}
        gender = gender_map.get(profile.get("gender", 0), str(profile.get("gender", "")))
        location = " ".join(filter(None, [
            profile.get("country", ""),
            profile.get("province", ""),
            profile.get("city", ""),
            profile.get("district", ""),
        ]))

        info_lines = [
            f"# {author_name}",
            f"",
            f"## 基本信息",
            f"",
            f"- 抖音号: {profile.get('unique_id', 'N/A')}",
            f"- 短ID: {profile.get('short_id', 'N/A')}",
            f"- UID: {profile.get('uid', 'N/A')}",
            f"- 性别: {gender}",
            f"- 年龄: {profile.get('age', 'N/A')}",
            f"- 地区: {location or 'N/A'}",
            f"- 学校: {profile.get('school', 'N/A')}",
            f"- 简介: {profile.get('desc', 'N/A')}",
            f"- 认证: {profile.get('custom_verify', '') or profile.get('enterprise_verify_reason', '') or '无'}",
            f"",
            f"## 数据统计",
            f"",
            f"- 作品数: {profile.get('aweme_count', 'N/A')}",
            f"- 粉丝数: {profile.get('follower_count', 'N/A')}",
            f"- 关注数: {profile.get('following_count', 'N/A')}",
            f"- 获赞数: {profile.get('favoriting_count', 'N/A')}",
            f"- 被赞数: {profile.get('total_favorited', 'N/A')}",
            f"",
            f"## 下载信息",
            f"",
            f"- 主页链接: {self.url.strip()}",
            f"- 下载日期: {download_date}",
            f"- 头像: {profile.get('avatar_url', 'N/A')}",
            f"",
        ]
        (out_dir / "主页信息.md").write_text("\n".join(info_lines), encoding='utf-8')

        tracker_path = out_dir / ".downloaded.json"
        tracker = {}
        if tracker_path.exists():
            try:
                tracker = json.loads(tracker_path.read_text(encoding='utf-8'))
            except Exception:
                pass

        headers = {
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/141.0.0.0 Safari/537.36 '
                          'SLBrowser/9.0.8.5161 SLBChan/111 SLBVPV/64-bit'),
            'Referer': 'https://www.douyin.com/',
        }

        stats = {"video": 0, "image": 0, "music": 0, "skip": 0, "fail": 0}

        for i, post in enumerate(all_posts):
            # 检查点: 取消/暂停
            if self._check_cancel():
                break
            self._wait_if_paused()

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

            # 保存作品文案
            desc_path = post_dir / "desc.md"
            if not desc_path.exists():
                desc_path.write_text(post.get("desc", ""), encoding='utf-8')

            has_video = bool(post.get("video"))
            has_images = bool(post.get("images"))
            has_real_video = False

            # 视频 (bit_rate 最高画质 > 无水印 > 播放地址)
            if has_video:
                best_url = pick_best_video_url(post["video"])
                if best_url:
                    has_real_video = True
                    ok = self._download(best_url, post_dir / "video.mp4", headers)
                    if ok:
                        stats["video"] += 1
                    else:
                        stats["fail"] += 1

            # 音乐
            if self._check_cancel():
                break
            if not has_real_video:
                music = post.get("music") or {}
                mp = music.get("play_url")
                mp_urls = (mp.get("url_list") if isinstance(mp, dict) else
                          [mp] if isinstance(mp, str) and mp else [])
                if mp_urls:
                    ok = self._download(mp_urls[0], post_dir / "music.mp3", headers)
                    if ok:
                        stats["music"] += 1
                    else:
                        stats["fail"] += 1

            # 图片
            if has_images:
                for j, img in enumerate(post["images"]):
                    if self._check_cancel():
                        break
                    self._wait_if_paused()
                    img_urls = img.get("url_list", [])
                    img_url = pick_best_url(img_urls, "jpeg") or pick_best_url(img_urls, "jpg")
                    if img_url:
                        ext = get_ext_from_url(img_url, ".jpg")
                        is_live = img.get('live_photo_type', 0) == 1
                        live_tag = '(实况)' if is_live else ''
                        ok = self._download(img_url, post_dir / f"{j+1:02d}{live_tag}{ext}", headers)
                        if ok:
                            stats["image"] += 1
                        else:
                            stats["fail"] += 1

                        # 实况图: 下载关联视频 (bit_rate 最高画质优先)
                        if is_live:
                            lv = img.get('video') or {}
                            best_live_url = pick_best_video_url(lv)
                            if best_live_url:
                                ok2 = self._download(best_live_url, post_dir / f"{j+1:02d}{live_tag}.mp4", headers)
                                if ok2:
                                    stats["video"] += 1
                                else:
                                    stats["fail"] += 1

            tracker[aweme_id] = {
                "desc": desc, "folder": folder_name,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

        # 保存进度 (即使被取消也保存)
        tracker_path.write_text(json.dumps(tracker, ensure_ascii=False, indent=2), encoding='utf-8')

        if self._cancelled:
            self.log_signal.emit("===== CANCELLED =====")
        else:
            self.log_signal.emit("===== DONE =====")
        self.log_signal.emit(f"视频:{stats['video']} 图片:{stats['image']} 音乐:{stats['music']} 跳过:{stats['skip']} 失败:{stats['fail']}")
        self.log_signal.emit(f"输出目录: {out_dir}")
        stats["cancelled"] = self._cancelled
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
            self.log_signal.emit(f"  ! 失败: {e}")
            if path.exists():
                path.unlink()
            return False


# ============ 样式 ============
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
QComboBox {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
    min-width: 90px;
}
QComboBox:hover {
    border: 1px solid #e94560;
}
QComboBox QAbstractItemView {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 4px;
    selection-background-color: #e94560;
    outline: none;
}
QComboBox QAbstractItemView::item {
    padding: 6px 10px;
}
QComboBox QAbstractItemView::item:hover {
    background-color: #0f3460;
}
"""


# ============ 主窗口 ============
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("抖音下载器")
        self.resize(900, 650)
        self.setMinimumSize(700, 500)
        self.setStyleSheet(STYLE)

        self.thread = None
        self.out_dir = OUTPUT_ROOT
        self.output_path = OUTPUT_ROOT

        self._build_ui()
        self._refresh_users()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # ---- 标题 ----
        title = QLabel("抖音用户主页下载")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #e94560; padding: 4px 0;")
        layout.addWidget(title)

        # ---- URL 输入行 ----
        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.douyin.com/user/MS4wLjAB...")
        self.url_input.returnPressed.connect(self._start_download)
        url_row.addWidget(self.url_input)

        self.dl_btn = QPushButton("下载")
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.clicked.connect(self._start_download)
        url_row.addWidget(self.dl_btn)

        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setObjectName("secondaryBtn")
        self.pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._pause_resume)
        url_row.addWidget(self.pause_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_download)
        url_row.addWidget(self.cancel_btn)
        layout.addLayout(url_row)

        # ---- 下载数量 + 保存路径 ----
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(10)

        ctrl_row.addWidget(QLabel("下载数量"))
        self.count_combo = QComboBox()
        self.count_combo.addItems(["全部下载", "10", "20", "50", "100"])
        self.count_combo.setEditable(True)
        self.count_combo.setCurrentIndex(0)  # 默认"全部下载"
        self.count_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        ctrl_row.addWidget(self.count_combo)

        ctrl_row.addSpacing(20)

        ctrl_row.addWidget(QLabel("保存路径"))
        self.path_input = QLineEdit()
        self.path_input.setText(str(OUTPUT_ROOT))
        self.path_input.setPlaceholderText("下载保存目录...")
        ctrl_row.addWidget(self.path_input)

        self.browse_btn = QPushButton("浏览")
        self.browse_btn.setObjectName("secondaryBtn")
        self.browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_btn.clicked.connect(self._browse_path)
        ctrl_row.addWidget(self.browse_btn)

        layout.addLayout(ctrl_row)

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
        left_layout.addWidget(QLabel("日志"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("下载日志将显示在此...")
        left_layout.addWidget(self.log_view)
        splitter.addWidget(left)

        # 右侧: 用户列表
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("已下载"))
        self.user_list = QListWidget()
        self.user_list.currentItemChanged.connect(self._on_user_select)
        right_layout.addWidget(self.user_list)

        self.open_btn = QPushButton("打开目录")
        self.open_btn.setObjectName("secondaryBtn")
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.clicked.connect(self._open_folder)
        right_layout.addWidget(self.open_btn)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setObjectName("secondaryBtn")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh_users)
        right_layout.addWidget(self.refresh_btn)

        splitter.addWidget(right)
        splitter.setSizes([550, 300])
        layout.addWidget(splitter, 1)

        # ---- 状态栏 ----
        self.status = QLabel("检查签名服务: http://localhost:8765/health")
        self.status.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.status)

    # ============ 逻辑 ============

    def _start_download(self):
        """直接启动下载 (总数由 scroll_user 获取后更新 UI)"""
        url = self.url_input.text().strip()
        if not url:
            self._log("[ERROR] 请输入URL")
            return

        # Cookie 检查：无文件则弹窗输入，过期则弹窗更新
        cookie_file = Path(__file__).resolve().parent.parent / "data" / "Cookie.txt"
        from PyQt6.QtWidgets import QInputDialog

        while True:
            cookie_str = ""
            if cookie_file.exists():
                cookie_str = cookie_file.read_text(encoding='utf-8').strip()

            if cookie_str:
                from src.api import DouyinAPI
                api = DouyinAPI(cookie_string=cookie_str)
                if api.check_cookie():
                    break
                # 过期弹窗
                new_cookie, ok = QInputDialog.getMultiLineText(
                    self, "Cookie 已过期",
                    "Cookie 已被封或过期，请粘贴新的 Cookie 后点确定：\n(点取消则中止本次下载)",
                    ""
                )
                if ok and new_cookie.strip():
                    cookie_file.parent.mkdir(parents=True, exist_ok=True)
                    cookie_file.write_text(new_cookie.strip(), encoding='utf-8')
                    continue
                else:
                    self.status.setText("已取消 — Cookie 未更新")
                    return
            else:
                # 首次使用，弹窗输入
                new_cookie, ok = QInputDialog.getMultiLineText(
                    self, "首次使用",
                    "未找到 Cookie 文件，请粘贴抖音登录后的 Cookie：\n(点取消则中止本次下载)",
                    ""
                )
                if ok and new_cookie.strip():
                    cookie_file.parent.mkdir(parents=True, exist_ok=True)
                    cookie_file.write_text(new_cookie.strip(), encoding='utf-8')
                    continue
                else:
                    self.status.setText("已取消 — 未设置 Cookie")
                    return

        # 解析路径
        custom_out_dir = None
        path_text = self.path_input.text().strip()
        if path_text:
            custom_out_dir = Path(path_text)
            try:
                custom_out_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "路径错误", f"无法创建目录: {e}")
                return
        self.output_path = custom_out_dir or OUTPUT_ROOT

        # 捕获用户输入
        pending_count_text = self.count_combo.currentText().strip()

        self.dl_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("暂停")
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.log_view.clear()
        self._log("[>>] 开始下载...")
        self._log(f"[>>] 保存路径: {self.output_path}")

        self.thread = DownloadThread(url, pending_count_text=pending_count_text,
                                     custom_out_dir=custom_out_dir)
        self.thread.log_signal.connect(self._log)
        self.thread.progress_signal.connect(self._update_progress)
        self.thread.paused_signal.connect(self._on_paused)
        self.thread.finished_signal.connect(self._on_finished)
        self.thread.total_signal.connect(self._on_total_ready)
        self.thread.start()

    def _on_total_ready(self, real_total):
        """scroll_user 完成后更新下拉框显示真实总数"""
        presets = [f"全部下载({real_total}个)"]
        for n in [10, 20, 50, 100]:
            if n < real_total:
                presets.append(str(n))
        self.count_combo.clear()
        self.count_combo.addItems(presets)
        self.count_combo.setCurrentIndex(0)
        self.count_combo.setCurrentText(presets[0])

    def _browse_path(self):
        """打开目录选择对话框"""
        current = self.path_input.text().strip() or str(OUTPUT_ROOT)
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", current)
        if folder:
            self.path_input.setText(folder)
            self.output_path = Path(folder)
            self._refresh_users()

    def _pause_resume(self):
        if self.thread and self.thread.isRunning():
            self.thread.toggle_pause()

    def _cancel_download(self):
        if self.thread and self.thread.isRunning():
            self.cancel_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.thread.cancel()

    def _on_paused(self, paused):
        if paused:
            self.pause_btn.setText("继续")
        else:
            self.pause_btn.setText("暂停")

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
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("暂停")
        self.cancel_btn.setEnabled(False)
        self.count_combo.setCurrentIndex(0)  # 重置为"全部下载"
        if stats.get("video", 0) + stats.get("image", 0) > 0:
            self.progress.setValue(self.progress.maximum())
        self._refresh_users()
        if stats.get("cancelled"):
            self.status.setText("已取消。")
        else:
            self.status.setText(f"完成! 视频:{stats.get('video',0)} 图片:{stats.get('image',0)} 音乐:{stats.get('music',0)}")

    def _refresh_users(self):
        self.user_list.clear()
        if not self.output_path.exists():
            self.status.setText(f"目录不存在: {self.output_path}，下载后自动创建")
            return
        try:
            dirs = sorted(self.output_path.iterdir(), reverse=True)
        except Exception as e:
            self.status.setText(f"读取目录失败: {e}")
            return
        count = 0
        for d in dirs:
            if not d.is_dir():
                continue
            tracker = d / ".downloaded.json"
            posts = 0
            if tracker.exists():
                try:
                    posts = len(json.loads(tracker.read_text(encoding='utf-8')))
                except Exception:
                    pass
            files = sum(1 for _ in d.rglob("*") if _.is_file() and _.name != ".downloaded.json")
            item = QListWidgetItem(f"{d.name}  [{posts}个作品, {files}个文件]")
            item.setData(Qt.ItemDataRole.UserRole, str(d))
            self.user_list.addItem(item)
            count += 1
        self.status.setText(f"已刷新: {count}个用户文件夹")

    def _on_user_select(self, current, previous):
        pass

    def _open_folder(self):
        item = self.user_list.currentItem()
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and Path(path).exists():
                os.startfile(path)
        else:
            # 没选中用户时打开当前输出根目录
            if self.output_path.exists():
                os.startfile(str(self.output_path))
