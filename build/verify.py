"""Checks the resolved Buildroot configuration and staged native output."""
from pathlib import Path
import re
import subprocess
import sys

import stage


def config(file):
    # Kconfig resolves dependencies; GPL-3.0 readline must not come in through bash.
    text = file.read_text()
    if "BR2_PACKAGE_READLINE=y" in text or "BR2_PACKAGE_BASH=y" in text:
        raise SystemExit("Bash/readline must not be enabled in the runtime")


def runtime(directory):
    usr = directory / "script.module.oriel.webkit/usr"
    if any(b"pdfjs/" in library.read_bytes() for library in (usr / "lib").glob("libWPEWebKit-*.so.*")):
        raise SystemExit("pdf.js shipped")
    if any(link.name != "libgbm.so.1" for link in (usr / "lib").rglob("*") if link.is_symlink() and not link.exists()):
        raise SystemExit("dangling runtime links")
    dev = directory / "dev/sysroot/usr/lib"
    if not (dev / "pkgconfig/wpe-webkit-2.0.pc").is_file():
        raise SystemExit("missing WebKit pkg-config file")
    for binary in [*usr.rglob("*"), (dev / "libWPEWebKit-2.0.so.1").resolve()]:
        if binary.is_file() and not binary.is_symlink() and stage.elf_info(binary) is not None:
            sections = subprocess.check_output(["readelf", "-S", str(binary)], text=True)
            if re.search(r"\s\.(?:debug_\w+|symtab)\s", sections):
                raise SystemExit(f"unstripped binary: {binary}")


if __name__ == "__main__":
    config(Path(sys.argv[1]))
    print("Buildroot configuration checks passed.")
    if len(sys.argv) > 2:
        runtime(Path(sys.argv[2]))
        print("Native output checks passed.")
