import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="oriel-webkit-test-")
        self.addCleanup(temporary.cleanup)
        self.temporary = Path(temporary.name)
        self.root = self.temporary / "repo"
        self.root.mkdir()
        for name in ("addon", "tools", "build", "tests"):
            shutil.copytree(REPO / name, self.root / name, ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("LICENSE", ".gitignore", "README.md"):
            shutil.copy(REPO / name, self.root / name)
        self.bin = self.temporary / "bin"
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", TEST_ROOT=str(self.root))
        self.v = dict(line.split("=", 1) for line in (self.root / "build/versions.env").read_text().splitlines()
                      if line and not line.startswith("#"))["VERSION"]

    def executable(self, name, text):
        file = self.bin / name
        file.write_text(text)
        file.chmod(0o755)

    def command(self, *args, success=True, **env):
        result = subprocess.run(args, cwd=self.root, env=dict(self.env, **env), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result.stdout.strip() + result.stderr.strip()

    def commit(self, message):
        self.command("git", "add", ".")
        self.command("git", "commit", "-qm", message)

    def init_git(self):
        self.command("git", "init", "-q", "-b", "main")
        self.command("git", "config", "user.name", "Release test")
        self.command("git", "config", "user.email", "test@example.invalid")
        self.commit("Release inputs")
        origin = self.temporary / "origin.git"
        self.command("git", "init", "--bare", "-q", str(origin))
        self.command("git", "remote", "add", "origin", str(origin))

    def docker(self):
        self.executable("docker", '''#!/usr/bin/env python3
import os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
if args[0] == 'build': sys.exit(0)
env = dict(os.environ)
source = None
while args:
    arg = args.pop(0)
    if arg == '-v':
        host, target = args.pop(0).split(':', 1)
        if target == '/work': source = host
    elif arg in ('-e', '--user'):
        value = args.pop(0)
        if arg == '-e':
            key, value = value.split('=', 1)
            if key != 'HOME': env[key] = value
    elif arg == 'oriel-webkit-builder': break
# Docker mounts the checkout's cache into a release snapshot.
cache = Path(env.get('ORIEL_CACHE', str(Path(source) / '.cache')))
if Path(source) != Path(env['TEST_ROOT']):
    (Path(source) / '.cache').symlink_to(cache)
sys.exit(subprocess.run(args, cwd=source, env=env).returncode)
''')


def native_fixture(root):
    if os.environ.get("TEST_CHANGE_SOURCE"):
        checkout = Path(os.environ["TEST_ROOT"])
        (checkout / "README.md").write_text("changed after export")
        (checkout / "build/runtime.config").write_text("changed after export")
    versions = dict(line.split("=", 1) for line in (root / "build/versions.env").read_text().splitlines()
                    if line and not line.startswith("#"))
    cache = root / ".cache"
    with (cache / "stages").open("a") as stream:
        stream.write("build\n")
    runtime = cache / "runtime"
    shutil.rmtree(runtime, ignore_errors=True)
    addon = runtime / "script.module.oriel.webkit"
    shutil.copytree(root / "addon", addon)
    xml = addon / "addon.xml"
    xml.write_text(xml.read_text().replace("@VERSION@", versions["VERSION"]))
    for name, content in {"usr/lib/libexample.so.1": b"compiled library", "usr/libexec/WPEWebProcess": b"process"}.items():
        file = addon / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
    (addon / "usr/lib/libexample.so").symlink_to("libexample.so.1")
    dev = runtime / "dev/sysroot/usr"
    (dev / "include").mkdir(parents=True)
    (dev / "include/example.h").write_text("header")
    shutil.copytree(addon / "usr/lib", dev / "lib", symlinks=True)
    (runtime / "dev/provided.txt").write_text("libexample.so.1\n")
    shutil.copy(root / "build/box.env", runtime / "dev/box.env")
    (runtime / "buildroot.config").write_text((root / "build/runtime.config").read_text())
    output = cache / "build/tree/output"
    listing = output / "build/example-1.0"
    listing.mkdir(parents=True, exist_ok=True)
    (listing / ".files-list.txt").write_text("example,./usr/lib/libexample.so.1\nexample,./usr/libexec/WPEWebProcess\n")
    (listing / ".files-list-staging.txt").write_text("example,./usr/lib/libexample.so.1\nexample,./usr/include/example.h\n")
    wpe = output / f"build/wpewebkit-{versions['WPE_VERSION']}/Source/WebCore"
    wpe.mkdir(parents=True, exist_ok=True)
    (wpe / "LICENSE").write_text("WebKit license")
    legal = output / "legal-info"
    legal.mkdir(parents=True, exist_ok=True)
    with (legal / "manifest.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["PACKAGE", "VERSION", "LICENSE", "LICENSE FILES", "SOURCE ARCHIVE"])
        writer.writerow(["example", "1.0", "LGPL-2.1+", "COPYING", "example.tar.gz"])
    for name, content in {"licenses/example-1.0/COPYING": "library license", "sources/example-1.0/example.tar.gz": "library source", "README": ""}.items():
        file = legal / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)
    source = cache / "build/tree/source"
    source.mkdir(parents=True, exist_ok=True)
    (source / "Makefile").write_text('legal-info:\n\ttest -f "$(O)/legal-info/manifest.csv"\n')
    (cache / "downloads").mkdir(exist_ok=True)
    (cache / f"downloads/buildroot-{versions['BUILDROOT_VERSION']}.tar.xz").write_bytes(b"Buildroot source")
    if os.environ.get("TEST_PUBLISH"):
        state = Path(os.environ["TEST_GITHUB"]) / "state.json"
        data = json.loads(state.read_text())
        data["releases"][os.environ["TEST_PUBLISH"]] = False
        state.write_text(json.dumps(data))
