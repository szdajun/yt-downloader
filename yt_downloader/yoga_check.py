"""瑜伽源预审 (轻量, 零 ML 依赖).

下载后用 ffmpeg 抽样 N 帧供人工衣着复核 —— 抖音"衣着暴露"风险预筛.
**不自动判衣着**: 紧身/露肤是 #1 触发点但机器测不准, 必须人眼看动片
(cf. memory yoga-pose-reject-vs-clothing-eye: 体态自动 REJECT 是保守误报,
 衣着维度才是抖音触发点, 用户眼看 > 自动层).

深度体态扫描 (可选): 本机检测到 fitness-video-pipeline venv 时, subprocess
调 scripts/yoga_source_check.py (YOLOv8-pose 自动体态 PASS/CAUTION/REJECT).
体态判定仅辅助标高危帧, 不替人拍板 —— 它 REJECT 不代表衣着有问题.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

from .verify import probe

# 已知好路径优先 (Winget 版编码兼容问题); 不存在则回退 PATH。
# env YT_FFMPEG_DIR 可覆盖; 默认 ~/ffmpeg —— 别写死用户名/盘符。同 verify.py / trim.py。
_FFMPEG_DIR = os.environ.get("YT_FFMPEG_DIR") or os.path.expanduser(r"~\ffmpeg")


def _ffmpeg() -> str:
    p = os.path.join(_FFMPEG_DIR, "ffmpeg.exe")
    return p if os.path.exists(p) else "ffmpeg"


def _fitness_root() -> str:
    """fitness-video-pipeline 根目录 (深度扫描用). env 可覆盖; 别的机器没有则深度按钮不出现."""
    env = os.environ.get("YT_FITNESS_ROOT")
    if env:
        return env
    # 默认取本仓库的兄弟目录 —— 与 cwd 无关, 整仓搬到别处仍能定位 (别写死盘符)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(os.path.dirname(repo_root), "fitness-video-pipeline")


def fitness_env() -> tuple[str, str] | None:
    """检测本机 fitness venv + yoga_source_check.py. 返回 (python_exe, script) 或 None."""
    root = _fitness_root()
    py = os.path.join(root, ".venv", "Scripts", "python.exe")
    script = os.path.join(root, "scripts", "yoga_source_check.py")
    if os.path.exists(py) and os.path.exists(script):
        return py, script
    return None


def extract_frames(path: str, n: int = 9, out_dir: str | None = None
                   ) -> tuple[list[tuple[int, float, str]], str | None]:
    """ffmpeg 一遍 fps 过滤均匀抽 n 帧 PNG 供人工衣着复核.

    返回 (frames, error). frames = [(idx, t_sec, png_path), ...] 按生成序排序.
    out_dir 由调用方提供 (worker 管 tempdir 生命周期); 缺省建临时目录 (调用方没法清, 慎用).

    fps 过滤一遍过 (不逐帧 output-seek 重解码), 9 帧秒级; 服装复核只需均匀覆盖,
    不要求帧精确 (cf. memory ffmpeg-fast-seek-frame-extraction-artifact: 帧精确抽帧
    才需 output-seek + select=eq(n), 这里不必).
    """
    if not os.path.exists(path):
        return [], f"源文件不存在: {path}"
    if out_dir is None:
        out_dir = tempfile.mkdtemp(prefix="yoga_frames_")
    else:
        os.makedirs(out_dir, exist_ok=True)
    pat = os.path.join(out_dir, "frame_%03d.png")

    # 时长 → fps: n 帧 / 时长 = 每秒采样数 → 均匀覆盖. 取不到时长按 ~30s/帧兜底.
    r = probe(path)
    dur = r.duration if (r and r.duration > 0) else n * 30.0
    fps = n / dur if dur > 0 else 1.0 / 30.0

    cmd = [_ffmpeg(), "-i", path, "-vf", f"fps={fps:.6f}", "-an", "-y", pat]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=180)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return [], f"ffmpeg 抽帧失败: {e}"
    if res.returncode != 0:
        return [], "ffmpeg 抽帧失败:\n" + (res.stderr or "")[-400:]

    frames: list[tuple[int, float, str]] = []
    for fn in sorted(os.listdir(out_dir)):
        if fn.startswith("frame_") and fn.endswith(".png"):
            idx = len(frames)
            t = round((idx + 0.5) * dur / n, 1)   # 近似中点时间标签 (仅展示用)
            frames.append((idx, t, os.path.join(out_dir, fn)))
    if not frames:
        return [], "ffmpeg 未输出帧 (视频无视频流或损坏? 先 ffmpeg 预转 h264 再试)"
    return frames, None


def run_deep_check(python_exe: str, script: str, video: str, work_dir: str
                   ) -> tuple[str | None, str | None, str | None]:
    """subprocess 调 fitness yoga_source_check.py 跑 YOLO 体态自动判定.

    work_dir = 帧/report 输出根 (yoga_source_check 会在其下建 <stem>/ 放帧 + report.json).
    返回 (verdict, summary, error):
      - verdict ∈ {"PASS","CAUTION","REJECT"} | None
      - summary = "REJECT — 高危体态 7/12, 特写 0, 暗光 0" 一行
    """
    cmd = [python_exe, script, video, "-n", "12", "-o", work_dir]
    try:
        # cwd = fitness 根: yolov8m-pose.pt 模型缓存落 fitness 而非 yt-downloader 目录
        res = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace",
                             cwd=os.path.dirname(script), timeout=600)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return None, None, f"深度扫描启动失败: {e}"
    if res.returncode != 0:
        return None, None, "深度扫描失败:\n" + (res.stderr or res.stdout or "")[-400:]

    # 读 report.json 取结构化判定 (yoga_source_check 写 work_dir/<stem>/report.json)
    stem = os.path.splitext(os.path.basename(video))[0]
    report = os.path.join(work_dir, stem, "report.json")
    try:
        with open(report, encoding="utf-8") as f:
            d = json.load(f)
        verdict = d.get("verdict")
        summary = (f"{verdict} — 高危体态 {d.get('pose_risk_frames', '?')}/"
                   f"{d.get('sampled', '?')}, 特写 {d.get('closeup_frames', 0)}, "
                   f"暗光 {d.get('dark_frames', 0)}")
        return verdict, summary, None
    except (OSError, json.JSONDecodeError):
        # report 没写出: 从 stdout 抓"自动判定: XXX"行兜底
        for ln in (res.stdout or "").splitlines():
            if "自动判定" in ln:
                return "CAUTION", ln.strip(), None
        return None, None, "未取到判定结果 (report.json 缺失)"
