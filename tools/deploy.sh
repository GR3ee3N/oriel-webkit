#!/bin/sh
# Reopen running apps after deployment to load the installed WebKit.
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd)
BOX="${BOX:?set BOX to your box, e.g. BOX=root@coreelec.local}"
[ "$#" -eq 0 ] || { echo "usage: tools/deploy.sh" >&2; exit 2; }
ADDONS=/storage/.kodi/addons
ID=script.module.oriel.webkit
cd "$REPO"
[ -f ".cache/runtime/$ID/addon.xml" ] || { echo "run tools/build.sh first" >&2; exit 1; }
# Keep installed files until their replacements have transferred.
rsync -rlt --delete-after --delay-updates --exclude .keep ".cache/runtime/$ID/" "$BOX:$ADDONS/$ID/"
ssh "$BOX" "kodi-send --action=UpdateLocalAddons >/dev/null"
ssh "$BOX" python3 - "$ID" < tools/enable.py
echo "installed $ID"
