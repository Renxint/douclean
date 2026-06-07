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

# 线程安全锁（保护共享文件读写）
_file_lock = threading.Lock()


def safe_read(path: Path) -> str:
    """线程安全读文件"""
    with _file_lock:
        if path.exists():
            return path.read_text(encoding='utf-8').strip()
    return ""


def safe_write(path: Path, content: str):
    """线程安全写文件（先写临时文件再原子替换）"""
    with _file_lock:
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(content, encoding='utf-8')
        tmp.replace(path)


def safe_read_json(path: Path, default=None):
    """线程安全读 JSON"""
    try:
        raw = safe_read(path)
        return json.loads(raw) if raw else (default or {})
    except:
        return default or {}


def safe_write_json(path: Path, data: dict):
    """线程安全写 JSON"""
    safe_write(path, json.dumps(data, ensure_ascii=False, indent=2))

# 版本 & 反馈
from src.config import VERSION, VERSION_URL, DINGTALK_WEBHOOK, USER_AGENT, WEBID, VERIFY_FP, FP, UIFID
from src.utils import clean_name, pick_best_video_url, compare_versions, parse_sec_user_id, classify_url


def load_font():
    """加载用户保存的字体设置"""
    try:
        data = safe_read_json(SETTINGS_FILE)
        if data:
            f = QFont(data.get("family", ""))
            if data.get("size"): f.setPointSize(data["size"])
            return f
    except: pass
    return None


def save_font(font):
    """保存字体设置（合并写入，不覆盖其他设置）"""
    try:
        data = safe_read_json(SETTINGS_FILE)
        data["family"] = font.family()
        data["size"] = font.pointSize()
        safe_write_json(SETTINGS_FILE, data)
    except: pass


def choose_font_dialog(parent, current_font=None):
    """显示字体选择对话框，返回 (accepted, font)"""
    from PyQt6.QtWidgets import QDialog, QFontComboBox, QSpinBox, QLabel, QVBoxLayout, QHBoxLayout, QDialogButtonBox
    dlg = QDialog(parent)
    dlg.setWindowTitle("字体设置"); dlg.resize(400, 150)
    dlg.setStyleSheet("QDialog { background: #0A0A14; } QLabel { color: #F1F5F9; }")
    layout = QVBoxLayout(dlg)
    r1 = QHBoxLayout(); r1.addWidget(QLabel("字体:"))
    combo = QFontComboBox(); combo.setEditable(False); r1.addWidget(combo, 1); layout.addLayout(r1)
    r2 = QHBoxLayout(); r2.addWidget(QLabel("字号:"))
    spin = QSpinBox(); spin.setRange(8, 48); spin.setValue(10); r2.addWidget(spin); r2.addStretch(); layout.addLayout(r2)
    preview = QLabel("预览效果 ABC 中文"); preview.setMinimumHeight(40)
    preview.setStyleSheet("border: 1px solid #252550; border-radius: 8px; padding: 8px; background: #12122A;")
    layout.addWidget(preview)
    if current_font is None: current_font = parent.font()
    combo.setCurrentFont(current_font); spin.setValue(current_font.pointSize())
    def on_change():
        f = combo.currentFont(); f.setPointSize(spin.value()); preview.setFont(f)
    combo.currentFontChanged.connect(on_change); spin.valueChanged.connect(on_change); on_change()
    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); layout.addWidget(btns)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        font = combo.currentFont(); font.setPointSize(spin.value())
        return (True, font)
    return (False, None)


def load_setting(key, default=None):
    return safe_read_json(SETTINGS_FILE).get(key, default)


def save_setting(key, value):
    data = safe_read_json(SETTINGS_FILE)
    data[key] = value
    safe_write_json(SETTINGS_FILE, data)


def get_single_download_path():
    return load_setting("single_download_path", str(OUTPUT_SINGLE))


def get_homepage_download_path():
    return load_setting("homepage_download_path", str(OUTPUT_HOMEPAGE))


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
CRASH_LOG = EXE_DIR / "_crash.log"


from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QProgressBar, QLabel, QFileDialog,
    QStackedWidget, QComboBox, QListWidget, QListWidgetItem, QSplitter,
    QMessageBox, QInputDialog, QFrame, QMenu, QSystemTrayIcon, QScrollArea,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTranslator, QLocale, QLibraryInfo, QTimer
from PyQt6.QtGui import QPalette, QColor, QIcon, QFont, QAction

import requests


# ============================================================
# 全局：单实例 + 异常钩子
# ============================================================
import socket
_instance_port = 19998


_instance_socket = None  # 全局持有，MainWindow 用 QTimer 监听


