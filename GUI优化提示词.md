# 抖净 DouClean — GUI 优化提示词（完整版）

> 喂给另一个 Claude，只改 UI 层，不动任何下载逻辑。

---

## 项目速览

| 项目 | 说明 |
|------|------|
| **工具名** | 抖净 DouClean — 抖音无水印下载工具 |
| **主文件** | `projects\douclean\unified_gui.py`（约 1258 行） |
| **GUI 框架** | PyQt6（`QMainWindow` + `QStackedWidget` 三页面） |
| **打包** | PyInstaller `--onedir --windowed` → `D:\抖净\抖净.exe` |
| **配色** | Cinema Dark（`#0A0A14` 底 + `#E11D48` 强调） |
| **版本** | `VERSION = "1.0.0"`，启动时后台检查 Gitee 更新 |

### 三页面架构

```
QStackedWidget
├── [0] ModePage      — 首页：模式选择（单视频 / 主页批量）
├── [1] SinglePage    — 单视频下载：粘贴分享链接 → 下载
└── [2] HomepagePage  — 主页批量下载：用户主页 → 全部作品
```

### 关键路径

```
BASE_DIR   → frozen: sys._MEIPASS / dev: Claude/
EXE_DIR    → frozen: exe所在目录 / dev: douclean/
COOKIE_FILE → EXE_DIR/data/Cookie.txt
OUTPUT_SINGLE → EXE_DIR/output/单视频
OUTPUT_HOMEPAGE → EXE_DIR/output/主页下载
SETTINGS_FILE → EXE_DIR/settings.json（字体偏好）
```

---

## ⛔ 红线 —— 绝对不要改

- 所有下载线程类（`SingleDownloadThread`、`HomepageDownloadThread`），包含 `run()`、`_resolve()`、`_fetch()`、`_download_aweme()`、`_dl()` 等全部方法
- `ensure_cookie()`（可调用但不可修改）
- `clean_name()`、`pick_best_video_url()`、`parse_sec_user_id()`
- `load_font()`、`save_font()`
- `_check_version()` 后台版本检查
- `_send_feedback()` 钉钉反馈
- 路径配置（`BASE_DIR`、`EXE_DIR`、`BOOTSTRAP_JS`、`NODE_CMD`、`COOKIE_FILE`、`OUTPUT_*`、`SETTINGS_FILE`）
- 版本号 `VERSION`、`VERSION_URL`、`DINGTALK_WEBHOOK`
- PyInstaller 路径适配逻辑（`if getattr(sys, 'frozen', False)` 块）
- Node.js 子进程调用、bootstrap.js 签名逻辑

---

# 第一部分：GUI 细节优化

> 当前 STYLE 样式表（约 489-561 行）已应用 Cinema Dark 配色，以下均为 **Python 代码层面的 UI 改动**。

---

## 1.1 首页 (ModePage) — 去 emoji，换卡片式按钮

**当前代码**（约 620-632 行）是 emoji 大按钮：

```python
self.single_btn = QPushButton("📱\n单视频下载\n\n粘贴分享链接\n下载单个视频/图集")
self.homepage_btn = QPushButton("👤\n主页批量下载\n\n粘贴用户主页链接\n下载全部作品")
```

**改成卡片式**，用数字 `"1"` / `"N"` 代替 emoji，按钮内部包 QVBoxLayout：

```python
# ========== 单视频卡片 ==========
self.single_btn = QPushButton()
self.single_btn.setObjectName("modeBtn")
self.single_btn.setCursor(Qt.CursorShape.PointingHandCursor)
self.single_btn.clicked.connect(self.single_clicked)
self.single_btn.setMinimumSize(260, 220)

s_inner = QVBoxLayout(self.single_btn)
s_inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
s_inner.setSpacing(8)

s_icon = QLabel("1")
s_icon.setStyleSheet(
    "font-size:32px; font-weight:800; color:#E11D48;"
    "background:#1A1030; border-radius:12px;"
    "min-width:52px; max-width:52px; min-height:52px; max-height:52px;")
s_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
s_inner.addWidget(s_icon, alignment=Qt.AlignmentFlag.AlignCenter)

s_title = QLabel("单视频下载")
s_title.setStyleSheet("font-size:18px; font-weight:700; color:#F1F5F9; background:transparent;")
s_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
s_inner.addWidget(s_title)

s_desc = QLabel("粘贴抖音分享链接\n下载视频 / 图集 / 实况照片\n自动创建文件夹分类")
s_desc.setStyleSheet("font-size:12px; color:#64748B; background:transparent;")
s_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
s_inner.addWidget(s_desc)

# ========== 主页卡片 ==========
self.homepage_btn = QPushButton()
self.homepage_btn.setObjectName("modeBtn")
self.homepage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
self.homepage_btn.clicked.connect(self.homepage_clicked)
self.homepage_btn.setMinimumSize(260, 220)

h_inner = QVBoxLayout(self.homepage_btn)
h_inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
h_inner.setSpacing(8)

h_icon = QLabel("N")
h_icon.setStyleSheet(
    "font-size:32px; font-weight:800; color:#E11D48;"
    "background:#1A1030; border-radius:12px;"
    "min-width:52px; max-width:52px; min-height:52px; max-height:52px;")
h_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
h_inner.addWidget(h_icon, alignment=Qt.AlignmentFlag.AlignCenter)

h_title = QLabel("主页批量下载")
h_title.setStyleSheet("font-size:18px; font-weight:700; color:#F1F5F9; background:transparent;")
h_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
h_inner.addWidget(h_title)

h_desc = QLabel("粘贴用户主页链接\n下载全部作品 / 批量归档\n支持指定数量下载")
h_desc.setStyleSheet("font-size:12px; color:#64748B; background:transparent;")
h_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
h_inner.addWidget(h_desc)
```

