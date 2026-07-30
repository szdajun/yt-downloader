"""设置持久化.

配置文件 ~/.yt-downloader/config.json — 跨更新保留, 不随项目目录走.
记录: 输出目录 / 默认品质 / 准入验证开关 / 外观主题 / cookies 浏览器.
启动加载填充 UI, 关闭时保存, 下次打开自动恢复 (用户改下载目录后不用重设).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".yt-downloader")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def default_output_dir() -> str:
    return os.path.join(os.path.expanduser("~"), "Downloads", "yt-downloader")


@dataclass
class Settings:
    output_dir: str = ""
    format_label: str = "最高画质 (mp4)"
    verify: bool = True
    appearance: str = "dark"          # dark / light / system
    cookies_browser: str = ""         # "firefox" — yt-dlp 仅能自动读 Firefox (chrome/edge 新版加密锁死)
    cookies_file: str = ""            # cookies.txt 路径 (Netscape 格式, 浏览器扩展导出; 最通用最可靠)
    force: bool = False               # 强制重新下载: 文件已存在时改名 a(1)/a(2) 重下 (默认跳过)


def load() -> Settings:
    s = Settings()
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, encoding="utf-8") as f:
                d = json.load(f)
            for k in ("output_dir", "format_label", "verify", "appearance",
                      "cookies_browser", "cookies_file", "force"):
                if k in d:
                    setattr(s, k, d[k])
    except Exception:
        pass
    if not s.output_dir:
        s.output_dir = default_output_dir()
    return s


def save(s: Settings) -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(s), f, ensure_ascii=False, indent=2)
    except Exception:
        pass
