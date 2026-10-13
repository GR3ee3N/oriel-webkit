#!/bin/bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"
set -a
source build/versions.env
set +a
[[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "VERSION in build/versions.env must be x.y.z" >&2; exit 2; }
JOBS=${JOBS:-$(nproc)}
[[ $JOBS =~ ^[1-9][0-9]*$ ]] || { echo "JOBS must be a positive integer" >&2; exit 2; }
CACHE=$REPO/.cache
export BR2_DL_DIR=$CACHE/downloads
TREE=$CACHE/build/tree
BR=$TREE/source
OUTPUT=$TREE/output
# Buildroot doesn't rebuild packages whose inputs changed.
rm -rf "$TREE"
build/configure.sh "$TREE"
make -C "$BR" O="$OUTPUT" BR2_JLEVEL="$JOBS" wpewebkit glib-networking xkeyboard-config dejavu shared-mime-info

RUNTIME=$CACHE/runtime
rm -rf "$RUNTIME"
mkdir -p "$RUNTIME/dev"
python3 build/stage.py "$OUTPUT/target" "$RUNTIME/script.module.oriel.webkit/usr" "$RUNTIME/dev" "$OUTPUT/host/bin/aarch64-buildroot-linux-gnu-strip"
rsync -a --exclude .keep addon/ "$RUNTIME/script.module.oriel.webkit/"
sed -i "s/@VERSION@/$VERSION/g" "$RUNTIME/script.module.oriel.webkit/addon.xml"
cp "$OUTPUT/.config" "$RUNTIME/buildroot.config"
python3 build/verify.py "$OUTPUT/.config" "$RUNTIME"
echo "Built .cache/runtime: the WebKit add-on, and in dev/ the sysroot apps build against."
