# 抖音下载器 v1.0.0

抖音作品下载工具，支持**单视频下载**和**主页批量下载**。

---

## 用户使用说明

### 下载安装

1. 从 [发行版](https://gitee.com/Renxint/douyin-downloader) 下载最新 `抖音下载器.zip`
2. 解压到任意文件夹
3. 双击 `抖音下载器.exe` 即可运行

**系统要求：** Windows 10+，无需安装任何额外软件

---

### 获取 Cookie（必需）

下载需要登录态 Cookie，获取方式：

1. 浏览器打开 `douyin.com` → 右上角**扫码登录**
2. 按 `F12` 打开开发者工具 → 点击 **Network**（网络）标签
3. 按 `F5` 刷新页面，在左侧请求列表顶部的筛选框输入 `aweme`，可以看到筛选出抖音 API 请求
4. 随便点击其中一个（如 `post/` 或 `detail/` 或 `profile/other/`）
5. 右侧面板 → **Request Headers**（请求头）→ 找到 `Cookie:` 开头的那一行
6. 在 `Cookie:` 这一行上**右键 → Copy value**（复制值）
7. 打开下载器 → 粘贴到 Cookie 弹窗中 → 确定

> **为什么不能用书签脚本？** 书签脚本用的是 `document.cookie`，只能拿到普通 Cookie。
> 而 `sessionid`、`ttwid`、`sid_guard` 等关键登录 Cookie 的 `HttpOnly` 属性为 `true`，
> JavaScript 无法读取。**必须从 Network 请求头中获取完整 Cookie。**
>
> **如何判断 Cookie 是否正确？** 粘贴后如果包含 `sessionid=` 和 `ttwid=`，
> 说明获取成功。如果只有 `bd_ticket_guard`、`UIFID` 等字段而缺少这两个，则无效。
>
> Cookie 大约每 1-3 天过期，届时下载器会自动弹窗提示更新。重新按上述步骤获取即可。

---

### 使用方式

启动后有两个模式可选：

**📱 单视频下载：** 粘贴抖音分享链接（如复制口令文本），下载单个视频/图集/实况照片

**👤 主页批量下载：** 粘贴用户主页链接（如 `https://www.douyin.com/user/MS4wLjAB...`），下载该用户全部公开作品

下载的文件保存在 exe 同目录下的 `output/` 文件夹中。

---

## 版本内容

### v1.0.0 (2026-06-08)

- 单视频下载：支持视频、图集、实况照片
- 主页批量下载：自动翻页、跳过已下载
- Cookie 自动管理：过期弹窗更新
- 反馈功能：内置钉钉反馈通道
- 版本检测：启动时自动检查更新

---

## 开发者指南（如何更新 & 发布）

### 前置准备

1. Python 3.12 + PyInstaller
2. Node.js（用于打包）
3. Gitee 仓库权限

### 发布新版本流程

#### 1. 修改代码

在 `projects/douyin_downloader/` 目录下编辑源码：
- `unified_gui.py` — 主界面
- `src/api.py` — API 客户端
- `src/downloader.py` — 下载核心
- `sign-server/bootstrap.js` — 浏览器自动化

#### 2. 更新版本号

修改 `unified_gui.py` 中的 `VERSION` 变量，以及 `version.json`：

```json
{
  "version": "1.0.1",
  "date": "2026-06-XX",
  "url": "https://gitee.com/Renxint/douyin-downloader/raw/master/抖音下载器.zip",
  "note": "修复xxx问题，新增xxx功能"
}
```

#### 3. 打包

```bash
cd D:\Pycharm环境\Claude
pyinstaller --onedir --windowed --name "抖音下载器" \
  --icon="C:/Users/lenovo/Desktop/抖音下载器_风格3_纯白甜心.ico" \
  --add-data "projects/douyin_downloader/sign-server;sign-server" \
  --hidden-import PyQt6 --hidden-import requests \
  --hidden-import src.api --hidden-import src.downloader \
  --hidden-import certifi --collect-all certifi \
  --distpath "C:/Users/lenovo/Desktop" --workpath build_temp -y \
  projects/douyin_downloader/unified_gui.py
```

复制 Node.js 并打包 zip：

```bash
cp "/c/Program Files/nodejs/node.exe" "C:/Users/lenovo/Desktop/抖音下载器/_internal/node.exe"
cd C:/Users/lenovo/Desktop
powershell Compress-Archive -Path "抖音下载器" -DestinationPath "抖音下载器.zip"
```

#### 4. 上传 & 发布

1. 上传 `抖音下载器.zip` 到 Gitee 仓库
2. 更新 `version.json` 版本号
3. 提交并推送：

```bash
cd D:\Pycharm环境\Claude\projects\douyin_downloader
git add -A
git commit -m "v1.0.1: 修复xxx"
git push
```

推送后，所有用户启动时都会自动收到更新提示。

### 项目结构

```
douyin_downloader/
├── unified_gui.py        # 统一 GUI 入口
├── single_gui.py          # 单视频下载界面
├── main_gui.py            # 主页批量下载界面
├── main.py                # CLI 命令行入口
├── version.json           # 版本信息（公开访问）
├── src/
│   ├── api.py             # 抖音 API 客户端（Cookie 直连）
│   ├── downloader.py      # 主页批量下载核心
│   └── gui.py             # GUI 组件
├── sign-server/
│   ├── bootstrap.js       # 一次性 Puppeteer（单视频用）
│   ├── puppeteer-server.js # 常驻签名服务（备用）
│   └── sdk/               # 抖音签名 SDK
└── old_version_test/      # 旧版代码（存档）
```

### 钉钉反馈

反馈通过钉钉机器人推送到开发者。Webhook URL 在 `unified_gui.py` 的 `DINGTALK_WEBHOOK` 变量中配置。

### Gitee 仓库

https://gitee.com/Renxint/douyin-downloader
