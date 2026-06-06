# -*- coding: utf-8 -*-
"""
抖音 API 客户端 - 通过本地签名服务代发请求
依赖 sign-server (Node.js + Puppeteer) 运行在 localhost:8765
"""
import sys, time, json, requests
from pathlib import Path
from typing import Optional, Dict, List, Any


class DouyinAPI:
    """抖音 API 客户端"""

    def __init__(self, sign_server: str = "http://localhost:8765"):
        self.sign_server = sign_server
        self._check_health()

    def _check_health(self) -> bool:
        try:
            resp = requests.get(f"{self.sign_server}/health", timeout=5)
            return resp.json().get("status") == "ok"
        except:
            return False

    def fetch(self, url: str, method: str = "GET",
              headers: Optional[Dict] = None, body: Any = None,
              timeout: int = 30) -> Dict:
        payload = {"url": url, "method": method}
        if headers: payload["headers"] = headers
        if body: payload["body"] = body
        resp = requests.post(f"{self.sign_server}/fetch", json=payload, timeout=timeout)
        return resp.json()

    def get_user_posts(self, sec_user_id: str, max_cursor: int = 0,
                        count: int = 18) -> Dict:
        """获取用户帖子列表（单页）"""
        params = {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "sec_user_id": sec_user_id,
            "max_cursor": str(max_cursor),
            "locate_query": "true",
            "show_live_replay_strategy": "1",
            "need_time_list": "0",
            "time_list_query": "0",
            "count": str(count),
            "publish_video_strategy_type": "2",
            "pc_client_type": "1",
            "version_code": "290100",
            "version_name": "29.1.0",
            "cookie_enabled": "true",
            "screen_width": "2560",
            "screen_height": "1440",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": "141.0.0.0",
            "os_name": "Windows",
            "os_version": "10",
            "device_memory": "8",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "round_trip_time": "50",
        }
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"https://www.douyin.com/aweme/v1/web/aweme/post/?{qs}"
        result = self.fetch(url)
        if result.get("status") == 200:
            return result.get("data", {})
        return {}

    def get_all_posts(self, sec_user_id: str, max_pages: int = 50) -> List[Dict]:
        """翻页获取用户全部帖子"""
        all_posts = []
        cursor = 0
        for page in range(max_pages):
            data = self.get_user_posts(sec_user_id, max_cursor=cursor, count=18)
            aweme_list = data.get("aweme_list", [])
            if not aweme_list:
                break
            all_posts.extend(aweme_list)
            if not data.get("has_more", 0):
                break
            cursor = data.get("max_cursor", 0)
            time.sleep(1)
        return all_posts
