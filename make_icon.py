"""YT 视频下载器 应用图标生成器 (Pillow + numpy).

设计: 圆角渐变磁贴 (紫→蓝) + 白色"下载箭头入托盘" = 视频下载, 简洁、小尺寸可辨.
运行 (任意带 Pillow+numpy 的 venv, 例如 fitness 项目):
    uv run --with pillow --with numpy python make_icon.py
产物: yt_downloader/assets/app.png (512) + app.ico (16..256 多尺寸, 供窗口/任务栏/快捷方式).
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image, ImageDraw

SZ = 1024
CX = SZ // 2

# 1) 对角线性渐变 violet(124,58,237) -> blue(37,99,235)
c1 = np.array([124, 58, 237], dtype=np.float32)
c2 = np.array([37, 99, 235], dtype=np.float32)
yy, xx = np.mgrid[0:SZ, 0:SZ]
t = ((xx + yy) / (2 * (SZ - 1)))[..., None]              # (SZ,SZ,1)
grad = ((1 - t) * c1 + t * c2).astype(np.uint8)          # (SZ,SZ,3)
rgb = Image.fromarray(grad, "RGB").convert("RGBA")

# 2) 圆角磁贴遮罩 (现代 app 图标标准)
mask = Image.new("L", (SZ, SZ), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, SZ - 1, SZ - 1],
                                       radius=int(SZ * 0.22), fill=255)
img = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
img.paste(rgb, (0, 0), mask)
d = ImageDraw.Draw(img)
W = (255, 255, 255, 255)
f = lambda v: int(SZ * v)

# 3) 箭头茎 (圆角矩形)
stem_w = f(0.135)
d.rounded_rectangle([CX - stem_w // 2, f(0.235), CX + stem_w // 2, f(0.495)],
                    radius=stem_w // 2, fill=W)
# 4) 箭头三角 (指向下, 与茎底微叠成一体)
hw = f(0.215)
d.polygon([(CX - hw, f(0.455)), (CX + hw, f(0.455)), (CX, f(0.59))], fill=W)
# 5) 托盘 (开口向上的 U = 下载落点)
span, th, arm_top, bar_y0 = f(0.245), f(0.072), f(0.625), f(0.705)
d.rounded_rectangle([CX - span, arm_top, CX - span + th, bar_y0 + th],
                    radius=th // 2, fill=W)               # 左竖
d.rounded_rectangle([CX + span - th, arm_top, CX + span, bar_y0 + th],
                    radius=th // 2, fill=W)               # 右竖
d.rounded_rectangle([CX - span, bar_y0, CX + span, bar_y0 + th],
                    radius=th // 2, fill=W)               # 底条

# 6) 输出 PNG + 多尺寸 ICO
out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "yt_downloader", "assets")
os.makedirs(out, exist_ok=True)
img.resize((512, 512), Image.LANCZOS).save(os.path.join(out, "app.png"))
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
icons = [img.resize(s, Image.LANCZOS) for s in sizes]
icons[0].save(os.path.join(out, "app.ico"), format="ICO",
              sizes=sizes, append_images=icons[1:])
print("saved:", sorted(os.listdir(out)))
