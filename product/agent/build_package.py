"""Package product AgentCore source and installed SDK; no cloud calls."""

import argparse
import importlib.util
from pathlib import Path
import zipfile


def build(destination):
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    files = [(path, path.name) for path in sorted(here.glob("*.py"))
             if not path.name.startswith("test_") and path.name != "build_package.py"]
    for module in ("boto3", "botocore", "s3transfer", "jmespath", "dateutil", "urllib3", "six"):
        spec = importlib.util.find_spec(module)
        if spec is None or spec.origin is None:
            raise RuntimeError(f"Missing {module}; install requirements first")
        origin = Path(spec.origin)
        if spec.submodule_search_locations:
            files.extend((path, path.relative_to(origin.parent.parent).as_posix()) for path in sorted(origin.parent.rglob("*"))
                         if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo"))
        else:
            files.append((origin, origin.name))
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for source, name in files:
            archive.write(source, name)
    print(f"Created {destination} ({destination.stat().st_size} bytes; {len(files)} files)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    build(parser.parse_args().output)