def setup_single_instance():
    """单实例检测 + 已运行则通知旧窗口激活"""
    try:
        # 尝试绑定端口 → 首个实例
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', _instance_port))
        s.listen(1)
        s.setblocking(False)
        return s  # 返回 socket，进程持有端口
    except OSError:
        # 端口被占用 → 已有实例，通知它激活窗口
        try:
            c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            c.settimeout(1)
            c.connect(('127.0.0.1', _instance_port))
            c.sendall(b'show')
            c.close()
        except Exception:
            pass
        return None


def global_exception_handler(exc_type, exc_value, exc_tb):
    """全局未捕获异常 → 写日志"""
    import traceback
    tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        CRASH_LOG.write_text(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] CRASH\n{tb_str}\n",
            encoding='utf-8'
        )
    except: pass


def load_window_geometry():
    return safe_read_json(SETTINGS_FILE).get("geometry")


def save_window_geometry(geometry):
    data = safe_read_json(SETTINGS_FILE)
    data["geometry"] = geometry
    safe_write_json(SETTINGS_FILE, data)


def colored_log(msg):
    """给日志文本加颜色 HTML"""
    if msg.startswith("[ERROR]") or msg.startswith("[FAIL]"):
        return f'<span style="color:#EF4444">{msg}</span>'
    elif msg.startswith("[OK]") or msg.startswith("===== DONE"):
        return f'<span style="color:#22C55E">{msg}</span>'
    elif msg.startswith("[>>]") or msg.startswith("[翻页]"):
        return f'<span style="color:#94A3B8">{msg}</span>'
    elif msg.startswith("[WARN]"):
        return f'<span style="color:#F59E0B">{msg}</span>'
    return msg


