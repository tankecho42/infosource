#!/usr/bin/env python3
"""
InfoSource Logo — 雷达波 + 信息卡 设计
赛博朋克风格，深底霓虹绿
"""
from PIL import Image, ImageDraw
import math

# LANCZOS in newer Pillow, fallback for older
try:
    RESAMPLE = Image.LANCZOS
except AttributeError:
    RESAMPLE = Image.Resampling.LANCZOS

SIZE = 512
CX, CY = SIZE // 2, SIZE // 2

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# 背景圆角矩形 — 深色
bg_radius = 60
draw.rounded_rectangle([0, 0, SIZE, SIZE], radius=bg_radius, fill=(10, 10, 15, 255))

# 雷达波纹 — 三圈，霓虹绿
accent = (0, 255, 136, 255)
accent_dim = (0, 255, 136, 60)
accent_mid = (0, 255, 136, 120)

for i, (r, alpha) in enumerate([(180, 25), (130, 50), (80, 90)]):
    color = (0, 255, 136, alpha)
    draw.ellipse(
        [CX - r, CY - r - 10, CX + r, CY + r - 10],
        outline=color,
        width=2,
    )

# 雷达扫描扇形 — 从中心向右上
for angle_deg in range(-80, 10, 2):
    angle = math.radians(angle_deg - 90)
    fade = abs(angle_deg + 35) / 45
    alpha = int(100 * (1 - fade))
    if alpha <= 0:
        continue
    x2 = CX + 175 * math.cos(angle)
    y2 = (CY - 10) + 175 * math.sin(angle)
    color = (0, 255, 136, alpha)
    draw.line([CX, CY - 10, x2, y2], fill=color, width=1)

# 中心信息卡片 — 白色发光小方块
card_w, card_h = 120, 90
card_x = CX - card_w // 2
card_y = CY - card_h // 2 - 10

# 卡片发光底
for spread in range(8, 0, -1):
    a = int(8 / spread * 40)
    draw.rounded_rectangle(
        [card_x - spread, card_y - spread, card_x + card_w + spread, card_y + card_h + spread],
        radius=12 + spread,
        fill=(0, 255, 136, a),
    )

# 卡片本体 — 深底绿边
draw.rounded_rectangle(
    [card_x, card_y, card_x + card_w, card_y + card_h],
    radius=12,
    fill=(15, 15, 25, 255),
    outline=accent,
    width=2,
)

# 卡片内容线条 — 模拟文字行
line_y = card_y + 18
for i, (lw, alpha) in enumerate([(70, 220), (50, 140), (80, 180), (40, 120)]):
    draw.rounded_rectangle(
        [card_x + 15, line_y, card_x + 15 + lw, line_y + 8],
        radius=4,
        fill=(0, 255, 136, alpha),
    )
    line_y += 16

# 右上角信号点 — 小亮点表示"检测到新信息"
dot_x, dot_y = CX + 95, CY - 95
for spread in range(6, 0, -1):
    a = int(40 / spread)
    draw.ellipse(
        [dot_x - spread, dot_y - spread, dot_x + spread, dot_y + spread],
        fill=(0, 255, 136, a),
    )
draw.ellipse([dot_x - 4, dot_y - 4, dot_x + 4, dot_y + 4], fill=(255, 255, 255, 255))

img.save("/home/tank/.hermes/scripts/infosource/assets/icon.png")

# 再存一个512x512无圆角的正方形版（适合当头像）
img_sq = img.crop((0, 0, SIZE, SIZE))
img_sq.save("/home/tank/.hermes/scripts/infosource/assets/icon_square.png")

# 256x256 小尺寸
img_small = img.resize((256, 256), RESAMPLE)
img_small.save("/home/tank/.hermes/scripts/infosource/assets/icon_256.png")

print("✓ Icons generated:")
print("  assets/icon.png (512x512 rounded)")
print("  assets/icon_square.png (512x512 square)")
print("  assets/icon_256.png (256x256)")
