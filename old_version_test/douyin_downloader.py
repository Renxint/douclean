# -*- coding: utf-8 -*-
"""
抖音用户主页一键下载脚本 v2

用法:
    python douyin_downloader.py
    输入: https://www.douyin.com/user/MS4wLjAB...?from_tab_name=main

特性:
    - 每个作品一个独立文件夹
    - 视频/图片按序号命名
    - 增量更新：新作品自动追加，旧作品不动
    - 作者删除/隐藏的作品，本地保留不删

前提: sign-server 已启动 (cd sign-server && npm start)
"""

import sys
import re
import time
import json
import requests
from pathlib import Path
from tqdm import tqdm

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from douyin_api import DouyinAPI

# ============ 配置 ============
def _get_base():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent

OUTPUT_ROOT = _get_base() / "output"
REQUEST_TIMEOUT = 60
PAGE_DELAY = 1.5
FOLDER_NAME_MAX_LEN = 40  # 文件夹名最大长度

# ============ 工具 ============

def clean_filename(name: str, max_len: int = FOLDER_NAME_MAX_LEN) -> str:
    """清除非法字符"""
    if not name:
        return "untitled"
    name = re.sub(r'[\\/:*?"<>|\x00-\x1F\x7F\n\r\t]', '', name)
    name = name.strip().rstrip('. ')
    if len(name) > max_len:
        name = name[:max_len]
    return name or "untitled"


def parse_sec_user_id(url: str) -> str:
    """从主页URL提取sec_user_id"""
    match = re.search(r'/user/(MS4wLjAB[A-Za-z0-9_\-]+)', url.strip())
    if match:
        return match.group(1)
    raise ValueError(f"无法从URL提取sec_user_id: {url}")


