#!/usr/bin/env python3
"""
InfoSource Logo v6 — 大白熊主体 + 丰富信息流元素
熊头为主体，周围环绕信息流线条、数据节点、信号波纹
"""
from PIL import Image, ImageDraw, ImageFilter
import math

try:
    RESAMPLE = Image.LANCZOS
except AttributeError:
    RESAMPLE = Image.Resampling.LANCZOS

SIZE = 512
SCALE = 2
S = SIZE * SCALE
cx, cy = S // 2, S // 2

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

# ── 背景：深色微渐变 ──────────────────────
bg = Image.new("RGBA", (S, S), (10, 10, 18, 255))
bg_draw = ImageDraw.Draw(bg)
for r in range(int(S * 0.7), 0, -2):
    t = 1 - r / (S * 0.7)
    b = int(10 * t)
    bg_draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=(10 + b, 10 + b, 18 + b * 2, 255),
    )
img = Image.alpha_composite(img, bg)
draw = ImageDraw.Draw(img)

WHITE = (255, 255, 255)
ACCENT = (99, 162, 255)     # 蓝
ACCENT2 = (0, 220, 180)     # 青绿
DIM = (60, 70, 95)

# ── 背景网格点（科技感底纹） ──────────────
grid = Image.new("RGBA", (S, S), (0, 0, 0, 0))
gd = ImageDraw.Draw(grid)
for gx in range(0, S, int(SCALE * 28)):
    for gy in range(0, S, int(SCALE * 28)):
        gd.ellipse([gx - SCALE, gy - SCALE, gx + SCALE, gy + SCALE], fill=(50, 60, 85, 40))
grid = grid.filter(ImageFilter.GaussianBlur(radius=1))
img = Image.alpha_composite(img, grid)
draw = ImageDraw.Draw(img)

# ── 信息流线条（熊头两侧，向中心汇聚） ────
def draw_flow_line(layer_d, points, color, alpha, width):
    for i in range(len(points) - 1):
        layer_d.line(
            [points[i], points[i + 1]],
            fill=(*color, alpha),
            width=width,
        )

flow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
fd = ImageDraw.Draw(flow)

# 左侧信息流 — 三条汇聚线
bear_y = cy + int(SCALE * 5)
head_r = int(S * 0.22)

# 左侧流入线
for i, (start_y, end_alpha, w, c) in enumerate([
    (bear_y - int(S * 0.12), 160, int(SCALE * 3), ACCENT),
    (bear_y, 120, int(SCALE * 2), ACCENT2),
    (bear_y + int(S * 0.12), 80, int(SCALE * 2), DIM),
]):
    sx = int(S * 0.08)
    ex = cx - head_r - int(SCALE * 18)
    # 贝塞尔近似
    mid_x = (sx + ex) // 2
    pts = [(sx, start_y), (mid_x, start_y - int(SCALE * 6)), (ex, start_y)]
    draw_flow_line(fd, pts, c, end_alpha, w)

# 右侧流入线
for i, (start_y, end_alpha, w, c) in enumerate([
    (bear_y - int(S * 0.12), 160, int(SCALE * 3), ACCENT),
    (bear_y, 120, int(SCALE * 2), ACCENT2),
    (bear_y + int(S * 0.12), 80, int(SCALE * 2), DIM),
]):
    sx = S - int(S * 0.08)
    ex = cx + head_r + int(SCALE * 18)
    mid_x = (sx + ex) // 2
    pts = [(sx, start_y), (mid_x, start_y - int(SCALE * 6)), (ex, start_y)]
    draw_flow_line(fd, pts, c, end_alpha, w)

flow = flow.filter(ImageFilter.GaussianBlur(radius=1))
img = Image.alpha_composite(img, flow)
draw = ImageDraw.Draw(img)

