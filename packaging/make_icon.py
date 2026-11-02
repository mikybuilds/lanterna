"""Draws the Lanterna app icon (same shapes as assets/logo.svg) into packaging/lanterna.ico and a PNG.

Run: python packaging/make_icon.py   (needs Pillow)
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

K = 4                      # draw at 4x of the 512 grid for smooth edges
S = 512 * K
OUT = Path(__file__).parent


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def vgrad(size, top, bottom):
    w, h = size
    g = Image.new("RGBA", size)
    d = ImageDraw.Draw(g)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(top, bottom, y / max(1, h - 1)))
    return g


def mask(draw_fn):
    m = Image.new("L", (S, S), 0)
    draw_fn(ImageDraw.Draw(m))
    return m


def over(img, src, m):
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    layer.paste(src, (0, 0), m)
    return Image.alpha_composite(img, layer)


def r(*v):
    return [x * K for x in v]


def main():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # tile
    tile = vgrad((S, S), (26, 32, 52, 255), (11, 14, 23, 255))
    img = over(img, tile, mask(lambda d: d.rounded_rectangle(r(0, 0, 512, 512), radius=114 * K, fill=255)))
    # halo
    halo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse(r(256 - 120, 282 - 120, 256 + 120, 282 + 120), fill=(245, 181, 68, 120))
    halo = halo.filter(ImageFilter.GaussianBlur(60 * K))
    img = Image.alpha_composite(img, halo)
    metal = vgrad((S, S), (255, 210, 122, 255), (227, 154, 46, 255))
    # handle (arc + two short legs)
    hm = mask(lambda m: (m.arc(r(212, 82, 300, 170), 180, 360, fill=255, width=18 * K),
                         m.line(r(212, 126, 212, 146), fill=255, width=18 * K),
                         m.line(r(300, 126, 300, 146), fill=255, width=18 * K)))
    img = over(img, metal, hm)
    # glass body
    glass = Image.new("RGBA", (S, S), (245, 181, 68, 50))
    img = over(img, glass, mask(lambda m: m.rounded_rectangle(r(196, 176, 316, 352), radius=42 * K, fill=255)))
    img = over(img, metal, mask(lambda m: m.rounded_rectangle(r(196, 176, 316, 352), radius=42 * K, outline=255, width=14 * K)))
    # cap and base
    img = over(img, metal, mask(lambda m: m.rounded_rectangle(r(178, 142, 334, 176), radius=13 * K, fill=255)))
    img = over(img, metal, mask(lambda m: m.rounded_rectangle(r(178, 350, 334, 382), radius=13 * K, fill=255)))
    # flame: teardrop = circle + triangle tip
    flame = vgrad((S, S), (255, 244, 214, 255), (240, 138, 36, 255))
    fm = mask(lambda m: (m.ellipse(r(214, 252, 298, 336), fill=255), m.polygon(r(256, 214, 219, 274, 293, 274), fill=255)))
    img = over(img, flame, fm.filter(ImageFilter.GaussianBlur(K)))
    big = img.resize((512, 512), Image.LANCZOS)
    big.save(OUT / "lanterna.png")
    big.save(OUT / "lanterna.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written")


if __name__ == "__main__":
    main()
