"""Publish the legacy pixel showcase only; leave root, watch and media untouched."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from deployment import load_deployment, load_outputs, validate_identity

ROOT = Path(__file__).resolve().parents[2]
ASSETS = {
    "product/pixel-formal.js": ROOT / "product/web/pixel-formal.js",
    "product/index.html": ROOT / "product/web/index.html",
}
PROTECTED = ("index.html", "product/watch/index.html", "product/watch/app.js",
             "product/watch/data/stories.json", "product/media/formal/enhanced.mp4")


def main():
    import boto3
    from botocore.config import Config

    target = load_deployment()
    outputs = load_outputs(target=target)
    session = boto3.Session(profile_name="nba", region_name="us-east-1")
    config = Config(connect_timeout=6, read_timeout=15, retries={"total_max_attempts": 2})
    validate_identity(session.client("sts", config=config).get_caller_identity(), target)
    s3 = session.client("s3", config=config)
    location = {"Bucket": outputs["Bucket"], "ExpectedBucketOwner": target["account"]}

    def identity(key):
        head = s3.head_object(Key=key, **location)
        return {"etag": head["ETag"], "bytes": head["ContentLength"],
                "sha256": head.get("Metadata", {}).get("sha256")}

    before = {key: identity(key) for key in PROTECTED}
    backup = ROOT / "product/build/pixel-formal"
    backup.mkdir(parents=True, exist_ok=True)
    previous = s3.get_object(Key="product/index.html", **location)["Body"].read()
    (backup / "previous-index.html").write_bytes(previous)
    uploaded = []
    for key, path in ASSETS.items():
        body = path.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        content_type = "text/html" if key.endswith(".html") else "application/javascript"
        s3.put_object(Key=key, Body=body, ContentType=content_type + "; charset=utf-8",
                      CacheControl="no-store", ServerSideEncryption="AES256",
                      Metadata={"sha256": digest}, **location)
        actual = identity(key)
        if actual["sha256"] != digest or actual["bytes"] != len(body):
            raise RuntimeError("Legacy page upload verification failed")
        uploaded.append({"key": key, **actual})
    after = {key: identity(key) for key in PROTECTED}
    receipt = {"checkedAt": datetime.now(timezone.utc).isoformat(), "account": target["account"],
               "url": outputs["Website"] + "/product/", "uploaded": uploaded,
               "protectedBefore": before, "protectedAfter": after,
               "protectedUnchanged": before == after, "newInference": False,
               "mediaReuploaded": False}
    (ROOT / "product/evidence/pixel-formal-publication-20261010.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False))
    if before != after:
        raise RuntimeError("Protected objects changed during publication; inspect concurrent release")


if __name__ == "__main__":
    main()