# ── 信息节点（流线上的小圆点） ────────────
nodes = Image.new("RGBA", (S, S), (0, 0, 0, 0))
nd = ImageDraw.Draw(nodes)
node_positions = [
    # 左侧
    (int(S * 0.14), bear_y - int(S * 0.12), ACCENT, 5),
    (int(S * 0.20), bear_y, ACCENT2, 4),
    (int(S * 0.16), bear_y + int(S * 0.12), DIM, 3),
    # 右侧
    (S - int(S * 0.14), bear_y - int(S * 0.12), ACCENT, 5),
    (S - int(S * 0.20), bear_y, ACCENT2, 4),
    (S - int(S * 0.16), bear_y + int(S * 0.12), DIM, 3),
]
for nx, ny, nc, nr in node_positions:
    nr_scaled = nr * SCALE
    # 外发光
    for glow_r in range(nr_scaled * 3, nr_scaled, -1):
        a = int(30 * (nr_scaled * 3 - glow_r) / (nr_scaled * 2))
        nd.ellipse(
            [nx - glow_r, ny - glow_r, nx + glow_r, ny + glow_r],
            fill=(*nc, a),
        )
    # 实心
    nd.ellipse(
        [nx - nr_scaled, ny - nr_scaled, nx + nr_scaled, ny + nr_scaled],
        fill=(*nc, 220),
    )
nodes = nodes.filter(ImageFilter.GaussianBlur(radius=SCALE))
img = Image.alpha_composite(img, nodes)
draw = ImageDraw.Draw(img)

# ── 白熊头（主体） ──────────────────────
ear_r = int(head_r * 0.55)
ear_offset = int(head_r * 0.75)
ear_up = int(SCALE * 8)

# 发光层
bear_glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
bg2 = ImageDraw.Draw(bear_glow)
for spread in range(int(SCALE * 6), 0, -1):
    a = int(20 / spread * 30)
    bg2.ellipse(
        [cx - head_r - spread, bear_y - head_r - spread,
         cx + head_r + spread, bear_y + head_r + spread],
        fill=(*WHITE, a),
    )
bear_glow = bear_glow.filter(ImageFilter.GaussianBlur(radius=SCALE * 4))
img = Image.alpha_composite(img, bear_glow)
draw = ImageDraw.Draw(img)

# 耳朵
left_ear_cx = cx - ear_offset
right_ear_cx = cx + ear_offset
ear_cy = bear_y - head_r + ear_r - ear_up

draw.ellipse(
    [left_ear_cx - ear_r, ear_cy - ear_r, left_ear_cx + ear_r, ear_cy + ear_r],
    fill=(*WHITE, 240),
)
draw.ellipse(
    [right_ear_cx - ear_r, ear_cy - ear_r, right_ear_cx + ear_r, ear_cy + ear_r],
    fill=(*WHITE, 240),
)

# 耳朵内侧
inner_ear_r = int(ear_r * 0.45)
draw.ellipse(
    [left_ear_cx - inner_ear_r, ear_cy - inner_ear_r,
     left_ear_cx + inner_ear_r, ear_cy + inner_ear_r],
    fill=(30, 30, 45, 180),
)
draw.ellipse(
    [right_ear_cx - inner_ear_r, ear_cy - inner_ear_r,
     right_ear_cx + inner_ear_r, ear_cy + inner_ear_r],
    fill=(30, 30, 45, 180),
)

# 头部
draw.ellipse(
    [cx - head_r, bear_y - head_r, cx + head_r, bear_y + head_r],
    fill=WHITE,
)

# 眼睛
eye_r = int(head_r * 0.09)
eye_offset_x = int(head_r * 0.32)
eye_offset_y = int(head_r * 0.1)
eye_y = bear_y - eye_offset_y
draw.ellipse(
    [cx - eye_offset_x - eye_r, eye_y - eye_r,
     cx - eye_offset_x + eye_r, eye_y + eye_r],
    fill=(30, 30, 45),
)
draw.ellipse(
    [cx + eye_offset_x - eye_r, eye_y - eye_r,
     cx + eye_offset_x + eye_r, eye_y + eye_r],
    fill=(30, 30, 45),
)

