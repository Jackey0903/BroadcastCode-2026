"""Read and verify the exact SDK pins without building assets or using AWS."""
from importlib import metadata
from pathlib import Path
import re

SDK_DISTRIBUTIONS = frozenset(('boto3', 'botocore', 's3transfer', 'jmespath',
                               'python-dateutil', 'urllib3', 'six'))
INSTALL_HINT = ('Install with readiness-lab/.venv/bin/python -m pip install '
                '-r product/agent/requirements.txt; build with '
                'readiness-lab/.venv/bin/python product/scripts/build.py.')


class BuildDependencyError(ValueError):
    pass


def read_pins(requirements):
    """Require one exact pin per audited SDK distribution; reject drift."""
    try:
        lines = Path(requirements).read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeError) as error:
        raise BuildDependencyError('Cannot read product SDK requirements. ' + INSTALL_HINT) from error
    pins = {}
    for line in lines:
        entry = line.split('#', 1)[0].strip()
        if not entry:
            continue
        match = re.fullmatch(r'([a-z0-9-]+)==([0-9][A-Za-z0-9.+_-]*)', entry)
        if not match or match[1] not in SDK_DISTRIBUTIONS or match[1] in pins:
            raise BuildDependencyError('Product SDK requirements must contain seven unique exact pins. ' + INSTALL_HINT)
        pins[match[1]] = match[2]
    if set(pins) != SDK_DISTRIBUTIONS:
        raise BuildDependencyError('Product SDK requirements omit an audited distribution. ' + INSTALL_HINT)
    return pins


def verify_dependencies(requirements, *, version_lookup=metadata.version):
    """Reject missing/mismatched installed distributions before asset writes."""
    pins = read_pins(requirements)
    for distribution, expected in pins.items():
        try:
            actual = version_lookup(distribution)
        except metadata.PackageNotFoundError as error:
            raise BuildDependencyError(f'Missing SDK distribution: {distribution}=={expected}. ' + INSTALL_HINT) from error
        if actual != expected:
            raise BuildDependencyError(f'SDK version mismatch: {distribution}; expected {expected}, installed {actual}. ' + INSTALL_HINT)
    return pins