两张卡片间距改为 `btn_layout.setSpacing(24)`。

---

## 1.2 单视频页 (SinglePage) 微调

### 1.2.1 顶栏加 Cookie 状态标签

在 `_build()` 的顶栏中，返回按钮之后、标题之前插入：

```python
cs = get_cookie_status()
self._cookie_label = QLabel("Cookie OK" if cs["ok"] else "Cookie !")
self._cookie_label.setStyleSheet(
    f"font-size:11px; color:{'#22C55E' if cs['ok'] else '#F59E0B'};"
    f"background:#111128; border-radius:4px; padding:4px 10px;")
top.addWidget(self._cookie_label)
top.addSpacing(8)
```

### 1.2.2 控件尺寸

```python
self.url_input.setMinimumHeight(42)
self.dl_btn.setFixedHeight(42)
self.dl_btn.setMinimumWidth(100)
self.progress.setFixedHeight(8)
# 浏览按钮
browse.setFixedHeight(36)
```

下载中/完成后切换文字：
- `_start()` 内加：`self.dl_btn.setText("下载中...")`
- `_done()` 内加：`self.dl_btn.setText("开始下载")`

### 1.2.3 已下载列表 — 右键菜单 + 双击

```python
self.downloaded_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
self.downloaded_list.customContextMenuRequested.connect(self._on_context_menu)
self.downloaded_list.itemDoubleClicked.connect(self._open_folder)
```

新增 `_on_context_menu` 方法：

```python
def _on_context_menu(self, pos):
    item = self.downloaded_list.itemAt(pos)
    if not item: return
    from PyQt6.QtWidgets import QMenu
    menu = QMenu(self)
    open_action = menu.addAction("打开文件夹")
    copy_action = menu.addAction("复制路径")
    action = menu.exec(self.downloaded_list.mapToGlobal(pos))
    p = item.data(Qt.ItemDataRole.UserRole)
    if not p: return
    if action == open_action and Path(p).exists():
        os.startfile(p)
    elif action == copy_action:
        QApplication.clipboard().setText(p)
```

### 1.2.4 `_done()` 末尾更新 Cookie 标签

```python
cs = get_cookie_status()
self._cookie_label.setText("Cookie OK" if cs["ok"] else "Cookie !")
self._cookie_label.setStyleSheet(
    f"font-size:11px; color:{'#22C55E' if cs['ok'] else '#F59E0B'};"
    f"background:#111128; border-radius:4px; padding:4px 10px;")
```

### 1.2.5 "打开目录"和"刷新"并排

把两个按钮从竖直排列包进 QHBoxLayout：

```python
btn_row = QHBoxLayout()
open_btn = QPushButton("打开目录")
open_btn.setObjectName("secondaryBtn")
open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
open_btn.clicked.connect(self._open_folder)
btn_row.addWidget(open_btn)

refresh_btn = QPushButton("刷新")
refresh_btn.setObjectName("secondaryBtn")
refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
refresh_btn.clicked.connect(self._refresh_downloaded)
btn_row.addWidget(refresh_btn)

rl.addLayout(btn_row)  # 替代原来的 rl.addWidget(open_btn) 和 rl.addWidget(refresh_btn)
```

---

## 1.3 主页批量页 (HomepagePage) 微调

改动与 SinglePage 完全对应：

### 1.3.1 顶栏加 Cookie 标签

```python
cs = get_cookie_status()
self._cookie_label = QLabel("Cookie OK" if cs["ok"] else "Cookie !")
self._cookie_label.setStyleSheet(
    f"font-size:11px; color:{'#22C55E' if cs['ok'] else '#F59E0B'};"
    f"background:#111128; border-radius:4px; padding:4px 10px;")
top.addWidget(self._cookie_label)
top.addSpacing(8)
```

### 1.3.2 控件尺寸

```python
self.url_input.setMinimumHeight(42)
self.dl_btn.setFixedHeight(42)
self.dl_btn.setMinimumWidth(100)
self.progress.setFixedHeight(8)
browse.setFixedHeight(36)
```

