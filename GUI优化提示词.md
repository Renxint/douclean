# 抖净 DouClean — GUI 优化提示词

> 喂给另一个 Claude，它就能直接改 `unified_gui.py`。只改 UI 层，不动任何下载逻辑。

---

## 任务

优化 `unified_gui.py` 的 GUI 界面，应用 **Cinema Dark 设计系统**。**禁止修改**任何下载线程、API 调用、Cookie 处理、字体保存、版本检测等逻辑代码。

---

## 一、配色全局替换

把 `STYLE` 样式表（约 489-541 行）的配色全部换成：

| 用途 | 旧值 | 新值 |
|------|------|------|
| 窗口/主背景 | `#1a1a2e` | `#0A0A14` |
| 输入框/卡片背景 | `#16213e` | `#12122A` |
| 边框 | `#0f3460` | `#252550` |
| CTA 按钮 | `#e94560` | `#E11D48` |
| CTA hover | `#ff6b81` | `#FF3566` |
| CTA pressed | 无 | `#C0183D` |
| 主文字 | `#e0e0e0` | `#F1F5F9` |
| 辅助文字 | `#8b949e` | `#94A3B8` |
| 弱文字 | `#555` | `#64748B` |
| 日志区背景 | `#0d1117` | `#0B0B1A` |
| 二级按钮背景 | `#0f3460` | `#18183A` |
| 二级按钮 hover | `#1a4a7a` | `#1E1E48` |
| 二级按钮边框 | 无 | `1px solid #252550` |
| 统一圆角 | `6px` | `8px` |
| 卡片圆角(modeBtn) | `12px` | `16px` |
| 输入框 focus 边框 | `#e94560` | `#E11D48` |
| 进度条背景 | `#16213e` | `#12122A` |
| 进度条填充 | `#e94560` | `#E11D48` |
| Splitter 手柄 | `#0f3460` | `#1E1E48`, 宽 `2px` |

**新增样式**（原有 STYLE 里没有的，要加）：

```css
/* 滚动条 */
QScrollBar:vertical { background: #0A0A14; width: 8px; border-radius: 4px; margin: 0; }
QScrollBar::handle:vertical { background: #334155; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #475569; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #0A0A14; height: 8px; }
QScrollBar::handle:horizontal { background: #334155; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #475569; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* 右键菜单 */
QMenu { background: #12122A; color: #F1F5F9; border: 1px solid #252550; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 8px 32px 8px 16px; border-radius: 4px; }
QMenu::item:selected { background: #E11D48; }

/* 下拉框箭头 */
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 6px solid #94A3B8; margin-right: 6px; }

/* 提示框 */
QToolTip { background: #1A1A3E; color: #F1F5F9; border: 1px solid #252550; border-radius: 6px; padding: 8px 12px; font-size: 12px; }

/* 分隔线 */
QFrame#separator { background: #1E1E48; max-height: 1px; }

/* 幽灵按钮(透明底) */
QPushButton#ghostBtn { background: transparent; color: #94A3B8; border: 1px solid transparent; font-weight: normal; }
QPushButton#ghostBtn:hover { background: #18183A; color: #F1F5F9; border-color: #252550; }

/* 禁用态统一 */
QPushButton:disabled { background: #1A1A2E; color: #475569; border-color: #1A1A2E; }

/* 输入框 focus */
QLineEdit:focus { border: 1px solid #E11D48; background: #161632; }
QLineEdit:disabled { background: #0E0E1E; color: #475569; border-color: #1A1A30; }

/* 下拉框 hover/focus */
QComboBox:hover { border: 1px solid #E11D48; }
QComboBox QAbstractItemView { background: #12122A; color: #F1F5F9; border: 1px solid #252550; selection-background: #E11D48; outline: none; padding: 4px; }

/* 列表项 */
QListWidget::item { padding: 10px 12px; border-radius: 6px; margin: 1px 0; }
QListWidget::item:selected { background: #E11D48; color: #FFFFFF; }
QListWidget::item:hover { background: #18183A; }

/* 按钮 pressed 态 */
QPushButton:pressed { background: #C0183D; }
QPushButton#secondaryBtn:pressed { background: #12122A; }
QPushButton#modeBtn:pressed { background: #0E0E22; border-color: #C0183D; }

/* Messagebox */
QMessageBox { background: #0A0A14; }
QMessageBox QLabel { color: #F1F5F9; font-size: 14px; }
QMessageBox QPushButton { min-width: 80px; padding: 8px 16px; }
```

---

## 二、首页 (ModePage) 大改

