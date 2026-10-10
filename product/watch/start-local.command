#!/bin/bash
set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python_bin="${BROADCASTCODE_PYTHON:-python3}"
if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "需要 Python 3.9 或更新版本。安装后重试，或设置 BROADCASTCODE_PYTHON 指向已有 Python。" >&2
  exit 1
fi
if ! "$python_bin" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "此预览需要 Python 3.9 或更新版本。" >&2
  exit 1
fi

echo "本地前端预览；按 Control-C 停止。"
exec "$python_bin" "$script_dir/preview.py" "$@"
