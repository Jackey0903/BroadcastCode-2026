"""Sound design for the highlight cut: original broadcast audio + synthesized (royalty-free) SFX."""
import subprocess, wave
from pathlib import Path
import numpy as np

SR = 48000
FPS = 60000 / 1001
SEG = [("intro", 150), ("live", 1110), ("rewind", 54), ("slow1", 324), ("freeze", 130), ("slow2", 163), ("outro", 330)]
starts, acc = {}, 0
for name, n in SEG:
    starts[name] = acc / FPS; acc += n
TOTAL = acc / FPS

def load(args):
    raw = subprocess.run(["ffmpeg", "-v", "error", *args, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()

src = np.empty((0, 2), np.float32)
def clip(a, b):
    return src[int(a * SR):int(b * SR)].copy()

out = np.empty((0, 2), np.float32)
def place(sig, at, gain=1.0, fade_in=0.01, fade_out=0.05):
    sig = sig.copy()
    n = len(sig); fi, fo = min(int(fade_in * SR), n // 2), min(int(fade_out * SR), n // 2)
    if fi: sig[:fi] *= np.linspace(0, 1, fi)[:, None]
    if fo: sig[-fo:] *= np.linspace(1, 0, fo)[:, None]
    i = int(at * SR); j = min(len(out), i + n)
    out[i:j] += sig[:j - i] * gain

def mono(x):
    return np.stack([x, x], 1).astype(np.float32)

rng = np.random.default_rng(7)
def t_axis(d):
    return np.arange(int(d * SR)) / SR

def kick(d=0.6, f0=150, f1=38, decay=7):
    t = t_axis(d); f = f1 + (f0 - f1) * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return mono(np.sin(ph) * np.exp(-t * decay))

def noise_burst(d=0.35, decay=18, hp=True):
    t = t_axis(d); n = rng.standard_normal(len(t))
    if hp: n = np.diff(n, prepend=0)
    return mono(n * np.exp(-t * decay) * 0.5)

def lowpass(x, cutoff):
    """One-pole low-pass; cutoff may be an array (Hz)."""
    a = np.exp(-2 * np.pi * np.broadcast_to(cutoff, x.shape[:1]) / SR)
    y = np.zeros_like(x); acc_ = np.zeros(x.shape[1:], np.float32)
    for i in range(len(x)):
        acc_ = (1 - a[i]) * x[i] + a[i] * acc_; y[i] = acc_
    return y

def whoosh(d=0.6, f0=300, f1=4000):
    t = t_axis(d); n = rng.standard_normal((len(t), 2)).astype(np.float32)
    cut = f0 * (f1 / f0) ** (t / d)
    y = lowpass(n, cut) - lowpass(n, cut * 0.25)
    return (y * np.sin(np.pi * t / d)[:, None] ** 2 * 1.4).astype(np.float32)

def riser(d=2.2):
    t = t_axis(d); f = 180 * (6 ** (t / d))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25
    n = rng.standard_normal(len(t)) * 0.18
    env = (t / d) ** 2.2
    return mono((tone + np.diff(n, prepend=0)) * env)

def ding(d=1.2, f=1320):
    t = t_axis(d)
    y = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.5 * t) + 0.25 * np.sin(2 * np.pi * f * 2.0 * t)) * np.exp(-t * 4)
    return mono(y * 0.35)

def tick(f=2600):
    t = t_axis(0.03); return mono(np.sin(2 * np.pi * f * t) * np.exp(-t * 180) * 0.5)

def drone(d, base=55):
    t = t_axis(d)
    y = sum(np.sin(2 * np.pi * base * k * t + k) / k for k in (1, 1.5, 2, 3)) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.5 * t))
    return mono(y * 0.12)

def ffmpeg_fx(sig, filt):
    p = subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ac", "2", "-ar", str(SR), "-i", "-", "-af", filt,
                        "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], input=sig.astype(np.float32).tobytes(),
                       capture_output=True, check=True)
    return np.frombuffer(p.stdout, np.float32).reshape(-1, 2).copy()

