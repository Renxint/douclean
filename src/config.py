# -*- coding: utf-8 -*-
"""
抖净 DouClean — 全局配置

所有硬编码的常量集中管理，方便替换和升级。
"""

# ============================================================
# 版本
# ============================================================
VERSION = "1.0.1"
VERSION_URL = "https://gitee.com/Renxint/douclean/raw/master/version.json"

# ============================================================
# 钉钉反馈（生产环境通过 config.json 覆盖）
# ============================================================
import json
from pathlib import Path
import os

_EXE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent  # douclean/
_CONFIG_FILE = _EXE_DIR / "data" / "config.json"

def _load_config():
    """加载 data/config.json，不存在则返回空"""
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}

_config = _load_config()
_DEFAULT_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=140b22bf4f35c675bf36c7441a78871f4678762df788dd7079dd0f565f312ee9"
DINGTALK_WEBHOOK = _config.get("dingtalk_webhook", _DEFAULT_WEBHOOK)

# ============================================================
# 设备指纹
# ============================================================
WEBID = "7385142668127356466"
VERIFY_FP = "verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD"
FP = "verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD"
UIFID = "7db62a7064f9afdec5c11ec3d692d7372ef41f2765cba0856d9e1b7b4940be6ed1b35a0f14230c327616b958a98d663b4443e89c625dc584c6b48e03ecc9c0ad"

# ============================================================
# User-Agent & 网络
# ============================================================
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36 "
    "SLBrowser/9.0.8.5161 SLBChan/111 SLBVPV/64-bit"
)
HTTP_TIMEOUT = 30
PAGE_DELAY = 1.5