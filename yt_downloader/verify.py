"""ffprobe 准入门槛验证.

下载后调用 ffprobe 读取规格, 对照 CLAUDE.md 钉死的源素材准入门槛:
  - 短边像素 ≥ 720    (平台最低 720×1280 / 1280×720, 低于此主管线 upscale 不补细节)
  - 码率     ≥ 2 Mbps (2026-09-17 从 5 下调以适配抖音源, 详见 THRESH_BITRATE 注释)
  - 时长     ≥ 30s    (太短不够完播率)

ffmpeg/ffprobe 已知好路径优先于 PATH (Winget 版有编码 bug),
stderr 丢弃避开 Windows GBK 解中文路径的坑 (与 fitness 主管线同根因).
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

# 已知好路径优先 (Winget 版有编码兼容问题); 不存在则回退 PATH.
_FFMPEG_DIR = r"C:\Users\18091\ffmpeg"


def _ffprobe_path() -> str:
    p = os.path.join(_FFMPEG_DIR, "ffprobe.exe")
    return p if os.path.exists(p) else "ffprobe"


# ---- 准入门槛 (钉死, 与 fitness-video-pipeline CLAUDE.md 一致) ----
THRESH_SHORT_SIDE = 720        # 短边像素
# 2 Mbps — 2026-09-17 用户拍板从 5 Mbps 下调, 以适配抖音源的现实。
# 抖音 1080p 档实测 2119~2898 kbps(容器实测 2.90 Mbps)、720p 档最高 1785 kbps,
# 2.0 正落在 1785~2119 这个天然断层里: 放行 1080p、挡住 720p。720p 的短边恰好
# 是 720 能过分辨率门槛, 只能靠码率挡 —— 所以这个数直接决定下游拿到哪个档。
# ⚠ 下游 fitness-video-pipeline(CLAUDE.md + coach-video-process/SKILL.md)有同值
#   硬门槛, 且「不达标直接放弃不硬上」。改这里必须同步改那边, 否则抖音文件在本
#   项目判达标、到下游被丢, 下载白费。
THRESH_BITRATE = 2_000_000     # 2 Mbps
THRESH_DURATION = 30.0         # 秒 (Shorts 最低)


@dataclass
class ProbeResult:
    width: int
    height: int
    duration: float
    bit_rate: int
    codec: str
    path: str

    @property
    def short_side(self) -> int:
        return min(self.width, self.height) if self.width and self.height else 0

    @property
    def has_video(self) -> bool:
        return self.width > 0 and self.height > 0

    @property
    def short_side_ok(self) -> bool:
        return self.short_side >= THRESH_SHORT_SIDE

    @property
    def bitrate_ok(self) -> bool:
        return self.bit_rate >= THRESH_BITRATE

    @property
    def duration_ok(self) -> bool:
        return self.duration >= THRESH_DURATION

    @property
    def ok(self) -> bool:
        return self.has_video and self.short_side_ok and self.bitrate_ok and self.duration_ok

    @property
    def failures(self) -> list[str]:
        """不达标项的可读列表 (达标时为空)."""
        f = []
        if not self.has_video:
            return ["无视频流 (纯音频?)"]
        if not self.short_side_ok:
            f.append(f"短边 {self.short_side} < {THRESH_SHORT_SIDE}")
        if not self.bitrate_ok:
            f.append(f"码率 {self.bit_rate / 1e6:.1f} < {THRESH_BITRATE / 1e6:g} Mbps")
        if not self.duration_ok:
            f.append(f"时长 {self.duration:.0f}s < 30s")
        return f


def probe(path: str) -> ProbeResult | None:
    """读取视频规格. 失败/无法解析返回 None (调用方降级为只显示文件大小)."""
    try:
        out = subprocess.run(
            [_ffprobe_path(), "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,codec_name",
             "-show_entries", "format=duration,bit_rate",
             "-of", "json", path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        d = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    st = (d.get("streams") or [{}])[0]
    fmt = d.get("format") or {}
    try:
        return ProbeResult(
            width=int(st.get("width") or 0),
            height=int(st.get("height") or 0),
            duration=float(fmt.get("duration") or 0),
            bit_rate=int(fmt.get("bit_rate") or 0),
            codec=st.get("codec_name") or "?",
            path=str(path),
        )
    except (TypeError, ValueError):
        return None
