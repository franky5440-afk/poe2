#!/usr/bin/env python3
"""Build the four hero scene layers from the supplied source images.

Run with the system interpreter (it has Pillow installed):
    python3 scripts/build_scene.py

The two source images are not in this repo (they are large and this repo is
public). Put them in ~/下載, or point POE2_SCENE_SRC at whatever directory
holds them:
    POE2_SCENE_SRC=/path/to/sources python3 scripts/build_scene.py

Parameters below are intentionally kept in one place:
* SKY_BRIGHTNESS darkens the supplied sky; SKY_SATURATION below 1 removes colour.
* TOWN_FADE_START/END define the transparent-to-opaque town edge feather.
* FRAME_CROP is the fraction of the source retained for each edge snake.
* FRAME_FADE_START/END define the snake's outward-to-inward alpha feather.
"""

import os
from pathlib import Path

from PIL import Image, ImageEnhance, ImageStat


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = Path(os.environ.get("POE2_SCENE_SRC") or Path.home() / "下載")
ORIGINAL = SOURCE_DIR / "image (1).webp"
SOURCE_SKY = SOURCE_DIR / "storm_clouds_dusk.webp"
OUT_DIR = ROOT / "static" / "scene"

SKY_BRIGHTNESS = 0.56
SKY_SATURATION = 0.35
TOWN_FADE_START = 0.18
TOWN_FADE_END = 0.28
FRAME_CROP = 0.28
FRAME_FADE_START = 0.20
FRAME_FADE_END = 0.255


def edge_alpha(width, start, end, reverse=False):
    """Create a horizontal alpha ramp, constant vertically."""
    values = []
    for x in range(width):
        position = x / max(width - 1, 1)
        if reverse:
            position = 1 - position
        if position <= start:
            alpha = 255
        elif position >= end:
            alpha = 0
        else:
            alpha = round(255 * (end - position) / (end - start))
        values.append(alpha)
    alpha = Image.new("L", (width, 1))
    alpha.putdata(values)
    return alpha


def town_layer(original):
    width, height = original.size
    alpha = Image.new("L", (width, height), 0)
    row = []
    for x in range(width):
        position = x / max(width - 1, 1)
        if position < TOWN_FADE_START:
            value = 0
        elif position < TOWN_FADE_END:
            value = round(255 * (position - TOWN_FADE_START) / (TOWN_FADE_END - TOWN_FADE_START))
        elif position <= 1 - TOWN_FADE_END:
            value = 255
        elif position <= 1 - TOWN_FADE_START:
            value = round(255 * (position - (1 - TOWN_FADE_END)) / (TOWN_FADE_END - TOWN_FADE_START))
        else:
            value = 0
        row.append(value)
    alpha.putdata(row * height)
    layer = original.convert("RGBA").copy()
    layer.putalpha(alpha)
    return layer


def frame_layer(original, left):
    width, height = original.size
    crop_width = round(width * FRAME_CROP)
    box = (0, 0, crop_width, height) if left else (width - crop_width, 0, width, height)
    layer = original.crop(box).convert("RGBA")
    if left:
        alpha = edge_alpha(crop_width, FRAME_FADE_START / FRAME_CROP, FRAME_FADE_END / FRAME_CROP)
    else:
        alpha = edge_alpha(crop_width, FRAME_FADE_START / FRAME_CROP, FRAME_FADE_END / FRAME_CROP, reverse=True)
    layer.putalpha(alpha.resize(layer.size))
    return layer


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    original = Image.open(ORIGINAL).convert("RGB")
    source_sky = Image.open(SOURCE_SKY).convert("RGB")

    sky = ImageEnhance.Color(source_sky).enhance(SKY_SATURATION)
    sky = ImageEnhance.Brightness(sky).enhance(SKY_BRIGHTNESS)
    town = town_layer(original)
    left = frame_layer(original, left=True)
    right = frame_layer(original, left=False)

    sky.save(OUT_DIR / "sky.webp", "WEBP", quality=88, method=6)
    town.save(OUT_DIR / "town.webp", "WEBP", quality=90, method=6)
    left.save(OUT_DIR / "frame-left.webp", "WEBP", quality=90, method=6)
    right.save(OUT_DIR / "frame-right.webp", "WEBP", quality=90, method=6)

    mean = ImageStat.Stat(sky).mean
    print(f"sky mean RGB: {tuple(round(v, 1) for v in mean)}")
    print(f"wrote {OUT_DIR / 'sky.webp'}, {OUT_DIR / 'town.webp'}, frame-left.webp, frame-right.webp")


if __name__ == "__main__":
    main()
