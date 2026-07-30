"""PySide6 对话框: 批量下载 + 裁剪/去广告 + 瑜伽预审.

  - BatchDialog: 多行 URL 文本框, 返回链接列表.
  - TrimDialog: 起止秒 + 去中间段 + 精确模式; 计算输出路径后发 trimRequested 信号,
    由 MainWindow 起 TrimWorker (不在对话框里跑 ffmpeg, 进度回主日志).
  - YogaReviewDialog: 抽样帧缩略图网格 + 衣着人工清单 + 可选深度体态扫描.
    只做辅助 —— 机器测不了衣着 (抖音"衣着暴露"#1 触发点), 必须人眼看动片.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BatchDialog(QDialog):
    """批量下载: 每行一个 URL."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("批量下载 — 每行一个 URL")
        self.resize(600, 400)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("每行一个链接, 将依次下载并验证:"))
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("https://www.youtube.com/watch?v=...\nhttps://www.douyin.com/video/...")
        lay.addWidget(self.edit, 1)

        go = QPushButton("开始批量下载")
        go.clicked.connect(self.accept)
        lay.addWidget(go)

    def urls(self) -> list[str]:
        return [ln.strip() for ln in self.edit.toPlainText().splitlines() if ln.strip()]


class TrimDialog(QDialog):
    """裁剪 / 去广告: 收集参数后发信号给主窗口跑 ffmpeg."""

    # (out_path, start, end, remove_mid, precise)
    trimRequested = Signal(str, float, float, bool, bool)

    def __init__(self, src: str, duration: float, parent=None) -> None:
        super().__init__(parent)
        self._src = src
        self.setWindowTitle("裁剪 / 去广告")
        self.resize(480, 340)

        lay = QVBoxLayout(self)
        info = QLabel(f"源: {os.path.basename(src)}" + (f"   (时长 {duration:.0f}s)" if duration else ""))
        info.setWordWrap(True)
        lay.addWidget(info)

        form = QFormLayout()
        self.e_start = QLineEdit("0")
        self.e_end = QLineEdit(f"{duration:.0f}" if duration else "30")
        self.e_start.setMaximumWidth(140)
        self.e_end.setMaximumWidth(140)
        form.addRow("开始 (秒)", self.e_start)
        form.addRow("结束 (秒)", self.e_end)
        lay.addLayout(form)

        self.cb_remove = QCheckBox("去除中间片段 (去广告/赞助) — 删掉该段, 拼接头尾")
        self.cb_precise = QCheckBox("精确模式 (重编码, 帧精确, 慢; 默认快速流拷贝)")
        lay.addWidget(self.cb_remove)
        lay.addWidget(self.cb_precise)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color:#fbbf24;")
        lay.addWidget(self.status)

        row = QHBoxLayout()
        go = QPushButton("✂ 执行")
        go.clicked.connect(self._emit)
        preview = QPushButton("▶ 预览原片 (用系统播放器定位广告时间)")
        preview.setStyleSheet("color:#9ca3af;")
        preview.clicked.connect(lambda: _startfile(src))
        row.addWidget(go)
        row.addWidget(preview)
        lay.addLayout(row)

    def _emit(self) -> None:
        try:
            s = float(self.e_start.text())
            e = float(self.e_end.text())
        except ValueError:
            self.status.setText("⚠ 请输入数字")
            return
        stem = os.path.splitext(os.path.basename(self._src))[0]
        tag = "noad" if self.cb_remove.isChecked() else "trim"
        out = os.path.join(os.path.dirname(self._src),
                           f"{stem}_{tag}_{int(s)}-{int(e)}s.mp4")
        self.trimRequested.emit(out, s, e, self.cb_remove.isChecked(), self.cb_precise.isChecked())
        self.accept()


def _startfile(path: str) -> None:
    """用系统默认程序打开 (Windows). 失败静默."""
    try:
        os.startfile(path)  # type: ignore[attr-defined]
    except Exception:
        pass


