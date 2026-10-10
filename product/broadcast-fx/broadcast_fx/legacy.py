"""Flagg clutch drive — 2K-style HUD + CourtVision-style commentary cut (no Agent system).

    python3 render.py <workdir>            # full render -> out/video.mp4 (no audio)
    python3 render.py <workdir> --preview 200,900,1400   # PNG stills of output frames
Data: official NBA PBP/shot quality (event 666), manual per-frame annotation (editorial).
"""
import functools, json, math, subprocess
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

WD = None
FPS = 60000 / 1001
WIDTH, HEIGHT = 1920, 1080
TR, FOOT, STAB, BALL, G = {}, {}, {}, {}, {}
RIM = None


def configure(workdir):
    """Load one prepared asset directory explicitly; importing does not read media."""
    global WD, TR, FOOT, STAB, BALL, G, RIM, COURT, PIX
    WD = str(Path(workdir).expanduser().resolve())
    with open(Path(WD) / "track.json", encoding="utf-8") as source:
        TR = json.load(source)
    FOOT = {int(k): v for k, v in TR["foot"].items()}
    STAB = {int(k): v for k, v in TR["stab"].items()}
    BALL = {int(k): v for k, v in TR["ball"].items()}
    G = {int(k): np.array(v) for k, v in TR["G"].items()}
    RIM = TR["rim"]
    COURT = None
    local_pixel = Path(WD) / "fonts" / "fusion-pixel.otf"
    local_woff = Path(WD) / "fonts" / "fusion-pixel.woff2"
    PIX = str(local_pixel if local_pixel.exists() else local_woff if local_woff.exists() else PIXEL_SOURCE)
    for cached in (load, font, text_rgba, tag_cached):
        cached.cache_clear()
    return TR

# ---------------------------------------------------------------- palette (BGR)
def hexc(h):
    h = h.lstrip("#"); return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))
BLUE, CYAN = hexc("2ea8ff"), hexc("6fe3ff")
ORANGE, FLAME, LED = hexc("f4541f"), hexc("ff9a3d"), hexc("ffb23f")
GREEN, PURPLE, VIOLET = hexc("3dff8a"), hexc("a855f7"), hexc("c9a2ff")
CHALK, MUTED, VOID = hexc("f2f0ea"), hexc("8d93a3"), hexc("07080b")

def rgb(c):
    return (c[2], c[1], c[0])

# ---------------------------------------------------------------- fonts / text
# System fonts stay on the user's machine. Fusion Pixel is bundled under OFL.
REPO_ROOT = Path(__file__).resolve().parents[2]
PIXEL_SOURCE = REPO_ROOT / "web/assets/fonts/fusion-pixel-12px-monospaced-zh_hans.otf.woff2"
DIN = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"
DINA = "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"
CJK = "/System/Library/Fonts/Hiragino Sans GB.ttc"
PIX = str(PIXEL_SOURCE)

@functools.lru_cache(maxsize=None)
def font(path, size):
    candidates = [(path, 2 if path == CJK else 0), (PIX, 0)]
    for candidate, index in candidates:
        if not Path(candidate).is_file():
            continue
        try:
            return ImageFont.truetype(candidate, size, index=index)
        except OSError:
            if candidate.endswith(".woff2"):
                try:
                    from io import BytesIO
                    from fontTools.ttLib import TTFont
                    converted = TTFont(candidate)
                    converted.flavor = None
                    buffer = BytesIO()
                    converted.save(buffer)
                    buffer.seek(0)
                    return ImageFont.truetype(buffer, size)
                except (ImportError, OSError) as error:
                    raise RuntimeError("Install requirements.txt to enable the bundled Fusion Pixel font") from error
    raise RuntimeError("No usable font. Run prepare.py to prepare Fusion Pixel, or install requirements.txt.")

