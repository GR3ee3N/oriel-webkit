#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
source build/versions.env
set +a
export BR2_DL_DIR=$PWD/.cache/downloads
build/check.sh
build/compile.sh
python3 build/release.py .cache/build/tree/source .cache/build/tree/output "$1" .cache/release-source.tar
