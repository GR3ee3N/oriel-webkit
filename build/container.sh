#!/bin/bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"
set -a
source build/versions.env
set +a
case "$(uname -s):$(uname -m)" in
    Linux:x86_64|Linux:aarch64) ;;
    *) echo "build tools require Linux on x86_64 or ARM64" >&2; exit 1 ;;
esac
command -v docker >/dev/null || { echo "install and start Docker before building" >&2; exit 1; }
# Release snapshots share dependency caches and output with the checkout.
CACHE=${ORIEL_CACHE:-$REPO/.cache}
mkdir -p "$CACHE/home"
CACHE=$(cd "$CACHE" && pwd)
exec 9>"$CACHE/build.lock"
flock -n 9 || { echo "another local build or check is running" >&2; exit 1; }
docker build --build-arg "DEBIAN_SNAPSHOT=$DEBIAN_SNAPSHOT" -t oriel-webkit-builder -f build/Dockerfile build
exec docker run --rm --init --user "$(id -u):$(id -g)" \
    -e "JOBS=${JOBS:-$(nproc)}" -e HOME=/work/.cache/home \
    -v "$REPO:/work" -v "$CACHE:/work/.cache" oriel-webkit-builder "$@"
