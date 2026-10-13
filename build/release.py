"""Packages the WebKit add-on and its dev sysroot with their licenses and sources."""
import csv
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
import zipfile

REPO = Path(__file__).resolve().parent.parent
GITHUB = "GR3ee3N/oriel-webkit"
LICENSE_FILE = re.compile(r"^(?:licen[cs]e|copying|copyright|notice|unlicense)(?:[-._].*)?$", re.I)


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def digest(file):
    with Path(file).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


# Licenses that require publishing the source.
COPYLEFT = re.compile(r"\b[AL]?GPL\b|\bMPL\b|\bEPL\b|\bCDDL\b")


def shipped(output, usr, listing_name=".files-list.txt"):
    """Buildroot packages with files in this tree."""
    owner = {}
    for listing in (output / "build").glob(f"*/{listing_name}"):
        for line in listing.read_text().splitlines():
            package, _, path = line.partition(",")
            owner[path.removeprefix("./")] = package
    packages = set()
    for file in usr.rglob("*"):
        if file.is_file() and not file.is_symlink():
            relative = file.relative_to(usr).as_posix()
            package = owner.get(f"usr/{relative}") or owner.get(relative)
            require(package, f"no Buildroot package installed {relative}")
            packages.add(package)
    return packages


def validate_legal(directory, packages):
    """Returns the package-version names to publish licenses and sources for."""
    licenses, sources, found = set(), set(), set()
    with (directory / "manifest.csv").open() as stream:
        for row in csv.DictReader(stream):
            if row["PACKAGE"] not in packages:
                continue
            found.add(row["PACKAGE"])
            name = f"{row['PACKAGE']}-{row['VERSION']}"
            require(row["LICENSE"] and row["LICENSE"] != "unknown", f"unknown license: {name}")
            require(any(p.is_file() for p in (directory / "licenses" / name).rglob("*")), f"missing license text: {name}")
            licenses.add(name)
            if COPYLEFT.search(row["LICENSE"]):
                require((directory / "sources" / name / row["SOURCE ARCHIVE"]).is_file(), f"missing redistributable source: {name}")
                sources.add(name)
    require(found == packages, f"shipped packages missing from legal-info: {sorted(packages - found)}")
    warnings = [line for line in (directory / "README").read_text().splitlines() if line.startswith("WARNING:")]
    require(all(line == "WARNING: the Buildroot source code has not been saved" for line in warnings),
            "unresolved Buildroot legal-info warnings:\n" + "\n".join(warnings))
    return licenses, sources


def tar_tree(directory, destination):
    with tarfile.open(destination, "w:gz" if destination.name.endswith(".gz") else "w:xz") as archive:
        archive.add(directory, arcname=directory.name)


def zip_tree(directory, destination):
    # Old upstream files predate ZIP's 1980 epoch.
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
        for file in sorted(directory.rglob("*")):
            require(not file.is_symlink(), f"ZIP must not contain Unix links: {file}")
            archive.write(file, f"{directory.name}/{file.relative_to(directory).as_posix()}")


def checksum(file):
    file.with_name(file.name + ".sha256").write_text(f"{digest(file)}  {file.name}\n")


# Tests, build tools and the disabled pdf.js don't ship.
UNSHIPPED = {"gtest", "tests", "test_utils", "tools", "unifdef", "util", "pdfjs"}