下载中/完成后：`self.dl_btn.setText("下载中...")` / `self.dl_btn.setText("开始下载")`

### 1.3.3 用户列表 — 右键菜单 + 双击

```python
self.user_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
self.user_list.customContextMenuRequested.connect(self._on_context_menu)
self.user_list.itemDoubleClicked.connect(self._open_folder)
```

新增 `_on_context_menu` 方法（注意操作的是 `self.user_list` 而非 `downloaded_list`）：

```python
def _on_context_menu(self, pos):
    item = self.user_list.itemAt(pos)
    if not item: return
    from PyQt6.QtWidgets import QMenu
    menu = QMenu(self)
    open_action = menu.addAction("打开文件夹")
    copy_action = menu.addAction("复制路径")
    action = menu.exec(self.user_list.mapToGlobal(pos))
    p = item.data(Qt.ItemDataRole.UserRole)
    if not p: return
    if action == open_action and Path(p).exists():
        os.startfile(p)
    elif action == copy_action:
        QApplication.clipboard().setText(p)
```

### 1.3.4 `_done()` 末尾更新 Cookie 标签

同 SinglePage 1.2.4。

### 1.3.5 "打开目录"和"刷新"并排

同 SinglePage 1.2.5，包进 QHBoxLayout。

### 1.3.6 Splitter 分屏比例

```python
splitter.setSizes([520, 280])
```

---

## 1.4 MainWindow — 补充 `_on_cookie_updated()`

当前方法体为空（`pass`），替换为：

```python
def _on_cookie_updated(self):
    """Cookie 更新后同步到子页面的标签"""
    cs = get_cookie_status()
    ok = cs["ok"]
    color = "#22C55E" if ok else "#F59E0B"
    text = "Cookie OK" if ok else "Cookie !"
    style = (f"font-size:11px; color:{color}; background:#111128;"
             f"border-radius:4px; padding:4px 10px;")
    self.single_page._cookie_label.setText(text)
    self.single_page._cookie_label.setStyleSheet(style)
    self.homepage_page._cookie_label.setText(text)
    self.homepage_page._cookie_label.setStyleSheet(style)
```

---

## 1.5 `main()` QPalette 配色同步

当前 `main()` 中的 `QPalette` 部分还是旧值：

```python
# 旧值（需改）
palette.setColor(QPalette.ColorRole.WindowText, QColor(224, 224, 224))  # ← 旧
palette.setColor(QPalette.ColorRole.Base, QColor(22, 33, 62))            # ← 旧
palette.setColor(QPalette.ColorRole.Text, QColor(224, 224, 224))         # ← 旧
```

全部替换为与 STYLE 样式表一致的 Cinema Dark 配色：

```python
palette.setColor(QPalette.ColorRole.Window, QColor(10, 10, 20))
palette.setColor(QPalette.ColorRole.WindowText, QColor(241, 245, 249))
palette.setColor(QPalette.ColorRole.Base, QColor(18, 18, 42))
palette.setColor(QPalette.ColorRole.Text, QColor(241, 245, 249))
palette.setColor(QPalette.ColorRole.Button, QColor(225, 29, 72))
palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
palette.setColor(QPalette.ColorRole.Highlight, QColor(225, 29, 72))
palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(100, 116, 139))
palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(26, 26, 62))
palette.setColor(QPalette.ColorRole.ToolTipText, QColor(241, 245, 249))
# 禁用态
palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(26, 26, 46))
palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(71, 85, 105))
palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(71, 85, 105))
```

---

# 第二部分：.exe 工具级 GUI 框架增强

> DouClean 打包为独立 .exe 后，需要以下桌面应用级别的功能。

---

## 2.1 系统托盘（完整代码）

> 以下代码统一放在 `MainWindow.__init__()` 中，**在 `self.stack.setCurrentIndex(0)` 之前**。
> 新增的 `_show_from_tray`、`_on_tray_activated`、`_real_quit`、`closeEvent`、`_show_about` 五个方法放在 `MainWindow` 类内部（与 `_go_home` 同级即可）。

**要点**：
- `self.tray` 是 MainWindow 的公开属性，子页面通过 `self._tray` 引用同一对象
- 托盘菜单一次性构建，包含：显示主窗口 / 分隔线 / 开机自启 / 关于 / 退出
- 关于和开机自启的 action 也要存为属性（`self._autorun_action` / `self._about_action`），方便后续扩展

### 2.1.1 托盘初始化（写进 `__init__`）

