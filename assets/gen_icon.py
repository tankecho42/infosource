#!/usr/bin/env python3
"""
InfoSource Logo v4 — 极简信号传播 + 白熊印记
概念：信号从中心向外传播，中心是一个极简的白熊头剪影
灵感：Linear / Stripe / Arc 风格 + Echo的白色大熊身份
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
bg = Image.new("RGBA", (S, S), (12, 12, 20, 255))
bg_draw = ImageDraw.Draw(bg)
for r in range(int(S * 0.7), 0, -2):
    t = 1 - r / (S * 0.7)
    b = int(8 * t)
    bg_draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=(12 + b, 12 + b, 20 + b * 2, 255),
    )
img = Image.alpha_composite(img, bg)
draw = ImageDraw.Draw(img)

WHITE = (255, 255, 255)
ACCENT = (99, 162, 255)

# ── 信号波纹 ────────────────────────────
def arc(radius, start, end, width, color, alpha):
    bbox = [cx - radius, cy - radius * 0.85, cx + radius, cy + radius * 1.15]
    draw.arc(bbox, start=start, end=end, fill=(*color, alpha), width=width)

arc(int(S * 0.19), 205, 335, int(SCALE * 7), WHITE, 200)
arc(int(S * 0.26), 210, 330, int(SCALE * 6), ACCENT, 160)
arc(int(S * 0.33), 212, 328, int(SCALE * 5), ACCENT, 90)

# ── 中心发光底层 ──────────────────────────
dot_r = int(SCALE * 6)
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
glow_draw = ImageDraw.Draw(glow)
glow_draw.ellipse(
    [cx - dot_r * 5, cy - dot_r * 5, cx + dot_r * 5, cy + dot_r * 5],
    fill=(*ACCENT, 50),
)
glow = glow.filter(ImageFilter.GaussianBlur(radius=SCALE * 10))
img = Image.alpha_composite(img, glow)
draw = ImageDraw.Draw(img)

# ── 中心标志：极简白熊头 ──────────────────
# 概念：一个圆头 + 两个小圆耳朵 = 一眼认出是熊
# 尺寸经过精心调整，确保在小尺寸下耳朵依然可见
bear_y = cy  # 略微上移让弧线从下方发出
head_r = int(SCALE * 11)
ear_r = int(SCALE * 5.5)
ear_offset = int(SCALE * 9)   # 耳朵中心到头顶中心的距离
ear_up = int(SCALE * 4)       # 耳朵往上超出头顶多少

# 发光层
bear_glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
bg_draw2 = ImageDraw.Draw(bear_glow)
for spread in range(int(SCALE * 4), 0, -1):
    a = int(15 / spread * 25)
    bg_draw2.ellipse(
        [cx - head_r - spread, bear_y - head_r - spread,
         cx + head_r + spread, bear_y + head_r + spread],
        fill=(*WHITE, a),
    )
bear_glow = bear_glow.filter(ImageFilter.GaussianBlur(radius=SCALE * 3))
img = Image.alpha_composite(img, bear_glow)
draw = ImageDraw.Draw(img)

# 耳朵（先画耳朵，被头部稍微遮挡）
left_ear_cx = cx - ear_offset
right_ear_cx = cx + ear_offset
ear_cy = bear_y - head_r + ear_r - ear_up

draw.ellipse(
    [left_ear_cx - ear_r, ear_cy - ear_r, left_ear_cx + ear_r, ear_cy + ear_r],
    fill=(*WHITE, 235),
)
draw.ellipse(
    [right_ear_cx - ear_r, ear_cy - ear_r, right_ear_cx + ear_r, ear_cy + ear_r],
    fill=(*WHITE, 235),
)

# 头部
draw.ellipse(
    [cx - head_r, bear_y - head_r, cx + head_r, bear_y + head_r],
    fill=WHITE,
)

# ── 外圈细线装饰 ──────────────────────────
draw.ellipse(
    [cx - int(S * 0.42), cy - int(S * 0.42), cx + int(S * 0.42), cy + int(S * 0.42)],
    outline=(255, 255, 255, 12),
    width=SCALE,
)

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

print("✓ v4 icons generated — 白熊印记版")
