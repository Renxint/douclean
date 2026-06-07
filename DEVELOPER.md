# 抖净 DouClean — 开发者指南

## 前置准备

1. Python 3.12 + PyInstaller
2. Node.js（用于单视频下载的浏览器自动化）
3. Gitee / GitHub 仓库推送权限

---

## 项目结构

```
douclean/
├── unified_gui.py        # 统一 GUI 入口
├── single_gui.py          # 单视频下载界面（独立版）
├── main_gui.py            # 主页批量下载界面（独立版）
├── main.py                # CLI 命令行入口
├── version.json           # 版本信息（客户端读取此文件检查更新）
├── app.ico                # 应用图标（替换此文件即可换图标）
├── src/
│   ├── api.py             # 抖音 API 客户端（Cookie 直连，无需签名）
│   ├── downloader.py      # 主页批量下载核心
│   └── gui.py             # GUI 组件
├── sign-server/
│   ├── bootstrap.js       # 一次性 Puppeteer（单视频用，用完即关）
│   ├── puppeteer-server.js # 常驻签名服务（备用）
│   └── sdk/               # 抖音签名 SDK（bdms.js 等）
└── old_version_test/      # 旧版代码（存档）
```

---

## 发布新版本流程

### 1. 修改代码

编辑 `src/` 下的源码。主要文件：
- `unified_gui.py` — 主界面
- `src/api.py` — API 客户端
- `src/downloader.py` — 下载核心
- `sign-server/bootstrap.js` — 浏览器自动化

### 2. 更新版本号

修改两处：

`unified_gui.py` 顶部：
```python
VERSION = "1.0.1"
```

`version.json`：
```json
{
  "version": "1.0.1",
  "date": "2026-06-XX",
  "url": "https://gitee.com/Renxint/douyin-downloader/raw/master/抖净.zip",
  "note": "修复xxx问题，新增xxx功能"
}
```

### 3. 打包

```bash
cd D:\Pycharm环境\Claude

pyinstaller --onedir --windowed --name "抖净" \
  --icon="dy.ico" \
  --add-data "projects/douclean/sign-server;sign-server" \
  --add-data "projects/douclean/app.ico;." \
  --hidden-import PyQt6 --hidden-import requests \
  --hidden-import src.api --hidden-import src.downloader \
  --hidden-import certifi --collect-all certifi \
  --distpath "D:/" --workpath build_temp -y \
  projects/douclean/unified_gui.py

# 复制 Node.js 运行环境
cp "/c/Program Files/nodejs/node.exe" "D:/抖净/_internal/node.exe"

# 清理临时文件
rm -rf build_temp
```

### 4. 上传 & 发布

1. 将 `D:/抖净/` 打包为 `抖净.zip`
2. 上传 `抖净.zip` 到 Gitee 仓库
3. 更新 `version.json`
4. 提交并推送：

```bash
cd D:\Pycharm环境\Claude\projects\douclean
git add -A
git commit -m "v1.0.1: 修复xxx"
git push gitee master
git push github master
```

推送后，所有用户下次启动时都会收到更新提示。

---

## 换图标

替换项目根目录的 `app.ico`，重新打包即可。窗口图标、任务栏图标、exe 图标会自动同步。

---

## 钉钉反馈

反馈通过钉钉机器人 Webhook 推送。URL 配置在 `unified_gui.py` 的 `DINGTALK_WEBHOOK` 变量中。

---

## 仓库地址

- Gitee: https://gitee.com/Renxint/douyin-downloader
- GitHub: https://github.com/Renxint/douclean