```python
# ═══ 系统托盘 ═══
self.tray = QSystemTrayIcon(self)
ico = BASE_DIR / "app.ico"
if ico.exists():
    self.tray.setIcon(QIcon(str(ico)))
self.tray.setToolTip("抖净 DouClean")

# 托盘右键菜单（一次性构建完整）
tray_menu = QMenu()

show_action = QAction("显示主窗口", self)
show_action.triggered.connect(self._show_from_tray)
tray_menu.addAction(show_action)

tray_menu.addSeparator()

# 开机自启（勾选即写入注册表）
self._autorun_action = QAction("开机自启", self)
self._autorun_action.setCheckable(True)
self._autorun_action.setChecked(get_autorun_status())
self._autorun_action.triggered.connect(lambda checked: set_autorun(checked))
tray_menu.addAction(self._autorun_action)

tray_menu.addSeparator()

# 关于
about_action = QAction("关于 抖净", self)
about_action.triggered.connect(self._show_about)
tray_menu.addAction(about_action)

tray_menu.addSeparator()

# 退出
quit_action = QAction("退出", self)
quit_action.triggered.connect(self._real_quit)
tray_menu.addAction(quit_action)

self.tray.setContextMenu(tray_menu)
self.tray.activated.connect(self._on_tray_activated)
self.tray.show()
```

### 2.1.2 新增五个方法

```python
def _on_tray_activated(self, reason):
    """双击托盘图标 → 显示窗口"""
    if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
        self._show_from_tray()

def _show_from_tray(self):
    """从托盘恢复窗口"""
    self.showNormal()
    self.activateWindow()
    self.raise_()

def _real_quit(self):
    """真正的退出：停止下载线程 + 移除托盘 + 退出进程"""
    try:
        t1 = self.single_page.thread
        if t1 and t1.isRunning():
            t1.terminate()
        t2 = self.homepage_page.thread
        if t2 and t2.isRunning():
            t2.cancel()
    except Exception:
        pass
    self.tray.hide()
    QApplication.quit()

def closeEvent(self, event):
    """点 X → 最小化到托盘，不退出"""
    if self.tray.isVisible():
        self.hide()
        self.tray.showMessage(
            "抖净", "已最小化到系统托盘，右键可退出",
            QSystemTrayIcon.MessageIcon.Information, 2000)
        event.ignore()
    else:
        self._real_quit()

def _show_about(self):
    """关于对话框"""
    QMessageBox.about(
        self, "关于 抖净 DouClean",
        f"<h2>抖净 DouClean</h2>"
        f"<p>版本: v{VERSION}</p>"
        f"<p>抖音无水印下载工具</p>"
        f"<p>单视频 / 图集 / 实况 / 主页批量</p>"
        f"<hr>"
        f"<p>反馈与更新: "
        f"<a href='https://gitee.com/Renxint/douyin-downloader'>Gitee</a></p>"
    )
```

---

## 2.2 单实例检测

防止用户双击 exe 启动多个实例。**修改 `main()` 函数开头**：

```python
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DouClean")

    # --- 单实例检测 ---
    shared_mem = QSharedMemory("DouClean_SingleInstance_Key")
    if shared_mem.attach():
        QMessageBox.warning(None, "抖净", "程序已在运行中，请查看系统托盘。")
        sys.exit(0)
    shared_mem.create(1)
    # QSharedMemory 随进程退出自动释放，无需手动 detach

    # ... 后面是原有的初始化：翻译、Fusion、palette ...
    app.setStyle('Fusion')
    # ... palette ...

    window = MainWindow()
    window._shared_mem = shared_mem  # 防止被 gc 回收
    window.show()
    sys.exit(app.exec())
```

---

## 2.3 开机自启

### 2.3.1 注册表工具函数（放在文件顶部，`ensure_cookie()` 附近）

```python
import winreg

_AUTORUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTORUN_NAME = "抖净DouClean"

def get_autorun_status() -> bool:
    """读取注册表，检查是否已设开机自启"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTORUN_KEY, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, _AUTORUN_NAME)
        winreg.CloseKey(key)
        return value.endswith("抖净.exe")
    except FileNotFoundError:
        return False

def set_autorun(enable: bool):
    """写入/删除注册表开机自启项"""
    if enable:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTORUN_KEY, 0,
                             winreg.KEY_WRITE)
        exe_path = str(EXE_DIR / "抖净.exe")
        winreg.SetValueEx(key, _AUTORUN_NAME, 0, winreg.REG_SZ, exe_path)
    else:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTORUN_KEY, 0,
                                 winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, _AUTORUN_NAME)
        except FileNotFoundError:
            pass
    winreg.CloseKey(key)
```

> 托盘菜单中的「开机自启」action 已在 2.1.1 中一并构建，无需额外代码。

---

## 2.4 下载完成通知 + 状态栏

### 2.4.1 底部状态栏（加在 `MainWindow.__init__` 末尾）

```python
# 底部状态栏
self.statusBar().showMessage(f"v{VERSION} | 关闭窗口可最小化到系统托盘")
self.statusBar().setStyleSheet("color: #64748B; font-size: 11px;")
```

### 2.4.2 子页面注入 tray 引用（加在 `MainWindow.__init__` 创建子页面后）

