#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
shellcheck -x -e SC2029 tools/*.sh build/*.sh
python3 -m unittest discover -s tests -t . -v
mkdir -p .cache
WORK=$(mktemp -d "$PWD/.cache/check.XXXXXX")
trap 'rm -rf "$WORK"' EXIT
build/configure.sh "$WORK"
python3 build/verify.py "$WORK/output/.config"
