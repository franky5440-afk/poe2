#!/usr/bin/env python3
"""hero 場景素材的契約測試。

跑法：python3 tests/scene_assets.py      （要用系統 python3，venv 裡沒有 PIL）

只驗證「幾何上可量測」的條件——也就是 Bug A（巨蛇被裁掉）的修法必須滿足的性質。
Bug B（捲動殘影）屬於視覺問題，量不出來，一律由主對話截圖驗收，不在此處假裝有測到。
"""
import sys
from PIL import Image, ImageStat

SCENE = "static/scene"
FAILS = []
PASSES = []


def check(name, fn):
    try:
        r = fn()
    except Exception as e:  # noqa: BLE001
        r = f"EXCEPTION: {e}"
    if r is True:
        PASSES.append(name)
        print(f"  [PASS] {name}")
    else:
        FAILS.append(name)
        print(f"  [FAIL] {name}\n         → {r}")


def alpha_band(img, x0, x1):
    """回傳 [x0, x1) 這段垂直條帶的 alpha 平均值（x 用 0~1 的比例）。"""
    w, h = img.size
    box = (int(w * x0), 0, max(int(w * x1), int(w * x0) + 1), h)
    return ImageStat.Stat(img.split()[3].crop(box)).mean[0]


def load(name):
    return Image.open(f"{SCENE}/{name}").convert("RGBA")


def monotonic_fade(img, reverse=False):
    """alpha 沿 x 必須大致單調遞減（reverse=True 則遞增），容忍 8/255 的抖動。"""
    vals = [alpha_band(img, i / 24, (i + 1) / 24) for i in range(24)]
    if reverse:
        vals = vals[::-1]
    bad = [(i, round(vals[i]), round(vals[i + 1]))
           for i in range(len(vals) - 1) if vals[i + 1] > vals[i] + 8]
    return True if not bad else f"alpha 沿 x 不是單調淡出，反轉處 {bad}"


print("hero 場景素材契約\n")

# ── A1 檔案齊全 ──────────────────────────────────────────────────
check("A1 四張場景素材都存在（sky / town / frame-left / frame-right）", lambda: (
    True if all(__import__("os").path.exists(f"{SCENE}/{n}")
                for n in ("sky.webp", "town.webp", "frame-left.webp", "frame-right.webp"))
    else "缺檔：" + ", ".join(n for n in ("sky.webp", "town.webp", "frame-left.webp", "frame-right.webp")
                              if not __import__("os").path.exists(f"{SCENE}/{n}"))))

if FAILS:
    print(f"\n  {len(PASSES)}/{len(PASSES) + len(FAILS)} 通過（缺檔，後續檢查略過）")
    sys.exit(1)

left, right = load("frame-left.webp"), load("frame-right.webp")

# ── A2 左邊框：蛇貼在最左緣，內側（右）羽化到透明 ────────────────
check("A2a frame-left 最左 6% 是實心（alpha >= 200）",
      lambda: True if alpha_band(left, 0, .06) >= 200
      else f"實得 {alpha_band(left, 0, .06):.0f}，蛇沒有貼齊左緣")
check("A2b frame-left 最右 8% 已透明（alpha <= 8）",
      lambda: True if alpha_band(left, .92, 1) <= 8
      else f"實得 {alpha_band(left, .92, 1):.0f}，內側沒有羽化乾淨，會出現硬邊")
check("A2c frame-left alpha 沿 x 單調淡出", lambda: monotonic_fade(left))

# ── A3 右邊框：鏡像條件 ──────────────────────────────────────────
check("A3a frame-right 最右 6% 是實心（alpha >= 200）",
      lambda: True if alpha_band(right, .94, 1) >= 200
      else f"實得 {alpha_band(right, .94, 1):.0f}，蛇沒有貼齊右緣")
check("A3b frame-right 最左 8% 已透明（alpha <= 8）",
      lambda: True if alpha_band(right, 0, .08) <= 8
      else f"實得 {alpha_band(right, 0, .08):.0f}，內側沒有羽化乾淨，會出現硬邊")
check("A3c frame-right alpha 沿 x 單調淡出（由右往左）",
      lambda: monotonic_fade(right, reverse=True))

# ── A4 左右邊框寬高比必須是窄長條，否則貼邊後仍會蓋住畫面中央 ────
def narrow(img, who):
    w, h = img.size
    return True if w / h <= 1.0 else f"{who} 是 {w}x{h}（寬高比 {w/h:.2f}），太寬，貼邊後會侵占畫面中央"

check("A4a frame-left 是窄長條（寬高比 <= 1.0）", lambda: narrow(left, "frame-left"))
check("A4b frame-right 是窄長條（寬高比 <= 1.0）", lambda: narrow(right, "frame-right"))

# ── A5 左右邊框高度一致，避免貼邊後上下對不齊 ────────────────────
check("A5 左右邊框高度一致",
      lambda: True if left.size[1] == right.size[1]
      else f"left 高 {left.size[1]}，right 高 {right.size[1]}")

# ── A6 town 左右兩側必須羽化乾淨：巨蛇只能由 frame 層負責 ──────
# town 目前是「整張圖」的羽化版，蛇也含在裡面。frame 拆成左右貼邊之後，
# town 裡那條被 cover 裁到別的位置的蛇會跟貼邊的蛇疊成雙影 —— 等於修掉
# Bug B 又長出一個同類的問題。所以 town 兩側要淡到看不見蛇為止。
town = load("town.webp")
check("A6a town 最左 18% 已羽化乾淨（alpha <= 10）",
      lambda: True if alpha_band(town, 0, .18) <= 10
      else f"實得 {alpha_band(town, 0, .18):.0f}，town 左側仍有蛇，會與 frame-left 疊成雙影")
check("A6b town 最右 18% 已羽化乾淨（alpha <= 10）",
      lambda: True if alpha_band(town, .82, 1) <= 10
      else f"實得 {alpha_band(town, .82, 1):.0f}，town 右側仍有蛇，會與 frame-right 疊成雙影")

print(f"\n  {len(PASSES)}/{len(PASSES) + len(FAILS)} 通過")
sys.exit(0 if not FAILS else 1)