```python
# 子页面需要 tray 来发通知
self.single_page._tray = self.tray
self.homepage_page._tray = self.tray
```

### 2.4.3 SinglePage 下载完成通知

在 `SinglePage._done()` 末尾加：

```python
if ok and hasattr(self, '_tray') and self._tray:
    self._tray.showMessage("抖净", f"下载完成！\n{msg}",
                           QSystemTrayIcon.MessageIcon.Information, 3000)
```

### 2.4.4 HomepagePage 下载完成通知

在 `HomepagePage._done()` 末尾加：

```python
if not stats.get("cancelled") and hasattr(self, '_tray') and self._tray:
    v = stats.get('video', 0); i = stats.get('image', 0)
    self._tray.showMessage("抖净", f"批量下载完成！\n视频:{v} 图片:{i}",
                           QSystemTrayIcon.MessageIcon.Information, 3000)
```

> 使用 `self._tray`（带下划线）区别于 MainWindow 的 `self.tray`，避免混淆。
> `hasattr` 防御：源码运行时子页面也有 `_tray`，无需额外处理。

---

## 2.5 设置持久化扩展

当前 `SETTINGS_FILE`（`EXE_DIR/settings.json`）只存字体。扩展为统一配置存储。

### 2.5.1 新增通用读写函数（放在文件顶部 `load_font/save_font` 之后）

```python
def load_settings() -> dict:
    """读取所有设置，不存在则返回空字典"""
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}

def save_settings(data: dict):
    """写入设置文件"""
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass
```

### 2.5.2 适配现有字体函数（**不删不改签名，只调整内部实现**）

`load_font()` 改为从 `load_settings()` 的 `"font"` 字段读取：

```python
def load_font():
    """加载用户保存的字体设置"""
    try:
        s = load_settings().get("font")
        if s:
            f = QFont(s.get("family", ""))
            if s.get("size"):
                f.setPointSize(s["size"])
            return f
    except Exception:
        pass
    return None
```

`save_font()` 改为读写完整 settings 后写回：

```python
def save_font(font):
    """保存字体设置（不影响 settings.json 中其他字段）"""
    try:
        data = load_settings()
        data["font"] = {"family": font.family(), "size": font.pointSize()}
        save_settings(data)
    except Exception:
        pass
```

> 这样字体函数签名不变（调用方无需改动），同时 settings.json 可以扩展更多字段。

---

## 2.6 import 汇总

以下为修改完成后文件顶部应有的完整 import 清单。**逐个对比当前代码**，缺少的就补上：

```python
import sys, re, json, time, threading, subprocess, os, winreg
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QProgressBar, QLabel, QFileDialog,
    QStackedWidget, QComboBox, QListWidget, QListWidgetItem, QSplitter,
    QMessageBox, QInputDialog, QFrame,
    QSystemTrayIcon, QMenu, QStatusBar,   # ← 新增：托盘+菜单+状态栏
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTranslator, QLocale, QLibraryInfo,
    QSharedMemory,   # ← 新增：单实例检测
)
from PyQt6.QtGui import (
    QPalette, QColor, QIcon, QFont,
    QAction,   # ← 新增：托盘菜单 Action
)

import requests
```

> `QStatusBar` 可省略 —— QMainWindow 自带 `statusBar()` 方法，无需手动创建。仅导入以防万一。

---

## 代码改动边界总结

| 改动 | 涉及方法/区域 |
|------|-------------|
| ModePage 卡片 | `ModePage.__init__()` 中 single_btn / homepage_btn 的创建 |
| Cookie 标签（子页） | `SinglePage._build()` / `HomepagePage._build()` 顶栏 |
| 控件尺寸 | `_build()` 中 url_input / dl_btn / browse / progress |
| 右键菜单+双击 | `_build()` 连接信号 + 新增 `_on_context_menu()` 方法 |
| 按钮并排 | `_build()` 中 open_btn + refresh_btn 的布局 |
| `_done()` 标签更新 | `SinglePage._done()` / `HomepagePage._done()` 末尾 |
| Splitter 比例 | `HomepagePage._build()` splitter.setSizes |
| `_on_cookie_updated` | `MainWindow._on_cookie_updated()` |
| `main()` 调色板 | `main()` 函数 QPalette 值 |
| 系统托盘 | `MainWindow.__init__()` 大量新增 + 3 新方法 |
| 单实例 | `main()` 开头 + `QSharedMemory` |
| 开机自启 | 文件顶部 `get_autorun/set_autorun` 函数 + 托盘菜单 |
| 下载通知 | `_done()` 末尾 `showMessage` + `_tray` 注入 |
| 关于对话框 | 托盘菜单 + `_show_about()` |
| 状态栏 | `MainWindow.__init__` 末尾 |
| 设置扩展 | `load_settings/save_settings` + 重构字体保存 |
| 全局异常捕获 | `main()` 中 `sys.excepthook` + `_debug.log` 写入 |
| 单实例激活 | `main()` 改进：检测到已有实例时激活其窗口 |
| 窗口几何记忆 | `MainWindow.__init__` / `closeEvent` / `moveEvent` / `resizeEvent` |
| 拖放 | `MainWindow` + `SinglePage` + `HomepagePage` dragEnter/drop 事件 |
| 命令行参数 | `main()` 开头解析 `sys.argv`，传给 `MainWindow` |
| 快捷键 | `MainWindow.__init__` 中逐页绑定 |
| 托盘 ToolTip | 下载开始时更新 `self.tray.setToolTip(...)` |

