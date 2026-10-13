import shutil

from .repository import RepositoryTests


class CheckTests(RepositoryTests):
    def setUp(self):
        super().setUp()
        self.docker()
        self.executable("shellcheck", "#!/bin/sh\nexit 0\n")
        shutil.rmtree(self.root / "tests")
        (self.root / "tests").mkdir()
        (self.root / "tests/__init__.py").touch()
        (self.root / "tests/test_sentinel.py").write_text('''from pathlib import Path
import unittest
class Sentinel(unittest.TestCase):
    def test_discovery(self):
        Path('.cache/discovered').touch()
''')
        configure = self.root / "build/configure.sh"
        configure.write_text('''#!/bin/sh
set -eu
mkdir -p "$1/output"
printf '%s\\n' '# BR2_PACKAGE_BASH is not set' > "$1/output/.config"
''')
        self.cache = self.root / ".cache"
        (self.cache / "build/tree/output").mkdir(parents=True)
        (self.cache / "build/tree/output/compiled").write_bytes(b"expensive build")
        (self.cache / "runtime").mkdir()
        (self.cache / "runtime/installed").write_bytes(b"ready to deploy")

    def test_checks_discover_tests_and_preserve_existing_build_and_runtime(self):
        self.command("tools/check.sh")
        self.assertTrue((self.cache / "discovered").exists())
        self.assertEqual((self.cache / "build/tree/output/compiled").read_bytes(), b"expensive build")
        self.assertEqual((self.cache / "runtime/installed").read_bytes(), b"ready to deploy")
        self.assertEqual(list(self.cache.glob("check.*")), [])

    def test_discovered_failure_stops_checks(self):
        sentinel = self.root / "tests/test_sentinel.py"
        sentinel.write_text(sentinel.read_text() + '        self.fail("discovered failure")\n')
        self.assertIn("discovered failure", self.command("tools/check.sh", success=False))
        self.assertEqual((self.cache / "build/tree/output/compiled").read_bytes(), b"expensive build")

    def test_invalid_resolved_config_fails_and_cleans_temporary_tree(self):
        configure = self.root / "build/configure.sh"
        configure.write_text(configure.read_text().replace("# BR2_PACKAGE_BASH is not set", "BR2_PACKAGE_BASH=y"))
        self.assertIn("must not be enabled", self.command("tools/check.sh", success=False))
        self.assertEqual(list(self.cache.glob("check.*")), [])

    def test_build_and_check_share_a_lock(self):
        import fcntl
        with (self.cache / "build.lock").open("w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertIn("another local build or check", self.command("tools/check.sh", success=False))
        self.assertFalse((self.cache / "discovered").exists())
