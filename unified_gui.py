# -*- coding: utf-8 -*-
"""
抖净 DouClean — 统一界面

模式:
  1. 单视频下载 — 分享链接 → 下载视频/图集/实况
  2. 主页批量下载 — 用户主页 → 全部作品

用法:
    python unified_gui.py
"""

import sys, re, json, time, threading, subprocess, os
from pathlib import Path

# Windows 隐藏子进程窗口
CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

# 版本 & 反馈
VERSION = "1.0.0"
VERSION_URL = "https://gitee.com/Renxint/douyin-downloader/raw/master/version.json"
DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=140b22bf4f35c675bf36c7441a78871f4678762df788dd7079dd0f565f312ee9"


def load_font():
    """加载用户保存的字体设置"""
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
            f = QFont(data.get("family", ""))
            if data.get("size"): f.setPointSize(data["size"])
            return f
    except: pass
    return None


def save_font(font):
    """保存字体设置"""
    try:
        SETTINGS_FILE.write_text(
            json.dumps({"family": font.family(), "size": font.pointSize()}, ensure_ascii=False),
            encoding='utf-8'
        )
    except: pass

# PyInstaller 路径适配
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)  # _internal 目录
    EXE_DIR = Path(sys.executable).parent  # exe 所在目录
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Claude/
    EXE_DIR = Path(__file__).resolve().parent.parent  # douclean/

PROJECT_ROOT = BASE_DIR
PROJECT_DIR = BASE_DIR / "projects" / "douclean" if not getattr(sys, 'frozen', False) else BASE_DIR
sys.path.insert(0, str(BASE_DIR))

SETTINGS_FILE = EXE_DIR / "settings.json"

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QProgressBar, QLabel, QFileDialog,
    QStackedWidget, QComboBox, QListWidget, QListWidgetItem, QSplitter,
    QMessageBox, QInputDialog, QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTranslator, QLocale, QLibraryInfo
from PyQt6.QtGui import QPalette, QColor, QIcon, QFont

import requests

# ============================================================
# 共享配置
# ============================================================
# 只读资源（打包在 _internal 里）
BOOTSTRAP_JS = BASE_DIR / "sign-server" / "bootstrap.js"
# Node.js：优先用打包的，其次系统安装的
NODE_EXE = BASE_DIR / "node.exe"
NODE_CMD = str(NODE_EXE) if NODE_EXE.exists() else "node"
# 可写文件（放在 exe 旁边）
COOKIE_FILE = EXE_DIR / "data" / "Cookie.txt"
OUTPUT_BASE = EXE_DIR / "output"
OUTPUT_SINGLE = OUTPUT_BASE / "单视频"
OUTPUT_HOMEPAGE = OUTPUT_BASE / "主页下载"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36 "
    "SLBrowser/9.0.8.5161 SLBChan/111 SLBVPV/64-bit"
)


def clean_name(s, n=50):
    s = re.sub(r'[\\/:*?"<>|\x00-\x1F\x7F\n\r\t]', '', s or '')
    s = re.sub(r'[​-‏ - ﻿ -‏]', '', s)
    s = s.strip().rstrip('. ')
    return s[:n] or "untitled"


def pick_best_video_url(vdata):
    def _first(urls):
        for u in (urls or []):
            if u and ".mp3" not in u:
                return u
        return ""
    bit_rates = vdata.get("bit_rate") or []
    if bit_rates:
        best = max(bit_rates, key=lambda b: b.get("bit_rate", 0))
        return _first((best.get("play_addr") or {}).get("url_list") or [])
    return _first((vdata.get("download_addr") or {}).get("url_list") or []) or \
           _first((vdata.get("play_addr") or {}).get("url_list") or [])


def parse_sec_user_id(url):
    m = re.search(r'/user/(MS4wLjAB[A-Za-z0-9_\-]+)', url.strip())
    if m: return m.group(1)
    raise ValueError(f"无法提取sec_user_id: {url}")


def ensure_cookie(parent_widget) -> str:
    """确保 Cookie 存在，为空则弹窗输入"""
    while True:
        cookie_str = ""
        if COOKIE_FILE.exists():
            cookie_str = COOKIE_FILE.read_text(encoding='utf-8').strip()
        if cookie_str:
            return cookie_str  # 有就先用，下载时遇到 blocked 再提示
        # 首次使用：弹窗输入
        new, ok = QInputDialog.getMultiLineText(
            parent_widget, "首次使用",
            "请粘贴抖音登录后的 Cookie：\n(点取消则中止)",
            ""
        )
        if ok and new.strip():
            COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
            COOKIE_FILE.write_text(new.strip(), encoding='utf-8')
            return new.strip()
        return ""


