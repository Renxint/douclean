# -*- coding: utf-8 -*-
"""
抖音签名模块 - 通过 Puppeteer 签名服务获取 a_bogus + msToken
"""

import requests
import urllib.parse


class DouyinSigner:
    """从 Puppeteer 签名服务获取签名后的 URL"""

    def __init__(self, sign_server="http://localhost:8765"):
        self.sign_server = sign_server

    def get_signed_url(self, url: str, timeout: int = 30) -> str:
        """
        请求签名服务获取带 a_bogus + msToken 的完整 URL

        Args:
            url: 不含签名的原始 API URL
            timeout: 超时秒数

        Returns:
            签名后的完整 URL (含 a_bogus, msToken 参数)
        """
        try:
            resp = requests.get(
                f"{self.sign_server}/sign",
                params={"url": url},
                timeout=timeout,
            )
            data = resp.json()
            signed_url = data.get("full_url", url)
            return signed_url
        except Exception as e:
            print(f"[Signer] 签名失败: {e}, 降级使用原始URL")
            return url

    def sign_params(self, url: str, timeout: int = 30) -> dict:
        """
        从签名后的 URL 中提取 a_bogus 和 msToken

        Returns:
            {"a_bogus": "...", "msToken": "...", "full_url": "..."}
        """
        signed = self.get_signed_url(url, timeout)
        parsed = urllib.parse.urlparse(signed)
        params = urllib.parse.parse_qs(parsed.query)
        return {
            "a_bogus": params.get("a_bogus", [""])[0],
            "msToken": params.get("msToken", [""])[0],
            "full_url": signed,
        }
