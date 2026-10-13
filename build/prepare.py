"""Adapts Buildroot's recipes for Oriel's headless WPE WebKit."""
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
    """Adds a license file Buildroot's recipe leaves out."""
    variable = package.upper().replace("-", "_") + "_LICENSE_FILES"
    replace(f"package/{package}/{package}.mk", f"{variable} = {files}", f"{variable} = {files} {path}")
    with (root / f"package/{package}/{package}.hash").open("a") as file:
        file.write(f"sha256  {checksum}  {path}\n")


def pin(package, archive, checksum):
    # Keep upstream's license file hashes; add the pinned source archive.
    with (root / f"package/{package}/{package}.hash").open("a") as file:
        file.write(f"sha256  {checksum}  {archive}\n")


wpe, glibc = os.environ["WPE_VERSION"], os.environ["GLIBC_VERSION"]
# The shell presents WebKit's frames itself, so WebKit uses headless WPEPlatform
# instead of libwpe and wpebackend-fdo. Kodi plays the media, so no GStreamer.
replace("package/wpewebkit/wpewebkit.mk", "WPEWEBKIT_VERSION = 2.50.5", f"WPEWEBKIT_VERSION = {wpe}")
replace("package/wpewebkit/wpewebkit.mk", "webp wpebackend-fdo", "webp libxkbcommon libdrm libgbm woff2")
replace("package/wpewebkit/Config.in", "select BR2_PACKAGE_WPEBACKEND_FDO", "select BR2_PACKAGE_LIBXKBCOMMON")
replace("package/wpewebkit/wpewebkit.mk", "-DPORT=WPE", '-DPORT=WPE \\\n\t-DENABLE_WPE_PLATFORM=ON \\\n\t-DENABLE_WPE_PLATFORM_HEADLESS=ON \\\n\t-DENABLE_WPE_PLATFORM_DRM=OFF \\\n\t-DENABLE_WPE_PLATFORM_WAYLAND=OFF \\\n\t-DENABLE_WPE_LEGACY_API=OFF \\\n\t-DUSE_LIBHYPHEN=OFF \\\n\t-DENABLE_PDFJS=OFF')
replace("package/wpewebkit/wpewebkit.mk", "-DENABLE_WEB_CODECS=OFF", '-DENABLE_WEB_CODECS=OFF \\\n\t-DUSE_GSTREAMER=OFF')
replace("package/glibc/glibc.mk", "GLIBC_VERSION = 2.44-36-g2d5421ffca8893534d5e02ad38c28acd8e778fa3", f"GLIBC_VERSION = {glibc}")
replace("package/glibc/glibc.mk", "GLIBC_SITE = https://gitlab.com/gnutools/glibc.git\nGLIBC_SITE_METHOD = git", "GLIBC_SITE = https://ftp.gnu.org/gnu/glibc\nGLIBC_SOURCE = glibc-$(GLIBC_VERSION).tar.xz")
pin("wpewebkit", f"wpewebkit-{wpe}.tar.xz", os.environ["WPE_SHA256"])
pin("glibc", f"glibc-{glibc}.tar.xz", os.environ["GLIBC_SHA256"])
# Buildroot's recipe names no license, and every distributed package needs one.
replace("package/dejavu/dejavu.mk", "DEJAVU_LICENSE_FILES = LICENSE",
        "DEJAVU_LICENSE = Bitstream-Vera, Arev fonts license\nDEJAVU_LICENSE_FILES = LICENSE")
# The ISC part Buildroot declares (ucdn) carries its notice only in its source file.
license_file("harfbuzz", "COPYING", "src/hb-ucd.cc", "0bb1dc09aee15ca98a2222f7307d1a9d279646c486f8240efd50035c86554420")
# libpsl compiles in the MPL-2.0 public suffix list, so its source must be published too.
replace("package/libpsl/libpsl.mk", "LIBPSL_LICENSE = MIT, BSD-3-Clause", "LIBPSL_LICENSE = MIT, BSD-3-Clause, MPL-2.0 (public suffix list)")
license_file("libpsl", "COPYING src/LICENSE.chromium", "list/public_suffix_list.dat", "8a99ee709c83a545413c0ad81033681696fddd3ed2b7296d9a88a11235fe5c6f")
replace("package/glib-networking/glib-networking.mk", "GLIB_NETWORKING_LICENSE = LGPL-2.0+", "GLIB_NETWORKING_LICENSE = LGPL-2.0+ with OpenSSL exception")
license_file("glib-networking", "COPYING", "LICENSE_EXCEPTION", "85685a53e87aa7d3a70016856b646ad1b09c8e636295241f9f7c2d55cd7f05ce")

# The 2.52.6 custom binding lacks the guard used by its generated header.
(root / "package/wpewebkit/0001-guard-disabled-video-binding.patch").write_text(
    "--- a/Source/WebCore/bindings/js/JSHTMLMediaElementCustom.cpp\n"
    "+++ b/Source/WebCore/bindings/js/JSHTMLMediaElementCustom.cpp\n"
    "@@ -24,6 +24,8 @@\n"
    "  */\n"
    " \n"
    ' #include "config.h"\n'
    "+// Modified for Oriel on 2026-10-08: allow builds without video.\n"
    "+#if ENABLE(VIDEO)\n"
    ' #include "JSHTMLMediaElement.h"\n'
    " \n"
    ' #include "TrackOpaqueRoot.h"\n'
    "@@ -40,3 +42,4 @@\n"
    " DEFINE_VISIT_ADDITIONAL_CHILDREN(JSHTMLMediaElement);\n"
    " \n"
    " } // namespace WebCore\n"
    "+#endif // ENABLE(VIDEO)\n"
)

# WPEPlatform is an ENABLE feature, not a USE feature.
(root / "package/wpewebkit/0002-fix-gamepad-platform-guard.patch").write_text(
    "--- a/Source/WebKit/UIProcess/Gamepad/UIGamepadProvider.cpp\n"
    "+++ b/Source/WebKit/UIProcess/Gamepad/UIGamepadProvider.cpp\n"
    "@@ -253 +253,2 @@\n"
    "-#if !PLATFORM(COCOA) && !(USE(MANETTE) && OS(LINUX)) && !USE(LIBWPE) && !USE(WPE_PLATFORM)\n"
    "+// Modified for Oriel on 2026-10-08: fix the WPEPlatform feature guard.\n"
    "+#if !PLATFORM(COCOA) && !(USE(MANETTE) && OS(LINUX)) && !USE(LIBWPE) && !ENABLE(WPE_PLATFORM)\n"
    "@@ -274 +275 @@\n"
    "-#endif // !PLATFORM(COCOA) && !(USE(MANETTE) && OS(LINUX)) && !USE(LIBWPE) && !USE(WPE_PLATFORM)\n"
    "+#endif // !PLATFORM(COCOA) && !(USE(MANETTE) && OS(LINUX)) && !USE(LIBWPE) && !ENABLE(WPE_PLATFORM)\n"
)
