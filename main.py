# -*- coding: utf-8 -*-
"""
抖音用户主页下载器 - CLI 入口

用法:
    python main.py
    python main.py https://www.douyin.com/user/MS4wLjAB...
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Claude/
PROJECT_DIR = Path(__file__).resolve().parent  # douyin_downloader/
for p in (str(PROJECT_ROOT), str(PROJECT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.utils.logger import get_logger

logger = get_logger(__name__)
COOKIE_FILE = PROJECT_DIR / "data" / "Cookie.txt"


def ensure_cookie() -> str:
    """确保 Cookie 有效：读文件 → 检查 → 过期则提示重新输入 → 保存 → 循环"""
    from src.api import DouyinAPI

    while True:
        cookie_str = ""
        if COOKIE_FILE.exists():
            cookie_str = COOKIE_FILE.read_text(encoding='utf-8').strip()

        if cookie_str:
            api = DouyinAPI(cookie_string=cookie_str)
            if api.check_cookie():
                logger.info(f"Cookie 有效 ({len(cookie_str)} 字符)")
                return cookie_str
            logger.warning("Cookie 已过期/被封!")
        else:
            logger.info("未找到 Cookie 文件")

        new_cookie = input("请粘贴新的 Cookie (直接回车取消): ").strip()
        if not new_cookie:
            logger.error("未提供 Cookie，退出")
            sys.exit(1)

        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        COOKIE_FILE.write_text(new_cookie, encoding='utf-8')
        logger.info(f"Cookie 已保存 ({len(new_cookie)} 字符)，重新检查...")


def main():
    logger.info("=" * 50)
    logger.info("  抖音用户主页下载 v2 (直连模式)")
    logger.info("=" * 50)

    cookie_str = ensure_cookie()

    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("请输入抖音用户主页URL: ").strip()

    if not url:
        logger.error("未输入URL")
        return

    from src.downloader import DouyinDownloader

    downloader = DouyinDownloader(cookie_string=cookie_str)
    try:
        downloader.download_user(url)
    except Exception as e:
        logger.error(f"下载失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
