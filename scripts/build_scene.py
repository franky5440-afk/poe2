#!/usr/bin/env python3
"""Build the four hero scene layers from the supplied source images.

Run with the system interpreter (it has Pillow installed):
    python3 scripts/build_scene.py

Source images live in picture/ (not in this repo: large, and this repo is
public). Point POE2_SCENE_SRC at another directory if needed:
    POE2_SCENE_SRC=/path/to/sources python3 scripts/build_scene.py

Sources:
* aztec_ruined_city.jpg      full scene WITHOUT serpents -> town layer as-is
* storm_clouds_dusk.webp     plain sky -> sky layer (darkened, desaturated)
* serpent-left-cut.png       true alpha cutout of the left serpent (Adobe
* serpent-right-cut.png      image_remove_background on a white-bg render)

The serpents were rendered on white with flat bright light, far brighter than
the dusk scene, so FRAME_* grades them back down into the scene's tonality.
An earlier version of this script faked the cutout with a rectangular alpha
ramp; that is why scrolling dragged a slab of background along with the snake.
"""

import os
from pathlib import Path

from PIL import Image, ImageEnhance, ImageStat


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = Path(os.environ.get("POE2_SCENE_SRC") or ROOT / "picture")
SOURCE_SCENE = SOURCE_DIR / "aztec_ruined_city.jpg"
SOURCE_SKY = SOURCE_DIR / "storm_clouds_dusk.webp"
SOURCE_LEFT = SOURCE_DIR / "serpent-left-cut.png"
SOURCE_RIGHT = SOURCE_DIR / "serpent-right-cut.png"
OUT_DIR = ROOT / "static" / "scene"

SKY_BRIGHTNESS = 0.56
SKY_SATURATION = 0.35
FRAME_BRIGHTNESS = 0.42
FRAME_SATURATION = 0.80
FRAME_TINT = (0.94, 0.99, 1.08)  # per-channel multiplier: push the stone cold


def grade_frame(layer):
    """Darken/cool a white-background render so it sits in the dusk scene."""
    rgb = layer.convert("RGB")
    rgb = ImageEnhance.Color(rgb).enhance(FRAME_SATURATION)
    rgb = ImageEnhance.Brightness(rgb).enhance(FRAME_BRIGHTNESS)
    r, g, b = rgb.split()
    r = r.point(lambda v: min(255, round(v * FRAME_TINT[0])))
    g = g.point(lambda v: min(255, round(v * FRAME_TINT[1])))
    b = b.point(lambda v: min(255, round(v * FRAME_TINT[2])))
    out = Image.merge("RGB", (r, g, b)).convert("RGBA")
    out.putalpha(layer.getchannel("A"))
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scene = Image.open(SOURCE_SCENE).convert("RGB")
    source_sky = Image.open(SOURCE_SKY).convert("RGB")
    left = Image.open(SOURCE_LEFT).convert("RGBA")
    right = Image.open(SOURCE_RIGHT).convert("RGBA")

    sky = ImageEnhance.Color(source_sky).enhance(SKY_SATURATION)
    sky = ImageEnhance.Brightness(sky).enhance(SKY_BRIGHTNESS)

    sky.save(OUT_DIR / "sky.webp", "WEBP", quality=88, method=6)
    scene.save(OUT_DIR / "town.webp", "WEBP", quality=90, method=6)
    grade_frame(left).save(OUT_DIR / "frame-left.webp", "WEBP", quality=88, method=6)
    grade_frame(right).save(OUT_DIR / "frame-right.webp", "WEBP", quality=88, method=6)

    mean = ImageStat.Stat(sky).mean
    print(f"sky mean RGB: {tuple(round(v, 1) for v in mean)}")
    for name in ("sky", "town", "frame-left", "frame-right"):
        p = OUT_DIR / f"{name}.webp"
        print(f"wrote {p.relative_to(ROOT)} {Image.open(p).size} {p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
