import os
import re
import secrets
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont


def _slugify(value):
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def _pick_color():
    palette = [
        "#0D6E6E",
        "#2E7D32",
        "#1E88E5",
        "#6A1B9A",
        "#F57C00",
        "#C62828",
        "#00897B",
        "#455A64",
    ]
    return secrets.choice(palette)


def _fit_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = []
    for word in words:
        test = " ".join(current + [word]).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines[:2]


def generate_organization_text_logo(static_folder, organization_name):
    logos_dir = os.path.join(static_folder, "assets", "images", "client-logos")
    os.makedirs(logos_dir, exist_ok=True)

    img = Image.new("RGB", (800, 320), "#F7FAF7")
    draw = ImageDraw.Draw(img)
    accent = _pick_color()

    draw.rectangle((0, 0, 800, 18), fill=accent)
    draw.rectangle((0, 302, 800, 320), fill=accent)

    initials = "".join(part[0] for part in (organization_name or "").split()[:2]).upper() or "MC"
    draw.ellipse((36, 85, 196, 245), fill=accent)
    try:
        initials_font = ImageFont.truetype("arial.ttf", 72)
    except OSError:
        initials_font = ImageFont.load_default()
    ibox = draw.textbbox((0, 0), initials, font=initials_font)
    iw = ibox[2] - ibox[0]
    ih = ibox[3] - ibox[1]
    draw.text((116 - iw / 2, 165 - ih / 2), initials, font=initials_font, fill="white")

    try:
        title_font = ImageFont.truetype("arial.ttf", 52)
    except OSError:
        title_font = ImageFont.load_default()
    lines = _fit_text(draw, organization_name or "Organization", title_font, 540)
    y = 110
    for line in lines:
        draw.text((235, y), line, font=title_font, fill="#0F2E2E")
        y += 64

    draw.text((235, 248), "Client Organization", fill=accent, font=ImageFont.load_default())

    filename = (
        f"org-text-{_slugify(organization_name) or 'organization'}-"
        f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.png"
    )
    destination = os.path.join(logos_dir, filename)
    img.save(destination, format="PNG")
    return f"assets/images/client-logos/{filename}"
