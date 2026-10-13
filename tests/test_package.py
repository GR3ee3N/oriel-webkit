import csv
import hashlib
import io
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from build import release

REPO = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.v = "1.2.3"
        repo = patch.object(release, "REPO", self.root)
        repo.start()
        self.addCleanup(repo.stop)
        version = patch.dict(os.environ, VERSION=self.v)
        version.start()
        self.addCleanup(version.stop)
        shutil.copytree(REPO / "addon", self.root / "addon")
        shutil.copy(REPO / "LICENSE", self.root / "LICENSE")

    def package(self):
        root = self.root
        v = self.v
        runtime = root / ".cache/runtime"
        shutil.copytree(root / "addon", runtime / "script.module.oriel.webkit", ignore=shutil.ignore_patterns(".keep"))
        addon_xml = runtime / "script.module.oriel.webkit/addon.xml"
        addon_xml.write_text(addon_xml.read_text().replace("@VERSION@", v))
        usr = runtime / "script.module.oriel.webkit/usr"
        (usr / "lib").mkdir(parents=True)
        (usr / "lib/libexample.so.1").write_bytes(b"example")
        (usr / "lib/libexample.so").symlink_to("libexample.so.1")
        (usr / "libexec").mkdir()
        (usr / "libexec/WPEWebProcess").write_text("process")
        dev = runtime / "dev"
        (dev / "sysroot/usr/lib").mkdir(parents=True)
        (dev / "sysroot/usr/lib/libexample.so.1").write_bytes(b"example")
        (dev / "sysroot/usr/lib/libexample.so").symlink_to("libexample.so.1")
        (dev / "provided.txt").write_text("libexample.so.1\n")
        licenses = root / ".cache/licenses"
        (licenses / "example-1.0").mkdir(parents=True)
        (licenses / "example-1.0/COPYING").write_text("license text\n")
        sources = root / f".cache/sources/oriel-webkit-{v}-sources"
        sources.mkdir(parents=True)
        (sources / "README").write_text("matching source")
        output = root / ".cache/release"
        release.package(runtime, sources, licenses, output)
        files = output / "files"
        url = f"https://github.com/GR3ee3N/oriel-webkit/releases/download/v{v}/oriel-webkit-{v}-sources.tar.xz\n"
        return files, url

    def test_archives_preserve_runtime_dev_sources_and_licenses(self):
        files, url = self.package()
        v = self.v
        with zipfile.ZipFile(files / f"script.module.oriel.webkit-{v}.zip") as archive:
            self.assertEqual(archive.read("script.module.oriel.webkit/SOURCE.txt").decode(), url)
            self.assertFalse(any(name.startswith("script.module.oriel.webkit/usr/") for name in archive.namelist()))
            self.assertEqual(archive.read("script.module.oriel.webkit/LICENSES/example-1.0/COPYING"), b"license text\n")
            notices = archive.read("script.module.oriel.webkit/THIRD-PARTY-NOTICES.txt").decode()
            self.assertIn("The FreeType Project", notices)
            self.assertIn("Independent JPEG Group", notices)
            with tarfile.open(fileobj=io.BytesIO(archive.read("script.module.oriel.webkit/usr.tar.gz"))) as payload:
                self.assertEqual(payload.extractfile("usr/lib/libexample.so.1").read(), b"example")
                self.assertEqual(payload.getmember("usr/lib/libexample.so").linkname, "libexample.so.1")
        with tarfile.open(files / f"oriel-webkit-{v}-dev.tar.xz") as archive:
            top = f"oriel-webkit-{v}-dev"
            self.assertEqual(archive.extractfile(f"{top}/provided.txt").read(), b"libexample.so.1\n")
            self.assertEqual(archive.extractfile(f"{top}/LICENSES/example-1.0/COPYING").read(), b"license text\n")
            self.assertEqual(archive.getmember(f"{top}/sysroot/usr/lib/libexample.so").linkname, "libexample.so.1")
            self.assertEqual(archive.extractfile(f"{top}/sysroot/usr/lib/libexample.so.1").read(), b"example")
            self.assertEqual(archive.extractfile(f"{top}/SOURCE.txt").read().decode(), url)
        with tarfile.open(files / f"oriel-webkit-{v}-sources.tar.xz") as archive:
            top = f"oriel-webkit-{v}-sources"
            self.assertEqual(archive.extractfile(f"{top}/README").read(), b"matching source")
            self.assertEqual(archive.extractfile(f"{top}/licenses/example-1.0/COPYING").read(), b"license text\n")

    def test_webkit_bundled_licenses_exclude_unshipped_code(self):
        root = self.root
        # WebKit's bundled components, minus tests, tools and pdf.js.
        webkit = root / ".cache/wpewebkit"
        for name in ("Source/WebCore/LICENSE-APPLE", "Source/ThirdParty/skia/LICENSE", "Source/WTF/wtf/dtoa/COPYING",
                     "Source/ThirdParty/pdfjs/LICENSE", "Source/ThirdParty/gtest/LICENSE", "Source/WTF/wtf/Vector.h"):
            (webkit / name).parent.mkdir(parents=True, exist_ok=True)
            (webkit / name).write_text(name)
        release.webkit_licenses(webkit, root / ".cache/webkit-licenses")
        self.assertEqual(sorted(file.relative_to(root / ".cache/webkit-licenses").as_posix() for file in (root / ".cache/webkit-licenses").rglob("*") if file.is_file()), ["Source/ThirdParty/skia/LICENSE", "Source/WTF/wtf/dtoa/COPYING", "Source/WebCore/LICENSE-APPLE"])

    def test_kodi_index_and_independent_checksums_match_artifacts(self):
        files, _ = self.package()
        v = self.v
        listing = (files / "addons.xml").read_text()
        self.assertTrue(f'id="script.module.oriel.webkit" name="Oriel WebKit" version="{v}"' in listing and "@VERSION@" not in listing)
        self.assertIn(f"<path>script.module.oriel.webkit-{v}.zip</path>", listing)
        self.assertEqual(sorted(f.name for f in files.iterdir()), sorted([f"script.module.oriel.webkit-{v}.zip", f"script.module.oriel.webkit-{v}.zip.sha256", "addons.xml", "addons.xml.sha256",
                                                                   f"oriel-webkit-{v}-dev.tar.xz", f"oriel-webkit-{v}-sources.tar.xz"]))
        for name in (f"script.module.oriel.webkit-{v}.zip", "addons.xml"):
            checksum = hashlib.sha256((files / name).read_bytes()).hexdigest()
            self.assertEqual((files / f"{name}.sha256").read_text(), f"{checksum}  {name}\n")

    def test_legal_info_rejects_missing_licenses_and_sources(self):
        root = self.root
        # Distributed packages need their license texts; only copyleft ones also their source.
        legal = root / ".cache/legal"
        legal.mkdir(parents=True)
        with (legal / "manifest.csv").open("w") as stream:
            writer = csv.writer(stream)
            writer.writerow(["PACKAGE", "VERSION", "LICENSE", "LICENSE FILES", "SOURCE ARCHIVE", "SOURCE SITE"])
            for name, license in (("webkit", "LGPL-2.1+, BSD-2-Clause"), ("zlib", "Zlib"), ("bash", "GPL-3.0+")):
                writer.writerow([name, "1.0", license, "COPYING", f"{name}.tar.gz", "https://example.invalid"])
        for name in ("webkit", "zlib"):
            (legal / f"licenses/{name}-1.0").mkdir(parents=True)
            (legal / f"licenses/{name}-1.0/COPYING").write_text("license text")
        native_source = legal / "sources/webkit-1.0/webkit.tar.gz"
        native_source.parent.mkdir(parents=True)
        native_source.write_bytes(b"source")
        (legal / "README").write_text("WARNING: the Buildroot source code has not been saved\n")
        self.assertEqual(release.validate_legal(legal, {"webkit", "zlib"}), ({"webkit-1.0", "zlib-1.0"}, {"webkit-1.0"}))
        def refused(message, packages=("webkit", "zlib")):
            try:
                release.validate_legal(legal, set(packages))
            except SystemExit as error:
                self.assertIn(message, str(error), error)
            else:
                raise AssertionError(f"accepted despite {message}")
        refused("shipped packages missing from legal-info", ("webkit", "zlib", "mesa"))
        native_source.unlink()
        refused("missing redistributable source")
        native_source.write_bytes(b"source")
        license_file = legal / "licenses/zlib-1.0/COPYING"
        license_file.unlink()
        refused("missing license text")
        license_file.write_text("license text")
        manifest = legal / "manifest.csv"
        valid = manifest.read_text()
        manifest.write_text(valid.replace(",Zlib,", ",unknown,"))
        refused("unknown license")
        manifest.write_text(valid.replace("LGPL-2.1+, BSD-2-Clause", "MPL-2.0"))
        native_source.unlink()
        refused("missing redistributable source")
        native_source.write_bytes(b"source")
        manifest.write_text(valid)
        (legal / "README").write_text("WARNING: example: source not saved\n")
        refused("unresolved Buildroot")

    def test_shipped_packages_follow_buildroot_file_ownership(self):
        root = self.root
        buildroot = root / ".cache/buildroot-output"
        for name, path in (("webkit", "./usr/lib/libWPEWebKit.so.1"), ("zlib", "./lib/libz.so.1")):
            (buildroot / f"build/{name}-1.0").mkdir(parents=True)
            (buildroot / f"build/{name}-1.0/.files-list.txt").write_text(f"{name},{path}\n")
        (buildroot / "build/zlib-1.0/.files-list-staging.txt").write_text("zlib,./usr/include/zlib.h\n")
        overlay = root / ".cache/overlay"
        (overlay / "lib").mkdir(parents=True)
        for name in ("libWPEWebKit.so.1", "libz.so.1"):
            (overlay / "lib" / name).write_text(name)
        (overlay / "lib/libz.so").symlink_to("libz.so.1")
        (overlay / "lib/libgbm.so.1").symlink_to("libMali.so")
        self.assertEqual(release.shipped(buildroot, overlay), {"webkit", "zlib"})
        staging = root / ".cache/staging"
        (staging / "usr/include").mkdir(parents=True)
        (staging / "usr/include/zlib.h").write_text("header")
        self.assertEqual(release.shipped(buildroot, staging, ".files-list-staging.txt"), {"zlib"})
        (overlay / "lib/stray.so").write_text("stray")
        try:
            release.shipped(buildroot, overlay)
        except SystemExit as error:
            self.assertIn("no Buildroot package installed lib/stray.so", str(error))
        else:
            raise AssertionError("unowned overlay file accepted")