# ============================================================
# 单视频下载线程
# ============================================================
class SingleDownloadThread(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, raw_text, save_dir):
        super().__init__()
        self.raw_text = raw_text
        self.save_dir = Path(save_dir) if save_dir else OUTPUT_SINGLE

    def _dbg(self, msg):
        """写调试日志到文件"""
        try:
            log = EXE_DIR / "_debug.log"
            with open(log, 'a', encoding='utf-8') as f:
                f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
        except: pass

    def run(self):
        try:
            self._dbg("run start")
            self.log.emit("[>>] 解析链接...")
            self._dbg(f"resolve: {self.raw_text[:80]}")
            aweme_id = self._resolve(self.raw_text)
            self._dbg(f"aweme_id: {aweme_id}")
            self.log.emit(f"[OK] 视频ID: {aweme_id}")

            self._dbg("loading cookie")
            cookie = COOKIE_FILE.read_text(encoding='utf-8').strip() if COOKIE_FILE.exists() else ""
            self._dbg(f"cookie: {len(cookie)} chars, file exists: {COOKIE_FILE.exists()}")

            self.log.emit("[>>] 获取数据 (启动浏览器 ~15s)...")
            self._dbg(f"fetch: NODE={NODE_CMD}, JS={BOOTSTRAP_JS}, cwd={BOOTSTRAP_JS.parent}")
            aweme = self._fetch(aweme_id, cookie)
            self._dbg("fetch done")

            desc = aweme.get("desc", "") or aweme_id
            author = aweme.get("author", {}).get("nickname", "")
            self._dbg(f"author={author}")
            self.log.emit(f"  作者: {author}")
            self.log.emit(f"  描述: {desc[:60]}")

            self._dbg("download_aweme start")
            self._download_aweme(aweme)
            self._dbg("download_aweme done")
        except Exception as e:
            import traceback
            self._dbg(f"CRASH: {e}\n{traceback.format_exc()}")
            self.log.emit(f"[ERROR] {e}")
            self.finished.emit(False, str(e))

    def _resolve(self, raw):
        for pat in [r'https?://v\.douyin\.com/[A-Za-z0-9_\-/]+',
                     r'https?://(?:www\.)?douyin\.com/(?:video|note)/(\d+)']:
            m = re.search(pat, raw)
            if m: url = m.group(0); break
        else: raise ValueError("未识别抖音链接")
        m = re.search(r'/(?:video|note)/(\d+)', url)
        if m: return m.group(1)
        if 'v.douyin.com' in url:
            s = requests.Session(); s.headers.update({"User-Agent": UA})
            r = s.get(url, allow_redirects=True, timeout=15, stream=True); r.close()
            m = re.search(r'/(?:video|note)/(\d+)', r.url)
            if m: return m.group(1)
        raise ValueError(f"无法解析: {url}")

    def _fetch(self, aweme_id, cookie):
        # 用固定输出文件避免管道死锁
        self.save_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.save_dir / "_bootstrap.json"
        err_file = self.save_dir / "_bootstrap_err.log"
        try:
            with open(log_file, 'w', encoding='utf-8') as out:
                subprocess.run(
                    [NODE_CMD, str(BOOTSTRAP_JS), aweme_id, cookie],
                    stdout=out, stderr=subprocess.DEVNULL,
                    timeout=120, cwd=str(BOOTSTRAP_JS.parent),
                    creationflags=CREATE_NO_WINDOW,
                )
            raw_text = log_file.read_text(encoding='utf-8')
            if not raw_text.strip():
                raise RuntimeError("bootstrap 输出为空")
            data = json.loads(raw_text)
            if '_error' in data:
                raise RuntimeError(data['_error'])
            return data.get('aweme_detail', {})
        except subprocess.TimeoutExpired:
            raise RuntimeError("获取视频数据超时(120s)")
        finally:
            try: log_file.unlink()
            except: pass

    def _download_aweme(self, aweme):
        desc = aweme.get("desc", "") or aweme.get("aweme_id", "untitled")
        author = aweme.get("author", {}).get("nickname", "")
        video = aweme.get("video")
        images = aweme.get("images") or []

        safe_a = clean_name(author, 20); safe_d = clean_name(desc, 40)
        post_dir = self.save_dir / f"{safe_a}（{safe_d}）"
        post_dir.mkdir(parents=True, exist_ok=True)

        stats = {"v": 0, "i": 0, "f": 0}

        if video:
            url = pick_best_video_url(video)
            if url:
                if self._dl(url, post_dir / "video.mp4"): stats["v"] += 1
                else: stats["f"] += 1

        if images:
            for j, img in enumerate(images):
                urls = img.get("url_list", [])
                img_url = next((u for u in urls if 'jpeg' in u.lower() or 'jpg' in u.lower()), urls[0] if urls else "")
                if not img_url: continue
                is_live = img.get('live_photo_type', 0) == 1
                tag = '_实况' if is_live else ''
                if self._dl(img_url, post_dir / f"{j+1:02d}{tag}.jpg"): stats["i"] += 1
                else: stats["f"] += 1
                if is_live:
                    lv = img.get('video') or {}
                    live_url = pick_best_video_url(lv)
                    if live_url:
                        if self._dl(live_url, post_dir / f"{j+1:02d}{tag}.mp4"): stats["v"] += 1
                        else: stats["f"] += 1

        (post_dir / "desc.txt").write_text(desc, encoding='utf-8')
        self.log.emit(f"===== 视频:{stats['v']} 图片:{stats['i']} 失败:{stats['f']} =====")
        self.finished.emit(True, f"完成! {author}")

    def _dl(self, url, path):
        if path.exists():
            self.log.emit(f"  [SKIP] {path.name}")
            self.progress.emit(100)
            return True
        headers = {"User-Agent": UA, "Referer": "https://www.douyin.com/"}
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=120)
            r.raise_for_status()
            total = int(r.headers.get('content-length', 0))
            dl = 0
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk); dl += len(chunk)
                    if total: self.progress.emit(dl * 100 // total)
            self.log.emit(f"  [OK] {path.name} ({dl/1024/1024:.1f}MB)")
            self.progress.emit(100)
            return True
        except Exception as e:
            self.log.emit(f"  [FAIL] {e}")
            if path.exists(): path.unlink()
            return False


# ============================================================
# 主页批量下载线程 (复用现有逻辑)
# ============================================================
class HomepageDownloadThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal(dict)
    paused_signal = pyqtSignal(bool)
    total_signal = pyqtSignal(int)

    def __init__(self, url, pending_count_text="全部下载", custom_out_dir=None):
        super().__init__()
        self.url = url
        self.pending_count_text = pending_count_text
        self.custom_out_dir = custom_out_dir or OUTPUT_HOMEPAGE
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancelled = False

    def pause(self): self._pause_event.clear(); self.paused_signal.emit(True); self.log_signal.emit("[PAUSED]")
    def resume(self): self._pause_event.set(); self.paused_signal.emit(False); self.log_signal.emit("[RESUMED]")
    def toggle_pause(self): self.resume() if not self._pause_event.is_set() else self.pause()
    def cancel(self): self._cancelled = True; self._pause_event.set()
    def _check_cancel(self): return self._cancelled
    def _wait(self): self._pause_event.wait()

    def run(self):
        from src.api import DouyinAPI
        from src.downloader import pick_best_video_url as pbvu

        url = self.url.strip()
        try: sec_id = parse_sec_user_id(url)
        except Exception as e:
            self.log_signal.emit(f"[ERROR] {e}")
            self.finished_signal.emit({"video":0,"image":0,"music":0,"skip":0,"fail":0,"cancelled":True})
            return

        self.log_signal.emit(f"[OK] 用户: {sec_id[:24]}...")

        cookie_str = COOKIE_FILE.read_text(encoding='utf-8').strip() if COOKIE_FILE.exists() else ""
        api = DouyinAPI(cookie_string=cookie_str)
        profile = api.get_user_profile(sec_id)
        self.log_signal.emit("[>>] 获取作品列表...")
        all_posts, seen_ids, cursor, author_name = [], set(), 0, profile.get("nickname", "")

        for page in range(1, 50):
            if self._check_cancel():
                self.finished_signal.emit({"video":0,"image":0,"music":0,"skip":0,"fail":0,"cancelled":True})
                return
            self._wait()
            data = api.get_user_posts(sec_id, max_cursor=cursor, count=18)
            aweme_list = data.get("aweme_list", [])
            if not aweme_list: break
            new = sum(1 for a in aweme_list if a["aweme_id"] not in seen_ids)
            for a in aweme_list:
                if a["aweme_id"] not in seen_ids:
                    seen_ids.add(a["aweme_id"]); all_posts.append(a)
            if not author_name and aweme_list:
                author_name = aweme_list[0].get("author", {}).get("nickname", "")
            has_more = data.get("has_more", 0); cursor = data.get("max_cursor", 0)
            self.log_signal.emit(f"[翻页] P{page}: +{new} 累计{len(all_posts)} has_more={has_more}")
            if not has_more: break
            time.sleep(1.5)

        real_total = len(all_posts)
        self.total_signal.emit(real_total)

        try: max_count = int(self.pending_count_text)
        except: max_count = None
        if max_count and max_count > real_total: max_count = real_total
        if max_count: all_posts = all_posts[:max_count]

        total = len(all_posts)
        self.log_signal.emit(f"[OK] {real_total}个作品, 下载{total}个 | 作者: {author_name}")

        safe_author = clean_name(author_name, 20) or sec_id[:8]
        out_dir = Path(self.custom_out_dir) / safe_author
        out_dir.mkdir(parents=True, exist_ok=True)

        # 保存主页信息
        d_date = time.strftime("%Y-%m-%d %H:%M:%S")
        gm = {0:"未设置",1:"男",2:"女"}
        gender = gm.get(profile.get("gender",0), str(profile.get("gender","")))
        loc = " ".join(filter(None,[profile.get("country",""),profile.get("province",""),profile.get("city",""),profile.get("district","")]))
        info = [
            f"# {author_name}", "",
            f"## 基本信息", "",
            f"- 抖音号: {profile.get('unique_id','N/A')}",
            f"- UID: {profile.get('uid','N/A')}",
            f"- 性别: {gender}", f"- 年龄: {profile.get('age','N/A')}",
            f"- 地区: {loc or 'N/A'}", f"- 学校: {profile.get('school','N/A')}",
            f"- 简介: {profile.get('desc','N/A')}",
            f"- 认证: {profile.get('custom_verify','') or profile.get('enterprise_verify_reason','') or '无'}",
            f"", f"## 数据统计", "",
            f"- 作品数: {profile.get('aweme_count','N/A')}",
            f"- 粉丝数: {profile.get('follower_count','N/A')}",
            f"- 关注数: {profile.get('following_count','N/A')}",
            f"- 获赞数: {profile.get('favoriting_count','N/A')}",
            f"- 被赞数: {profile.get('total_favorited','N/A')}",
            f"", f"## 下载信息", "",
            f"- 主页链接: {self.url.strip()}",
            f"- 下载日期: {d_date}",
            f"- 头像: {profile.get('avatar_url','N/A')}", "",
        ]
        (out_dir / "主页信息.md").write_text("\n".join(info), encoding='utf-8')

        tracker = {}
        tp = out_dir / ".downloaded.json"
        if tp.exists():
            try: tracker = json.loads(tp.read_text(encoding='utf-8'))
            except: pass

        headers = {"User-Agent": UA, "Referer": "https://www.douyin.com/"}
        stats = {"video":0,"image":0,"music":0,"skip":0,"fail":0}

        for i, post in enumerate(all_posts):
            if self._check_cancel(): break
            self._wait()
            aweme_id = post.get("aweme_id","")
            desc = clean_name(post.get("desc","")) or aweme_id
            folder = f"{i+1:03d}_{desc}"
            post_dir = out_dir / folder
            self.progress_signal.emit(i+1, total)

            if aweme_id in tracker:
                stats["skip"] += 1; continue

            post_dir.mkdir(parents=True, exist_ok=True)
            self.log_signal.emit(f"[{i+1}/{total}] {desc[:40]}")

            (post_dir / "desc.md").write_text(post.get("desc",""), encoding='utf-8')
            has_v = bool(post.get("video")); has_i = bool(post.get("images"))
            has_rv = False

            if has_v:
                best = pick_best_video_url(post["video"])
                if best:
                    has_rv = True
                    if self._dl(best, post_dir/"video.mp4", headers): stats["video"] += 1
                    else: stats["fail"] += 1
            if not has_rv:
                music = post.get("music") or {}
                mp = music.get("play_url")
                mp_urls = mp.get("url_list") if isinstance(mp, dict) else ([mp] if isinstance(mp, str) and mp else [])
                if mp_urls:
                    if self._dl(mp_urls[0], post_dir/"music.mp3", headers): stats["music"] += 1
                    else: stats["fail"] += 1
            if has_i:
                for j, img in enumerate(post["images"]):
                    if self._check_cancel(): break
                    self._wait()
                    urls = img.get("url_list",[])
                    img_url = next((u for u in urls if 'jpeg' in u.lower() or 'jpg' in u.lower()), urls[0] if urls else "")
                    if not img_url: continue
                    ext = ".jpg"
                    is_live = img.get("live_photo_type",0)==1
                    tag = '_实况' if is_live else ''
                    if self._dl(img_url, post_dir/f"{j+1:02d}{tag}{ext}", headers): stats["image"] += 1
                    else: stats["fail"] += 1
                    if is_live:
                        lv = img.get('video') or {}
                        live_url = pick_best_video_url(lv)
                        if live_url:
                            if self._dl(live_url, post_dir/f"{j+1:02d}{tag}.mp4", headers): stats["video"] += 1
                            else: stats["fail"] += 1

            tracker[aweme_id] = {"desc": desc, "folder": folder, "time": time.strftime("%Y-%m-%d %H:%M:%S")}

        tp.write_text(json.dumps(tracker, ensure_ascii=False, indent=2), encoding='utf-8')

        self.log_signal.emit(f"===== DONE =====")
        self.log_signal.emit(f"视频:{stats['video']} 图片:{stats['image']} 音乐:{stats['music']} 跳过:{stats['skip']} 失败:{stats['fail']}")
        stats["cancelled"] = self._cancelled
        self.finished_signal.emit(stats)

    def _dl(self, url, path, headers):
        if path.exists(): return True
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            r.raise_for_status()
            with open(path, 'wb') as f:
                for chunk in r.iter_content(8192): f.write(chunk)
            return True
        except:
            if path.exists(): path.unlink()
            return False


# ============================================================
# 样式
# ============================================================
STYLE = """
QMainWindow, QWidget { background-color: #1a1a2e; color: #e0e0e0; }
QLineEdit {
    background-color: #16213e; color: #e0e0e0;
    border: 1px solid #0f3460; border-radius: 6px;
    padding: 8px 12px; font-size: 14px;
}
QLineEdit:focus { border: 1px solid #e94560; }
QPushButton {
    background-color: #e94560; color: white;
    border: none; border-radius: 6px; padding: 8px 20px;
    font-size: 14px; font-weight: bold;
}
QPushButton:hover { background-color: #ff6b81; }
QPushButton#secondaryBtn { background-color: #0f3460; }
QPushButton#secondaryBtn:hover { background-color: #1a4a7a; }
QPushButton#modeBtn {
    background-color: #16213e; color: #e0e0e0;
    border: 2px solid #e94560; border-radius: 12px;
    padding: 40px; font-size: 18px;
}
QPushButton#modeBtn:hover { background-color: #0f3460; border-color: #ff6b81; }
QPushButton:disabled { background-color: #333; color: #666; }
QTextEdit {
    background-color: #0d1117; color: #8b949e;
    border: 1px solid #0f3460; border-radius: 6px; padding: 6px;
    font-family: 'Consolas', 'Courier New', monospace; font-size: 12px;
}
QProgressBar {
    background-color: #16213e; border: 1px solid #0f3460;
    border-radius: 4px; height: 10px; text-align: center;
}
QProgressBar::chunk { background-color: #e94560; border-radius: 3px; }
QLabel { color: #8b949e; font-size: 13px; }
QComboBox {
    background-color: #16213e; color: #e0e0e0;
    border: 1px solid #0f3460; border-radius: 6px;
    padding: 6px 12px; font-size: 13px; min-width: 90px;
}
QComboBox:hover { border: 1px solid #e94560; }
QComboBox QAbstractItemView {
    background-color: #16213e; color: #e0e0e0;
    border: 1px solid #0f3460; selection-background-color: #e94560;
}
QListWidget {
    background-color: #16213e; border: 1px solid #0f3460;
    border-radius: 6px; padding: 4px; font-size: 13px; outline: none;
}
QListWidget::item:selected { background-color: #e94560; }
QListWidget::item:hover { background-color: #0f3460; }
QListWidget::item { padding: 6px 8px; border-radius: 4px; }
QSplitter::handle { background-color: #0f3460; width: 1px; }
"""


# ============================================================
# 页面1: 模式选择
# ============================================================
class ModePage(QWidget):
    """首页：选择单视频 或 主页批量"""
    single_clicked = pyqtSignal()
    homepage_clicked = pyqtSignal()
    font_changed = pyqtSignal(QFont)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(30)

        title = QLabel("抖净 DouClean")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #e94560;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("选择下载模式")
        sub.setStyleSheet("font-size: 14px; color: #8b949e;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(40)
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.single_btn = QPushButton("📱\n单视频下载\n\n粘贴分享链接\n下载单个视频/图集")
        self.single_btn.setObjectName("modeBtn")
        self.single_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.single_btn.clicked.connect(self.single_clicked)
        self.single_btn.setMinimumSize(280, 200)
        btn_layout.addWidget(self.single_btn)

        self.homepage_btn = QPushButton("👤\n主页批量下载\n\n粘贴用户主页链接\n下载全部作品")
        self.homepage_btn.setObjectName("modeBtn")
        self.homepage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.homepage_btn.clicked.connect(self.homepage_clicked)
        self.homepage_btn.setMinimumSize(280, 200)
        btn_layout.addWidget(self.homepage_btn)

        layout.addLayout(btn_layout)

        # 反馈 + 字体
        bottom_layout = QHBoxLayout()
        bottom_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bottom_layout.setSpacing(12)
        self.font_btn = QPushButton("字体设置")
        self.font_btn.setObjectName("secondaryBtn")
        self.font_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.font_btn.clicked.connect(self._choose_font)
        self.font_btn.setFixedWidth(120)
        bottom_layout.addWidget(self.font_btn)
        self.feedback_btn = QPushButton("反馈建议")
        self.feedback_btn.setObjectName("secondaryBtn")
        self.feedback_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.feedback_btn.clicked.connect(self._send_feedback)
        self.feedback_btn.setFixedWidth(120)
        bottom_layout.addWidget(self.feedback_btn)
        layout.addLayout(bottom_layout)

        status = QLabel(f"Cookie 自动管理 | 过期弹窗更新 | v{VERSION}")
        status.setStyleSheet("color: #555; font-size: 11px;")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(status)

    def _choose_font(self):
        from PyQt6.QtWidgets import QDialog, QFontComboBox, QSpinBox, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("字体设置")
        dlg.resize(400, 150)
        layout = QVBoxLayout(dlg)

        # 字体选择
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("字体:"))
        combo = QFontComboBox()
        combo.setEditable(False)
        row1.addWidget(combo, 1)
        layout.addLayout(row1)

        # 字号选择
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("字号:"))
        spin = QSpinBox()
        spin.setRange(8, 48)
        spin.setValue(10)
        row2.addWidget(spin)
        row2.addStretch()
        layout.addLayout(row2)

        # 预览
        preview = QLabel("预览效果 ABC 中文")
        preview.setMinimumHeight(40)
        preview.setStyleSheet("border: 1px solid #0f3460; border-radius: 4px; padding: 8px;")
        layout.addWidget(preview)

        # 当前设置
        current = load_font()
        if current:
            combo.setCurrentFont(current)
            spin.setValue(current.pointSize())
        else:
            combo.setCurrentFont(self.font())
            spin.setValue(self.font().pointSize())

        def on_change():
            f = combo.currentFont()
            f.setPointSize(spin.value())
            preview.setFont(f)

        combo.currentFontChanged.connect(on_change)
        spin.valueChanged.connect(on_change)
        on_change()

        # 按钮
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            font = combo.currentFont()
            font.setPointSize(spin.value())
            save_font(font)
            self.font_changed.emit(font)

    def _send_feedback(self):
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        text, ok = QInputDialog.getMultiLineText(
            self, "反馈建议",
            "请描述你遇到的问题或建议（至少包含'反馈'二字）：\n(反馈将发送到开发者钉钉)",
            ""
        )
        if not ok or not text.strip():
            return
        try:
            import requests as req
            import platform
            info = f"Win{platform.release()} | v{VERSION}"
            payload = {
                "msgtype": "text",
                "text": {"content": f"[抖净 DouClean 反馈]\n系统: {info}\n内容:\n{text.strip()}"}
            }
            r = req.post(DINGTALK_WEBHOOK, json=payload, timeout=10)
            if r.json().get("errcode") == 0:
                QMessageBox.information(self, "发送成功", "感谢反馈!")
            else:
                QMessageBox.warning(self, "发送失败", r.text[:200])
        except Exception as e:
            QMessageBox.warning(self, "发送失败", str(e))


