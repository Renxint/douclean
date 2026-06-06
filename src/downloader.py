# -*- coding: utf-8 -*-
"""
抖音用户主页下载核心逻辑
"""

import sys
import re
import time
import json
from pathlib import Path
from typing import List, Dict

# 确保可以导入 shared 库及本项目的 src
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # Claude/
PROJECT_DIR = Path(__file__).resolve().parent.parent  # douyin_downloader/
for p in (str(PROJECT_ROOT), str(PROJECT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import requests
from tqdm import tqdm

import logging
from src.api import DouyinAPI

logger = logging.getLogger(__name__)

# ============ 配置 ============
PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_DIR / "output"
REQUEST_TIMEOUT = 60
PAGE_DELAY = 1.5
FOLDER_NAME_MAX_LEN = 40  # 文件夹名最大长度


# ============ 工具函数 ============

def clean_filename(name: str, max_len: int = FOLDER_NAME_MAX_LEN) -> str:
    """清除非法字符，包括Unicode零宽/不可见字符"""
    if not name:
        return "untitled"
    # 移除文件系统非法字符 (ASCII 控制字符 + Windows 非法符号)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1F\x7F\n\r\t]', '', name)
    # 移除 Unicode 格式控制字符 (Cf类: 零宽空格/连接符/方向标记/BOM等)
    name = re.sub(r'[​-‏ - ﻿ ⁠-⁯]', '', name)
    name = name.strip().rstrip('. ')
    # 截断后必须再次strip
    if len(name) > max_len:
        name = name[:max_len].strip().rstrip('. ')
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
    tracker_path.write_text(
        json.dumps(tracker, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )


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
        logger.error(f"下载失败: {e}")
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


def pick_best_video_url(vdata: dict) -> str:
    """
    从视频数据中选出最优画质的下载URL。

    优先级:
      1. bit_rate 中最高码率的 play_addr.url_list[0] (最接近原画)
      2. download_addr.url_list[0] (无水印下载地址)
      3. play_addr.url_list[0] (普通播放地址)
      4. play_addr_h264 / play_addr_lowbr 降级兜底
    自动跳过纯音频链接 (.mp3)
    """
    def _is_video(u: str) -> bool:
        return bool(u) and ".mp3" not in u.lower()

    def _first_valid(urls: list) -> str:
        for u in (urls or []):
            if _is_video(u):
                return u
        return ""

    # 1) 从 bit_rate 数组选最高码率
    bit_rates = vdata.get("bit_rate") or []
    if bit_rates:
        best = max(bit_rates, key=lambda b: b.get("bit_rate", 0))
        url = _first_valid((best.get("play_addr") or {}).get("url_list") or [])
        if url:
            return url

    # 2) download_addr (无水印)
    da = vdata.get("download_addr") or {}
    url = _first_valid(da.get("url_list") or [])
    if url:
        return url

    # 3) play_addr
    pa = vdata.get("play_addr") or {}
    url = _first_valid(pa.get("url_list") or [])
    if url:
        return url

    # 4) 降级兜底: play_addr_h264 -> play_addr_lowbr
    for key in ("play_addr_h264", "play_addr_lowbr"):
        pa = vdata.get(key) or {}
        url = _first_valid(pa.get("url_list") or [])
        if url:
            return url

    return ""


# ============ 下载器 ============

class DouyinDownloader:
    """抖音用户主页下载器"""

    def __init__(self, cookie_string: str = ""):
        self.api = DouyinAPI(cookie_string=cookie_string)
        self.headers = {
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/141.0.0.0 Safari/537.36 '
                          'SLBrowser/9.0.8.5161 SLBChan/111 SLBVPV/64-bit'),
            'Referer': 'https://www.douyin.com/',
        }
        self.new_videos = 0
        self.new_images = 0
        self.new_music = 0
        self.skipped = 0
        self.failed = 0

    def download_user(self, homepage_url: str):
        sec_id = parse_sec_user_id(homepage_url)
        logger.info(f"sec_user_id: {sec_id[:24]}...")

        # ---- 获取用户简介 ----
        profile = self.api.get_user_profile(sec_id)

        # ---- 获取全部作品列表 ----
        logger.info("获取作品列表...")
        all_posts = []
        cursor = 0
        author_name = profile.get("nickname", "")

        while True:
            data = self.api.get_user_posts(sec_id, max_cursor=cursor, count=18)
            aweme_list = data.get("aweme_list", [])
            if not aweme_list:
                break
            all_posts.extend(aweme_list)
            if not author_name and aweme_list:
                author_name = aweme_list[0].get("author", {}).get("nickname", "")
            if not data.get("has_more", 0):
                break
            cursor = data.get("max_cursor", 0)
            time.sleep(PAGE_DELAY)

        logger.info(f"作品总数: {len(all_posts)}  作者: {author_name}")

        # ---- 准备输出目录 ----
        safe_author = clean_filename(author_name, 20) if author_name else sec_id[:8]
        out_dir = OUTPUT_ROOT / safe_author
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
            f"- 主页链接: {homepage_url}",
            f"- 下载日期: {download_date}",
            f"- 头像: {profile.get('avatar_url', 'N/A')}",
            f"",
        ]
        (out_dir / "主页信息.md").write_text("\n".join(info_lines), encoding='utf-8')

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
            logger.info(f"[{i+1}/{total}] {folder_name}")

            # 保存作品文案
            desc_path = post_dir / "desc.md"
            if not desc_path.exists():
                desc_path.write_text(post.get("desc", ""), encoding='utf-8')

            has_video = bool(post.get("video"))
            has_images = bool(post.get("images"))
            images = post.get("images") or []

            ok = True

            # --- 下载视频 (bit_rate 最高画质 > 无水印 > 播放地址) ---
            has_real_video = False
            if has_video:
                best_url = pick_best_video_url(post["video"])
                if best_url:
                    has_real_video = True
                    vpath = post_dir / "video.mp4"
                    if download_file(best_url, vpath, "  video", self.headers):
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
                        if download_file(mp_urls[0], mpath, "  music", self.headers):
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
                    is_live = img.get('live_photo_type', 0) == 1
                    live_tag = '(实况)' if is_live else ''
                    img_path = post_dir / f"{j+1:02d}{live_tag}{ext}"
                    if download_file(img_url, img_path,
                                    f"  img {j+1}/{len(images)}", self.headers):
                        self.new_images += 1
                    else:
                        self.failed += 1
                        ok = False

                    # 实况图: 下载关联视频 (bit_rate 最高画质优先)
                    if is_live:
                        lv = img.get('video') or {}
                        best_live_url = pick_best_video_url(lv)
                        if best_live_url:
                            live_path = post_dir / f"{j+1:02d}{live_tag}.mp4"
                            if download_file(best_live_url, live_path,
                                            f"  live {j+1}/{len(images)}", self.headers):
                                self.new_videos += 1
                            else:
                                self.failed += 1

            # --- 纯文本/无媒体 ---
            if not has_video and not has_images:
                logger.info("  (无媒体内容)")
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
        summary = (
            f"\n{'='*40}\n"
            f"  新增视频: {self.new_videos}\n"
            f"  新增图片: {self.new_images}\n"
            f"  新增音乐: {self.new_music}\n"
            f"  跳过(已下载): {self.skipped}\n"
            f"  失败: {self.failed}\n"
            f"  输出: {out_dir}\n"
            f"{'='*40}"
        )
        logger.info(summary)
        return summary
