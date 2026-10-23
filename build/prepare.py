"""Configure Buildroot recipes for headless WPE WebKit and runtime packaging."""
import os
from pathlib import Path
import sys

root = Path(sys.argv[1])


def replace(path, before, after):
    file = root / path
    text = file.read_text()
    if text.count(before) != 1:
        raise SystemExit(f"unexpected Buildroot recipe: {path}: {before!r}")
    file.write_text(text.replace(before, after))


def license_file(package, files, path, checksum):
    """Include a missing license file and its checksum in the Buildroot recipe."""
    variable = package.upper().replace("-", "_") + "_LICENSE_FILES"
    replace(f"package/{package}/{package}.mk", f"{variable} = {files}", f"{variable} = {files} {path}")
    with (root / f"package/{package}/{package}.hash").open("a") as file:
        file.write(f"sha256  {checksum}  {path}\n")


def pin(package, archive, checksum):
    # Append the pinned archive checksum while retaining upstream license-file hashes.
    with (root / f"package/{package}/{package}.hash").open("a") as file:
        file.write(f"sha256  {checksum}  {archive}\n")


wpe, glibc = os.environ["WPE_VERSION"], os.environ["GLIBC_VERSION"]
# Use headless WPEPlatform because the framework shell submits page buffers
# for Kodi to draw. Disable GStreamer because Kodi handles media playback.
replace("package/wpewebkit/wpewebkit.mk", "WPEWEBKIT_VERSION = 2.50.5", f"WPEWEBKIT_VERSION = {wpe}")
replace("package/wpewebkit/wpewebkit.mk", "webp wpebackend-fdo", "webp libxkbcommon libdrm libgbm woff2")
replace("package/wpewebkit/Config.in", "select BR2_PACKAGE_WPEBACKEND_FDO", "select BR2_PACKAGE_LIBXKBCOMMON")
replace("package/wpewebkit/wpewebkit.mk", "-DPORT=WPE", '-DPORT=WPE \\\n\t-DENABLE_WPE_PLATFORM=ON \\\n\t-DENABLE_WPE_PLATFORM_HEADLESS=ON \\\n\t-DENABLE_WPE_PLATFORM_DRM=OFF \\\n\t-DENABLE_WPE_PLATFORM_WAYLAND=OFF \\\n\t-DENABLE_WPE_LEGACY_API=OFF \\\n\t-DUSE_LIBHYPHEN=OFF \\\n\t-DENABLE_PDFJS=OFF \\\n\t-DENABLE_SPELLCHECK=OFF')
replace("package/wpewebkit/wpewebkit.mk", "-DENABLE_WEB_CODECS=OFF", '-DENABLE_WEB_CODECS=OFF \\\n\t-DUSE_GSTREAMER=OFF')
replace("package/glibc/glibc.mk", "GLIBC_VERSION = 2.44-36-g2d5421ffca8893534d5e02ad38c28acd8e778fa3", f"GLIBC_VERSION = {glibc}")
replace("package/glibc/glibc.mk", "GLIBC_SITE = https://gitlab.com/gnutools/glibc.git\nGLIBC_SITE_METHOD = git", "GLIBC_SITE = https://ftp.gnu.org/gnu/glibc\nGLIBC_SOURCE = glibc-$(GLIBC_VERSION).tar.xz")
pin("wpewebkit", f"wpewebkit-{wpe}.tar.xz", os.environ["WPE_SHA256"])
pin("glibc", f"glibc-{glibc}.tar.xz", os.environ["GLIBC_SHA256"])
# Declare the font licenses so the release manifest identifies every shipped package.
replace("package/dejavu/dejavu.mk", "DEJAVU_LICENSE_FILES = LICENSE",
        "DEJAVU_LICENSE = Bitstream-Vera, Arev fonts license\nDEJAVU_LICENSE_FILES = LICENSE")
# Include the ucdn ISC notice embedded in HarfBuzz's hb-ucd.cc source file.
license_file("harfbuzz", "COPYING", "src/hb-ucd.cc", "0bb1dc09aee15ca98a2222f7307d1a9d279646c486f8240efd50035c86554420")
# Include the MPL-2.0 public suffix list license and source with libpsl.
replace("package/libpsl/libpsl.mk", "LIBPSL_LICENSE = MIT, BSD-3-Clause", "LIBPSL_LICENSE = MIT, BSD-3-Clause, MPL-2.0 (public suffix list)")
license_file("libpsl", "COPYING src/LICENSE.chromium", "list/public_suffix_list.dat", "8a99ee709c83a545413c0ad81033681696fddd3ed2b7296d9a88a11235fe5c6f")
replace("package/glib-networking/glib-networking.mk", "GLIB_NETWORKING_LICENSE = LGPL-2.0+", "GLIB_NETWORKING_LICENSE = LGPL-2.0+ with OpenSSL exception")
license_file("glib-networking", "COPYING", "LICENSE_EXCEPTION", "85685a53e87aa7d3a70016856b646ad1b09c8e636295241f9f7c2d55cd7f05ce")

# Copy active patches from build/patches/wpewebkit for Buildroot to apply in filename order.
for patch in sorted((Path(__file__).parent / "patches/wpewebkit").glob("*.patch")):
    (root / "package/wpewebkit" / patch.name).write_bytes(patch.read_bytes())