### 2.1 去掉 emoji

把 `📱 单视频下载\n\n粘贴分享链接\n下载单个视频/图集` 这种 emoji+文字的大按钮，改成**卡片式 QPushButton**：

```python
# 单视频卡片 — 在 QPushButton#modeBtn 内部包一个 QVBoxLayout
s_icon = QLabel("1")  # 不用 emoji，用数字
s_icon.setStyleSheet("font-size:32px; font-weight:800; color:#E11D48; "
                     "background:#1A1030; border-radius:12px; "
                     "min-width:52px; max-width:52px; min-height:52px; max-height:52px;")
s_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

s_title = QLabel("单视频下载")
s_title.setStyleSheet("font-size:18px; font-weight:700; color:#F1F5F9;")

s_desc = QLabel("粘贴抖音分享链接\n下载视频 / 图集 / 实况照片\n自动创建文件夹分类")
s_desc.setStyleSheet("font-size:12px; color:#64748B;")

# 主页卡片同理，图标用 "N"
```

两张卡片并排，`setMinimumSize(260, 220)`，间距 24px。

### 2.2 新增 Cookie 状态栏

在两张卡片下方、分隔线之后，增加 Cookie 状态显示：

```
[●] Cookie 已就绪 (2834字符) · 06-07 08:30    [更新Cookie]
```

- 绿点 `#22C55E` = Cookie 有效（包含 `sessionid=` 和 `ttwid=`）
- 黄点 `#F59E0B` = Cookie 存在但无效/过期
- 红点 `#EF4444` = Cookie 未设置
- 右侧按钮用 `ghostBtn` 样式，点击弹 `QInputDialog.getMultiLineText` 输入 Cookie

**新增工具函数**（放在文件顶部 `ensure_cookie()` 旁边）：

```python
def get_cookie_status() -> dict:
    if not COOKIE_FILE.exists():
        return {"ok": False, "length": 0, "mtime": None}
    try:
        cookie = COOKIE_FILE.read_text(encoding='utf-8').strip()
        mtime = COOKIE_FILE.stat().st_mtime
        return {
            "ok": bool(cookie) and "sessionid=" in cookie and "ttwid=" in cookie,
            "length": len(cookie),
            "mtime": mtime,
        }
    except:
        return {"ok": False, "length": 0, "mtime": None}
```

**ModePage 新增方法**：
- `refresh_cookie_status()` — 调用 `get_cookie_status()`，更新图标颜色和文字
- `_set_cookie()` — 弹窗粘贴 Cookie，保存后调 `refresh_cookie_status()` + emit `cookie_updated`

**ModePage 新增信号**：`cookie_updated = pyqtSignal()`

### 2.3 标题区优化

```
DouClean  [v1.0.0]        ← 标题 32px 粗体 #F1F5F9，版本标签红底白字圆角
抖净 · 抖音无水印下载工具   ← 副标题 14px #64748B
───────────────            ← QFrame#separator, 宽 320px
```

### 2.4 底部按钮

字体设置和反馈建议保持原样，用 `secondaryBtn` 样式，固定宽 110px。

---

## 三、单视频页面 (SinglePage) 微调

### 3.1 顶栏

```python
back = QPushButton("  < 返回")  # 不用 ← emoji
back.setFixedHeight(36)

# 右侧加 Cookie 状态小标签
cs = get_cookie_status()
cookie_label = QLabel("Cookie OK" if cs["ok"] else "Cookie !")
cookie_label.setStyleSheet(f"font-size:11px; color:{'#22C55E' if cs['ok'] else '#F59E0B'};"
                           f"background:#111128; border-radius:4px; padding:4px 10px;")
# 保存引用: self._cookie_label = cookie_label
```

### 3.2 输入框和按钮

- URL 输入框: `setMinimumHeight(42)`
- 下载按钮: 文字改为 `"开始下载"`，`setFixedHeight(42)`，`setMinimumWidth(100)`
- 下载中: `self.dl_btn.setText("下载中...")`
- 浏览按钮: 文字改为 `"浏览..."`，`setFixedHeight(36)`

### 3.3 进度条

`self.progress.setFixedHeight(8)`

### 3.4 已下载列表 — 加右键菜单

```python
self.downloaded_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
self.downloaded_list.customContextMenuRequested.connect(self._on_context_menu)
self.downloaded_list.itemDoubleClicked.connect(self._open_folder)
```

右键菜单方法：
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
    if action == open_action and Path(p).exists(): os.startfile(p)
    elif action == copy_action: QApplication.clipboard().setText(p)
