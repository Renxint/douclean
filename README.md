# 抖音下载器

> 抖音用户主页视频/图集一键下载，支持增量更新、断点续传

## 功能

- 输入抖音用户主页链接，自动下载全部作品
- 视频: 自动选最高画质 (bit_rate > 无水印 > 普通)
- 图集: 批量下载图片 + 实况图联动视频
- 增量更新: 已下载的作品跳过，新作品自动追加
- PyQt6 桌面界面: 暂停/继续/取消，下载历史管理

## 架构

```
├── main.py             # CLI 入口
├── main_gui.py         # GUI 入口
├── src/
│   ├── api.py          # 抖音 API 客户端 (通过 sign-server 代理)
│   ├── downloader.py   # 下载核心逻辑
│   └── gui.py          # PyQt6 桌面界面
├── sign-server/        # Node.js 签名服务
├── output/             # 下载输出 (不进 git)
└── requirements.txt
```

## 使用方法

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 启动签名服务 (Node.js)
cd sign-server
npm install
npm start        # Puppeteer 模式
# 或
npm run start-vm # VM 补环境模式

# 3. 运行
python main.py              # CLI 交互模式
python main.py <URL>        # CLI 直接下载
python main_gui.py          # GUI 桌面界面
```

或双击 `启动.bat` 一键启动 (自动拉起签名服务 + GUI)。

## 输出

每个用户一个独立文件夹 `output/<作者名>/`:
```
output/作者名/
├── 主页链接.md
├── .downloaded.json        # 下载记录 (增量更新)
├── 001_作品描述/
│   ├── desc.md             # 文案
│   ├── video.mp4           # 视频
│   └── 01.jpg              # 图片
├── 002_另一个作品/
│   └── ...
```
