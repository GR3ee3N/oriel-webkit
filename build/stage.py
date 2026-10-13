"""Stages WebKit's add-on, minus what CoreELEC has, and the dev sysroot apps build against."""
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys

BOX = dict(line.split("=", 1) for line in (Path(__file__).parent / "box.env").read_text().splitlines()
           if line and not line.startswith("#"))
CORE = re.compile(BOX["LIBRARIES"])


# The rest of share/ is docs and tooling.
SHARE = {"fontconfig", "fonts", "mime", "wpe-webkit-2.0", "X11"}


def ignore(directory, names):
    directory = Path(directory)
    if directory.name == "share" and directory.parent.name == "usr":
        return [name for name in names if name not in SHARE]
    return [name for name in names if CORE.fullmatch(name) or name.startswith("libgallium-") or
            name.endswith((".a", ".la")) or
            name in {"pkgconfig", "cmake", "dri", "gbm", "girepository-1.0", "man", "doc", "info", "aclocal", "locale",
                     "icu", "xsltConf.sh", "terminfo"}]


def prune(out):
    """Dynamic loads are not visible in DT_NEEDED; their modules must be roots."""
    lib = out / "lib"
    roots = []
    for file in out.rglob("*"):
        if file.is_file() and not file.is_symlink() and (
                "libexec" in file.relative_to(out).parts or file.parent.name in {"modules", "injected-bundle"}):
            with file.open("rb") as stream:
                if stream.read(4) == b"\x7fELF":
                    roots.append(file)
    names = {file.name: file for file in lib.iterdir()}
    reached, pending = set(), roots
    while pending:
        file = pending.pop().resolve()
        if file not in reached:
            reached.add(file)
            dynamic = subprocess.check_output(["readelf", "-d", str(file)], text=True)
            pending += [names[name] for name in re.findall(r"\(NEEDED\).*\[(.*?)\]", dynamic) if name in names]
    # Decide before deleting: symlink chains no longer resolve once their file is gone.
    unused = [file for file in lib.rglob("*.so*") if file.resolve() not in reached]
    for file in unused:
        file.unlink()
    for directory in sorted(lib.rglob("*"), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def version(text):
    return tuple(map(int, text.split(".")))


def require_versions(file, needs):
    for name, required in re.findall(r"\b(GLIBC|GLIBCXX|CXXABI|GCC)_([0-9]+(?:\.[0-9]+)*)\b", needs):
        if version(required) > version(BOX[name]):
            raise SystemExit(f"{file} requires {name}_{required}; the box provides {name}_{BOX[name]}")


def elf_info(file):
    with file.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            return None
    header = subprocess.check_output(["readelf", "-h", str(file)], text=True)
    if not re.search(r"Machine:\s+AArch64", header):
        raise SystemExit(f"not an ARM64 binary: {file}")
    versions = subprocess.check_output(["readelf", "-V", str(file)], text=True)
    # Only requirements, not the versions a library itself exports.
    require_versions(file, versions.partition("Version needs section")[2])
    dynamic = subprocess.check_output(["readelf", "-d", str(file)], text=True)
    return re.findall(r"\(NEEDED\).*\[(.*?)\]", dynamic)


# The box's libc and libstdc++, and the kernel's headers; apps link against their own toolchain's.
TOOLCHAIN = {"gcc-final", "glibc", "linux-headers"}


def dev(output, destination, strip, shipped):
    """Headers and pkg-config files of every staged package but the toolchain, and the add-on's libraries."""
    sysroot = output / "host/aarch64-buildroot-linux-gnu/sysroot"
    for listing in sorted((output / "build").glob("*/.files-list-staging.txt")):
        for line in listing.read_text().splitlines():
            package, _, path = line.partition(",")
            path = PurePosixPath(path.removeprefix("./"))
            if package in TOOLCHAIN or path.suffix in {".a", ".la"} or not (
                    path.parts[:2] in {("usr", "include"), ("usr", "lib")} or path.parts[:3] == ("usr", "share", "pkgconfig")):
                continue
            source, target = sysroot / path, destination / path
            # Distribute no library the add-on doesn't; the box brings its own graphics libraries.
            if ".so" in path.name and source.resolve().name not in shipped:
                continue
            if source.is_symlink() or source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_symlink():
                    target.unlink(missing_ok=True)
                    target.symlink_to(source.readlink())
                else:
                    shutil.copy2(source, target)
                    # Linking needs only the dynamic symbols.
                    with target.open("rb") as stream:
                        if stream.read(4) == b"\x7fELF":
                            subprocess.run([str(strip), "--strip-unneeded", str(target)], check=True)


def main():
    target, out, devdir, strip = map(Path, sys.argv[1:])
    out.mkdir(parents=True)
    for source, destination in ((target / "usr/lib", out / "lib"), (target / "lib", out / "lib"),
                                (target / "usr/libexec", out / "libexec"), (target / "usr/share", out / "share")):
        if source.is_dir():
            shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True, ignore=ignore)
    for name in ("WPEWebProcess", "WPENetworkProcess", "libgioopenssl.so"):
        if not any(out.rglob(name)):
            raise SystemExit(f"missing runtime component: {name}")
    prune(out)
    # Mali exports GBM, but CoreELEC provides no libgbm.so.1 filename.
    (out / "lib/libgbm.so.1").symlink_to("libMali.so")
    provided = {file.name for file in (out / "lib").rglob("*") if file.is_file() or file.is_symlink()}
    for file in out.rglob("*"):
        needs = elf_info(file) if file.is_file() and not file.is_symlink() else None
        if needs is not None:
            missing = [name for name in needs if name not in provided and not CORE.fullmatch(name)]
            if missing:
                raise SystemExit(f"missing runtime libraries for {file}: {', '.join(missing)}")
            subprocess.run([str(strip), "--strip-unneeded", str(file)], check=True)
    dev(target.parent, devdir / "sysroot", strip, provided)
    # Libraries supplied by the add-on; box.env describes CoreELEC's separately.
    (devdir / "provided.txt").write_text("".join(f"{name}\n" for name in sorted(provided)))
    shutil.copy(Path(__file__).parent / "box.env", devdir)


if __name__ == "__main__":
    main()
