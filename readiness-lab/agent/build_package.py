"""Build a code ZIP from already installed SDK files; no install or AWS calls."""

import argparse
import importlib.util
from pathlib import Path
import zipfile


def build(destination):
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = [(Path(__file__).with_name("main.py"), "main.py")]
    for module in ("boto3", "botocore", "s3transfer", "jmespath", "dateutil", "urllib3", "six"):
        spec = importlib.util.find_spec(module)
        if spec is None or spec.origin is None:
            raise RuntimeError(f"Missing {module}; install requirements in a dedicated environment first")
        origin = Path(spec.origin)
        if spec.submodule_search_locations:
            for path in sorted(origin.parent.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo"):
                    files.append((path, path.relative_to(origin.parent.parent).as_posix()))
        else:
            files.append((origin, origin.name))
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for source, name in files:
            archive.write(source, name)
    print(f"Created {destination} ({destination.stat().st_size} bytes; {len(files)} files)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", help="Local output ZIP path; no upload or deployment is performed")
    build(parser.parse_args().output)