# 鼻子
nose_w = int(head_r * 0.22)
nose_h = int(head_r * 0.16)
nose_y = bear_y + int(head_r * 0.15)
draw.ellipse(
    [cx - nose_w, nose_y - nose_h, cx + nose_w, nose_y + nose_h],
    fill=(30, 30, 45),
)

# ── 信号弧线（头顶，三层） ────────────────
def arc(radius, start, end, width, color, alpha):
    arc_cy = bear_y - head_r - int(SCALE * 5)
    bbox = [cx - radius, arc_cy - radius * 0.9, cx + radius, arc_cy + radius * 0.9]
    draw.arc(bbox, start=start, end=end, fill=(*color, alpha), width=width)

arc(int(S * 0.11), 205, 335, int(SCALE * 4), WHITE, 200)
arc(int(S * 0.14), 210, 330, int(SCALE * 3), ACCENT, 140)
arc(int(S * 0.17), 212, 328, int(SCALE * 2), ACCENT2, 70)

# ── 底部信息卡片剪影（代表信息流内容） ────
card_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
cd = ImageDraw.Draw(card_layer)
card_y = bear_y + head_r + int(SCALE * 14)
card_w = int(S * 0.35)
card_h = int(SCALE * 16)
card_gap = int(SCALE * 4)

for i, alpha in enumerate([70, 50, 30]):
    offset_x = (i - 1) * int(SCALE * 6)
    cy_card = card_y + i * card_gap
    # 卡片背景
    cd.rounded_rectangle(
        [cx - card_w // 2 + offset_x, cy_card,
         cx + card_w // 2 + offset_x, cy_card + card_h],
        radius=int(SCALE * 4),
        fill=(80, 100, 140, alpha),
    )
    # 卡片上的文字线（模拟标题）
    line_h = int(SCALE * 3)
    cd.rectangle(
        [cx - card_w // 2 + offset_x + int(SCALE * 6),
         cy_card + int(SCALE * 5),
         cx - card_w // 2 + offset_x + int(card_w * 0.5),
         cy_card + int(SCALE * 5) + line_h],
        fill=(140, 160, 200, alpha + 40),
    )
    # 短行
    cd.rectangle(
        [cx - card_w // 2 + offset_x + int(SCALE * 6),
         cy_card + int(SCALE * 11),
         cx - card_w // 2 + offset_x + int(card_w * 0.3),
         cy_card + int(SCALE * 11) + line_h],
        fill=(120, 140, 180, alpha + 20),
    )

card_layer = card_layer.filter(ImageFilter.GaussianBlur(radius=SCALE))
img = Image.alpha_composite(img, card_layer)
draw = ImageDraw.Draw(img)

# ── 外圈装饰环 ────────────────────────────
ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
rd = ImageDraw.Draw(ring)
rd.ellipse(
    [cx - int(S * 0.43), cy - int(S * 0.43), cx + int(S * 0.43), cy + int(S * 0.43)],
    outline=(99, 162, 255, 25),
    width=int(SCALE * 2),
)
rd.ellipse(
    [cx - int(S * 0.46), cy - int(S * 0.46), cx + int(S * 0.46), cy + int(S * 0.46)],
    outline=(255, 255, 255, 8),
    width=SCALE,
)
ring = ring.filter(ImageFilter.GaussianBlur(radius=SCALE))
img = Image.alpha_composite(img, ring)
draw = ImageDraw.Draw(img)

# ── 圆角裁剪 ────────────────────────────
mask = Image.new("L", (S, S), 0)
mask_draw = ImageDraw.Draw(mask)
mask_draw.rounded_rectangle([0, 0, S, S], radius=int(72 * SCALE), fill=255)
img = Image.composite(img, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask)

# ── 缩放到目标尺寸 ──────────────────────
img = img.resize((SIZE, SIZE), RESAMPLE)
img.save("/home/tank/.hermes/scripts/infosource/assets/icon.png")
img.save("/home/tank/.hermes/scripts/infosource/assets/icon_square.png")
img.resize((256, 256), RESAMPLE).save("/home/tank/.hermes/scripts/infosource/assets/icon_256.png")

print("✓ v6 icons generated — 大白熊+信息流丰富版")
