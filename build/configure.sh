#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
source build/versions.env
set +a
TREE=$1
BR=$TREE/source
OUTPUT=$TREE/output
export BR2_DL_DIR=$PWD/.cache/downloads
mkdir -p "$BR2_DL_DIR" "$BR" "$OUTPUT"
ARCHIVE=$BR2_DL_DIR/buildroot-$BUILDROOT_VERSION.tar.xz
if [[ ! -f $ARCHIVE ]]; then
    curl -fL --retry 3 "https://buildroot.org/downloads/buildroot-$BUILDROOT_VERSION.tar.xz" -o "$ARCHIVE.tmp"
    mv "$ARCHIVE.tmp" "$ARCHIVE"
fi
printf '%s  %s\n' "$BUILDROOT_SHA256" "$ARCHIVE" | sha256sum --check
tar -xJf "$ARCHIVE" --strip-components=1 -C "$BR"
python3 build/prepare.py "$BR"
make -C "$BR" O="$OUTPUT" BR2_DEFCONFIG="$PWD/build/runtime.config" defconfig
# Kconfig silently drops unsupported selections; catch that before compiling.
for symbol in BR2_PACKAGE_WPEWEBKIT BR2_PACKAGE_MESA3D_OPENGL_ES; do
    grep -qx "$symbol=y" "$OUTPUT/.config" || { echo "$symbol was not enabled" >&2; exit 1; }
done
