"""trim.py — trim() / remove_segment() 参数校验 + 命令拼接.

subprocess 层用 mock;真实 ffmpeg 集成层 optional。
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from yt_downloader.trim import remove_segment, trim


def test_trim_rejects_end_le_start():
    out, err = trim("src.mp4", "out.mp4", 5.0, 3.0)
    assert out is None
    assert "结束时间必须大于开始时间" in err


def test_trim_rejects_missing_src(tmp_path):
    out, err = trim(str(tmp_path / "no.mp4"), str(tmp_path / "out.mp4"), 1.0, 5.0)
    assert out is None
    assert "源文件不存在" in err


def test_trim_command_construction_copy_mode(tmp_path):
    """precise=False 模式:应该用 -c copy + -avoid_negative_ts."""
    src = tmp_path / "src.mp4"
    src.write_bytes(b"\x00" * 16)  # 最小文件,不会真跑 ffmpeg
    out = tmp_path / "out.mp4"

    fake = MagicMock()
    fake.returncode = 0
    # 创建 out 文件让 trim() 认为成功了
    out.write_bytes(b"\x00" * 16)

    with patch("yt_downloader.trim.subprocess.run", return_value=fake) as m:
        result, err = trim(str(src), str(out), 1.0, 5.0, precise=False)

    assert err is None
    assert result == str(out)
    # 验证调用的命令包含 -c copy 和 -ss
    cmd = m.call_args[0][0]
    assert "-c" in cmd and "copy" in cmd
    assert "-ss" in cmd
    assert "1.000" in cmd


def test_trim_command_construction_precise_mode(tmp_path):
    src = tmp_path / "src.mp4"
    src.write_bytes(b"\x00" * 16)
    out = tmp_path / "out.mp4"
    out.write_bytes(b"\x00" * 16)

    fake = MagicMock()
    fake.returncode = 0
    with patch("yt_downloader.trim.subprocess.run", return_value=fake) as m:
        result, err = trim(str(src), str(out), 1.0, 5.0, precise=True)

    assert err is None
    cmd = m.call_args[0][0]
    assert "libx264" in cmd
    assert "-crf" in cmd


def test_trim_returns_error_on_nonzero(tmp_path):
    src = tmp_path / "src.mp4"
    src.write_bytes(b"\x00" * 16)
    out = tmp_path / "out.mp4"

    fake = MagicMock()
    fake.returncode = 1
    fake.stderr = "ffmpeg error: invalid data"
    with patch("yt_downloader.trim.subprocess.run", return_value=fake):
        result, err = trim(str(src), str(out), 1.0, 5.0)

    assert result is None
    assert "ffmpeg" in err.lower() or "ffmpeg" in err


def test_remove_segment_rejects_end_le_start():
    out, err = remove_segment("x.mp4", "y.mp4", 5.0, 3.0)
    assert out is None
    assert "结束时间必须大于开始时间" in err


def test_remove_segment_rejects_negative_only():
    out, err = remove_segment("x.mp4", "y.mp4", -5.0, -1.0)
    assert out is None
    assert "请输入有效" in err


def test_remove_segment_command_construction_copy(tmp_path):
    """precise=False 模式:三步 (切 p1, 切 p2, concat demuxer)."""
    src = tmp_path / "src.mp4"
    src.write_bytes(b"\x00" * 16)
    out = tmp_path / "out.mp4"

    def fake_subprocess(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", kwargs.get("cmd", []))
        # p1 cut: cmd 包含 -t 5.000 → 写出 .p1.mp4
        if "-t" in cmd and "5.000" in cmd:
            p1 = [a for a in cmd if a.endswith(".p1.mp4")][0]
            Path(p1).write_bytes(b"")
        # p2 cut: cmd 包含 -ss 10.000 → 写出 .p2.mp4
        elif "-ss" in cmd and "10.000" in cmd:
            p2 = [a for a in cmd if a.endswith(".p2.mp4")][0]
            Path(p2).write_bytes(b"")
        # concat: cmd 包含 -f concat → 写出最终 out
        elif "-f" in cmd and "concat" in cmd:
            out_idx = cmd.index("-y") + 1
            Path(cmd[out_idx]).write_bytes(b"")
        return MagicMock(returncode=0, stderr="")

    with patch("yt_downloader.trim.subprocess.run", side_effect=fake_subprocess) as m:
        result, err = remove_segment(str(src), str(out), 5.0, 10.0, precise=False)

    # 验证返回值
    assert result == str(out)
    assert err is None
    # 验证 subprocess.run 被调用了 3 次 (p1 + p2 + concat)
    assert m.call_count == 3
    # 验证至少一次调用使用了 -f concat (concat demuxer)
    assert any("-f" in c.args[0] and "concat" in c.args[0] for c in m.call_args_list)
    # 验证至少一次调用使用了 -t 5.000 (p1 起始时间)
    assert any("-t" in c.args[0] and "5.000" in c.args[0] for c in m.call_args_list)


def test_remove_segment_precise_mode_uses_select(tmp_path):
    src = tmp_path / "src.mp4"
    src.write_bytes(b"\x00" * 16)
    out = tmp_path / "out.mp4"
    out.write_bytes(b"\x00" * 16)

    fake_ok = MagicMock(returncode=0, stderr="")
    with patch("yt_downloader.trim.subprocess.run", return_value=fake_ok) as m:
        result, err = remove_segment(str(src), str(out), 5.0, 10.0, precise=True)

    assert err is None
    cmd = m.call_args[0][0]
    assert "select=" in " ".join(cmd) or any("select=" in str(x) for x in cmd)
    assert "libx264" in cmd
