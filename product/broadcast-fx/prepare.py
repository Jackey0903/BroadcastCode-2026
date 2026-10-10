#!/usr/bin/env python3
"""Rebuild local frame caches and copy persistent GameBuddy editorial assets.

Only the hash-verified Flagg source is accepted: these annotations are not a
model for arbitrary video. Generated media stays in the caller's workdir.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
PIXEL = ROOT.parent / "web/assets/fonts/fusion-pixel-12px-monospaced-zh_hans.otf.woff2"


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def extract_commands(source, workdir):
    """Keep the exact FFmpeg extraction settings used by the preserved prototype."""
    return [
        ["ffmpeg", "-v", "error", "-y", "-i", str(source), "-start_number", "0", "-q:v", "2", str(workdir / "full/f%04d.jpg")],
        ["ffmpeg", "-v", "error", "-y", "-ss", "14.9", "-t", "3.0", "-i", str(source), "-an", "-vf",
         "minterpolate=fps=179.82:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1", "-q:v", "2", "-start_number", "0",
         str(workdir / "slow/s%04d.jpg")],
    ]


def prepare(source, workdir, assets_only=False):
    source = Path(source).expanduser().resolve()
    workdir = Path(workdir).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    digest = sha256(source)
    if digest != manifest["source"]["sha256"]:
        raise ValueError("Source hash differs from the annotated Flagg clip. New footage requires new reviewed annotations.")
    if not assets_only and shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg is required to rebuild the frame cache")
    for folder in ("full", "slow", "out", "tac", "fonts"):
        (workdir / folder).mkdir(parents=True, exist_ok=True)
    for entry in manifest["files"]:
        if entry["path"].startswith("source-tools/"):
            continue
        original = DATA / entry["path"]
        if sha256(original) != entry["sha256"]:
            raise ValueError(f"Persistent asset differs from manifest: {entry['path']}")
        target = workdir / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    shutil.copy2(DATA / "manifest.json", workdir / "asset-manifest.json")
    # Keep the OFL font in the generated bundle. FreeType can read WOFF2 on
    # supported Pillow builds; other builds use the pinned FontTools fallback.
    from PIL import ImageFont
    shutil.copy2(PIXEL, workdir / "fonts/fusion-pixel.woff2")
    try:
        ImageFont.truetype(str(PIXEL), 24)
    except OSError:
        from fontTools.ttLib import TTFont
        converted = TTFont(PIXEL)
        converted.flavor = None
        converted.save(workdir / "fonts/fusion-pixel.otf")
    shutil.copy2(PIXEL.parent / "OFL.txt", workdir / "fonts/OFL.txt")
    commands = extract_commands(source, workdir)
    if not assets_only:
        for command in commands:
            subprocess.run(command, check=True)
        for relative in ("full/f0006.jpg", "full/f1290.jpg", "slow/s0018.jpg", "slow/s0504.jpg"):
            if not (workdir / relative).is_file():
                raise RuntimeError(f"Frame extraction incomplete: {relative}")
    evidence = {
        "source_sha256": digest,
        "mode": "assets-only" if assets_only else "frames-and-assets",
        "commands": commands,
        "full_frame_count": len(list((workdir / "full").glob("f[0-9][0-9][0-9][0-9].jpg"))),
        "slow_frame_count": len(list((workdir / "slow").glob("s[0-9][0-9][0-9][0-9].jpg"))),
        "coordinate_scope": manifest["coordinate_scope"],
    }
    (workdir / "preparation.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Exact original Flagg MP4")
    parser.add_argument("--workdir", required=True, type=Path, help="Local generated media cache")
    parser.add_argument("--assets-only", action="store_true", help="Copy annotations/fonts while preserving an existing full/slow frame cache")
    args = parser.parse_args(argv)
    result = prepare(args.source, args.workdir, args.assets_only)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
