"""ffmpeg 裁剪片段.

两种模式:
  - precise=False (默认): input-seek + -c copy, 秒级快速, 关键帧对齐
    (起点可能偏到最近关键帧, 健身片段去头去尾通常够用).
  - precise=True: output-seek + 重编码 (libx264 crf18), 帧精确, 慢.

输出命名: <stem>_trim_<start>-<end>s.mp4
"""
from __future__ import annotations

import os
import subprocess

# env YT_FFMPEG_DIR 可覆盖; 默认 ~/ffmpeg —— 别写死用户名/盘符。同 verify.py。
_FFMPEG_DIR = os.environ.get("YT_FFMPEG_DIR") or os.path.expanduser(r"~\ffmpeg")


def _ffmpeg() -> str:
    p = os.path.join(_FFMPEG_DIR, "ffmpeg.exe")
    return p if os.path.exists(p) else "ffmpeg"


def trim(src: str, out: str, start: float, end: float,
         precise: bool = False) -> tuple[str | None, str | None]:
    """裁剪 [start, end] 秒. 返回 (out_path | None, error | None)."""
    dur = end - start
    if dur <= 0:
        return None, "结束时间必须大于开始时间"
    if not os.path.exists(src):
        return None, f"源文件不存在: {src}"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    if precise:
        cmd = [_ffmpeg(), "-ss", f"{start:.3f}", "-i", src, "-t", f"{dur:.3f}",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
               "-c:a", "aac", "-y", out]
    else:
        # input-seek (快) + 流拷贝 (不重编码)
        cmd = [_ffmpeg(), "-ss", f"{start:.3f}", "-i", src, "-t", f"{dur:.3f}",
               "-c", "copy", "-avoid_negative_ts", "make_zero", "-y", out]

    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 or not os.path.exists(out):
        tail = (r.stderr or "ffmpeg 失败")[-400:]
        return None, tail
    return out, None


def remove_segment(src: str, out: str, start: float, end: float,
                   precise: bool = False) -> tuple[str | None, str | None]:
    """去除 [start, end] 段, 输出 = [0,start] + [end,EOF] 拼接 (去中间广告/赞助).

    - precise=False (默认): 两段 -c copy 切出 + concat demuxer 拼接, 秒级快速
      (切割对齐关键帧, 接缝处可能有 ≤1s 偏移, 健身/去广告通常够).
    - precise=True: select 过滤 + 重编码, 帧精确, 慢 (整片重编).
    """
    if end <= start:
        return None, "结束时间必须大于开始时间"
    if start <= 0 and end <= 0:
        return None, "请输入有效的起止时间"
    if not os.path.exists(src):
        return None, f"源文件不存在: {src}"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    if precise:
        cmd = [_ffmpeg(), "-i", src,
               "-vf", f"select='not(between(t,{start},{end}))',setpts=N/FRAME_RATE/TB",
               "-af", f"aselect='not(between(t,{start},{end}))',asetpts=N/SR/TB",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
               "-c:a", "aac", "-y", out]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0 or not os.path.exists(out):
            return None, (r.stderr or "ffmpeg 失败")[-400:]
        return out, None

    # 两段 copy + concat (ffmpeg concat demuxer; 同源 -c copy 两段参数一致, 通常可直接拼)
    tmp1 = out + ".p1.mp4"
    tmp2 = out + ".p2.mp4"
    lst = out + ".list.txt"
    try:
        r1 = subprocess.run(
            [_ffmpeg(), "-i", src, "-t", f"{start:.3f}", "-c", "copy",
             "-avoid_negative_ts", "make_zero", "-y", tmp1],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        r2 = subprocess.run(
            [_ffmpeg(), "-ss", f"{end:.3f}", "-i", src, "-c", "copy",
             "-avoid_negative_ts", "make_zero", "-y", tmp2],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r1.returncode != 0 or r2.returncode != 0 or not os.path.exists(tmp1):
            return None, "切分失败:\n" + ((r1.stderr or "") + (r2.stderr or ""))[-400:]
        # concat demuxer 在 Windows 上路径用正斜杠最稳
        with open(lst, "w", encoding="utf-8") as f:
            f.write(f"file '{tmp1.replace(os.sep, '/')}'\n")
            f.write(f"file '{tmp2.replace(os.sep, '/')}'\n")
        r3 = subprocess.run(
            [_ffmpeg(), "-f", "concat", "-safe", "0", "-i", lst,
             "-c", "copy", "-y", out],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r3.returncode != 0 or not os.path.exists(out):
            return None, "拼接失败 (可勾选精确模式重试):\n" + (r3.stderr or "")[-400:]
        return out, None
    finally:
        for p in (tmp1, tmp2, lst):
            try:
                os.remove(p)
            except OSError:
                pass