def build(workdir, source):
    """Create the preserved 37.7-second mix for later timeline insertion.

    The source broadcast audio is retained; extra SFX are synthesized locally.
    Importing this module performs no media reads or subprocess calls.
    """
    global src, out, rng
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    output = Path(workdir).expanduser().resolve() / "out" / "audio.wav"
    output.parent.mkdir(parents=True, exist_ok=True)
    src = load(["-i", str(source)])
    out = np.zeros((int((TOTAL + 0.5) * SR), 2), np.float32)
    rng = np.random.default_rng(7)
    # ---- intro (0 .. 2.5 s)
    place(drone(2.6), 0.0, 1.0, 0.3, 0.4)
    place(riser(2.0), 0.1, 0.8, 0.05, 0.1)
    for at, g in ((0.28, 1.0), (0.70, 0.55), (1.25, 0.7)):
        place(kick(), at, 0.9 * g); place(noise_burst(0.25), at, 0.35 * g)
    place(whoosh(0.55, 400, 6000), 1.95, 0.7)
    # ---- live: original broadcast audio
    s_live = starts["live"]
    place(clip(0.1001, 0.1001 + 1110 / FPS), s_live, 1.0, 0.25, 0.2)
    ev = lambda src_t: s_live + (src_t - 0.1001)
    place(whoosh(0.35, 800, 5000), ev(6.45), 0.35); place(kick(0.4, 120, 45, 9), ev(6.55), 0.45)
    place(whoosh(0.4, 600, 7000), ev(15.38), 0.5); place(kick(0.5, 160, 40, 8), ev(15.5), 0.6)
    place(kick(0.8, 170, 36, 5), ev(17.38), 1.0); place(noise_burst(0.5, 9), ev(17.38), 0.35); place(ding(1.4, 1320), ev(17.40), 0.55)
    place(tick(3200), ev(17.85), 0.6); place(tick(2400), ev(17.95), 0.5)
    # ---- rewind: reversed, 4x tape spin-up
    rw = clip(15.0, 18.6)[::-1]
    idx = np.linspace(0, len(rw) - 1, int(54 / FPS * SR))
    rw = np.stack([np.interp(idx, np.arange(len(rw)), rw[:, c]) for c in (0, 1)], 1).astype(np.float32)
    place(rw, starts["rewind"], 0.7, 0.02, 0.08); place(whoosh(0.9, 2000, 300), starts["rewind"], 0.6)
    # ---- slow replay: pitched-down, 3x longer, with space
    slow_fx = "asetrate=28800,aresample=48000,atempo=0.5556,aecho=0.8:0.7:90|180:0.35|0.2,lowpass=f=3200"
    s1 = ffmpeg_fx(clip(15.0, 16.8), slow_fx)
    place(s1[:int(324 / FPS * SR)], starts["slow1"], 0.9, 0.2, 0.15)
    place(drone(10.4, 41.2), starts["slow1"], 0.9, 0.6, 0.8)
    sf = starts["freeze"]
    place(kick(1.2, 180, 30, 3.5), sf, 1.1); place(noise_burst(0.8, 5), sf, 0.3); place(whoosh(0.6, 5000, 300), sf - 0.3, 0.45)
    for k, dt in enumerate((0.2, 0.45, 0.75, 0.9, 1.05, 1.2)):
        place(tick(2200 + 300 * k), sf + dt, 0.5)
    s2 = ffmpeg_fx(clip(16.8, 17.7), slow_fx)
    place(s2[:int(163 / FPS * SR)], starts["slow2"], 0.9, 0.1, 0.2)
    make_out = starts["slow2"] + (int((17.38 - 14.9) * 179.82) - 342) / FPS
    place(kick(1.0, 170, 34, 4), make_out, 1.0); place(ding(1.8, 990), make_out + 0.02, 0.6)
    # ---- outro
    so = starts["outro"]
    place(kick(1.4, 160, 30, 3), so + 0.25, 0.9); place(drone(5.2, 55), so, 0.8, 0.4, 1.6)
    for k in range(3):
        place(tick(2800), so + 0.7 + k * 0.12, 0.5)
    place(kick(0.6, 150, 40, 8), so + 0.6, 0.6)
    for k in range(4):
        place(tick(1800 + 400 * k), so + 1.0 + k * 0.12, 0.45)
    # ---- master
    out = out[:int(TOTAL * SR)]
    out = np.tanh(out * 1.1) / np.tanh(1.1)
    peak = np.abs(out).max(); out *= 0.89 / max(peak, 1e-6)
    pcm = (out * 32767).astype(np.int16)
    with wave.open(str(output), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    print("audio", round(TOTAL, 3), "s; segment starts", {k: round(v, 3) for k, v in starts.items()})
    return output


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Rebuild the source broadcast plus synthetic highlight SFX")
    parser.add_argument("workdir")
    parser.add_argument("source")
    args = parser.parse_args(argv)
    build(args.workdir, args.source)


if __name__ == "__main__":
    main()