def webkit_licenses(source, destination):
    """Buildroot declares only WebCore's licenses; WebKit bundles more code."""
    for file in sorted((source / "Source").rglob("*")):
        relative = file.relative_to(source)
        if file.is_file() and LICENSE_FILE.match(file.name) and not UNSHIPPED & set(relative.parts):
            (destination / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(file, destination / relative)


def notices(directory, url):
    (directory / "THIRD-PARTY-NOTICES.txt").write_text(
        "Third-party components keep their own licenses; see LICENSES/. Oriel's\n"
        "build scripts are GPL-3.0-or-later (LICENSE.txt).\n"
        "\n"
        "FreeType is used under the FreeType License. Portions of this software are\n"
        "copyright (C) 2026 The FreeType Project (https://freetype.org). All rights\n"
        "reserved.\n"
        "This software is based in part on the work of the Independent JPEG Group.\n"
        "\n"
        "CoreELEC provides the system and graphics libraries; they are not bundled.\n"
        "You may modify the bundled libraries and replace them with\n"
        "interface-compatible versions.\n"
        f"Complete source, patches and build scripts: {url}\n"
    )
    (directory / "SOURCE.txt").write_text(url + "\n")
    shutil.copy(REPO / "LICENSE", directory / "LICENSE.txt")


def package(runtime, source, licenses, destination):
    v = os.environ["VERSION"]
    url = f"https://github.com/{GITHUB}/releases/download/v{v}/{source.name}.tar.xz"
    stage = destination / "packages"
    files = destination / "files"
    files.mkdir(parents=True)
    addon = stage / "script.module.oriel.webkit"
    shutil.copytree(runtime / "script.module.oriel.webkit", addon, symlinks=True)
    tar_tree(addon / "usr", addon / "usr.tar.gz")
    shutil.rmtree(addon / "usr")
    dev = stage / f"oriel-webkit-{v}-dev"
    shutil.copytree(runtime / "dev", dev, symlinks=True)
    for directory in (addon, dev, source):
        shutil.copytree(licenses, directory / ("licenses" if directory == source else "LICENSES"))
    for directory in (addon, dev):
        notices(directory, url)
    zip_name = f"script.module.oriel.webkit-{v}.zip"
    zip_tree(addon, files / zip_name)
    tar_tree(dev, files / f"{dev.name}.tar.xz")
    tar_tree(source, files / f"{source.name}.tar.xz")
    # Kodi's index, served from the latest release with the zip it names.
    addons = ET.Element("addons")
    element = ET.fromstring((REPO / "addon/addon.xml").read_text().replace("@VERSION@", v).encode())
    ET.SubElement(element.find('extension[@point="xbmc.addon.metadata"]'), "path").text = zip_name
    addons.append(element)
    ET.indent(addons)
    ET.ElementTree(addons).write(files / "addons.xml", encoding="UTF-8", xml_declaration=True)
    for name in (zip_name, "addons.xml"):
        checksum(files / name)


def main():
    br, output = (Path(arg).resolve() for arg in sys.argv[1:3])
    commit = sys.argv[3]
    snapshot = Path(sys.argv[4])
    runtime = REPO / ".cache/runtime"
    v = os.environ["VERSION"]
    destination = REPO / ".cache/release.next"
    if destination.exists():
        shutil.rmtree(destination)
    source = destination / f"oriel-webkit-{v}-sources"
    source.mkdir(parents=True)
    with tarfile.open(snapshot) as archive:
        archive.extractall(source, filter="data")

    subprocess.run(["make", "-C", str(br), f"O={output}", "legal-info"], check=True)
    legal = output / "legal-info"
    packages = shipped(output, runtime / "script.module.oriel.webkit/usr") | shipped(output, runtime / "dev/sysroot", ".files-list-staging.txt")
    licensed, sourced = validate_legal(legal, packages)

    def published(directory, names):
        # Leave out build tools, the toolchain and permissive packages' sources.
        return {legal: ["host-sources"],
                legal / "licenses": [name for name in names if name not in licensed],
                legal / "sources": [name for name in names if name not in sourced]}.get(Path(directory), [])
    shutil.copytree(legal, source / "legal-info", ignore=published)
    # Its checksum list still names the omitted files.
    (source / "legal-info/legal-info.sha256").unlink(missing_ok=True)
    shutil.copy(REPO / f".cache/downloads/buildroot-{os.environ['BUILDROOT_VERSION']}.tar.xz", source)
    shutil.copy(runtime / "buildroot.config", source)
    (source / "COMMIT").write_text(commit + "\n")
    (source / "README.txt").write_text(
        "Build instructions: oriel-webkit/README.md. The source archives and\n"
        "applied patches of the copyleft packages are in legal-info/sources;\n"
        "licenses/ holds the license texts of every distributed package.\n"
        "The complete Buildroot archive includes support/libtool patches omitted by\n"
        "legal-info. Build tools are downloaded by the build. WebKit patches\n"
        "identify the changes and their dates in modified files. Libraries may be\n"
        "modified and rebuilt using the same scripts.\n"
    )

    licenses = destination / "licenses"
    for name in licensed:
        shutil.copytree(legal / "licenses" / name, licenses / name)
    wpe = f"wpewebkit-{os.environ['WPE_VERSION']}"
    webkit_licenses(output / "build" / wpe, licenses / wpe)

    package(runtime, source, licenses, destination)
    # tools/release.sh publishes only packages of the commit it releases.
    (destination / "COMMIT").write_text(commit + "\n")
    for leftover in (destination / "packages", source, licenses):
        shutil.rmtree(leftover)
    release = REPO / ".cache/release"
    if release.exists():
        shutil.rmtree(release)
    destination.rename(release)
    print(f"Release packages, licenses and source: {release / 'files'}")


if __name__ == "__main__":
    main()
