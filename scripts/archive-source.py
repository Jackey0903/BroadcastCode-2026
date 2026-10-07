#!/usr/bin/env python3
"""Create and verify a local committed-source backup; no push or cloud access."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
from zoneinfo import ZoneInfo


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def main():
    repo = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=repo.parent / (repo.name + "-backups"))
    parser.add_argument("--source-only", action="store_true", help="Skip locally available practice inputs and rendered media.")
    args = parser.parse_args()
    if git(repo, "status", "--porcelain"):
        raise SystemExit("Commit all intended changes before archiving; working tree is not clean.")

    commit = git(repo, "rev-parse", "HEAD").decode().strip()
    branch = git(repo, "branch", "--show-current").decode().strip()
    created = datetime.now(ZoneInfo("Asia/Shanghai"))
    destination = args.destination.expanduser().resolve()
    if destination == repo or repo in destination.parents:
        raise SystemExit("Choose a backup destination outside the working repository.")
    destination.mkdir(parents=True, exist_ok=True)
    snapshot = destination / (created.strftime("%Y%m%d-%H%M%S-%f") + "-" + commit[:12])
    snapshot.mkdir()
    snapshot.chmod(0o700)

    bundle = snapshot / "repository.bundle"
    archive = snapshot / "source.tar.gz"
    git(repo, "bundle", "create", str(bundle), "--all")
    git(repo, "bundle", "verify", str(bundle))
    git(repo, "archive", "--format=tar.gz", "--prefix=BroadcastCode/", "--output=" + str(archive), commit)
    source_files = git(repo, "ls-tree", "-r", "--name-only", "-z", commit).decode().split("\0")
    source_files = sorted(name for name in source_files if name)
    with tarfile.open(archive) as source:
        archived_files = sorted(member.name.removeprefix("BroadcastCode/")
                                for member in source.getmembers() if not member.isdir())
    if archived_files != source_files:
        raise RuntimeError("Source archive file list differs from the committed tree.")
    with tempfile.TemporaryDirectory(prefix="broadcastcode-restore-check-") as temporary:
        restored = Path(temporary) / "repository"
        subprocess.run(["git", "clone", "--quiet", str(bundle), str(restored)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if git(restored, "rev-parse", "HEAD").decode().strip() != commit:
            raise RuntimeError("Bundle restore does not select the expected commit.")
        restored_files = sorted(name for name in git(restored, "ls-files", "-z").decode().split("\0") if name)
        if restored_files != source_files:
            raise RuntimeError("Bundle restore file list differs from the committed tree.")

    artifacts = [bundle, archive]
    media_files = {}
    missing_media = []
    if not args.source_only:
        media_paths = [
            "data/reference/train_video/train_video/训练_弗拉格2月1日.mp4",
            "data/reference/train_video/train_video/训练_阿门1月4日 .mp4",
            "data/reference/train-video-metadata.json",
            *[f"data/reference/frames/{sample}-{second:02d}s.jpg"
              for sample in ("flagg", "amen") for second in (3, 6, 15, 18)],
            "readiness-lab/build/verified/flagg.mp4",
            "readiness-lab/build/verified/amen.mp4",
        ]
        media_archive = snapshot / "practice-media.tar"
        with tarfile.open(media_archive, "w") as target:
            for relative in media_paths:
                source = repo / relative
                if not source.is_file():
                    missing_media.append(relative)
                    continue
                if source.is_symlink() or not source.resolve().is_relative_to(repo):
                    raise RuntimeError("Refusing a media path outside the local repository.")
                media_files[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
                target.add(source, arcname="BroadcastCode/" + relative, recursive=False)
        with tarfile.open(media_archive) as source:
            actual = {}
            for member in source.getmembers():
                with source.extractfile(member) as data:
                    actual[member.name.removeprefix("BroadcastCode/")] = hashlib.sha256(data.read()).hexdigest()
        if actual != media_files:
            raise RuntimeError("Media archive content hashes differ from the source files.")
        artifacts.append(media_archive)

    manifest = {
        "createdAt": created.isoformat(), "commit": commit, "branch": branch,
        "repository": "https://github.com/Jackey0903/BroadcastCode",
        "sourceFileCount": len(source_files), "bundleVerified": True,
        "offlineCloneVerified": True, "sourceArchiveFileListVerified": True,
        "mediaFiles": media_files, "missingMediaFiles": missing_media,
        "mediaArchiveHashesVerified": bool(media_files),
        "artifacts": {path.name: {"bytes": path.stat().st_size,
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                      for path in artifacts},
        "scope": "Committed source and Git history; optional whitelisted local practice clips, metadata, frames and rendered MP4s. Dependencies, credentials and deployment configuration outputs excluded.",
    }
    (snapshot / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"backupDirectory": str(snapshot), "commit": commit,
                      "sourceFileCount": len(source_files), "restoreVerified": True,
                      "mediaFileCount": len(media_files), "missingMediaFiles": missing_media}, ensure_ascii=False))


if __name__ == "__main__":
    main()