sys.excepthook = global_exception_handler


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
QMainWindow, QWidget { background-color: #0A0A14; color: #F1F5F9; }
QLineEdit {
    background-color: #12122A; color: #F1F5F9;
    border: 1px solid #252550; border-radius: 8px;
    padding: 8px 12px; font-size: 14px;
}
QLineEdit:focus { border: 1px solid #E11D48; background: #161632; }
QLineEdit:disabled { background: #0E0E1E; color: #475569; border-color: #1A1A30; }
QPushButton {
    background-color: #E11D48; color: white;
    border: none; border-radius: 8px; padding: 8px 20px;
    font-size: 14px; font-weight: bold;
}
QPushButton:hover { background-color: #FF3566; }
QPushButton:pressed { background: #C0183D; }
QPushButton#secondaryBtn { background-color: #18183A; border: 1px solid #252550; }
QPushButton#secondaryBtn:hover { background-color: #1E1E48; }
QPushButton#secondaryBtn:pressed { background: #12122A; }
QPushButton#modeBtn {
    background-color: #12122A; color: #F1F5F9;
    border: 2px solid #252550; border-radius: 16px;
    padding: 32px; font-size: 16px; text-align: left;
}
QPushButton#modeBtn:hover { background-color: #18183A; border-color: #E11D48; }
QPushButton#modeBtn:pressed { background: #0E0E22; border-color: #C0183D; }
QPushButton#ghostBtn { background: transparent; color: #94A3B8; border: 1px solid transparent; font-weight: normal; }
QPushButton#ghostBtn:hover { background: #18183A; color: #F1F5F9; border-color: #252550; }
QPushButton:disabled { background: #1A1A2E; color: #475569; border-color: #1A1A2E; }
QTextEdit {
    background-color: #0B0B1A; color: #94A3B8;
    border: 1px solid #252550; border-radius: 8px; padding: 6px;
    font-family: 'Consolas', 'Courier New', monospace; font-size: 12px;
}
QProgressBar {
    background-color: #12122A; border: 1px solid #252550;
    border-radius: 4px; height: 8px; text-align: center;
}
QProgressBar::chunk { background-color: #E11D48; border-radius: 3px; }
QLabel { color: #94A3B8; font-size: 13px; }
QComboBox {
    background-color: #12122A; color: #F1F5F9;
    border: 1px solid #252550; border-radius: 8px;
    padding: 6px 12px; font-size: 13px; min-width: 90px;
}
QComboBox:hover { border: 1px solid #E11D48; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 6px solid #94A3B8; margin-right: 6px; }
QComboBox QAbstractItemView { background: #12122A; color: #F1F5F9; border: 1px solid #252550; selection-background: #E11D48; outline: none; padding: 4px; }
QListWidget {
    background-color: #12122A; border: 1px solid #252550;
    border-radius: 8px; padding: 4px; font-size: 13px; outline: none;
}
QListWidget::item { padding: 10px 12px; border-radius: 6px; margin: 1px 0; }
QListWidget::item:selected { background: #E11D48; color: #FFFFFF; }
QListWidget::item:hover { background: #18183A; }
QSplitter::handle { background-color: #1E1E48; width: 2px; }
QScrollBar:vertical { background: #0A0A14; width: 8px; border-radius: 4px; margin: 0; }
QScrollBar::handle:vertical { background: #334155; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #475569; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #0A0A14; height: 8px; }
QScrollBar::handle:horizontal { background: #334155; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #475569; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QMenu { background: #12122A; color: #F1F5F9; border: 1px solid #252550; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 8px 32px 8px 16px; border-radius: 4px; }
QMenu::item:selected { background: #E11D48; }
QToolTip { background: #1A1A3E; color: #F1F5F9; border: 1px solid #252550; border-radius: 6px; padding: 8px 12px; font-size: 12px; }
QMessageBox { background: #0A0A14; }
QMessageBox QLabel { color: #F1F5F9; font-size: 14px; }
QMessageBox QPushButton { min-width: 80px; padding: 8px 16px; }
QScrollArea { background: transparent; border: none; }
"""





def get_cookie_status() -> dict:
    if not COOKIE_FILE.exists():
        return {"ok": False, "length": 0, "mtime": None}
    try:
        cookie = COOKIE_FILE.read_text(encoding="utf-8").strip()
        mtime = COOKIE_FILE.stat().st_mtime
        return {
            "ok": bool(cookie) and "sessionid=" in cookie and "ttwid=" in cookie,
            "length": len(cookie),
            "mtime": mtime,
        }
    except:
        return {"ok": False, "length": 0, "mtime": None}


# ============================================================
# 页面1: 模式选择
class ModePage(QWidget):
    """首页：选择单视频 或 主页批量"""
    single_clicked = pyqtSignal()
    homepage_clicked = pyqtSignal()
    font_changed = pyqtSignal(QFont)
    cookie_updated = pyqtSignal()
    settings_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(30)

        # 标题行: DouClean + 版本徽章
        title_row = QHBoxLayout()
        title_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("DouClean")
        title.setStyleSheet("font-size: 32px; font-weight: 800; color: #F1F5F9;")
        title_row.addWidget(title)
        ver = QLabel(f"v{VERSION}")
        ver.setStyleSheet("font-size: 11px; color: #FFF; background: #E11D48; border-radius: 4px; padding: 2px 8px;")
        ver.setFixedHeight(20)
        title_row.addWidget(ver)
        manual_btn = QPushButton("使用手册")
        manual_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        manual_btn.setFixedSize(80, 24)
        manual_btn.setStyleSheet("font-size:11px; color:#94A3B8; background:transparent; border:1px solid #334155; border-radius:4px; padding:0 8px;")
        manual_btn.clicked.connect(self._show_manual)
        title_row.addWidget(manual_btn)
        layout.addLayout(title_row)

        sub = QLabel("抖净 · 抖音无水印下载工具")
        sub.setStyleSheet("font-size: 14px; color: #64748B;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedWidth(320)
        sep_layout = QHBoxLayout()
        sep_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sep_layout.addWidget(sep)
        layout.addLayout(sep_layout)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(40)
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 单视频卡片
        self.single_btn = QPushButton()
        self.single_btn.setObjectName("modeBtn")
        self.single_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.single_btn.clicked.connect(self.single_clicked)
        self.single_btn.setMinimumSize(260, 190)
        sl = QVBoxLayout(self.single_btn); sl.setContentsMargins(20,20,20,20); sl.setSpacing(8)
        si = QLabel("⬇"); si.setStyleSheet("font-size:24px;font-weight:800;color:#E11D48;background:#1A1030;border-radius:12px;min-width:44px;max-width:44px;min-height:44px;max-height:44px;"); si.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(si)
        st = QLabel("单视频下载"); st.setStyleSheet("font-size:16px;font-weight:700;color:#F1F5F9;")
        sl.addWidget(st)
        sd = QLabel("粘贴抖音分享链接\n下载视频 / 图集 / 实况照片"); sd.setStyleSheet("font-size:12px;color:#64748B;")
        sl.addWidget(sd); sl.addStretch()
        # shadow removed for stability
        btn_layout.addWidget(self.single_btn)

        # 主页卡片
        self.homepage_btn = QPushButton()
        self.homepage_btn.setObjectName("modeBtn")
        self.homepage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.homepage_btn.clicked.connect(self.homepage_clicked)
        self.homepage_btn.setMinimumSize(260, 190)
        hl = QVBoxLayout(self.homepage_btn); hl.setContentsMargins(20,20,20,20); hl.setSpacing(8)
        hi = QLabel("☰"); hi.setStyleSheet("font-size:24px;font-weight:800;color:#E11D48;background:#1A1030;border-radius:12px;min-width:44px;max-width:44px;min-height:44px;max-height:44px;"); hi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(hi)
        ht = QLabel("主页批量下载"); ht.setStyleSheet("font-size:16px;font-weight:700;color:#F1F5F9;")
        hl.addWidget(ht)
        hd = QLabel("粘贴用户主页链接\n下载全部公开作品"); hd.setStyleSheet("font-size:12px;color:#64748B;")
        hl.addWidget(hd); hl.addStretch()
        # shadow removed
        btn_layout.addWidget(self.homepage_btn)

        layout.addLayout(btn_layout)

        # 底部按钮
        bottom_layout = QHBoxLayout()
        bottom_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bottom_layout.setSpacing(12)
        self.settings_btn = QPushButton("设置")
        self.settings_btn.setObjectName("secondaryBtn")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(self.settings_clicked)
        self.settings_btn.setFixedWidth(110)
        bottom_layout.addWidget(self.settings_btn)
        self.feedback_btn = QPushButton("反馈建议")
        self.feedback_btn.setObjectName("secondaryBtn")
        self.feedback_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.feedback_btn.clicked.connect(self._send_feedback)
        self.feedback_btn.setFixedWidth(120)
        bottom_layout.addWidget(self.feedback_btn)
        layout.addLayout(bottom_layout)

        status = self._cookie_status = QLabel()
        status.setStyleSheet("color: #64748B; font-size: 11px; padding: 4px 0;")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cookie_status.mousePressEvent = lambda e: self._set_cookie()
        self.refresh_cookie_status()
        layout.addWidget(self._cookie_status)

    def _show_manual(self):
        QMessageBox.information(self, "使用手册",
            "📱 单视频下载\n"
            "  粘贴抖音分享链接（口令文本），下载视频/图集/实况照片\n\n"
            "👤 主页批量下载\n"
            "  粘贴用户主页链接，自动翻页下载全部公开作品\n\n"
            "🍪 Cookie 获取\n"
            "  1. 浏览器打开 douyin.com 扫码登录\n"
            "  2. F12 → Network → 搜作品标题关键词 → 点 post/ 请求\n"
            "  3. Request Headers → Cookie: 行 → 右键 Copy value\n"
            "  4. 回到抖净粘贴\n\n"
            "⌨️ 快捷键\n"
            "  Ctrl+H 回首页 | Ctrl+, 设置 | Ctrl+Q 退出 | Esc 托盘")

    def _choose_font(self):
        accepted, font = choose_font_dialog(self, load_font() or self.font())
        if accepted:
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

    def refresh_cookie_status(self):
        cs = get_cookie_status()
        if cs["ok"]:
            dot, txt = "#22C55E", "Cookie 已就绪"
        elif cs["length"] > 0:
            dot, txt = "#F59E0B", "Cookie 可能无效"
        else:
            dot, txt = "#EF4444", "Cookie 未设置"
        time_str = time.strftime("%m-%d %H:%M", time.localtime(cs["mtime"])) if cs["mtime"] else ""
        self._cookie_status.setText(f"● {txt} ({cs['length']}字符)  {time_str}    [点击更新]")
        self._cookie_status.setStyleSheet(f"color: {dot}; font-size: 11px; padding: 4px 0;")
        self._cookie_status.setCursor(Qt.CursorShape.PointingHandCursor)

    def _set_cookie(self, event=None):
        from PyQt6.QtWidgets import QInputDialog
        current = COOKIE_FILE.read_text(encoding="utf-8").strip() if COOKIE_FILE.exists() else ""
        new, ok = QInputDialog.getMultiLineText(self, "设置 Cookie", "请粘贴抖音登录后的 Cookie：", current)
        if ok and new.strip():
            COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
            COOKIE_FILE.write_text(new.strip(), encoding="utf-8")
            self.refresh_cookie_status()
            self.cookie_updated.emit()


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
        back = QPushButton("  < 返回")
        back.setObjectName("secondaryBtn")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_clicked)
        back.setFixedSize(90, 36)
        top.addWidget(back)

        title = QLabel("单视频下载")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #E11D48;")
        top.addWidget(title)
        top.addStretch()
        layout.addLayout(top)

        # URL
        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴分享链接或视频URL... 支持视频/图集/实况")
        self.url_input.setMinimumHeight(42)
        self.url_input.returnPressed.connect(self._start)
        url_row.addWidget(self.url_input)
        self.dl_btn = QPushButton("开始下载")
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.clicked.connect(self._start)
        self.dl_btn.setFixedHeight(42); self.dl_btn.setMinimumWidth(100)
        url_row.addWidget(self.dl_btn)
        layout.addLayout(url_row)

        # 路径
        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        path_row.addWidget(QLabel("保存到"))
        self.path_input = QLineEdit()
        self.path_input.setText(get_single_download_path())
        path_row.addWidget(self.path_input)
        browse = QPushButton("浏览...")
        browse.setObjectName("secondaryBtn")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.setFixedHeight(36)
        browse.clicked.connect(lambda: self._browse(self.path_input))
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        # 进度
        self.progress = QProgressBar()
        self.progress.setFixedHeight(8)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # 主体: 日志 + 已下载列表
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0,0,0,0)
        ll.addWidget(QLabel("下载日志"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        ll.addWidget(self.log_view)
        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0,0,0,0)
        rl.addWidget(QLabel("已下载"))
        self.downloaded_list = QListWidget()
        self.downloaded_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.downloaded_list.customContextMenuRequested.connect(self._on_context_menu)
        self.downloaded_list.itemDoubleClicked.connect(self._open_folder)
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
        splitter.setSizes([480, 240])
        layout.addWidget(splitter, 1)

        # 状态
        self.status = QLabel("就绪")
        self.status.setStyleSheet("color: #64748B; font-size: 11px; padding: 4px 0;")
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
        self.dl_btn.setText("下载中...")
        self.progress.setVisible(True); self.progress.setValue(0)
        self.log_view.clear()

        self.thread = SingleDownloadThread(text, save_dir)
        self.thread.log.connect(self._log)
        self.thread.progress.connect(self.progress.setValue)
        self.thread.finished.connect(self._done)
        self.thread.start()

    def _log(self, msg):
        self.log_view.append(colored_log(msg))
        sb = self.log_view.verticalScrollBar(); sb.setValue(sb.maximum())

    def _on_context_menu(self, pos):
        item = self.downloaded_list.itemAt(pos)
        if not item: return
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        a1 = menu.addAction("打开文件夹")
        a2 = menu.addAction("复制路径")
        action = menu.exec(self.downloaded_list.mapToGlobal(pos))
        p = item.data(Qt.ItemDataRole.UserRole)
        if not p: return
        if action == a1 and Path(p).exists(): os.startfile(p)
        elif action == a2: QApplication.clipboard().setText(p)

    def _done(self, ok, msg):
        self.dl_btn.setEnabled(True)
        self.dl_btn.setText("开始下载")
        self.status.setText(msg)
        if ok: self.progress.setValue(100)
        self._refresh_downloaded()
        # 托盘通知
        w = self.window()
        if ok and hasattr(w, 'tray_notify'):
            w.tray_notify("抖净", "下载完成", duration=3000)


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
        back = QPushButton("  < 返回")
        back.setObjectName("secondaryBtn")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_clicked)
        back.setFixedSize(90, 36)
        top.addWidget(back)

        title = QLabel("主页批量下载")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #E11D48;")
        top.addWidget(title)
        top.addStretch()
        layout.addLayout(top)

        # URL 行
        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.douyin.com/user/MS4wLjAB...")
        self.url_input.setMinimumHeight(42)
        self.url_input.returnPressed.connect(self._start)
        url_row.addWidget(self.url_input)
        self.dl_btn = QPushButton("开始下载")
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.clicked.connect(self._start)
        self.dl_btn.setFixedHeight(42)
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
        ctrl.addWidget(QLabel("保存到"))
        self.path_input = QLineEdit()
        self.path_input.setText(get_homepage_download_path())
        ctrl.addWidget(self.path_input)
        browse = QPushButton("浏览...")
        browse.setObjectName("secondaryBtn")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.setFixedHeight(36)
        browse.clicked.connect(lambda: self._browse(self.path_input))
        ctrl.addWidget(browse)
        layout.addLayout(ctrl)

        # 进度
        self.progress = QProgressBar()
        self.progress.setFixedHeight(8)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # 主体
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0,0,0,0)
        ll.addWidget(QLabel("下载日志"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        ll.addWidget(self.log_view)
        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0,0,0,0)
        rl.addWidget(QLabel("已下载"))
        self.user_list = QListWidget()
        self.user_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.user_list.customContextMenuRequested.connect(self._on_context_menu)
        self.user_list.itemDoubleClicked.connect(self._open_folder)
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
        self.status.setStyleSheet("color: #64748B; font-size: 11px; padding: 4px 0;")
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
        self.dl_btn.setText("下载中...")
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
        self.log_view.append(colored_log(msg))
        sb = self.log_view.verticalScrollBar(); sb.setValue(sb.maximum())

    def _on_context_menu(self, pos):
        item = self.user_list.itemAt(pos)
        if not item: return
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        a1 = menu.addAction("打开文件夹")
        a2 = menu.addAction("复制路径")
        action = menu.exec(self.user_list.mapToGlobal(pos))
        p = item.data(Qt.ItemDataRole.UserRole)
        if not p: return
        if action == a1 and Path(p).exists(): os.startfile(p)
        elif action == a2: QApplication.clipboard().setText(p)

    def _done(self, stats):
        self.dl_btn.setEnabled(True)
        self.dl_btn.setText("开始下载")
        self.pause_btn.setEnabled(False); self.cancel_btn.setEnabled(False)
        self.pause_btn.setText("暂停")
        if stats.get("cancelled"):
            self.status.setText("已取消")
        else:
            total = stats.get('video',0) + stats.get('image',0)
            self.status.setText(f"视频:{stats.get('video',0)} 图片:{stats.get('image',0)} 跳过:{stats.get('skip',0)}")
            # 托盘通知
            w = self.window()
            if total > 0 and hasattr(w, 'tray_notify'):
                w.tray_notify("抖净", f"下载完成 · 视频{stats.get('video',0)} 图片{stats.get('image',0)}", duration=3000)
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
# ============================================================
# 页面4: 设置
# ============================================================
class SettingsPage(QWidget):
    back_clicked = pyqtSignal()
    font_changed = pyqtSignal(QFont)
    cookie_updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16); outer.setSpacing(0)

        top = QHBoxLayout()
        back = QPushButton("  < 返回"); back.setObjectName("secondaryBtn")
        back.setCursor(Qt.CursorShape.PointingHandCursor); back.clicked.connect(self.back_clicked)
        back.setFixedSize(90, 36); top.addWidget(back)
        icon_lbl = QLabel("S")
        icon_lbl.setStyleSheet("font-size:28px;font-weight:800;color:#E11D48;background:#1A1030;border-radius:12px;min-width:44px;max-width:44px;min-height:44px;max-height:44px;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); top.addWidget(icon_lbl)
        title = QLabel("设置"); title.setStyleSheet("font-size:20px;font-weight:bold;color:#E11D48;")
        top.addWidget(title); top.addStretch(); outer.addLayout(top); outer.addSpacing(16)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget(); cards_layout = QVBoxLayout(container)
        cards_layout.setSpacing(16); cards_layout.setContentsMargins(0, 0, 0, 0)

        # Card 1: 字体
        fc = self._card("字体设置")
        self.font_preview = QLabel("预览效果 ABC 中文")
        cf = load_font() or self.font(); self.font_preview.setFont(cf); self.font_preview.setMinimumHeight(36)
        self.font_preview.setStyleSheet("background:#0B0B1A;border:1px solid #252550;border-radius:8px;padding:10px;color:#F1F5F9;")
        fc.layout().addWidget(self.font_preview)
        self.font_info = QLabel(f"当前: {cf.family()}, {cf.pointSize()}pt")
        self.font_info.setStyleSheet("color:#64748B;font-size:12px;padding:4px 0;"); fc.layout().addWidget(self.font_info)
        fbr = QHBoxLayout(); fbr.addStretch()
        fb = QPushButton("更改字体"); fb.setObjectName("secondaryBtn"); fb.setCursor(Qt.CursorShape.PointingHandCursor)
        fb.clicked.connect(self._choose_font); fbr.addWidget(fb); fc.layout().addLayout(fbr)
        cards_layout.addWidget(fc)

        # Card 2: 下载路径
        pc = self._card("下载路径")
        for label, getter, setter in [
            ("单视频保存到:", get_single_download_path, "_change_single_path"),
            ("主页下载保存到:", get_homepage_download_path, "_change_homepage_path"),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label); lbl.setStyleSheet("color:#94A3B8;font-size:13px;min-width:110px;"); row.addWidget(lbl)
            pl = QLabel(getter()); pl.setStyleSheet("color:#64748B;font-size:12px;background:#0B0B1A;border:1px solid #252550;border-radius:6px;padding:6px 10px;")
            pl.setWordWrap(True); row.addWidget(pl, 1)
            ch = QPushButton("更改"); ch.setObjectName("secondaryBtn"); ch.setCursor(Qt.CursorShape.PointingHandCursor)
            ch.setFixedWidth(72); ch.clicked.connect(getattr(self, setter)); row.addWidget(ch); pc.layout().addLayout(row)
            setattr(self, "single_path_label" if "单" in label else "homepage_path_label", pl)
        cards_layout.addWidget(pc)

        # Card 3: Cookie
        cc = self._card("Cookie 管理")
        self.cookie_status_label = QLabel(); self.cookie_status_label.setStyleSheet("font-size:13px;padding:4px 0;")
        self.cookie_time_label = QLabel(); self.cookie_time_label.setStyleSheet("color:#64748B;font-size:12px;padding:2px 0;")
        cc.layout().addWidget(self.cookie_status_label); cc.layout().addWidget(self.cookie_time_label)
        cbr = QHBoxLayout(); cbr.addStretch()
        cb = QPushButton("更新 Cookie"); cb.setObjectName("secondaryBtn"); cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.clicked.connect(self._set_cookie); cbr.addWidget(cb); cc.layout().addLayout(cbr)
        cards_layout.addWidget(cc)

        # Card 4: 关于
        ac = self._card("关于")
        at = QLabel(f"<b>抖净 DouClean</b> &nbsp; v{VERSION}<br><br>抖音无水印下载工具<br>支持单视频 / 图集 / 实况照片 / 主页批量下载<br><br><a href='https://gitee.com/Renxint/douclean' style='color:#E11D48;'>Gitee: gitee.com/Renxint/douclean</a><br><br><span style='color:#64748B;'>© 2026 Renxint</span>")
        at.setOpenExternalLinks(True); at.setStyleSheet("color:#94A3B8;font-size:13px;"); at.setTextFormat(Qt.TextFormat.RichText)
        ac.layout().addWidget(at); cards_layout.addWidget(ac)
        cards_layout.addStretch()
        scroll.setWidget(container); outer.addWidget(scroll, 1)
        self.refresh_cookie_status()

    def _card(self, title_text):
        card = QFrame()
        card.setStyleSheet("QFrame { background:#12122A;border:1px solid #252550;border-radius:12px; }")
        layout = QVBoxLayout(card); layout.setContentsMargins(20, 16, 20, 16); layout.setSpacing(10)
        t = QLabel(title_text); t.setStyleSheet("font-size:15px;font-weight:bold;color:#E11D48;border:none;background:transparent;")
        layout.addWidget(t); return card

    def refresh_cookie_status(self):
        cs = get_cookie_status()
        if cs["ok"]: dot, txt = "#22C55E", "Cookie 已就绪"
        elif cs["length"] > 0: dot, txt = "#F59E0B", "Cookie 可能无效"
        else: dot, txt = "#EF4444", "Cookie 未设置"
        self.cookie_status_label.setText(f'<span style="color:{dot};font-size:16px;">●</span> <span style="color:#F1F5F9;">{txt}</span> <span style="color:#64748B;">({cs["length"]}字符)</span>')
        if cs["mtime"]:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(cs["mtime"]))
            age = (time.time() - cs["mtime"]) / 86400
            hint = " (可能已过期)" if age > 7 else ""
            self.cookie_time_label.setText(f"最后更新: {ts}{hint}")
        else:
            self.cookie_time_label.setText("尚未设置 Cookie")

    def _choose_font(self):
        accepted, font = choose_font_dialog(self, load_font() or self.font())
        if accepted:
            save_font(font); self.font_preview.setFont(font)
            self.font_info.setText(f"当前: {font.family()}, {font.pointSize()}pt")
            self.font_changed.emit(font)

    def _change_single_path(self):
        folder = QFileDialog.getExistingDirectory(self, "选择单视频保存目录", get_single_download_path())
        if folder: save_setting("single_download_path", folder); self.single_path_label.setText(folder)

    def _change_homepage_path(self):
        folder = QFileDialog.getExistingDirectory(self, "选择主页下载保存目录", get_homepage_download_path())
        if folder: save_setting("homepage_download_path", folder); self.homepage_path_label.setText(folder)

    def _set_cookie(self):
        current = COOKIE_FILE.read_text(encoding="utf-8").strip() if COOKIE_FILE.exists() else ""
        new, ok = QInputDialog.getMultiLineText(self, "设置 Cookie", "请粘贴抖音登录后的 Cookie：", current)
        if ok and new.strip():
            COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
            COOKIE_FILE.write_text(new.strip(), encoding="utf-8")
            self.refresh_cookie_status(); self.cookie_updated.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("抖净 DouClean")
        self.setStyleSheet(STYLE)

        # 任务栏/标题栏图标
        ico = BASE_DIR / "app.ico"
        self._app_icon = QIcon(str(ico)) if ico.exists() else QIcon()
        self.setWindowIcon(self._app_icon)

        # 恢复窗口位置
        geo = load_window_geometry()
        if geo:
            try: self.restoreGeometry(bytes.fromhex(geo.get("geo","")))
            except: self.resize(820, 640)
        else:
            self.resize(820, 640)
        self.setMinimumSize(640, 480)

        # 系统托盘
        self._setup_tray()

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.mode_page = ModePage()
        self.single_page = SinglePage()
        self.homepage_page = HomepagePage()
        self.settings_page = SettingsPage()

        self.stack.addWidget(self.mode_page)      # 0
        self.stack.addWidget(self.single_page)     # 1
        self.stack.addWidget(self.homepage_page)   # 2
        self.stack.addWidget(self.settings_page)   # 3

        self.mode_page.single_clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.mode_page.homepage_clicked.connect(lambda: self.stack.setCurrentIndex(2))
        self.mode_page.settings_clicked.connect(lambda: self.stack.setCurrentIndex(3))
        self.single_page.back_clicked.connect(lambda: self._go_home())
        self.homepage_page.back_clicked.connect(lambda: self._go_home())
        self.settings_page.back_clicked.connect(lambda: self._go_home())
        self.mode_page.font_changed.connect(self._apply_font)
        self.settings_page.font_changed.connect(self._apply_font)

        # 加载保存的字体
        saved = load_font()
        if saved:
            QApplication.instance().setFont(saved)

        self.mode_page.cookie_updated.connect(self._on_cookie_updated)
        self.settings_page.cookie_updated.connect(self._on_cookie_updated)
        self.stack.setCurrentIndex(0)

        # 快捷键
        self._setup_shortcuts()

        # socket 监听：收到双开通知时弹窗
        if _instance_socket:
            self._instance_socket = _instance_socket
            self._instance_timer = QTimer()
            self._instance_timer.timeout.connect(self._check_instance)
            self._instance_timer.start(500)

        # 启动后延迟检查版本更新（主线程，QTimer）
        QTimer.singleShot(2000, self._check_version)

    def _check_instance(self):
        """检查是否有第二个实例发来的激活信号"""
        try:
            conn, _ = self._instance_socket.accept()
            data = conn.recv(4)
            conn.close()
            if data == b'show':
                self._show_from_tray()
        except BlockingIOError:
            pass
        except Exception:
            pass

    def _setup_shortcuts(self):
        from PyQt6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(lambda: self._go_home())
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self._real_quit)
        QShortcut(QKeySequence("Ctrl+,"), self).activated.connect(lambda: self.stack.setCurrentIndex(3))
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(lambda: self.stack.setCurrentIndex(3))
        QShortcut(QKeySequence("Escape"), self).activated.connect(lambda: self.hide() if self._tray and self._tray.isVisible() else None)

    def _apply_font(self, font):
        QApplication.instance().setFont(font)

    def _check_version(self):
        try:
            r = requests.get(VERSION_URL, timeout=5)
            data = r.json()
            remote = data.get("version", "")
            if compare_versions(remote, VERSION) > 0:
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

    def _go_home(self):
        self.mode_page.refresh_cookie_status()
        self.settings_page.refresh_cookie_status()
        self.stack.setCurrentIndex(0)

    def _on_cookie_updated(self):
        self.settings_page.refresh_cookie_status()

    # ============ 托盘 & 窗口管理 ============

    def _setup_tray(self):
        """初始化系统托盘"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None; return
        self._tray = QSystemTrayIcon(self._app_icon, self)
        self._tray.setToolTip("抖净 DouClean · 就绪")
        self._tray.activated.connect(self._on_tray_activated)

        menu = QMenu()
        a_show = menu.addAction("显示主窗口")
        a_show.triggered.connect(self._show_from_tray)
        menu.addSeparator()
        a_about = menu.addAction("关于 抖净")
        a_about.triggered.connect(lambda: QMessageBox.about(self, "关于 抖净", f"抖净 DouClean v{VERSION}\n抖音无水印下载工具\n\n© 2026 Renxint"))
        a_update = menu.addAction("检查更新")
        a_update.triggered.connect(self._check_version)
        menu.addSeparator()
        a_quit = menu.addAction("退出")
        a_quit.triggered.connect(self._real_quit)
        self._tray.setContextMenu(menu)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        """点 X → 最小化到托盘，不退出"""
        if self._tray and self._tray.isVisible():
            self.hide()
            self._tray.showMessage("抖净", "已最小化到托盘，双击恢复", QSystemTrayIcon.MessageIcon.Information, 2000)
            event.ignore()
        else:
            self._real_quit()

    def _real_quit(self):
        """真正退出"""
        # 保存窗口位置
        try:
            geo_hex = self.saveGeometry().toHex().data().decode()
            save_window_geometry({"geo": geo_hex})
        except: pass
        if self._tray:
            self._tray.hide()
        # 释放单实例 socket
        try:
            if _instance_socket:
                _instance_socket.close()
        except Exception:
            pass
        QApplication.quit()

    def tray_notify(self, title, msg, icon=QSystemTrayIcon.MessageIcon.Information, duration=3000):
        """托盘气泡通知"""
        if self._tray:
            self._tray.showMessage(title, msg, icon, duration)


def main():
    global _instance_socket
    # 单实例检测（socket 端口占用 + 双开激活旧窗口）
    _instance_socket = setup_single_instance()
    if _instance_socket is None:
        # 已通知旧窗口激活，退出
        return

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出，配合托盘

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
    palette.setColor(QPalette.ColorRole.Window, QColor(10, 10, 20))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(241, 245, 249))
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