class YogaReviewDialog(QDialog):
    """瑜伽源预审: 抽样帧缩略图网格 + 衣着人工清单 + 可选深度体态扫描.

    设计原则 (cf. memory yoga-pose-reject-vs-clothing-eye):
      - 自动测不了衣着 (紧身/露肤 = 抖音"衣着暴露"触发点), 必须人眼看动片;
      - 深度体态判定 (YOLO) 是保守误报方向 (折叠/劈叉剪影密度高 ≠ 衣着暴露),
        仅标高危帧辅助复核, 不替人拍板.
    深度扫描不在对话框里 subprocess —— 发 deepRequested 信号, 由 MainWindow 起
    DeepCheckWorker, 完成后回填 set_deep_result (与 TrimDialog 同模式).
    """

    deepRequested = Signal()

    def __init__(self, frames: list, deep_available: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("瑜伽源预审 — 衣着人工复核")
        self.resize(820, 660)
        self._frames = frames
        self.deep_btn: QPushButton | None = None
        lay = QVBoxLayout(self)

        hint = QLabel("⚠ 自动测不了衣着 (紧身/露肤 = 抖音\"衣着暴露\"触发点). "
                      "逐帧看 + 关窗后用 ▶ 播放看动片; 全绿才发, 任意一项红 → 换源, 别打码.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#fbbf24;")
        lay.addWidget(hint)

        # ---- 缩略图网格 (3 列) ----
        grid = QGridLayout()
        grid.setSpacing(8)
        cols, thumb_w = 3, 240
        for i, (idx, t, p) in enumerate(frames):
            img = QLabel()
            pm = QPixmap(p)
            if pm.isNull():
                img.setText("(帧读取失败)")
                img.setFixedSize(thumb_w, 135)
                img.setAlignment(Qt.AlignCenter)
            else:
                img.setPixmap(pm.scaledToWidth(thumb_w, Qt.SmoothTransformation))
            img.setStyleSheet("background:#000;")
            img.setMinimumWidth(thumb_w)
            tlab = QLabel(f"#{idx}   t={t}s")
            tlab.setStyleSheet("color:#9ca3af;")
            tlab.setAlignment(Qt.AlignCenter)
            cell = QVBoxLayout()
            cell.setContentsMargins(0, 0, 0, 0)
            cell.addWidget(img)
            cell.addWidget(tlab)
            wrap = QWidget()
            wrap.setLayout(cell)
            r, c = divmod(i, cols)
            grid.addWidget(wrap, r, c)
        lay.addLayout(grid)

        # ---- 人工衣着清单 (勾上 = 这条有风险) ----
        lay.addWidget(QLabel("人工复核 (勾上 = 该项有风险):"))
        self.cb_clothing = QCheckBox("衣着: 运动内衣/超薄紧身, 或露腰腹/胸/臀  (#1 触发点)")
        self.cb_pose = QCheckBox("体态: 大量俯身/劈叉/桥式特写")
        self.cb_shot = QCheckBox("镜头: 低角度仰拍/躯干近景/卧室昏暗私房感")
        for cb in (self.cb_clothing, self.cb_pose, self.cb_shot):
            lay.addWidget(cb)

        # ---- 深度体态扫描结果区 ----
        self.deep_result = QLabel("")
        self.deep_result.setWordWrap(True)
        self.deep_result.setStyleSheet("color:#93c5fd;")
        lay.addWidget(self.deep_result)

        # ---- 操作行 ----
        row = QHBoxLayout()
        if deep_available:
            self.deep_btn = QPushButton("🧘 深度体态扫描 (YOLO, ~10-30s)")
            self.deep_btn.setToolTip("本机检测到 fitness-video-pipeline, 调其 YOLO pose 判体态.\n"
                                     "体态 REJECT ≠ 衣着有问题 (折叠/劈叉剪影密度高而已), 衣着维度仍以你眼看为准.")
            self.deep_btn.clicked.connect(self._request_deep)
            row.addWidget(self.deep_btn)
        row.addStretch(1)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def _request_deep(self) -> None:
        if self.deep_btn:
            self.deep_btn.setEnabled(False)
        self.deep_result.setText("扫描中… (首次需加载 YOLO 模型, 稍候)")
        self.deep_result.setStyleSheet("color:#93c5fd;")
        self.deepRequested.emit()

    def set_deep_result(self, verdict, summary, error) -> None:
        """DeepCheckWorker 完成后由 MainWindow 回填."""
        if self.deep_btn:
            self.deep_btn.setEnabled(True)
        if error:
            self.deep_result.setText(f"✗ {error}")
            self.deep_result.setStyleSheet("color:#f87171;")
            return
        color = {"PASS": "#4ade80", "CAUTION": "#fbbf24",
                 "REJECT": "#f87171"}.get(verdict, "#93c5fd")
        note = "\n(体态是保守误报: 折叠/劈叉剪影密度高 ≠ 衣着暴露; 衣着维度仍以你眼看动片为准)"
        self.deep_result.setText(f"深度体态判定: {summary}{note}")
        self.deep_result.setStyleSheet(f"color:{color};")
