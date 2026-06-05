import io
import random
from PIL import Image, ImageDraw, ImageFont


def generate_captcha() -> tuple[io.BytesIO, str]:
    answer = str(random.randint(1000, 9999))

    width, height = 220, 80
    bg_color = (18, 18, 18)
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    for _ in range(600):
        x = random.randint(0, width)
        y = random.randint(0, height)
        r = random.randint(60, 130)
        draw.point((x, y), fill=(r, r, r))

    for _ in range(6):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=(60, 60, 60), width=1)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
    except Exception:
        font = ImageFont.load_default()

    for i, ch in enumerate(answer):
        x = 22 + i * 46 + random.randint(-4, 4)
        y = 16 + random.randint(-6, 6)
        shade = random.randint(190, 240)
        draw.text((x, y), ch, fill=(shade, shade, shade), font=font)

    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf, answer
