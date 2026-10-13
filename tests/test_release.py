import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

from .repository import RepositoryTests


def fake_gh(args):
    store = Path(os.environ["TEST_GITHUB"])
    state = store / "state.json"
    data = json.loads(state.read_text())
    action, tag = args[1:3]
    directory = store / tag
    if action == "view":
        if tag not in data["releases"]:
            sys.exit(1)
        print(str(data["releases"][tag]).lower())
    elif action == "delete":
        shutil.rmtree(directory)
        del data["releases"][tag]
        if "--cleanup-tag" in args:
            subprocess.run(["git", "push", "-q", "origin", f":refs/tags/{tag}"], check=True)
    elif action == "create":
        # Interrupted uploads leave the draft in place.
        directory.mkdir()
        data["releases"][tag] = "--draft" in args
        state.write_text(json.dumps(data))
        for file in (Path(arg) for arg in args[3:] if not arg.startswith("-") and Path(arg).is_file()):
            if data.get("fail_upload") == file.name:
                sys.exit(1)
            shutil.copyfile(file, directory / file.name)
        data["created"] = data.get("created", 0) + 1
    else:
        raise AssertionError(args)
    state.write_text(json.dumps(data))


class ReleaseTests(RepositoryTests):
    def setUp(self):
        super().setUp()
        self.docker()
        self.executable("gh", '''#!/usr/bin/env python3
import os,sys
sys.path.insert(0,os.environ['TEST_ROOT'])
from tests.test_release import fake_gh
fake_gh(sys.argv[1:])
''')
        (self.root / "build/check.sh").write_text('''#!/bin/sh
set -eu
printf 'check\\n' >> .cache/stages
[ "${TEST_FAIL_CHECK:-}" != 1 ]
''')
        (self.root / "build/compile.sh").write_text('''#!/bin/sh
set -eu
python3 -c 'from pathlib import Path; from tests.repository import native_fixture; native_fixture(Path.cwd())'
[ "${TEST_FAIL_BUILD:-}" != 1 ]
''')
        self.github = self.temporary / "github"
        self.github.mkdir()
        self.state = self.github / "state.json"
        self.state.write_text(json.dumps({"releases": {}}))
        self.env["TEST_GITHUB"] = str(self.github)
        self.tag = f"v{self.v}"
        self.init_git()

    def release(self, success=True, **env):
        return self.command("tools/release.sh", "Release notes", success=success, **env)

    def data(self):
        return json.loads(self.state.read_text())

    def update(self, **changes):
        data = self.data()
        data.update(changes)
        self.state.write_text(json.dumps(data))

    def test_draft_contains_artifacts_and_source_from_the_tagged_commit(self):
        self.release()
        self.assertEqual(self.data()["releases"], {self.tag: True})
        head = self.command("git", "rev-parse", "HEAD")
        self.assertIn(head, self.command("git", "ls-remote", "origin", f"refs/tags/{self.tag}^{{}}"))
        self.assertEqual((self.root / ".cache/stages").read_text().splitlines(), ["check", "build"])
        files = self.root / ".cache/release/files"
        self.assertEqual(sorted(p.name for p in (self.github / self.tag).iterdir()), sorted(p.name for p in files.iterdir()))
        for file in files.iterdir():
            self.assertEqual((self.github / self.tag / file.name).read_bytes(), file.read_bytes())
        with tarfile.open(files / f"oriel-webkit-{self.v}-sources.tar.xz") as archive:
            prefix = f"oriel-webkit-{self.v}-sources"
            self.assertEqual(archive.extractfile(f"{prefix}/COMMIT").read().decode().strip(), head)
            self.assertEqual(archive.extractfile(f"{prefix}/oriel-webkit/README.md").read(), (self.root / "README.md").read_bytes())
            self.assertEqual(archive.extractfile(f"{prefix}/buildroot.config").read(), (self.root / "build/runtime.config").read_bytes())
            self.assertEqual(archive.extractfile(f"{prefix}/legal-info/sources/example-1.0/example.tar.gz").read(), b"library source")
            self.assertEqual(archive.extractfile(f"{prefix}/licenses/example-1.0/COPYING").read(), b"library license")

    def test_dirty_tree_is_refused_before_build(self):
        (self.root / "CHANGES").write_text("uncommitted")
        self.assertIn("not clean", self.release(success=False))
        self.assertEqual(self.data()["releases"], {})
        self.assertFalse((self.root / ".cache/stages").exists())

    def test_failed_checks_preserve_the_previous_draft_and_skip_compilation(self):
        self.release()
        head = self.command("git", "rev-parse", "HEAD")
        (self.root / "README.md").write_text("fix")
        self.commit("Fix")
        (self.root / ".cache/stages").unlink()
        self.release(success=False, TEST_FAIL_CHECK="1")
        self.assertEqual((self.root / ".cache/stages").read_text().splitlines(), ["check"])
        self.assertEqual(self.data()["created"], 1)
        self.assertIn(head, self.command("git", "ls-remote", "origin", f"refs/tags/{self.tag}^{{}}"))

    def test_failed_compilation_never_tags_or_uploads(self):
        self.release(success=False, TEST_FAIL_BUILD="1")
        self.assertEqual(self.data()["releases"], {})
        self.assertEqual(self.command("git", "tag"), "")
        self.assertFalse((self.root / ".cache/release").exists())

    def test_changes_during_build_do_not_enter_exported_source_or_get_uploaded(self):
        original = (self.root / "README.md").read_bytes()
        config = (self.root / "build/runtime.config").read_bytes()
        self.assertIn("source changed", self.release(success=False, TEST_CHANGE_SOURCE="1"))
        self.assertEqual(self.data()["releases"], {})
        with tarfile.open(self.root / f".cache/release/files/oriel-webkit-{self.v}-sources.tar.xz") as archive:
            self.assertEqual(archive.extractfile(f"oriel-webkit-{self.v}-sources/oriel-webkit/README.md").read(), original)
            self.assertEqual(archive.extractfile(f"oriel-webkit-{self.v}-sources/buildroot.config").read(), config)

    def test_interrupted_upload_can_be_retried(self):
        self.update(fail_upload=f"oriel-webkit-{self.v}-dev.tar.xz")
        self.release(success=False)
        self.assertEqual(self.data()["releases"], {self.tag: True})
        self.update(fail_upload=None)
        self.release()
        self.assertEqual(self.data()["releases"], {self.tag: True})
        self.assertEqual(sorted(p.name for p in (self.github / self.tag).iterdir()),
                         sorted(p.name for p in (self.root / ".cache/release/files").iterdir()))

    def test_new_commit_replaces_draft_but_not_a_published_release(self):
        self.release()
        (self.root / "README.md").write_text("fix")
        self.commit("Fix")
        self.release()
        head = self.command("git", "rev-parse", "HEAD")
        self.assertIn(head, self.command("git", "ls-remote", "origin", f"refs/tags/{self.tag}^{{}}"))
        self.update(releases={self.tag: False})
        self.assertIn("already released", self.release())
        self.assertEqual(self.data()["created"], 2)
        (self.root / "README.md").write_text("new code")
        self.commit("Change")
        self.assertIn("bump VERSION", self.release(success=False))

    def test_version_bump_can_release_after_a_published_version(self):
        self.release()
        self.update(releases={self.tag: False})
        versions = self.root / "build/versions.env"
        versions.write_text(versions.read_text().replace(f"\nVERSION={self.v}", "\nVERSION=1.99.0"))
        self.commit("Bump version")
        self.release()
        self.assertEqual(self.data()["releases"], {self.tag: False, "v1.99.0": True})

    def test_draft_published_during_build_is_preserved(self):
        self.release()
        head = self.command("git", "rev-parse", "HEAD")
        (self.root / "README.md").write_text("new code")
        self.commit("Change")
        self.assertIn("no longer a draft", self.release(success=False, TEST_PUBLISH=self.tag))
        self.assertEqual(self.data()["releases"], {self.tag: False})
        self.assertEqual(self.data()["created"], 1)
        self.assertIn(head, self.command("git", "ls-remote", "origin", f"refs/tags/{self.tag}^{{}}"))

    def test_concurrent_release_is_refused(self):
        import fcntl
        lock = self.root / ".cache/release.lock"
        lock.parent.mkdir()
        with lock.open("w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertIn("another release", self.release(success=False))
        self.assertEqual(self.data()["releases"], {})
