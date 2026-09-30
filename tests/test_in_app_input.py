"""Games whose player input is imported in the app (no --disc at build time)."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

from padmint.cli import execute, validate
from fixtures import entries, write_ipa

MANIFEST = {
    "schema_version": 1, "id": "maskpad", "name": "Synthetic", "game": "Synthetic",
    "kind": "decomp-patches", "status": "experimental",
    "inputs": [{"type": "n64-rom", "when": "in-app"}],
    "targets": {"ios": {"hosts": {"macos-arm64": "experimental"},
                        "command": ["/bin/bash", "{repo}/scripts/build-personal-ipa.sh",
                                    "--work", "{work}", "--output", "{output}"],
                        "output": "ipa", "check": "ipa"}},
    "publication": {"public_binaries": False},
}


class InAppInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="padmint in-app ")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.repo = root / "backend"
        (self.repo / "scripts").mkdir(parents=True)
        ipa = root / "synthetic.ipa"
        members = entries()
        members.pop("KartPadBuilderProvenance.json")
        write_ipa(ipa, members)
        (self.repo / ".gitignore").write_text("build/\n")
        (self.repo / "padmint.json").write_text(json.dumps(MANIFEST))
        (self.repo / "scripts/build-personal-ipa.sh").write_text(
            'while [ $# -gt 0 ]; do if [ "$1" = --output ]; then cp %s "$2"; exit 0; fi; shift; done; exit 2\n'
            % shlex.quote(str(ipa)))
        for command in (["init", "-q"], ["config", "user.email", "t@example.invalid"],
                        ["config", "user.name", "T"], ["add", "."], ["commit", "-qm", "synthetic"]):
            subprocess.run(["git", "-C", str(self.repo), *command], check=True)
        revision = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        self.args = argparse.Namespace(game="maskpad", repo=self.repo, disc=None, revision=revision,
                                       source_only=False, no_mods=False, jobs=2)
        self.disc_path = root / "rom.z64"

    def test_build_without_disc_records_generic_check_and_gate(self):
        repo, disc = validate(self.args)
        self.assertIsNone(disc)
        self.assertEqual(execute(self.args, repo, disc), 0)
        record = json.loads(next((self.repo / "build/padmint").glob("*/runs/*/record.json")).read_text())
        self.assertIsNone(record["disc_sha256"])
        self.assertEqual(record["package_validation"]["check"], "minimal-ipa-structure")
        self.assertEqual(record["publication_gate"]["label"], "personal build, not publishable")

    def test_disc_is_refused_when_game_reads_nothing_at_build_time(self):
        self.disc_path.write_bytes(b"synthetic")
        self.args.disc = self.disc_path
        with self.assertRaisesRegex(ValueError, "import them in the app"):
            validate(self.args)


if __name__ == "__main__":
    unittest.main()

