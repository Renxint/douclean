# -*- coding: utf-8 -*-
"""抖净 DouClean — 公共工具函数"""

import re


def clean_name(name: str, max_len: int = 50) -> str:
    """清除文件名非法字符"""
    if not name:
        return "untitled"
    name = re.sub(r'[\\/:*?"<>|\x00-\x1F\x7F\n\r\t]', '', name)
    name = re.sub(r'[​-‏ - ﻿ -‏]', '', name)
    name = name.strip().rstrip('. ')
    if len(name) > max_len:
        name = name[:max_len].strip().rstrip('. ')
    return name or "untitled"


def pick_best_video_url(vdata: dict) -> str:
    """从视频数据中选最优画质 URL"""
    def _first(urls):
        for u in (urls or []):
            if u and ".mp3" not in u:
                return u
        return ""

    bit_rates = vdata.get("bit_rate") or []
    if bit_rates:
        best = max(bit_rates, key=lambda b: b.get("bit_rate", 0))
        return _first((best.get("play_addr") or {}).get("url_list") or [])

    return (
        _first((vdata.get("download_addr") or {}).get("url_list") or [])
        or _first((vdata.get("play_addr") or {}).get("url_list") or [])
    )


def pick_best_url(url_list: list, prefer: str = "jpeg") -> str:
    """从多个 URL 中优先选择指定格式"""
    if not url_list:
        return ""
    for u in url_list:
        if prefer in u.lower():
            return u
    return url_list[0]


def parse_sec_user_id(url: str) -> str:
    """从主页 URL 提取 sec_user_id"""
    m = re.search(r'/user/(MS4wLjAB[A-Za-z0-9_\-]+)', url.strip())
    if m:
        return m.group(1)
    raise ValueError(f"无法提取 sec_user_id: {url}")


def classify_url(url: str) -> str:
    """自动识别链接类型: single / homepage"""
    # 短链接
    if 'v.douyin.com' in url:
        return "single"
    # 视频/图文
    if re.search(r'/(?:video|note)/(\d+)', url):
        return "single"
    # 用户主页
    if '/user/MS4wLjAB' in url:
        return "homepage"
    raise ValueError(f"无法识别链接类型: {url[:60]}")


def compare_versions(v1: str, v2: str) -> int:
    """比较语义化版本: 返回 -1/0/1"""
    def to_tuple(v):
        try:
            return tuple(map(int, v.split(".")))
        except (ValueError, AttributeError):
            return (0,)
    t1, t2 = to_tuple(v1), to_tuple(v2)
    if t1 < t2: return -1
    if t1 > t2: return 1
    return 0


def safe_read(path) -> str:
    """线程安全读文件"""
    import threading
    lock = threading.Lock()
    with lock:
        if path.exists():
            return path.read_text(encoding='utf-8').strip()
    return ""


def safe_read_json(path, default=None):
    """线程安全读 JSON"""
    import json
    try:
        raw = safe_read(path)
        return json.loads(raw) if raw else (default or {})
    except (json.JSONDecodeError, ValueError):
        return default or {}


def safe_write_json(path, data: dict):
    """线程安全写 JSON（原子替换）"""
    import json
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)