# ============================================================
# 页面2: 单视频下载
# ============================================================
class SinglePage(QWidget):
    back_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.thread = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # 顶栏
        top = QHBoxLayout()
        back = QPushButton("← 返回")
        back.setObjectName("secondaryBtn")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_clicked)
        back.setFixedWidth(80)
        top.addWidget(back)

        title = QLabel("单视频下载")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #e94560;")
        top.addWidget(title)
        top.addStretch()
        layout.addLayout(top)

        # URL
        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴分享链接或视频URL... 支持视频/图集/实况")
        self.url_input.returnPressed.connect(self._start)
        url_row.addWidget(self.url_input)
        self.dl_btn = QPushButton("下载")
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.clicked.connect(self._start)
        url_row.addWidget(self.dl_btn)
        layout.addLayout(url_row)

        # 路径
        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        path_row.addWidget(QLabel("保存路径"))
        self.path_input = QLineEdit()
        self.path_input.setText(str(OUTPUT_SINGLE))
        path_row.addWidget(self.path_input)
        browse = QPushButton("浏览")
        browse.setObjectName("secondaryBtn")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.clicked.connect(lambda: self._browse(self.path_input))
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        # 进度
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # 主体: 日志 + 已下载列表
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0,0,0,0)
        ll.addWidget(QLabel("日志"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        ll.addWidget(self.log_view)
        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0,0,0,0)
        rl.addWidget(QLabel("已下载"))
        self.downloaded_list = QListWidget()
        rl.addWidget(self.downloaded_list)
        open_btn = QPushButton("打开目录")
        open_btn.setObjectName("secondaryBtn")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._open_folder)
        rl.addWidget(open_btn)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondaryBtn")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_downloaded)
        rl.addWidget(refresh_btn)
        splitter.addWidget(right)
        splitter.setSizes([500, 250])
        layout.addWidget(splitter, 1)

        # 状态
        self.status = QLabel("就绪")
        self.status.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.status)

        self._refresh_downloaded()

    def _browse(self, input_widget):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", input_widget.text())
        if folder: input_widget.setText(folder)

    def _refresh_downloaded(self):
        self.downloaded_list.clear()
        out = Path(self.path_input.text().strip()) if self.path_input.text().strip() else OUTPUT_SINGLE
        if not out.exists(): return
        for d in sorted(out.iterdir(), reverse=True):
            if not d.is_dir(): continue
            files = sum(1 for _ in d.rglob("*") if _.is_file())
            item = QListWidgetItem(f"{d.name}  [{files}文件]")
            item.setData(Qt.ItemDataRole.UserRole, str(d))
            self.downloaded_list.addItem(item)

    def _open_folder(self):
        item = self.downloaded_list.currentItem()
        out = Path(self.path_input.text().strip()) if self.path_input.text().strip() else OUTPUT_SINGLE
        if item:
            p = item.data(Qt.ItemDataRole.UserRole)
            if p and Path(p).exists(): os.startfile(p)
        elif out.exists(): os.startfile(str(out))

    def _start(self):
        text = self.url_input.text().strip()
        if not text: return

        cookie = ensure_cookie(self)
        if not cookie:
            self.status.setText("已取消 - Cookie 未设置")
            return

        save_dir = self.path_input.text().strip() or str(OUTPUT_SINGLE)
        self.dl_btn.setEnabled(False)
        self.progress.setVisible(True); self.progress.setValue(0)
        self.log_view.clear()

        self.thread = SingleDownloadThread(text, save_dir)
        self.thread.log.connect(self._log)
        self.thread.progress.connect(self.progress.setValue)
        self.thread.finished.connect(self._done)
        self.thread.start()

    def _log(self, msg):
        self.log_view.append(msg)
        sb = self.log_view.verticalScrollBar(); sb.setValue(sb.maximum())

    def _done(self, ok, msg):
        self.dl_btn.setEnabled(True)
        self.status.setText(msg)
        if ok: self.progress.setValue(100)
        self._refresh_downloaded()