```

### 3.5 下载完成后更新 Cookie 标签

在 `_done()` 方法末尾加：
```python
cs = get_cookie_status()
self._cookie_label.setText("Cookie OK" if cs["ok"] else "Cookie !")
self._cookie_label.setStyleSheet(...)
```

### 3.6 布局微调

- "打开目录"和"刷新"两个按钮包进 `QHBoxLayout` 并排
- Splitter 分屏比例 `setSizes([480, 240])`
- 标签文字 `"保存路径"` → `"保存到"`
- 标签文字 `"日志"` → `"下载日志"`

---

## 四、主页批量页面 (HomepagePage) 微调

改动与 SinglePage 基本一致：
- 返回按钮 `"  < 返回"`，`setFixedHeight(36)`
- 右侧 Cookie 标签 `self._cookie_label`
- URL 输入框 `setMinimumHeight(42)`
- 按钮 `"开始下载"` / `"下载中..."`，`setFixedHeight(42)`
- 浏览按钮 `"浏览..."`，`setFixedHeight(36)`
- 进度条 `setFixedHeight(8)`
- 用户列表加右键菜单（同 SinglePage）+ 双击打开
- Splitter 分屏比例 `setSizes([520, 280])`
- `_done()` 末尾更新 Cookie 标签
- 标签文字 `"保存路径"` → `"保存到"`

---

## 五、主窗口 (MainWindow) 小改

### 5.1 返回首页时刷新 Cookie

```python
def _go_home(self):
    self.mode_page.refresh_cookie_status()
    self.stack.setCurrentIndex(0)
```

把 `single_page.back_clicked` 和 `homepage_page.back_clicked` 的信号绑定改掉：

```python
# 旧: self.single_page.back_clicked.connect(lambda: self.stack.setCurrentIndex(0))
# 新:
self.single_page.back_clicked.connect(lambda: self._go_home())
self.homepage_page.back_clicked.connect(lambda: self._go_home())
```

### 5.2 Cookie 更新回调

```python
self.mode_page.cookie_updated.connect(self._on_cookie_updated)

def _on_cookie_updated(self):
    """Cookie 更新后同步到子页面的标签"""
    self.single_page._cookie_label.setText("Cookie OK")
    self.single_page._cookie_label.setStyleSheet(
        "font-size:11px; color:#22C55E; background:#111128; border-radius:4px; padding:4px 10px;")
    self.homepage_page._cookie_label.setText("Cookie OK")
    self.homepage_page._cookie_label.setStyleSheet(
        "font-size:11px; color:#22C55E; background:#111128; border-radius:4px; padding:4px 10px;")
```

### 5.3 窗口尺寸

```python
self.resize(820, 640)
self.setMinimumSize(640, 480)
```

---

## 六、main() 调色板

把 `main()` 函数中的 `QPalette` 值换成：

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

## 七、import 补充

文件顶部 import 区域增加（如果还没有的话）：
```python
QFrame, QSizePolicy, QScrollArea  # 从 PyQt6.QtWidgets
QTimer, QPropertyAnimation, QEasingCurve, QSize  # 从 PyQt6.QtCore
QFontDatabase  # 从 PyQt6.QtGui
```

---

## ⚠️ 红线 — 绝对不要改的

- 所有下载线程类（`SingleDownloadThread`、`HomepageDownloadThread`）
- `ensure_cookie()` 函数（但可以新增 `get_cookie_status()`）
- `clean_name()`、`pick_best_video_url()`、`parse_sec_user_id()`
- `load_font()`、`save_font()`
- `_check_version()`
- 路径配置（`BASE_DIR`、`EXE_DIR`、`BOOTSTRAP_JS` 等）
- 反馈发送逻辑（`_send_feedback`）
- 所有下载开始/暂停/取消的业务逻辑
- 版本号 `VERSION`

---

## 验证

改完后运行：
```bash
python D:\Pycharm环境\Claude\projects\douclean\unified_gui.py
```

检查清单：
- [ ] 首页无 emoji，两张卡片好看
- [ ] Cookie 状态灯正确显示（绿/黄/红）
- [ ] 点击设置 Cookie → 弹窗 → 粘贴 → 状态变绿
- [ ] 进单视频页 → 返回按钮/输入框/按钮都好看
- [ ] 已下载列表右键菜单正常
- [ ] 双击已下载项 → 打开文件夹
- [ ] 进主页批量页 → 同上
- [ ] 返回首页 → Cookie 状态同步
- [ ] 全局暗色主题协调，文字清晰
- [ ] 所有按钮 hover 有视觉变化
