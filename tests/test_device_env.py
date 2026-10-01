"""Apple's /usr/bin/python3 (what PadMint.command runs) exports the Mac SDK as SDKROOT and
/usr/local as CPATH and LIBRARY_PATH. iPhone builds must not inherit them (MaskPad linked
iPhone code against the Mac's libz); Mac and Android builds keep today's environment."""
import argparse
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest import mock

from fixtures import entries, write_ipa
from padmint.cli import execute, validate

MAC_SDK = "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"
SHIM = {"SDKROOT": MAC_SDK, "CPATH": "/usr/local/include", "LIBRARY_PATH": "/usr/local/lib"}


class DeviceEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="padmint env ")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.repo = root / "backend"
        (self.repo / "scripts").mkdir(parents=True)
        self.seen = root / "env.txt"
        (self.repo / ".gitignore").write_text("build/\n")
        # The fake backend records its environment, then copies a synthetic package.
        fixture = self.repo / "fixture.ipa"
        write_ipa(fixture, entries())
        (self.repo / "scripts/build.sh").write_text("env > %s\ncp %s \"$1\"\n" % (shlex.quote(str(self.seen)), shlex.quote(str(fixture))))
        for command in (["init", "-q"], ["config", "user.email", "t@example.invalid"], ["config", "user.name", "T"]):
            subprocess.run(["git", "-C", str(self.repo), *command], check=True)

    def build(self, target, steps=True):
        command = ["/bin/bash", "{repo}/scripts/build.sh", "{output}"]
        declared = {"hosts": {"macos-arm64": "experimental", "linux-x86_64": "experimental"},
                    "output": "ipa", "check": "none"}
        declared.update({"steps": [{"stage": "build", "command": command}]} if steps else {"command": command})
        manifest = {"schema_version": 1, "id": "maskpad", "name": "Synthetic", "game": "Synthetic",
                    "kind": "decomp-patches", "status": "draft-untested",
                    "inputs": [{"type": "n64-rom", "when": "in-app"}], "targets": {target: declared},
                    "publication": {"public_binaries": False}}
        (self.repo / "padmint.json").write_text(json.dumps(manifest))
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "synthetic", "--allow-empty"], check=True)
        revision = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        args = argparse.Namespace(game="maskpad", repo=self.repo, disc=None, revision=revision, target=target,
                                  source_only=False, no_mods=False, jobs=2)
        out = io.StringIO()
        with mock.patch.dict(os.environ, SHIM), redirect_stdout(out):
            repo, disc = validate(args)
            self.assertEqual(execute(args, repo, disc), 0)
        log = next((self.repo / "build/padmint").glob("*/runs/*/backend.log")).read_text()
        env = dict(line.split("=", 1) for line in self.seen.read_text().splitlines() if "=" in line)
        return env, out.getvalue(), log

    def test_an_iphone_build_does_not_inherit_the_macs_sdk_or_libraries(self):
        for steps in (True, False):
            env, printed, log = self.build("ios", steps)
            for key in SHIM:
                self.assertNotIn(key, env)
            self.assertEqual(env["PATH"], os.environ["PATH"])
            note = "PadMint ignores SDKROOT, CPATH, LIBRARY_PATH for iPhone builds"
            self.assertIn(note, printed)
            self.assertIn(note, log)
            for stale in (self.repo / "build/padmint").glob("*/runs/*"):
                for item in stale.iterdir():
                    item.unlink()
                stale.rmdir()

    def test_mac_and_android_builds_keep_their_environment(self):
        for target in ("macos", "android"):
            env, printed, log = self.build(target)
            self.assertEqual({key: env.get(key) for key in SHIM}, SHIM)
            self.assertNotIn("PadMint ignores", printed + log)

    def test_nothing_to_say_when_nothing_was_set(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in SHIM:
                os.environ.pop(key, None)
            self.assertEqual(__import__("padmint.cli", fromlist=["x"]).inherited_env("ios")[1], [])


if __name__ == "__main__":
    unittest.main()