def load_tracker(tracker_path: Path) -> dict:
    """加载下载记录"""
    if tracker_path.exists():
        try:
            return json.loads(tracker_path.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def save_tracker(tracker_path: Path, tracker: dict):
    """保存下载记录"""
    tracker_path.write_text(json.dumps(tracker, ensure_ascii=False, indent=2),
                           encoding='utf-8')


def download_file(url: str, save_path: Path, desc: str, headers: dict) -> bool:
    """下载单个文件，已存在则跳过"""
    if save_path.exists():
        return True

    try:
        resp = requests.get(url, headers=headers, stream=True,
                          timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        total = int(resp.headers.get('content-length', 0))
        with open(save_path, 'wb') as f:
            with tqdm(total=total, unit='B', unit_scale=True,
                     desc=desc, leave=False, ncols=80) as bar:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
                    bar.update(len(chunk))
        return True
    except Exception as e:
        print(f"  ! {e}")
        if save_path.exists():
            save_path.unlink()
        return False


def pick_best_url(url_list: list, prefer: str = "jpeg") -> str:
    """从多个URL中优先选择指定格式，降级到第一个"""
    if not url_list:
        return ""
    for u in url_list:
        if prefer in u.lower():
            return u
    return url_list[0]


def get_ext_from_url(url: str, fallback: str = ".jpg") -> str:
    """从URL提取文件扩展名"""
    import urllib.parse
    path = urllib.parse.urlparse(url).path
    # 去掉 :q75 这样的质量参数
    base = path.split('?')[0].split(':')[0]
    ext = base.split('.')[-1].lower() if '.' in base else ''
    if ext in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
        return '.' + ('jpg' if ext == 'jpeg' else ext)
    return fallback


# ============ 主逻辑 ============

class DouyinDownloader:
    def __init__(self):
        self.api = DouyinAPI()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                         'AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36',
            'Referer': 'https://www.douyin.com/',
        }
        self.new_videos = 0
        self.new_images = 0
        self.new_music = 0
        self.skipped = 0
        self.failed = 0

    def download_user(self, homepage_url: str):
        sec_id = parse_sec_user_id(homepage_url)
        print(f"sec_user_id: {sec_id[:24]}...")

        # ---- 获取全部作品列表 ----
        print("获取作品列表...")
        all_posts = []
        cursor = 0
        author_name = ""
        page = 0

        while page < 50:
            page += 1
            data = self.api.get_user_posts(sec_id, max_cursor=cursor, count=18)
            aweme_list = data.get("aweme_list", [])
            if not aweme_list:
                break
            all_posts.extend(aweme_list)
            if not author_name and aweme_list:
                author_name = aweme_list[0].get("author", {}).get("nickname", "")
            print(f"  第{page}页: {len(aweme_list)}条, 累计{len(all_posts)}条, has_more={data.get('has_more')}")
            if not data.get("has_more", 0):
                break
            cursor = data.get("max_cursor", 0)
            time.sleep(PAGE_DELAY)

        print(f"作品总数: {len(all_posts)}  作者: {author_name}")

        # ---- 准备输出目录 ----
        safe_author = clean_filename(author_name, 20) if author_name else sec_id[:8]
        out_dir = OUTPUT_ROOT / safe_author
        out_dir.mkdir(parents=True, exist_ok=True)

        tracker_path = out_dir / ".downloaded.json"
        tracker = load_tracker(tracker_path)

        # ---- 逐个作品下载 ----
        total = len(all_posts)
        for i, post in enumerate(all_posts):
            aweme_id = post.get("aweme_id", "")
            desc = clean_filename(post.get("desc", "")) or aweme_id

            # 作品文件夹
            folder_name = f"{i+1:03d}_{desc}"
            post_dir = out_dir / folder_name

            # 检查是否已下载
            if aweme_id in tracker:
                self.skipped += 1
                continue

            post_dir.mkdir(parents=True, exist_ok=True)
            print(f"[{i+1}/{total}] {folder_name}")

            # 记录将要下载的内容
            has_video = bool(post.get("video"))
            has_images = bool(post.get("images"))
            images = post.get("images") or []

            ok = True

            # --- 下载视频 (无水印优先) ---
            has_real_video = False
            if has_video:
                vdata = post["video"]
                da_urls = (vdata.get("download_addr") or {}).get("url_list") or []
                pa_urls = (vdata.get("play_addr") or {}).get("url_list") or []
                raw = (da_urls[0] if da_urls else None) or (pa_urls[0] if pa_urls else None)
                if raw and ".mp3" not in raw.lower():
                    has_real_video = True
                    vpath = post_dir / "video.mp4"
                    if download_file(raw, vpath, f"  video", self.headers):
                        self.new_videos += 1
                    else:
                        self.failed += 1
                        ok = False

            # --- 下载背景音乐 (仅图集/幻灯片, 视频已有音轨) ---
            if not has_real_video:
                music = post.get("music") or {}
                mp = music.get("play_url")
                mp_urls = (mp.get("url_list") if isinstance(mp, dict) else
                           [mp] if isinstance(mp, str) and mp else [])
                if mp_urls:
                    mpath = post_dir / "music.mp3"
                    if not mpath.exists():
                        if download_file(mp_urls[0], mpath, f"  music", self.headers):
                            self.new_music += 1
                        else:
                            self.failed += 1

            # --- 下载图集 ---
            if has_images:
                for j, img in enumerate(images):
                    img_urls = img.get("url_list", [])
                    # 优先 jpg/jpeg 原图，其次 webp
                    img_url = pick_best_url(img_urls, "jpeg") or pick_best_url(img_urls, "jpg")
                    if not img_url:
                        continue
                    ext = get_ext_from_url(img_url, ".jpg")
                    img_path = post_dir / f"{j+1:02d}{ext}"
                    if download_file(img_url, img_path,
                                   f"  img {j+1}/{len(images)}", self.headers):
                        self.new_images += 1
                    else:
                        self.failed += 1
                        ok = False

            # --- 纯文本/无媒体 ---
            if not has_video and not has_images:
                print(f"  (无媒体内容)")
                self.skipped += 1

            # 标记已下载
            if ok:
                tracker[aweme_id] = {
                    "desc": desc,
                    "folder": folder_name,
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            else:
                tracker[aweme_id] = {
                    "desc": desc,
                    "folder": folder_name,
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "partial": True,
                }

        # ---- 保存记录 ----
        save_tracker(tracker_path, tracker)

        # ---- 汇总 ----
        print(f"\n{'='*40}")
        print(f"  新增视频: {self.new_videos}")
        print(f"  新增图片: {self.new_images}")
        print(f"  新增音乐: {self.new_music}")
        print(f"  跳过(已下载): {self.skipped}")
        print(f"  失败: {self.failed}")
        print(f"  输出: {out_dir}")
        print(f"{'='*40}")


# ============ CLI ============

def main():
    print("=" * 50)
    print("  抖音用户主页下载 v2")
    print("=" * 50)

    # 检查签名服务
    try:
        resp = requests.get("http://localhost:8765/health", timeout=5)
        if resp.json().get("status") != "ok":
            print("[ERROR] 签名服务未就绪，请先: cd sign-server && npm start")
            return
    except Exception:
        print("[ERROR] 签名服务不可用 (http://localhost:8765)")
        return

    print("[OK] 签名服务就绪\n")

    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("请输入抖音用户主页URL: ").strip()

    if not url:
        print("[ERROR] 未输入URL")
        return

    downloader = DouyinDownloader()
    try:
        downloader.download_user(url)
    except Exception as e:
        print(f"\n[FATAL] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
