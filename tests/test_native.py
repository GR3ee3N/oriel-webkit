from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from build import stage


class StageTests(unittest.TestCase):
    def test_runtime_excludes_box_libraries_and_tooling(self):
        self.assertEqual(stage.ignore("lib", ["libEGL.so.1", "libgbm.so.1", "libc.so.6", "libstdc++.so.6", "libWPEWebKit-2.0.so.1", "libglib-2.0.so.0"]), ["libEGL.so.1", "libgbm.so.1", "libc.so.6", "libstdc++.so.6"])
        self.assertEqual(stage.ignore("lib", ["libgallium-26.1.8.so", "locale", "aclocal", "fonts", "icu", "xsltConf.sh"]), ["libgallium-26.1.8.so", "locale", "aclocal", "icu", "xsltConf.sh"])
        self.assertEqual(stage.ignore("target/usr/share", ["fonts", "gtk-doc", "X11", "terminfo", "drirc.d"]), ["gtk-doc", "terminfo", "drirc.d"])

    def test_text_is_ignored_and_wrong_architecture_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            text = Path(temporary) / "text"
            text.write_text("not a binary")
            self.assertIs(stage.elf_info(text), None)
            # Reject an x86_64 ELF header even when the test itself runs on ARM64.
            wrong_arch = Path(temporary) / "x86_64.elf"
            wrong_arch.write_bytes(struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF\x02\x01\x01", 1, 62, 1, 0, 0, 0, 0, 64, 0, 0, 0, 0, 0))
            try:
                stage.elf_info(wrong_arch)
            except SystemExit as error:
                self.assertIn("not an ARM64 binary", str(error))
            else:
                raise AssertionError("x86_64 binary accepted into ARM64 runtime")

    def test_dev_sysroot_keeps_headers_and_shipped_library_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            sysroot = output / "host/aarch64-buildroot-linux-gnu/sysroot"
            listings = {"glib": ["usr/include/glib.h", "usr/lib/libglib-2.0.so.0", "usr/lib/libglib-2.0.so", "usr/lib/libglib-2.0.a",
                                 "usr/lib/pkgconfig/glib-2.0.pc", "usr/bin/glib-mkenums", "usr/share/doc/glib.txt"],
                        "glibc": ["usr/include/stdio.h", "usr/lib/libc.so.6"],
                        "mesa3d": ["usr/include/EGL/egl.h", "usr/lib/libEGL.so.1", "usr/lib/libgallium-26.1.8.so", "usr/lib/dri/swrast_dri.so"]}
            for package, paths in listings.items():
                (output / f"build/{package}-1.0").mkdir(parents=True)
                (output / f"build/{package}-1.0/.files-list-staging.txt").write_text("".join(f"{package},./{path}\n" for path in paths))
                for path in paths:
                    (sysroot / path).parent.mkdir(parents=True, exist_ok=True)
                    if path == "usr/lib/libglib-2.0.so":
                        (sysroot / path).symlink_to("libglib-2.0.so.0")
                    else:
                        (sysroot / path).write_text(path)
            # Only the add-on's libraries; no ELF files here, so nothing to strip.
            stage.dev(output, Path(temporary) / "dev", "false", {"libglib-2.0.so.0"})
            copied = sorted(file.relative_to(Path(temporary) / "dev").as_posix() for file in (Path(temporary) / "dev").rglob("*") if not file.is_dir())
            self.assertEqual(copied, ["usr/include/EGL/egl.h", "usr/include/glib.h", "usr/lib/libglib-2.0.so", "usr/lib/libglib-2.0.so.0", "usr/lib/pkgconfig/glib-2.0.pc"], copied)
            self.assertTrue((Path(temporary) / "dev/usr/lib/libglib-2.0.so").is_symlink())

    def test_symbol_requirements_respect_coreelec_limits(self):
        needs = "  0x0010:   Name: GLIBCXX_3.4.36  Flags: none  Version: 3\n  0x0020:   Name: GLIBC_PRIVATE  Flags: none  Version: 2\n"
        stage.require_versions("probe", needs)
        for name, required in (("GLIBC", "2.45"), ("GLIBCXX", "3.4.37"), ("CXXABI", "1.3.18"), ("GCC", "16.1")):
            try:
                stage.require_versions("probe", f"  0x0010:   Name: {name}_{required}  Flags: none  Version: 2\n")
            except SystemExit as error:
                self.assertIn(f"requires {name}_{required}", str(error))
            else:
                raise AssertionError(f"newer {name} requirement accepted")


def rejected(library, name):
    original = stage.BOX[name]
    stage.BOX[name] = "1.0"
    try:
        stage.elf_info(library)
    except SystemExit as error:
        return f"requires {name}_" in str(error)
    finally:
        stage.BOX[name] = original
    return False


class CompilerTests(unittest.TestCase):
    def test_elf_symbol_requirements_from_arm64_compiler(self):
        host = Path(".cache/build/tree/output/host/bin")
        if not all((host / f"aarch64-buildroot-linux-gnu-{compiler}").exists() for compiler in ("gcc", "g++")):
            self.skipTest("Buildroot toolchain is not built yet")
        with tempfile.TemporaryDirectory() as temporary:
            for compiler, suffix, code, library_name, name in (
                ("gcc", "c", '#define _GNU_SOURCE\n#include <sys/mman.h>\nint probe(void) { return memfd_create("oriel", 0); }\n', "libc.so.6", "GLIBC"),
                ("g++", "cpp", '#include <string>\nstd::string probe() { return std::string(64, \'o\'); }\n', "libstdc++.so.6", "GLIBCXX"),
            ):
                source, library = Path(temporary) / f"probe.{suffix}", Path(temporary) / f"probe-{suffix}.so"
                source.write_text(code)
                subprocess.run([str(host / f"aarch64-buildroot-linux-gnu-{compiler}"), "-shared", "-fPIC", str(source), "-o", str(library)], check=True)
                self.assertIn(library_name, stage.elf_info(library))
                self.assertTrue(rejected(library, name), f"newer {name} requirement accepted")

    def test_pruning_keeps_only_libraries_reached_from_runtime_processes(self):
        with tempfile.TemporaryDirectory() as temporary:
            gcc = "gcc"
            out = Path(temporary) / "prune"
            (out / "lib").mkdir(parents=True)
            (out / "libexec").mkdir()
            for name in ("used", "unused"):
                (Path(temporary) / f"{name}.c").write_text(f"int {name}(void) {{ return 1; }}\n")
                subprocess.run([gcc, "-shared", "-fPIC", f"-Wl,-soname,lib{name}.so.1", str(Path(temporary) / f"{name}.c"), "-o", str(out / f"lib/lib{name}.so.1.0")], check=True)
                (out / f"lib/lib{name}.so.1").symlink_to(f"lib{name}.so.1.0")
                (out / f"lib/lib{name}.so").symlink_to(f"lib{name}.so.1")
            (Path(temporary) / "main.c").write_text("int used(void);\nint main(void) { return used(); }\n")
            subprocess.run([gcc, str(Path(temporary) / "main.c"), "-L", str(out / "lib"), "-lused", "-o", str(out / "libexec/process")], check=True)
            stage.prune(out)
            self.assertEqual(sorted(file.name for file in (out / "lib").iterdir()), ["libused.so", "libused.so.1", "libused.so.1.0"])
