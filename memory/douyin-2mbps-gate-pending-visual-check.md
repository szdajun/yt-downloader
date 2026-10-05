---
name: douyin-2mbps-gate-pending-visual-check
description: "码率门槛 2026-09-17 降至 2Mbps 以放行抖音源; 待实跑一条抖音源到主管线看 upscale 观感, 再定是否最终值"
metadata: 
  node_type: memory
  type: project
  originSessionId: e6d5a8f1-c7d9-4aeb-8788-dcaa83999bd8
  modified: 2026-09-16T18:44:15.144Z
---

2026-09-17 用户拍板把源准入码率门槛从 5Mbps 下调到 **2Mbps**。上游 `yt-downloader/verify.py` 的 `THRESH_BITRATE` 与下游 `fitness-video-pipeline/CLAUDE.md` 已同步(两边必须保持同值)。依据是抖音实测: 1080p 档 2119~2898 kbps、720p 档最高 1785, 2.0 落在 1785~2119 这个天然断层里 —— 放行 1080p、挡住 720p。

**待办** — 用户 2026-09-17 原话「以后再跑, 你记着此事即可」: 实跑一条抖音源走完 `fitness-video-pipeline` 主管线, **看 upscale 到 4K 后的观感**, 再定 2.0 是不是最终值。**这件事还没做。**

**Why:** 2Mbps 是**分辨率换码率**的取舍, 不是无损。算每像素码率 (bpp@30fps):

| 源 | 分辨率 | 码率 | bpp |
|---|---|---|---|
| 抖音 1080p (新门槛放行) | 1080×1920 | 2.90 Mbps | **0.047** |
| 小红豆独舞 (2026-07-18 被判「色块明显」丢弃) | 520×926 | 2.2 Mbps | **0.152** |

新门槛放进来的源, 每像素压缩程度是当初被拒那个的 **3 倍多**。抖音是「堆分辨率不跟码率」的打法, 门槛放行 ≠ 画质够用 —— 只有真跑一遍才知道够不够。

**How to apply:** 用户下次拿抖音源跑主管线时主动提这件事, 一起看 upscale 后有没有色块/糊感; 不够的话再跟用户讨论 2.0 是否上调、或给抖音源单开一档。**不要擅自改这个数** —— 它是核心业务逻辑, 且跨两个仓库钉死同值(见 [[project-scope]]), 改动必须两边同 commit。相关: [[downstream-pipeline]]。