---

# 第三部分：细节增强

> 以下功能让 .exe 工具的使用体验从"能用"升级到"好用"。

---

## 3.1 全局异常捕获 + 开发者日志

### 3.1.1 日志工具函数（文件顶部）

```python
import traceback

DEBUG_LOG = EXE_DIR / "_debug.log"

def debug_log(msg: str):
    """写调试日志（静默失败）"""
    try:
        with open(DEBUG_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
        # 日志轮转：超过 1MB 截半
        if DEBUG_LOG.stat().st_size > 1_000_000:
            keep = DEBUG_LOG.read_text(encoding='utf-8')[-500_000:]
            DEBUG_LOG.write_text(keep, encoding='utf-8')
    except Exception:
        pass
```

### 3.1.2 全局异常钩子（在 `main()` 开头，`app = QApplication(...)` 之后）

```python
def _global_excepthook(exc_type, exc_value, exc_tb):
    """捕获未处理异常，写日志 + 弹友好提示"""
    tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    debug_log(f"CRASH: {tb_str}")
    # 避免在崩溃处理中二次崩溃
    try:
        QMessageBox.critical(
            None, "抖净 · 出错了",
            f"程序遇到了未预期的错误：\n\n{exc_value}\n\n"
            f"详细信息已写入 _debug.log，可反馈给开发者。"
        )
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)  # 保留默认行为

sys.excepthook = _global_excepthook
```

### 3.1.3 关键位置加日志

在以下位置插入 `debug_log(...)` 调用（轻量，不影响正常运行）：

- `main()` 入口 → `debug_log("抖净启动 v{VERSION}")`
- `MainWindow.__init__` 末尾 → `debug_log("MainWindow 初始化完成")`
- `_real_quit()` → `debug_log("用户退出")`
- `_check_version()` 异常分支 → `debug_log(f"版本检查失败: {e}")`
- 任何 `except Exception: pass` 的地方 → 加 `debug_log(f"…: {e}")`

---

## 3.2 单实例增强：激活已有窗口

当前 2.2 的方案是弹警告 → 退出。改进为**激活已有实例的窗口**：

```python
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DouClean")

    # --- 单实例检测 + 激活已有窗口 ---
    shared_mem = QSharedMemory("DouClean_SingleInstance_Key")
    if shared_mem.attach():
        # 已有实例 → 通过 Windows 消息激活它
        from PyQt6.QtCore import QTimer
        # 发一条简单的"显示"指令：写入共享内存后退出
        shared_mem.detach()
        # 无法直接跨进程激活，降级为友好提示
        QMessageBox.information(None, "抖净", "程序已在运行中\n请查看屏幕右下角系统托盘")
        sys.exit(0)
    shared_mem.create(1)

    # ... 原有初始化 ...
```

> 跨进程激活的完美方案需要 Windows `SendMessage` + `FindWindow`，复杂度高。当前方案先保证「不重复启动 + 引导用户去托盘找」，已够用。

---

## 3.3 窗口几何记忆

启动时恢复上次的窗口位置和大小，关闭时保存。

### 3.3.1 保存几何（在 `closeEvent` 中，最小化到托盘之前）

```python
def closeEvent(self, event):
    if self.tray.isVisible():
        # 保存窗口几何
        data = load_settings()
        data["window"] = {
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
        }
        save_settings(data)

        self.hide()
        self.tray.showMessage("抖净", "已最小化到系统托盘，右键可退出",
                              QSystemTrayIcon.MessageIcon.Information, 2000)
        event.ignore()
    else:
        self._real_quit()
```

### 3.3.2 恢复几何（在 `MainWindow.__init__` 末尾，`show()` 之前）

```python
# 恢复窗口几何
geo = load_settings().get("window")
if geo and all(k in geo for k in ("x", "y", "w", "h")):
    self.setGeometry(geo["x"], geo["y"], geo["w"], geo["h"])
else:
    self.resize(820, 640)
self.setMinimumSize(640, 480)
```

---

## 3.4 拖放链接到输入框

从浏览器拖 URL 到窗口 → 自动填入。

### 3.4.1 MainWindow 接受拖放（`__init__` 中）

```python
self.setAcceptDrops(True)
```

### 3.4.2 MainWindow 拖放处理