@functools.lru_cache(maxsize=4096)
def text_rgba(text, path, size, color, track=0, stroke=0, stroke_color=(0, 0, 0), shear=0.0):
    """RGBA numpy image (RGB order) of a text line; `color` is BGR."""
    f = font(path, size)
    widths = [f.getlength(ch) for ch in text]
    total = int(sum(widths) + track * max(0, len(text) - 1)) + 2 * stroke + 8
    asc, desc = f.getmetrics()
    h = asc + desc + 2 * stroke + 6
    im = Image.new("RGBA", (total + int(abs(shear) * h) + 4, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = stroke + 2 + (int(abs(shear) * h) if shear > 0 else 0)
    for ch, w in zip(text, widths):
        d.text((x, stroke + 2), ch, font=f, fill=rgb(color) + (255,), stroke_width=stroke,
               stroke_fill=rgb(stroke_color) + (255,))
        x += w + track
    if shear:
        im = im.transform(im.size, Image.AFFINE, (1, shear, -shear * h * (1 if shear > 0 else 0), 0, 1, 0), Image.BICUBIC)
    return np.array(im)

def text_w(text, path, size, track=0):
    return text_rgba(text, path, size, (255, 255, 255), track).shape[1]

# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x
def ease_out(x):
    x = clamp(x); return 1 - (1 - x) ** 3
def ease_in_out(x):
    x = clamp(x); return 3 * x * x - 2 * x * x * x
def back_out(x, s=1.9):
    x = clamp(x) - 1; return x * x * ((s + 1) * x + s) + 1
def window(t, a, b, fin=0.25, fout=0.25):
    """0..1 envelope for an element visible from a to b."""
    if t < a or t > b:
        return 0.0
    return min(ease_out((t - a) / fin) if fin else 1.0, ease_out((b - t) / fout) if fout else 1.0)

# ---------------------------------------------------------------- frame io / compositing
@functools.lru_cache(maxsize=8)
def load(path):
    im = cv2.imread(path)
    if im is None:
        raise FileNotFoundError(path)
    return im

def src_frame(i):
    return load(f"{WD}/full/f{int(i):04d}.jpg")

def slow_frame(j):
    return cv2.resize(load(f"{WD}/slow/s{int(j):04d}.jpg"), (WIDTH, HEIGHT)) if load(f"{WD}/slow/s{int(j):04d}.jpg").shape[1] != WIDTH else load(f"{WD}/slow/s{int(j):04d}.jpg")

class Layers:
    def __init__(self, base):
        self.img = base.astype(np.float32)
        self.sharp = np.zeros((HEIGHT, WIDTH, 4), np.uint8)
        self.glow = np.zeros((HEIGHT, WIDTH, 3), np.uint8)

    def paste(self, rgba, x, y, alpha=1.0, scale=1.0, anchor="lt"):
        if alpha <= 0.003:
            return
        if scale != 1.0:
            rgba = cv2.resize(rgba, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR if scale > 1 else cv2.INTER_AREA)
        h, w = rgba.shape[:2]
        if anchor == "c":
            x, y = x - w / 2, y - h / 2
        elif anchor == "cb":
            x, y = x - w / 2, y - h
        elif anchor == "rt":
            x = x - w
        elif anchor == "lc":
            y = y - h / 2
        elif anchor == "rc":
            x, y = x - w, y - h / 2
        x, y = int(round(x)), int(round(y))
        x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, WIDTH), min(y + h, HEIGHT)
        if x0 >= x1 or y0 >= y1:
            return
        patch = rgba[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
        a = patch[..., 3:4] / 255.0 * alpha
        bgr = patch[..., 2::-1]
        roi = self.img[y0:y1, x0:x1]
        roi[:] = roi * (1 - a) + bgr * a

    def compose(self, glow_gain=1.0):
        g = cv2.resize(self.glow, (WIDTH // 4, HEIGHT // 4), interpolation=cv2.INTER_AREA).astype(np.float32)
        g = cv2.GaussianBlur(g, (0, 0), 5) * 1.0 + cv2.GaussianBlur(g, (0, 0), 14) * 0.9
        g = cv2.resize(g, (WIDTH, HEIGHT), interpolation=cv2.INTER_LINEAR)
        self.img += g * glow_gain
        a = self.sharp[..., 3:4].astype(np.float32) / 255.0
        self.img = self.img * (1 - a) + self.sharp[..., :3].astype(np.float32) * a
        return np.clip(self.img, 0, 255).astype(np.uint8)

def rect(L, x0, y0, x1, y1, color, alpha):
    """Translucent rectangle directly on the image."""
    x0, y0, x1, y1 = [int(v) for v in (max(0, x0), max(0, y0), min(WIDTH, x1), min(HEIGHT, y1))]
    if x1 <= x0 or y1 <= y0 or alpha <= 0:
        return
    roi = L.img[y0:y1, x0:x1]
    roi[:] = roi * (1 - alpha) + np.array(color, np.float32) * alpha

def P(v):
    return int(round(v * 16))

def ellipse(layer, c, axes, color, alpha, thick, a0=0, a1=360, rot=0):
    col = tuple(int(x) for x in color) + ((int(alpha * 255),) if layer.shape[2] == 4 else ())
    cv2.ellipse(layer, (P(c[0]), P(c[1])), (max(1, P(axes[0])), max(1, P(axes[1]))), rot, a0, a1, col,
                thick, cv2.LINE_AA, 4)

def line(layer, p, q, color, alpha, thick):
    col = tuple(int(x) for x in color) + ((int(alpha * 255),) if layer.shape[2] == 4 else ())
    cv2.line(layer, (P(p[0]), P(p[1])), (P(q[0]), P(q[1])), col, thick, cv2.LINE_AA, 4)

def scale_c(color, k):
    return tuple(min(255, int(c * k)) for c in color)

def mix(c1, c2, k):
    return tuple(int(a + (b - a) * clamp(k)) for a, b in zip(c1, c2))

# ---------------------------------------------------------------- tracking helpers
def foot_at(f):
    f0 = int(math.floor(f)); k = f - f0
    a, b = FOOT.get(f0), FOOT.get(f0 + 1, FOOT.get(f0))
    if a is None:
        return None
    return [a[i] + (b[i] - a[i]) * k for i in range(3)]

def ball_at(f):
    f0 = int(math.floor(f)); k = f - f0
    a, b = BALL.get(f0), BALL.get(f0 + 1, BALL.get(f0))
    if a is None:
        return None
    return [a[i] + (b[i] - a[i]) * k for i in range(2)]

def to_frame(f, q):
    Ginv = np.linalg.inv(G[int(round(f))])
    v = Ginv @ np.array([q[0], q[1], 1.0]); return v[:2] / v[2]

def shot_clock(t):
    """Mirrors the broadcast shot-clock graphic: its digits change at t = 0.74 + k s, i.e. 21.74 - t."""
    return max(0.0, 21.74 - t)

# ---------------------------------------------------------------- HUD elements
def draw_ring(L, f, t, color, energy, alpha=1.0, pulse=0.0, grow=1.0):
    p = foot_at(f)
    if p is None or alpha <= 0.01:
        return
    cx, cy, h = p
    s = (1.0 + 0.06 * math.sin(t * 2 * math.pi * 2.2) * pulse) * grow
    rx = 0.6 * h * s; ry = rx * 0.33
    ellipse(L.glow, (cx, cy), (rx * 0.95, ry * 0.95), scale_c(color, 0.55 * alpha), 1, -1)
    ellipse(L.glow, (cx, cy), (rx, ry), scale_c(color, 1.2 * alpha), 1, 10)
    ellipse(L.sharp, (cx, cy), (rx, ry), color, 0.95 * alpha, 3)
    ellipse(L.sharp, (cx, cy), (rx * 0.74, ry * 0.74), color, 0.45 * alpha, 2)
    rot = (t * 110) % 360
    for k in range(6):
        a0 = rot + k * 60
        ellipse(L.sharp, (cx, cy), (rx * 1.16, ry * 1.16), CHALK, 0.85 * alpha, 3, a0, a0 + 22)
        ellipse(L.glow, (cx, cy), (rx * 1.16, ry * 1.16), scale_c(color, alpha), 1, 6, a0, a0 + 22)
    if energy is not None:   # shot-clock energy arc
        sweep = 360 * clamp(energy)
        ellipse(L.sharp, (cx, cy), (rx * 0.88, ry * 0.88), mix(color, CHALK, 0.4), 0.95 * alpha, 5, -90, -90 + sweep)
        ellipse(L.glow, (cx, cy), (rx * 0.88, ry * 0.88), scale_c(color, 1.4 * alpha), 1, 9, -90, -90 + sweep)

def draw_trail(L, f, color, seconds=1.3, alpha=1.0):
    n = int(seconds * FPS); fi = int(round(f))
    pts = []
    for k in range(n, -1, -2):
        q = STAB.get(fi - k)
        if q is not None:
            pts.append((to_frame(f, q), 1 - k / n))
    for (a, wa), (b, wb) in zip(pts, pts[1:]):
        al = alpha * wb ** 1.6
        line(L.sharp, a, b, color, 0.75 * al, max(1, int(1 + 5 * wb)))
        line(L.glow, a, b, scale_c(color, 0.9 * al), 1, int(4 + 8 * wb))

def tag_card(lines_key):
    """Pre-render the floating head tag (RGBA)."""
    num, name, sub, accent = lines_key
    BLUE_ = accent
    w, h = 330, 92
    card = np.zeros((h + 18, w, 4), np.uint8)
    card[:h, :, :3] = (11, 9, 8); card[:h, :, 3] = 205
    card[:h, :78, :3] = BLUE_[::-1]; card[:h, :78, 3] = 245
    card[h - 3:h, 78:, :3] = BLUE_[::-1]; card[h - 3:h, 78:, 3] = 255
    # pointer triangle
    tri = np.array([[w // 2 - 12, h], [w // 2 + 12, h], [w // 2, h + 16]], np.int32)
    cv2.fillPoly(card, [tri], (11, 9, 8, 205) if False else (8, 9, 11, 205))
    def put(rgba, x, y):
        hh, ww = rgba.shape[:2]
        roi = card[y:y + hh, x:x + ww].astype(np.float32); a = rgba[..., 3:4] / 255.0
        roi[..., :3] = roi[..., :3] * (1 - a) + rgba[..., :3] * a
        roi[..., 3:4] = np.maximum(roi[..., 3:4], rgba[..., 3:4])
        card[y:y + hh, x:x + ww] = roi.astype(np.uint8)
    n = text_rgba(num, DIN, 64, (255, 255, 255))
    put(n, (78 - n.shape[1]) // 2, 12)
    put(text_rgba(name, DIN, 44, CHALK, 2), 92, 6)
    put(text_rgba(sub, CJK, 22, LED), 94, 56)
    return card

@functools.lru_cache(maxsize=64)
def tag_cached(num, name, sub, accent):
    return tag_card((num, name, sub, accent))

def draw_tag(L, f, t, alpha, sub="弗拉格 · 本场 32 分", color=BLUE):
    p = foot_at(f)
    if p is None or alpha <= 0.01:
        return
    cx, cy, h = p
    accent = BLUE if color[0] > color[2] and color != PURPLE else color
    card = tag_cached("32", "C. FLAGG", sub, PURPLE if color == PURPLE or (color[0] > 150 and color[2] > 150) else BLUE)
    bob = 3 * math.sin(t * 2 * math.pi * 0.8)
    tx = min(max(cx, 190), WIDTH - 190)
    L.paste(card, tx, cy - h - 34 + bob, alpha=alpha, scale=0.92 + 0.08 * back_out(min(1, alpha * 1.4)), anchor="cb")

def draw_caption(L, t, a, b, en, cn, color=ORANGE):
    if t < a or t > b:
        return
    k_in = ease_out((t - a) / 0.35); k_out = ease_out((b - t) / 0.25)
    al = min(k_in, k_out)
    x, y = 110, 838
    bar_h = int(96 * k_in)
    rect(L, x - 22, y + 4, x - 14, y + 4 + bar_h, color, 0.95 * al)
    box_w = max(text_w(cn, CJK, 48), text_w(en, DIN, 40, 5)) + 70
    rect(L, x - 30, y - 6, x + box_w, y + 112, (8, 9, 11), 0.55 * al)
    off = 40 * (1 - k_in) - 20 * (1 - k_out)
    L.paste(text_rgba(en, DIN, 40, color, 5), x + off, y, alpha=al)
    n = len(cn); shown = max(1, int(n * clamp((t - a - 0.08) / max(0.18, 0.018 * n))))
    L.paste(text_rgba(cn[:shown], CJK, 48, CHALK), x + off, y + 44, alpha=al)

def draw_popup(L, t, t0, text, pos, color, size=170, dur=1.05, sub=None, sub_color=None):
    dt = t - t0
    if dt < 0 or dt > dur:
        return
    k = back_out(min(1, dt / 0.2), 2.2)
    scale = 1.65 - 0.65 * k
    al = clamp(dt / 0.08) * ease_out((dur - dt) / 0.3)
    if dt > dur - 0.3:
        scale *= 1 + 0.25 * (1 - (dur - dt) / 0.3)
    im = text_rgba(text, DIN, size, (255, 255, 255), 4, 6, color, 0.18)
    glow = text_rgba(text, DIN, size, color, 4, 10, color, 0.18)
    L.paste(glow, pos[0], pos[1], alpha=0.55 * al, scale=scale * 1.02, anchor="c")
    L.paste(im, pos[0], pos[1], alpha=al, scale=scale, anchor="c")
    if sub:
        sw = text_w(sub, CJK, 40) + 36; sy = pos[1] + size * 0.58 * scale
        rect(L, pos[0] - sw / 2, sy - 30, pos[0] + sw / 2, sy + 30, (8, 9, 11), 0.6 * al)
        L.paste(text_rgba(sub, CJK, 40, sub_color or CHALK), pos[0], sy, alpha=al, anchor="c")

def draw_shot_clock(L, t, alpha):
    if alpha <= 0.01:
        return
    sc = shot_clock(t)
    x1, y0 = WIDTH - 70, 54
    rect(L, x1 - 250, y0, x1, y0 + 150, (8, 9, 11), 0.62 * alpha)
    col = CHALK if sc > 8 else FLAME if sc > 5 else ORANGE
    rect(L, x1 - 250, y0, x1 - 244, y0 + 150, col, 0.95 * alpha)
    L.paste(text_rgba("SHOT CLOCK", PIX, 24, MUTED), x1 - 226, y0 + 14, alpha=alpha)
    L.paste(text_rgba("进攻时间", CJK, 22, MUTED), x1 - 226, y0 + 96, alpha=alpha)
    val = f"{math.floor(sc * 10) / 10:.1f}" if sc < 5 else f"{int(math.floor(sc))}"
    pulse = 1.0 + (0.07 * max(0, math.sin((t % 1.0) * math.pi)) if sc < 5 else 0)
    L.paste(text_rgba(val, DIN, 104, col), x1 - 30, y0 + 104, alpha=alpha, scale=pulse, anchor="rc")
    frac = clamp(sc / 24)
    rect(L, x1 - 226, y0 + 134, x1 - 22, y0 + 140, (60, 60, 60), 0.6 * alpha)
    rect(L, x1 - 226, y0 + 134, x1 - 226 + 204 * frac, y0 + 140, col, 0.95 * alpha)
    if sc < 5:
        line(L.glow, (x1 - 226, y0 + 137), (x1 - 226 + 204 * frac, y0 + 137), scale_c(col, alpha), 1, 8)

def draw_game_tag(L, alpha, mode="LIVE", sub="DAL @ HOU · Q4"):
    if alpha <= 0.01:
        return
    x, y = 70, 58
    rect(L, x, y, x + 420, y + 64, (8, 9, 11), 0.6 * alpha)
    col = BLUE if mode == "LIVE" else PURPLE
    rect(L, x, y, x + 6, y + 64, col, alpha)
    L.paste(text_rgba("GAME MODE · 游戏视角" if mode == "LIVE" else "COACH MODE · 战术回放", PIX, 24, col), x + 22, y + 8, alpha=alpha)
    L.paste(text_rgba(sub, DIN, 30, CHALK, 2), x + 22, y + 34, alpha=alpha)

def draw_disclosure(L, alpha):
    if alpha <= 0.01:
        return
    L.paste(text_rgba("AI 解读字幕 · 特效依据人工关键帧与插值 · 非自动追踪", CJK, 20, CHALK), WIDTH - 70, 226,
            alpha=0.62 * alpha, anchor="rt")

def draw_ball_trail(L, f, color_head, color_tail, alpha=1.0, length=20):
    fi = f
    pts = []
    for k in range(length, -1, -1):
        b = ball_at(fi - k * 0.75)
        if b is not None:
            pts.append((b, 1 - k / length))
    for (a, wa), (b, wb) in zip(pts, pts[1:]):
        col = mix(color_tail, color_head, wb)
        line(L.sharp, a, b, col, alpha * (0.25 + 0.75 * wb), max(1, int(2 + 9 * wb)))
        line(L.glow, a, b, scale_c(col, alpha * (0.6 + wb)), 1, int(8 + 18 * wb))
    if pts:
        hx, hy = pts[-1][0]
        ellipse(L.glow, (hx, hy), (26, 26), scale_c(color_head, alpha * 1.3), 1, -1)
        ellipse(L.sharp, (hx, hy), (24, 24), CHALK, 0.9 * alpha, 2)
        rng = np.random.default_rng(int(f * 10))
        for _ in range(6):   # sparks
            a = rng.uniform(0, 2 * math.pi); r = rng.uniform(20, 60)
            sx, sy = hx + r * math.cos(a), hy + r * math.sin(a)
            line(L.glow, (sx, sy), (sx + 3, sy + 3), scale_c(LED, alpha), 1, 3)

def draw_burst(L, t, t0, center, color, dur=0.75, big=1.0):
    dt = t - t0
    if dt < 0 or dt > dur:
        return
    p = dt / dur
    cx, cy = center
    for k, delay in enumerate((0.0, 0.12, 0.24)):
        q = clamp((dt - delay) / (dur - delay))
        if q <= 0:
            continue
        r = (30 + 280 * ease_out(q)) * big
        ellipse(L.sharp, (cx, cy), (r, r * 0.42), color, (1 - q) * 0.9, 3)
        ellipse(L.glow, (cx, cy), (r, r * 0.42), scale_c(color, (1 - q) * 1.4), 1, 12)
    for k in range(14):   # rays
        a = k / 14 * 2 * math.pi + 0.2
        r0, r1 = (40 + 160 * ease_out(p)) * big, (90 + 300 * ease_out(p)) * big
        line(L.glow, (cx + r0 * math.cos(a), cy + r0 * math.sin(a) * 0.6),
             (cx + r1 * math.cos(a), cy + r1 * math.sin(a) * 0.6), scale_c(color, (1 - p) * 1.3), 1, 5)

def draw_scorecard(L, t, t0, alpha):
    if alpha <= 0.01:
        return
    k = ease_out((t - t0) / 0.4)
    y = 54 - 40 * (1 - k)
    cx = WIDTH / 2
    rect(L, cx - 300, y, cx + 300, y + 92, (8, 9, 11), 0.7 * alpha)
    rect(L, cx - 300, y + 88, cx + 300, y + 92, GREEN, alpha)
    flip = clamp((t - t0 - 0.25) / 0.25)
    dal = "105" if flip >= 1 else "103"
    L.paste(text_rgba("DAL", DIN, 44, MUTED, 3), cx - 270, y + 46, alpha=alpha, anchor="lc")
    L.paste(text_rgba(dal, DIN, 84, GREEN if flip >= 1 else CHALK), cx - 60, y + 50, alpha=alpha,
            scale=1 + 0.25 * (1 - flip) * (flip > 0), anchor="rc")
    L.paste(text_rgba("—", DIN, 60, MUTED), cx, y + 46, alpha=alpha, anchor="c")
    L.paste(text_rgba("107", DIN, 84, CHALK), cx + 60, y + 50, alpha=alpha, anchor="lc")
    L.paste(text_rgba("HOU", DIN, 44, MUTED, 3), cx + 270, y + 46, alpha=alpha, anchor="rc")

def vignette_mask():
    yy, xx = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float32)
    d = np.sqrt(((xx - WIDTH / 2) / (WIDTH * 0.62)) ** 2 + ((yy - HEIGHT / 2) / (HEIGHT * 0.62)) ** 2)
    return np.clip(1.08 - 0.42 * d ** 2, 0.45, 1.0)[..., None]
VIG = vignette_mask()

def grade(img, sat=1.0, gain=1.0, tint=None, vig=0.0):
    out = img.astype(np.float32)
    if sat != 1.0:
        gray = out.mean(axis=2, keepdims=True); out = gray + (out - gray) * sat
    if tint is not None:
        out = out * (1 - tint[1]) + np.array(tint[0], np.float32) * tint[1] * (out.mean(axis=2, keepdims=True) / 128)
    out *= gain
    if vig:
        out *= (1 - vig) + vig * VIG
    return np.clip(out, 0, 255).astype(np.uint8)

def shake(img, t, t0, amp=14, dur=0.28):
    dt = t - t0
    if dt < 0 or dt > dur:
        return img
    k = (1 - dt / dur) ** 2
    rng = np.random.default_rng(int(t * 1000))
    dx, dy = rng.uniform(-1, 1) * amp * k, rng.uniform(-1, 1) * amp * k * 0.6
    M = np.float32([[1.02, 0, dx - WIDTH * 0.01], [0, 1.02, dy - HEIGHT * 0.01]])
    return cv2.warpAffine(img, M, (WIDTH, HEIGHT), borderMode=cv2.BORDER_REFLECT)

# ---------------------------------------------------------------- segments
SLOW_BASE = 14.9 * FPS   # slow frame j shows source frame SLOW_BASE + j/3
SEGMENTS = [("intro", 150), ("live", 1110), ("rewind", 54), ("slow1", 324), ("freeze", 130), ("slow2", 163), ("outro", 330)]

def plan():
    out = []
    for name, n in SEGMENTS:
        for i in range(n):
            out.append((name, i, n))
    return out

LIVE_CAPTIONS = [
    (0.35, 3.25, "POSSESSION START · DOWN 4", "回合开始：独行侠 103–107 落后 4 分"),
    (3.4, 6.25, "FLAGG BRINGS IT UP", "弗拉格持球推进过半场"),
    (6.4, 9.35, "HIGH SCREEN", "队友上提，给他做掩护"),
    (9.5, 12.35, "ATTACK · RESET", "借掩护突破，受阻后拉出重新组织"),
    (12.5, 15.4, "CLOCK IS TICKING", "进攻时间不到 10 秒"),
    (15.5, 16.8, "LAST DRIVE", "最后一次启动，直杀篮下"),
    (17.40, 18.55, "FINGER ROLL — GOOD!", "突破挑篮命中，个人本场第 34 分"),
]

def render(name, i, n):
    if name == "intro":
        return render_intro(i, n)
    if name == "live":
        return render_live(6 + i)
    if name == "rewind":
        return render_rewind(i, n)
    if name in ("slow1", "freeze", "slow2"):
        j = 18 + i if name == "slow1" else 342 if name == "freeze" else 342 + i
        return render_slow(name, j, i, n)
    return render_outro(i, n)

# ---------------------------------------------------------------- intro
def render_intro(i, n):
    t = i / FPS
    base = src_frame(6)
    blur = cv2.GaussianBlur(base, (0, 0), 6 * (1 - ease_in_out(clamp((t - 1.9) / 0.6))) + 0.01)
    L = Layers(grade(blur, sat=0.6, gain=0.35 + 0.65 * ease_in_out(clamp((t - 1.9) / 0.6)), vig=0.6))
    # scan sweep
    sy = int(HEIGHT * ease_out(t / 0.45))
    if t < 0.5:
        rect(L, 0, 0, WIDTH, HEIGHT - sy, VOID, 1.0)
        rect(L, 0, HEIGHT - sy - 3, WIDTH, HEIGHT - sy, ORANGE, 0.9)
    out_k = ease_in_out(clamp((t - 2.0) / 0.45))
    al = 1 - out_k
    x = 150
    if t > 0.28:
        k = back_out(clamp((t - 0.28) / 0.2))
        L.paste(text_rgba("DOWN 4", DIN, 250, CHALK, 6, 0, (0, 0, 0), 0.16), x, 300, alpha=al * clamp((t - 0.28) / 0.06), scale=1.4 - 0.4 * k)
    if t > 0.7:
        k = ease_out((t - 0.7) / 0.3)
        L.paste(text_rgba("1:51 LEFT · 4TH QTR", DIN, 92, ORANGE, 6), x + 8 - 60 * (1 - k), 560, alpha=al * k)
        L.paste(text_rgba("落后 4 分 · 还剩 1分51秒", CJK, 46, CHALK), x + 10 - 60 * (1 - k), 668, alpha=al * k)
    if t > 1.25:
        k = ease_out((t - 1.25) / 0.35)
        rect(L, 0, 770, (x + 760) * k, 846, BLUE, 0.92 * al)
        L.paste(text_rgba("#32  COOPER FLAGG", DIN, 64, (255, 255, 255), 4), x + 10, 780, alpha=al * clamp((t - 1.4) / 0.2))
        L.paste(text_rgba("DAL", PIX, 24, CHALK), x + 690, 796, alpha=al * clamp((t - 1.4) / 0.2))
    if 1.95 < t:   # diagonal wipe
        p = ease_in_out((t - 1.95) / 0.5)
        pts = np.array([[int(-400 + 2800 * p), 0], [int(-100 + 2800 * p), 0], [int(-500 + 2800 * p), HEIGHT], [int(-800 + 2800 * p), HEIGHT]])
        cv2.fillPoly(L.sharp, [pts], ORANGE + (235,), cv2.LINE_AA)
    img = L.compose()
    return shake(img, t, 0.3, 18, 0.3)

# ---------------------------------------------------------------- live
def render_live(f):
    t = f / FPS
    L = Layers(grade(src_frame(f), sat=1.08, vig=0.25))
    drive = window(t, 15.45, 16.95, 0.2, 0.15)
    ring_a = window(t, 0.25, 16.95, 0.35, 0.18)
    color = mix(BLUE, FLAME, drive)
    if f in FOOT or f - 1 in FOOT:
        draw_trail(L, f, color, 1.3, ring_a * 0.9)
        lock = 1 + 1.1 * (1 - ease_out((t - 0.25) / 0.5)) if t < 0.75 else 1.0   # lock-on: ring snaps in
        draw_ring(L, f, t, color, shot_clock(t) / 24, ring_a, pulse=drive, grow=lock)
        draw_tag(L, f, t, window(t, 0.45, 16.75, 0.35, 0.2), color=color)
    if 16.7 <= t <= 17.75:
        draw_ball_trail(L, f, LED, ORANGE, window(t, 16.72, 17.75, 0.06, 0.2))
    draw_burst(L, t, 17.36, RIM, GREEN, 0.8, 1.0)
    if 17.36 <= t <= 17.7:
        ellipse(L.glow, RIM, (60, 22), scale_c(GREEN, 1.5 * (1 - (t - 17.36) / 0.34)), 1, -1)
    draw_shot_clock(L, t, window(t, 0.3, 17.5, 0.3, 0.3))
    draw_game_tag(L, window(t, 0.2, 18.6, 0.3, 0.0))
    for a, b, en, cn in LIVE_CAPTIONS:
        draw_caption(L, t, a, b, en, cn, GREEN if en.startswith("FINGER") else ORANGE)
    p = foot_at(f)
    if p:
        draw_popup(L, t, 6.55, "SCREEN", (p[0] - 420, p[1] - 0.55 * p[2]), PURPLE, 150, 1.0, "掩护", VIOLET)
        draw_popup(L, t, 15.5, "DRIVE", (p[0] - 380, p[1] - 0.55 * p[2]), FLAME, 170, 1.0, "突破", LED)
    draw_popup(L, t, 17.38, "+2", (RIM[0] + 330, RIM[1] + 10), GREEN, 210, 1.15, "本场第 34 分", CHALK)
    draw_scorecard(L, t, 17.6, window(t, 17.6, 18.6, 0.3, 0.0))
    draw_disclosure(L, 1.0)
    img = L.compose()
    if 17.36 <= t <= 17.46:
        img = cv2.addWeighted(img, 1.0, np.full_like(img, 255), 0.35 * (1 - (t - 17.36) / 0.1), 0)
    img = shake(img, t, 17.37, 16, 0.3)
    img = shake(img, t, 15.52, 8, 0.2)
    return img

# ---------------------------------------------------------------- rewind
def render_rewind(i, n):
    f = 1115 - i * 4
    t = i / FPS
    base = src_frame(f).astype(np.int16)
    b, g, r = cv2.split(base)
    s = 10
    b = np.roll(b, -s, axis=1); r = np.roll(r, s, axis=1)
    img = cv2.merge([b, g, r]).clip(0, 255).astype(np.uint8)
    img = grade(img, sat=0.55, gain=0.9, tint=(PURPLE, 0.25), vig=0.5)
    img[::3] = (img[::3] * 0.7).astype(np.uint8)
    band = int((t * 900) % HEIGHT)
    img[band:band + 40] = np.clip(img[band:band + 40].astype(np.int16) + 40, 0, 255).astype(np.uint8)
    L = Layers(img)
    for k in range(2):
        x = 120 + k * 52
        cv2.fillPoly(L.sharp, [np.array([[x + 50, 150], [x + 50, 214], [x, 182]], np.int32)], CHALK + (255,), cv2.LINE_AA)
    L.paste(text_rgba("REPLAY", PIX, 72, CHALK), 250, 140, alpha=1.0)
    L.paste(text_rgba("慢镜头回放", CJK, 44, VIOLET), 128, 230, alpha=1.0)
    out = L.compose()
    if i > n - 8:
        k = (i - (n - 8)) / 8
        out = cv2.addWeighted(out, 1 - 0.8 * k, np.full_like(out, 255), 0.8 * k, 0)
    return out

# ---------------------------------------------------------------- slow replay + freeze
def court_card():
    """Pixel-style half court (right basket) with the official shot location; RGBA."""
    w, h = 420, 300
    im = Image.new("RGBA", (w, h), (8, 9, 11, 215)); d = ImageDraw.Draw(im)
    ft = 7.6   # px per foot; half court 47 ft x 50 ft -> 357 x 380 (we crop to baseline-side 40 ft)
    ox, oy = 20, 28
    def X(x):   # x in feet from right baseline toward mid court
        return w - ox - x * ft
    def Y(y):
        return oy + (y - 8) * ft
    chalk = rgb(CHALK) + (200,); dim = rgb(MUTED) + (120,)
    d.rectangle([X(19), Y(17), X(0), Y(33)], outline=chalk, width=2)                  # paint 16 ft wide
    d.ellipse([X(19) - 6 * ft, Y(25) - 6 * ft, X(19) + 6 * ft, Y(25) + 6 * ft], outline=dim, width=2)
    d.arc([X(5.25) - 23.75 * ft, Y(25) - 23.75 * ft, X(5.25) + 23.75 * ft, Y(25) + 23.75 * ft], 112, 248, fill=chalk, width=2)
    d.line([X(0), Y(8), X(0), Y(42)], fill=chalk, width=3)
    d.ellipse([X(5.25) - 0.75 * ft, Y(25) - 0.75 * ft, X(5.25) + 0.75 * ft, Y(25) + 0.75 * ft], outline=rgb(ORANGE) + (255,), width=3)
    sx, sy = 94 - 0.89 * 94, 0.55 * 50     # official locX/locY (% of full court), side=right
    d.line([X(5.25), Y(25), X(sx), Y(sy)], fill=rgb(LED) + (255,), width=2)
    d.ellipse([X(sx) - 9, Y(sy) - 9, X(sx) + 9, Y(sy) + 9], fill=rgb(ORANGE) + (255,), outline=rgb(CHALK) + (255,), width=2)
    f = font(PIX, 24); d.text((14, 8), "SHOT CHART · 官方出手点", font=f, fill=rgb(CHALK) + (255,))
    f2 = font(DIN, 34); d.text((X(sx) - 120, Y(sy) + 14), "5 FT", font=f2, fill=rgb(LED) + (255,))
    return np.array(im)
COURT = None

def data_panel(k_items):
    """Right-hand official data panel; k_items 0..1 reveal progress."""
    w, h = 470, 560
    card = np.zeros((h, w, 4), np.uint8)
    card[..., :3] = (11, 9, 8); card[..., 3] = 212
    card[:, :5, :3] = PURPLE[::-1]; card[:, :5, 3] = 255
    return card

def render_slow(name, j, i, n):
    f = SLOW_BASE + j / 3.0
    t = f / FPS
    base = slow_frame(j)
    frz = name == "freeze"
    ft = i / FPS if frz else 0
    L = Layers(grade(base, sat=0.82 if not frz else 0.7, gain=1.0 if not frz else 0.82, tint=(PURPLE, 0.06), vig=0.45 if not frz else 0.7))
    ring_a = window(t, 14.9, 16.95, 0.0, 0.18)
    drive = window(t, 15.45, 16.95, 0.2, 0.15)
    color = mix(PURPLE, FLAME, drive * 0.6)
    if foot_at(f):
        draw_trail(L, f, color, 1.6, ring_a)
        draw_ring(L, f, t, color, None, ring_a, pulse=drive)
        draw_tag(L, f, t, window(t, 14.9, 16.75, 0.0, 0.2), sub="慢放 0.33× · 突破", color=color)
    if 16.7 <= t <= 17.75:
        draw_ball_trail(L, f, LED, ORANGE, window(t, 16.72, 17.75, 0.06, 0.2), length=26)
    draw_burst(L, t, 17.36, RIM, GREEN, 1.6, 1.15)
    draw_game_tag(L, 1.0, "COACH", "REPLAY · 0.33×")
    if name == "slow1":
        draw_caption(L, i / FPS, 0.2, 5.3, "REPLAY · THE DRIVE", "再看一次：最后一次启动，一路打到篮下", PURPLE)
    if frz:
        render_freeze(L, ft, n / FPS)
    if name == "slow2":
        tt = i / FPS
        draw_caption(L, tt, 0.1, 2.65, "OFFICIAL xFG 51%", "官方预期投篮命中率：51%", VIOLET)
        draw_popup(L, t, 17.38, "+2", (RIM[0] + 330, RIM[1] + 10), GREEN, 210, 1.3, "DAL 105 — 107 HOU", CHALK)
    draw_disclosure(L, 1.0)
    img = L.compose(glow_gain=1.0)
    if frz and ft < 0.12:
        img = cv2.addWeighted(img, 1.0, np.full_like(img, 255), 0.45 * (1 - ft / 0.12), 0)
    if frz:
        img = shake(img, ft, 0.0, 12, 0.25)
    return img

def render_freeze(L, ft, dur):
    global COURT
    if COURT is None:
        COURT = court_card()
    bx, by = BALL[1007]
    # release marker
    k = ease_out(ft / 0.35)
    r = 90 - 40 * k
    ellipse(L.sharp, (bx, by), (r, r), LED, 0.95, 3)
    ellipse(L.glow, (bx, by), (r, r), scale_c(LED, 1.2), 1, 10)
    for a in range(0, 360, 45):
        a0 = a + ft * 120
        ellipse(L.sharp, (bx, by), (r + 18, r + 18), CHALK, 0.9, 3, a0, a0 + 14)
    line(L.sharp, (bx + r * 0.8, by - r * 0.6), (bx + 230, by - 140), CHALK, 0.85 * k, 2)
    L.paste(text_rgba("RELEASE", DIN, 64, LED, 4), bx + 238, by - 196, alpha=k)
    L.paste(text_rgba("出手瞬间 · 进攻时间不到 5 秒", CJK, 30, CHALK), bx + 240, by - 128, alpha=k)
    # official data panel (right)
    px = WIDTH - 70 - 500 * (1 - ease_out((ft - 0.15) / 0.45)) * 0 - 470
    al = ease_out((ft - 0.15) / 0.4)
    x0, y0 = WIDTH - 540 + 80 * (1 - al), 264
    rect(L, x0, y0, x0 + 470, y0 + 610, (8, 9, 11), 0.78 * al)
    rect(L, x0, y0, x0 + 6, y0 + 610, PURPLE, al)
    L.paste(text_rgba("OFFICIAL · NBA 官方数据", PIX, 24, VIOLET), x0 + 28, y0 + 22, alpha=al)
    xk = ease_out((ft - 0.45) / 0.7)
    val = int(round(51 * xk))  # User-approved reveal animation; the settled official value is 51%.
    L.paste(text_rgba(f"{val}%", DIN, 168, (255, 255, 255)), x0 + 26, y0 + 50, alpha=al)
    L.paste(text_rgba("xFG", DIN, 56, ORANGE, 3), x0 + 300, y0 + 74, alpha=al)
    L.paste(text_rgba("预期命中率", CJK, 24, CHALK), x0 + 300, y0 + 140, alpha=al)
    rect(L, x0 + 28, y0 + 230, x0 + 442, y0 + 242, (55, 55, 55), 0.8 * al)
    rect(L, x0 + 28, y0 + 230, x0 + 28 + 414 * 0.51 * xk, y0 + 242, ORANGE, al)
    line(L.glow, (x0 + 28, y0 + 236), (x0 + 28 + 414 * 0.51 * xk, y0 + 236), scale_c(ORANGE, al), 1, 10)
    rows = [("5 FT", "出手距离 · 官方逐回合"), ("FINGER ROLL", "突破挑篮 · Driving Finger Roll Layup"), ("Q4 · 1:34", "第四节 1分34秒")]
    for idx, (a, b) in enumerate(rows):
        rk = ease_out((ft - 0.7 - idx * 0.15) / 0.35)
        yy = y0 + 270 + idx * 74
        L.paste(text_rgba(a, DIN, 44, CHALK, 2), x0 + 28 + 30 * (1 - rk), yy, alpha=al * rk)
        L.paste(text_rgba(b, CJK, 20, MUTED), x0 + 30 + 30 * (1 - rk), yy + 44, alpha=al * rk)
    sk = ease_out((ft - 1.15) / 0.4)
    rect(L, x0 + 28, y0 + 500, x0 + 442, y0 + 502, (80, 80, 80), al * sk)
    L.paste(text_rgba("NBA · EVENT 666", PIX, 24, VIOLET), x0 + 28, y0 + 514, alpha=al * sk)
    L.paste(text_rgba("官方出手质量 · xFG 51%", CJK, 30, CHALK), x0 + 28, y0 + 552, alpha=al * sk)
    # shot chart (left)
    ck = ease_out((ft - 0.3) / 0.45)
    L.paste(COURT, 70 - 60 * (1 - ck), 470, alpha=ck)
    draw_caption(L, ft, 0.25, dur - 0.05, "OFFICIAL xFG 51%", "官方预期投篮命中率：51%", PURPLE)

# ---------------------------------------------------------------- outro
def render_outro(i, n):
    t = i / FPS
    base = slow_frame(504)
    k0 = ease_in_out(t / 0.5)
    img = cv2.GaussianBlur(base, (0, 0), 1 + 9 * k0)
    L = Layers(grade(img, sat=1 - 0.5 * k0, gain=1 - 0.72 * k0, vig=0.8))
    cx = WIDTH / 2
    a1 = ease_out((t - 0.25) / 0.4)
    L.paste(text_rgba("COOPER FLAGG", DIN, 132, CHALK, 8), cx, 250 - 40 * (1 - a1), alpha=a1, anchor="c")
    L.paste(text_rgba("弗拉格  ·  DAL #32", CJK, 40, MUTED), cx, 340, alpha=a1, anchor="c")
    a2 = back_out(clamp((t - 0.55) / 0.3))
    num = 34  # The official event records 34 PTS after this basket.
    L.paste(text_rgba(str(num), DIN, 300, ORANGE, 0, 0, (0, 0, 0), 0.12), cx - 40, 560, alpha=clamp((t - 0.55) / 0.1), scale=1.3 - 0.3 * a2, anchor="rc")
    L.paste(text_rgba("PTS", DIN, 110, CHALK, 6), cx - 10, 600, alpha=clamp((t - 0.6) / 0.15), anchor="lc")
    L.paste(text_rgba("本场得分", CJK, 34, MUTED), cx - 6, 672, alpha=clamp((t - 0.6) / 0.15), anchor="lc")
    chips = [("xFG 51%", ORANGE), ("5 FT · FINGER ROLL", CHALK), ("Q4 · 1:34", FLAME), ("DAL 105 — 107 HOU", GREEN)]
    total = sum(text_w(c, DIN, 44, 2) + 60 for c, _ in chips) - 24
    x = cx - total / 2
    for idx, (c, col) in enumerate(chips):
        ck = ease_out((t - 1.0 - idx * 0.12) / 0.3)
        w = text_w(c, DIN, 44, 2)
        rect(L, x, 760 + 20 * (1 - ck), x + w + 36, 824 + 20 * (1 - ck), (20, 20, 24), 0.85 * ck)
        rect(L, x, 820 + 20 * (1 - ck), x + w + 36, 824 + 20 * (1 - ck), col, ck)
        L.paste(text_rgba(c, DIN, 44, col, 2), x + 18, 768 + 20 * (1 - ck), alpha=ck)
        x += w + 60
    fk = ease_out((t - 1.6) / 0.5)
    L.paste(text_rgba("数据：NBA 官方逐回合与出手质量（xFG）   |  特效依据人工关键帧与插值 · 非自动追踪  |  AI 解读字幕",
                      CJK, 22, MUTED), cx, 950, alpha=fk, anchor="c")
    L.paste(text_rgba("GameBuddy · NBA × AWS · TEAM 02", PIX, 24, CHALK), cx, 1000, alpha=fk, anchor="c")
    out = L.compose()
    if i > n - 20:
        out = (out * ((n - i) / 20)).astype(np.uint8)
    return out

# ---------------------------------------------------------------- standalone CLI
def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Render the preserved GameBuddy highlight cut")
    parser.add_argument("workdir")
    parser.add_argument("--preview", help="Comma-separated output frame numbers")
    args = parser.parse_args(argv)
    configure(args.workdir)
    (Path(WD) / "out").mkdir(parents=True, exist_ok=True)
    frames = plan()
    if args.preview:
        indices = [int(value) for value in args.preview.split(",")]
        for index in indices:
            cv2.imwrite(f"{WD}/out/preview-{index:04d}.jpg", render(*frames[index]), [cv2.IMWRITE_JPEG_QUALITY, 88])
        print("previews", indices, "of", len(frames))
        return
    command = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{WIDTH}x{HEIGHT}",
               "-r", "60000/1001", "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
               f"{WD}/out/video.mp4"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for index, frame in enumerate(frames):
            process.stdin.write(render(*frame).tobytes())
            if index % 120 == 0:
                print("frame", index, "/", len(frames), frame[0], flush=True)
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("FFmpeg rendering failed")
    print("done", len(frames), "frames", len(frames) / FPS, "s")

if __name__ == "__main__":
    main()
