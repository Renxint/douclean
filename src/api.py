# -*- coding: utf-8 -*-
"""
抖音 API 客户端 — Python requests + Cookie 直连，不依赖签名服务

关键发现:
  - 不需要 a_bogus，不需要 msToken
  - 仅需 Cookie + 正确的 browser_name/browser_version + 设备指纹即可翻页
  - browser_name 必须匹配真实 UA (Smart+Lenovo+Browser, 而非 Chrome)
"""

import sys
import json
from pathlib import Path
from typing import Optional, Dict, List

# 确保可以导入 shared 库和本项目 src
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # Claude/
PROJECT_DIR = Path(__file__).resolve().parent.parent  # douyin_downloader/
for p in (str(PROJECT_ROOT), str(PROJECT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import requests
import logging

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

# 设备指纹（从真实浏览器提取，跨账号通用）
WEBID = "7385142668127356466"
VERIFY_FP = "verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD"
FP = "verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD"
UIFID = "7db62a7064f9afdec5c11ec3d692d7372ef41f2765cba0856d9e1b7b4940be6ed1b35a0f14230c327616b958a98d663b4443e89c625dc584c6b48e03ecc9c0ad"

# User-Agent（必须匹配真实浏览器）
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36 "
    "SLBrowser/9.0.8.5161 SLBChan/111 SLBVPV/64-bit"
)

# Cookie 文件路径
COOKIE_FILE = PROJECT_DIR / "data" / "Cookie.txt"

# 请求超时
TIMEOUT = 30


def _get_avatar(user: dict) -> str:
    """从 user 对象提取头像 URL（可能是字符串或嵌套对象）"""
    for key in ("avatar_300_url", "avatar_url", "avatar_medium_url", "avatar_thumb_url"):
        val = user.get(key, "")
        if isinstance(val, dict):
            val = (val.get("url_list") or [""])[0]
        if val and isinstance(val, str) and val.startswith("http"):
            return val
    return ""


class DouyinAPI:
    """抖音 API 客户端 — Cookie 直连方式"""

    def __init__(self, cookie_string: str = ""):
        """
        Args:
            cookie_string: Cookie 字符串，为空则自动从 Cookie.txt 读取
        """
        if cookie_string:
            self.cookie = cookie_string
        else:
            self.cookie = self._load_cookie()

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Referer": "https://www.douyin.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cookie": self.cookie,
        })

    def _load_cookie(self) -> str:
        """从文件加载 Cookie"""
        if COOKIE_FILE.exists():
            return COOKIE_FILE.read_text(encoding='utf-8').strip()
        logger.warning(f"Cookie 文件不存在: {COOKIE_FILE}")
        return ""

    @staticmethod
    def _build_post_params(sec_user_id: str, max_cursor: int = 0,
                           count: int = 18) -> Dict[str, str]:
        """构建 /aweme/v1/web/aweme/post/ 请求参数"""
        return {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "sec_user_id": sec_user_id,
            "max_cursor": str(max_cursor),
            "locate_query": "false",
            "show_live_replay_strategy": "1",
            "need_time_list": "0",
            "time_list_query": "0",
            "whale_cut_token": "",
            "cut_version": "1",
            "count": str(count),
            "publish_video_strategy_type": "2",
            "from_user_page": "1",
            "update_version_code": "170400",
            "pc_client_type": "1",
            "pc_libra_divert": "Windows",
            "support_h265": "1",
            "support_dash": "1",
            "cpu_core_num": "32",
            "version_code": "290100",
            "version_name": "29.1.0",
            "cookie_enabled": "true",
            "screen_width": "2560",
            "screen_height": "1440",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            # ⚠️ 这两个必须匹配真实 UA，否则翻页失败
            "browser_name": "Smart+Lenovo+Browser",
            "browser_version": "9.0.8.5161",
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
            # 设备指纹（翻页必需）
            "webid": WEBID,
            "uifid": UIFID,
            "verifyFp": VERIFY_FP,
            "fp": FP,
        }

    def check_cookie(self) -> bool:
        """校验 Cookie 是否有效（未被封/未过期）"""
        try:
            resp = self.session.get(
                "https://www.douyin.com/aweme/v1/web/user/profile/other/"
                "?sec_user_id=MS4wLjABAAAAnsZ-gU2aYmYUiMq2a1dTwH0Bst9fK3s9mEpQnvVsosI"
                "&device_platform=webapp&aid=6383",
                timeout=10,
            )
            data = resp.json()
            return data.get("status_msg") != "blocked" and bool(data.get("user", {}))
        except Exception:
            return False

    def get_user_profile(self, sec_user_id: str) -> Dict:
        """
        获取用户资料

        Returns:
            {"nickname": "...", "aweme_count": N}
        """
        url = (f"https://www.douyin.com/aweme/v1/web/user/profile/other/"
               f"?sec_user_id={sec_user_id}&device_platform=webapp&aid=6383")
        try:
            resp = self.session.get(url, timeout=TIMEOUT)
            user = resp.json().get("user", {})
            return {
                "nickname": user.get("nickname", ""),
                "unique_id": user.get("unique_id", ""),
                "short_id": user.get("short_id", ""),
                "uid": user.get("uid", ""),
                "sec_uid": user.get("sec_uid", ""),
                "desc": user.get("desc", "") or user.get("signature", ""),
                "aweme_count": user.get("aweme_count", 0) or 0,
                "follower_count": user.get("follower_count", 0) or 0,
                "following_count": user.get("following_count", 0) or 0,
                "favoriting_count": user.get("favoriting_count", 0) or 0,
                "total_favorited": user.get("total_favorited", 0) or 0,
                "country": user.get("country", ""),
                "province": user.get("province", ""),
                "city": user.get("city", ""),
                "district": user.get("district", ""),
                "school": user.get("school", ""),
                "age": user.get("age", ""),
                "gender": user.get("gender", ""),
                "custom_verify": user.get("custom_verify", ""),
                "enterprise_verify_reason": user.get("enterprise_verify_reason", ""),
                "avatar_url": _get_avatar(user),
            }
        except Exception as e:
            logger.error(f"获取用户资料失败: {e}")
            return {}

    def get_user_posts(self, sec_user_id: str, max_cursor: int = 0,
                       count: int = 18) -> Dict:
        """
        获取用户作品列表

        Args:
            sec_user_id: 用户加密ID (MS4wLjAB...)
            max_cursor: 翻页游标，0=第一页
            count: 每页数量 (最大18)

        Returns:
            {"status_code": 0, "aweme_list": [...], "has_more": 1, "max_cursor": ...}
        """
        params = self._build_post_params(sec_user_id, max_cursor, count)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"https://www-hj.douyin.com/aweme/v1/web/aweme/post/?{query}"

        try:
            resp = self.session.get(url, timeout=TIMEOUT)
            return resp.json()
        except Exception as e:
            logger.error(f"请求失败: {e}")
            return {}


# ============ 测试 ============
if __name__ == "__main__":
    api = DouyinAPI()

    # 测试用户
    sec_id = "MS4wLjABAAAAnsZ-gU2aYmYUiMq2a1dTwH0Bst9fK3s9mEpQnvVsosI"

    profile = api.get_user_profile(sec_id)
    print(f"用户: {profile.get('nickname')} | 作品数: {profile.get('aweme_count')}")

    data = api.get_user_posts(sec_id, max_cursor=0, count=18)
    aweme_list = data.get("aweme_list", [])
    print(f"P1: {len(aweme_list)} 条 | has_more={data.get('has_more')} | max_cursor={data.get('max_cursor')}")

    for i, a in enumerate(aweme_list[:5]):
        print(f"  {i+1}. [{a.get('aweme_id')}] {a.get('desc', '')[:50]}")