```python
def dragEnterEvent(self, event):
    if event.mimeData().hasUrls() or event.mimeData().hasText():
        event.acceptProposedAction()

def dropEvent(self, event):
    text = event.mimeData().text().strip()
    if not text:
        urls = event.mimeData().urls()
        if urls: text = urls[0].toString()
    if not text: return

    if "douyin.com" in text or "v.douyin.com" in text:
        if "/user/" in text:
            # 主页链接 → 跳转主页批量页 + 填入
            self.stack.setCurrentIndex(2)
            self.homepage_page.url_input.setText(text)
        else:
            # 单视频链接 → 跳转单视频页 + 填入
            self.stack.setCurrentIndex(1)
            self.single_page.url_input.setText(text)
        self._show_from_tray()
```

### 3.4.3 每个页面的输入框也允许拖放

在 `SinglePage._build()` 和 `HomepagePage._build()` 中：

```python
self.url_input.setAcceptDrops(True)
# 可选：重写 url_input 的 dropEvent（见下方）
```

如果 `QLineEdit` 默认拖放行为不满足需求（比如拖入时替换而非追加），在各自的 `_build()` 后新增：

```python
class DropLineEdit(QLineEdit):
    """支持拖放链接的输入框"""
    def dragEnterEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasUrls():
            event.acceptProposedAction()
    def dropEvent(self, event):
        text = event.mimeData().text().strip()
        if not text and event.mimeData().urls():
            text = event.mimeData().urls()[0].toString()
        if text:
            self.setText(text)

# 然后在 _build() 中把 QLineEdit 换成 DropLineEdit
self.url_input = DropLineEdit()
```

> `DropLineEdit` 类放在文件顶部 `get_cookie_status()` 附近即可。

---

## 3.5 命令行参数

支持启动时直接传入链接。

### 3.5.1 在 `main()` 中解析参数，传给 `MainWindow`

```python
def main():
    # ... app 初始化 ...

    # 解析命令行参数（第一个参数是脚本路径，跳过）
    pending_url = None
    for arg in sys.argv[1:]:
        if arg.startswith("http"):
            pending_url = arg
            break

    window = MainWindow()
    window._shared_mem = shared_mem

    if pending_url:
        # 延迟处理（等窗口完全初始化后）
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(300, lambda: window._handle_startup_url(pending_url))

    window.show()
    sys.exit(app.exec())
```

### 3.5.2 MainWindow 新增方法

```python
def _handle_startup_url(self, url):
    """处理命令行/拖放传入的链接"""
    if not url or "douyin.com" not in url:
        return
    if "/user/" in url:
        self.stack.setCurrentIndex(2)
        self.homepage_page.url_input.setText(url)
    else:
        self.stack.setCurrentIndex(1)
        self.single_page.url_input.setText(url)
```

> `MainWindow.dropEvent` 也可以复用这个方法来去重。

---

## 3.6 键盘快捷键

### 3.6.1 在 `MainWindow.__init__` 末尾绑定

```python
# ═══ 键盘快捷键 ═══
# 窗口级（始终可用）
self._shortcut_quit = QShortcut("Ctrl+Q", self)
self._shortcut_quit.activated.connect(self._real_quit)

self._shortcut_home = QShortcut("Ctrl+H", self)
self._shortcut_home.activated.connect(self._go_home)

self._shortcut_settings = QShortcut("Ctrl+,", self)
self._shortcut_settings.activated.connect(self.mode_page._choose_font)

# Escape → 最小化到托盘
self._shortcut_hide = QShortcut("Escape", self)
self._shortcut_hide.activated.connect(lambda: self.close())
# ↑ close() 会走 closeEvent → 最小化到托盘
```

### 3.6.2 在 import 区补充

```python
from PyQt6.QtGui import QShortcut, QKeySequence
```

### 3.6.3 快捷键列表（显示在关于对话框中）

更新 `_show_about()` 方法，在链接下方加一行：

```python
f"<p><small>快捷键: Ctrl+Q 退出 | Ctrl+H 首页 | Ctrl+, 字体 | Esc 最小化</small></p>"
```

---

## 3.7 托盘 ToolTip 动态更新

让托盘图标悬停时显示当前状态。

### 3.7.1 下载开始时更新

在 `SinglePage._start()` 和 `HomepagePage._start()` 中加：

```python
# 通知托盘（如果存在）
if hasattr(self, '_main_window') and hasattr(self._main_window, 'tray'):
    self._main_window.tray.setToolTip("抖净 · 下载中...")
```

### 3.7.2 下载完成时恢复

在 `SinglePage._done()` 和 `HomepagePage._done()` 末尾加：

```python
if hasattr(self, '_main_window') and hasattr(self._main_window, 'tray'):
    self._main_window.tray.setToolTip("抖净 DouClean")
```

### 3.7.3 MainWindow 注入自身引用

在 `MainWindow.__init__` 中，`_tray` 注入旁边加一行：

```python
self.single_page._main_window = self
self.homepage_page._main_window = self
```