# ============================================================
# 页面3: 主页批量下载
# ============================================================
class HomepagePage(QWidget):
    back_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.thread = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # 顶栏
        top = QHBoxLayout()
        back = QPushButton("← 返回")
        back.setObjectName("secondaryBtn")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_clicked)
        back.setFixedWidth(80)
        top.addWidget(back)

        title = QLabel("主页批量下载")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #e94560;")
        top.addWidget(title)
        top.addStretch()
        layout.addLayout(top)

        # URL 行
        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.douyin.com/user/MS4wLjAB...")
        self.url_input.returnPressed.connect(self._start)
        url_row.addWidget(self.url_input)
        self.dl_btn = QPushButton("下载")
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.clicked.connect(self._start)
        url_row.addWidget(self.dl_btn)
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setObjectName("secondaryBtn")
        self.pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._pause)
        url_row.addWidget(self.pause_btn)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        url_row.addWidget(self.cancel_btn)
        layout.addLayout(url_row)

        # 数量 + 路径
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)
        ctrl.addWidget(QLabel("数量"))
        self.count_combo = QComboBox()
        self.count_combo.addItems(["全部下载", "10", "20", "50", "100"])
        self.count_combo.setEditable(True)
        ctrl.addWidget(self.count_combo)
        ctrl.addSpacing(20)
        ctrl.addWidget(QLabel("保存路径"))
        self.path_input = QLineEdit()
        self.path_input.setText(str(OUTPUT_HOMEPAGE))
        ctrl.addWidget(self.path_input)
        browse = QPushButton("浏览")
        browse.setObjectName("secondaryBtn")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.clicked.connect(lambda: self._browse(self.path_input))
        ctrl.addWidget(browse)
        layout.addLayout(ctrl)

        # 进度
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # 主体
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0,0,0,0)
        ll.addWidget(QLabel("日志"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        ll.addWidget(self.log_view)
        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0,0,0,0)
        rl.addWidget(QLabel("已下载"))
        self.user_list = QListWidget()
        rl.addWidget(self.user_list)
        open_btn = QPushButton("打开目录")
        open_btn.setObjectName("secondaryBtn")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._open_folder)
        rl.addWidget(open_btn)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondaryBtn")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_users)
        rl.addWidget(refresh_btn)
        splitter.addWidget(right)
        splitter.setSizes([550, 300])
        layout.addWidget(splitter, 1)

        # 状态
        self.status = QLabel("就绪")
        self.status.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.status)

        self._refresh_users()

    def _browse(self, input_widget):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", input_widget.text())
        if folder: input_widget.setText(folder)

    def _start(self):
        url = self.url_input.text().strip()
        if not url: return

        # Cookie 循环：无效则弹窗更新
        while True:
            cookie = ensure_cookie(self)
            if not cookie:
                self.status.setText("已取消 - Cookie 未设置")
                return

            # 检查 Cookie 是否被主页 API 接受
            from src.api import DouyinAPI
            api = DouyinAPI(cookie_string=cookie)
            test = api.get_user_profile("MS4wLjABAAAAnsZ-gU2aYmYUiMq2a1dTwH0Bst9fK3s9mEpQnvVsosI")
            if test.get("nickname"):
                break  # Cookie 有效

            # 弹窗更新
            from PyQt6.QtWidgets import QInputDialog
            new, ok = QInputDialog.getMultiLineText(
                self, "Cookie 已过期",
                "主页下载的 Cookie 已被封或过期\n请粘贴新的 Cookie（浏览器重新登录 douyin.com）：\n(点取消则中止)",
                ""
            )
            if ok and new.strip():
                COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
                COOKIE_FILE.write_text(new.strip(), encoding='utf-8')
                continue
            else:
                self.status.setText("已取消 - Cookie 未更新")
                return

        path_text = self.path_input.text().strip()
        custom_dir = Path(path_text) if path_text else OUTPUT_HOMEPAGE
        try: custom_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "路径错误", str(e)); return

        self.dl_btn.setEnabled(False)
        self.pause_btn.setEnabled(True); self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True); self.progress.setValue(0)
        self.log_view.clear()

        self.thread = HomepageDownloadThread(url, self.count_combo.currentText().strip(), str(custom_dir))
        self.thread.log_signal.connect(self._log)
        self.thread.progress_signal.connect(lambda c,t: (self.progress.setMaximum(t), self.progress.setValue(c)))
        self.thread.paused_signal.connect(lambda p: self.pause_btn.setText("继续" if p else "暂停"))
        self.thread.finished_signal.connect(self._done)
        self.thread.total_signal.connect(lambda t: (self.count_combo.setCurrentText(f"全部下载({t}个)")))
        self.thread.start()

    def _pause(self):
        if self.thread and self.thread.isRunning(): self.thread.toggle_pause()

    def _cancel(self):
        if self.thread and self.thread.isRunning():
            self.cancel_btn.setEnabled(False); self.pause_btn.setEnabled(False)
            self.thread.cancel()

    def _log(self, msg):
        self.log_view.append(msg)
        sb = self.log_view.verticalScrollBar(); sb.setValue(sb.maximum())

    def _done(self, stats):
        self.dl_btn.setEnabled(True)
        self.pause_btn.setEnabled(False); self.cancel_btn.setEnabled(False)
        self.pause_btn.setText("暂停")
        if stats.get("cancelled"):
            self.status.setText("已取消")
        else:
            self.status.setText(f"视频:{stats.get('video',0)} 图片:{stats.get('image',0)} 跳过:{stats.get('skip',0)}")
        if stats.get('video',0)+stats.get('image',0)>0: self.progress.setValue(self.progress.maximum())
        self._refresh_users()

    def _refresh_users(self):
        self.user_list.clear()
        out = OUTPUT_HOMEPAGE
        if not out.exists(): return
        for d in sorted(out.iterdir(), reverse=True):
            if not d.is_dir(): continue
            tracker = d / ".downloaded.json"
            posts = 0
            if tracker.exists():
                try: posts = len(json.loads(tracker.read_text(encoding='utf-8')))
                except: pass
            files = sum(1 for _ in d.rglob("*") if _.is_file() and _.name != ".downloaded.json")
            item = QListWidgetItem(f"{d.name}  [{posts}作品, {files}文件]")
            item.setData(Qt.ItemDataRole.UserRole, str(d))
            self.user_list.addItem(item)

    def _open_folder(self):
        item = self.user_list.currentItem()
        if item:
            p = item.data(Qt.ItemDataRole.UserRole)
            if p and Path(p).exists(): os.startfile(p)
        elif OUTPUT_HOMEPAGE.exists(): os.startfile(str(OUTPUT_HOMEPAGE))


# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("抖净 DouClean")
        self.resize(800, 620)
        self.setMinimumSize(600, 450)
        self.setStyleSheet(STYLE)

        # 任务栏/标题栏图标
        ico = BASE_DIR / "app.ico"
        if ico.exists():
            self.setWindowIcon(QIcon(str(ico)))

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.mode_page = ModePage()
        self.single_page = SinglePage()
        self.homepage_page = HomepagePage()

        self.stack.addWidget(self.mode_page)     # 0
        self.stack.addWidget(self.single_page)    # 1
        self.stack.addWidget(self.homepage_page)  # 2

        self.mode_page.single_clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.mode_page.homepage_clicked.connect(lambda: self.stack.setCurrentIndex(2))
        self.single_page.back_clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.homepage_page.back_clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.mode_page.font_changed.connect(self._apply_font)

        # 加载保存的字体
        saved = load_font()
        if saved:
            QApplication.instance().setFont(saved)

        self.stack.setCurrentIndex(0)

        # 后台检查版本更新
        threading.Thread(target=self._check_version, daemon=True).start()

    def _apply_font(self, font):
        QApplication.instance().setFont(font)

    def _check_version(self):
        try:
            r = requests.get(VERSION_URL, timeout=5)
            data = r.json()
            remote = data.get("version", "")
            if remote > VERSION:
                note = data.get("note", "")
                url = data.get("url", "")
                from PyQt6.QtWidgets import QMessageBox
                reply = QMessageBox.question(
                    self, "发现新版本",
                    f"当前版本: v{VERSION}\n最新版本: v{remote}\n更新内容: {note}\n\n是否下载新版本?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes and url:
                    import webbrowser
                    webbrowser.open(url)
        except:
            pass  # 网络不通，静默跳过


def main():
    app = QApplication(sys.argv)

    # 加载 Qt 中文翻译（qtbase 是基础组件如字体对话框，qt 是其他模块）
    trans_dir = Path(sys._MEIPASS if getattr(sys, 'frozen', False) else BASE_DIR) / "translations"
    sys_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for qm in ("qtbase_zh_CN", "qt_zh_CN"):
        t = QTranslator()
        local = trans_dir / f"{qm}.qm"
        if local.exists():
            t.load(str(local))
        else:
            t.load(qm, sys_dir)
        app.installTranslator(t)

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