---

## 改动边界总结（第三部分补充）

| 改动 | 涉及方法/区域 |
|------|-------------|
| 全局异常钩子 | `main()` + 新函数 `_global_excepthook` |
| debug_log | 文件顶部新函数 + 关键位置插调用 |
| 单实例激活 | `main()` 改进（当前方案 + 预留注释） |
| 窗口几何恢复 | `MainWindow.closeEvent` + `__init__` 末尾 |
| 拖放（窗口级） | `MainWindow.dragEnterEvent` / `dropEvent` |
| 拖放（输入框级） | 新类 `DropLineEdit` + 替换 `QLineEdit` |
| 命令行参数 | `main()` 解析 + `MainWindow._handle_startup_url` |
| 快捷键 | `MainWindow.__init__` 末尾 + import `QShortcut` |
| 托盘 ToolTip | `_start()` / `_done()` + `MainWindow` 注入 `_main_window` |

---

## 改动顺序建议（更新版）

```
 1. import 补充 (2.6)                       ← QShortcut、QKeySequence
 2. debug_log + 全局异常 (3.1)              ← 文件顶部 + main() 
 3. main() 调色板 (1.5) + 单实例 (2.2/3.2) + 命令行 (3.5)
 4. 注册表函数 + 设置扩展 (2.3 + 2.5)
 5. DropLineEdit 类 (3.4.3)                 ← 文件顶部，后面页面要用
 6. ModePage 卡片 (1.1)
 7. SinglePage 全部 (1.2)                   ← 含 DropLineEdit 替换
 8. HomepagePage 全部 (1.3)                 ← 同上
 9. MainWindow._on_cookie_updated (1.4)
10. MainWindow 托盘+状态栏+方法 (2.1+2.4)    ← 含 closeEvent 几何保存
11. 窗口几何恢复 (3.3)                      ← __init__ 末尾
12. 拖放+快捷键+注入 (3.4+3.6+3.7)          ← 最后加
```

## 验证清单

改完后运行：
```bash
python D:\Pycharm环境\Claude\projects\douclean\unified_gui.py
```

### 基础 GUI
- [ ] 首页无 emoji，两张卡片显示"1"和"N"数字图标
- [ ] 卡片 hover 有边框高亮
- [ ] Cookie 状态灯颜色正确（绿=有效 / 黄=存在但无效 / 红=未设置）
- [ ] 点击 Cookie 状态栏 → 弹窗粘贴 Cookie → 状态变绿
- [ ] 进单视频页 → Cookie 标签显示 + 控件尺寸正确
- [ ] 已下载列表右键菜单：打开文件夹 / 复制路径
- [ ] 双击已下载项 → 打开文件夹
- [ ] "打开目录"和"刷新"按钮并排
- [ ] 进度条高度 8px、Splitter 比例正确
- [ ] 下载完成 → Cookie 标签同步 + 托盘通知弹出
- [ ] 进主页批量页 → 同上所有检查
- [ ] 返回首页 → Cookie 状态同步
- [ ] 全局暗色主题协调，文字清晰
- [ ] 所有按钮 hover/pressed 有视觉变化

### 系统托盘
- [ ] 托盘图标出现，悬停显示"抖净 DouClean"
- [ ] 右键菜单含：显示主窗口 / 开机自启 / 关于 / 退出
- [ ] 双击托盘图标 → 显示窗口
- [ ] 点 X 关闭 → 最小化到托盘（不退出），弹出"已最小化"提示
- [ ] 托盘「退出」→ 真正退出进程
- [ ] 开机自启勾选 → 注册表写入；取消勾选 → 注册表删除
- [ ] 下载中托盘 ToolTip 变"下载中..."，完成后恢复

### 单实例
- [ ] 双击 exe 再次启动 → 提示"程序已在运行中，请查看系统托盘"

### 窗口几何
- [ ] 拖动窗口位置、调整大小 → 关闭再启动 → 恢复到上次位置
- [ ] 首次启动 → 默认 820×640

### 拖放
- [ ] 从浏览器拖抖音链接到窗口 → 自动跳转对应页面并填入
- [ ] 拖普通文本 → 不响应

### 命令行参数
- [ ] `python unified_gui.py "https://v.douyin.com/xxx"` → 启动后自动填入
- [ ] `python unified_gui.py "https://www.douyin.com/user/xxx"` → 跳转主页页

### 快捷键
- [ ] `Ctrl+Q` → 退出
- [ ] `Ctrl+H` → 回首页
- [ ] `Ctrl+,` → 字体设置
- [ ] `Esc` → 最小化到托盘

### 异常处理
- [ ] 故意制造错误（如删掉 sign-server 文件夹后下载） → 弹友好提示而非崩溃
- [ ] `_debug.log` 文件生成在 EXE_DIR，含时间戳和错误详情

### 关于
- [ ] 关于对话框显示版本号、功能列表、快捷键、Gitee 链接
