"""Manifests that list a game's existing scripts as ordered steps."""
import argparse
import io
from contextlib import redirect_stdout
import copy
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

from padmint.cli import execute, validate
from padmint.manifest import validate_manifest
from fixtures import entries, write_ipa

STEPS = {
    "schema_version": 1, "id": "starshippad", "name": "Synthetic", "game": "Synthetic",
    "kind": "decomp-patches", "status": "draft-untested",
    "inputs": [{"type": "n64-rom", "when": "in-app"}],
    "targets": {"ios": {"hosts": {"macos-arm64": "experimental"}, "output": "ipa", "check": "ipa",
                        "steps": [
                            {"stage": "dependencies", "command": ["/bin/bash", "{repo}/scripts/fetch.sh"]},
                            {"stage": "package", "command": ["/bin/bash", "{repo}/scripts/package.sh", "{output}"]}]}},
    "publication": {"public_binaries": False},
}


class StepsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="padmint steps ")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.repo = root / "backend"
        (self.repo / "scripts").mkdir(parents=True)
        ipa = root / "synthetic.ipa"
        members = entries()
        members.pop("KartPadBuilderProvenance.json")
        write_ipa(ipa, members)
        self.marker = root / "fetched"
        (self.repo / ".gitignore").write_text("build/\n")
        (self.repo / "scripts/fetch.sh").write_text("touch %s\n" % shlex.quote(str(self.marker)))
        (self.repo / "scripts/package.sh").write_text("test -f %s && cp %s \"$1\"\n"
                                                      % (shlex.quote(str(self.marker)), shlex.quote(str(ipa))))
        self.commit(STEPS)

    def commit(self, manifest):
        (self.repo / "padmint.json").write_text(json.dumps(manifest))
        if not (self.repo / ".git").exists():
            for command in (["init", "-q"], ["config", "user.email", "t@example.invalid"], ["config", "user.name", "T"]):
                subprocess.run(["git", "-C", str(self.repo), *command], check=True)
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "synthetic"], check=True)
        revision = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        self.args = argparse.Namespace(game="starshippad", repo=self.repo, disc=None, revision=revision,
                                       source_only=False, no_mods=False, jobs=2)

    def records(self):
        path = next((self.repo / "build/padmint").glob("*/runs/*/record.json"))
        events = [json.loads(line) for line in (path.parent / "progress.jsonl").read_text().splitlines()]
        return json.loads(path.read_text()), [(e["backend"]["event"], e["backend"]["stage"])
                                               for e in events if e["event"] == "backend_event"]

    def test_a_second_build_shows_time_left_from_the_first(self):
        repo, disc = validate(self.args)
        first, second = io.StringIO(), io.StringIO()
        with redirect_stdout(first):
            self.assertEqual(execute(self.args, repo, disc), 0)
        with redirect_stdout(second):
            self.assertEqual(execute(self.args, repo, disc), 0)
        self.assertNotIn("from your last build", first.getvalue())
        self.assertIn("less than a minute left (from your last build)", second.getvalue())
        self.assertEqual(second.getvalue().count("from your last build"), 2)  # once per stage

    def test_steps_run_in_order_with_stage_events(self):
        repo, disc = validate(self.args)
        self.assertEqual(execute(self.args, repo, disc), 0)
        record, stages = self.records()
        self.assertEqual(record["status"], "completed")
        self.assertEqual(stages, [("stage_started", "dependencies"), ("stage_completed", "dependencies"),
                                  ("stage_started", "package"), ("stage_completed", "package")])

    def test_failed_step_stops_the_build(self):
        (self.repo / "scripts/fetch.sh").write_text("exit 7\n")
        self.commit(STEPS)
        repo, disc = validate(self.args)
        self.assertEqual(execute(self.args, repo, disc), 7)
        record, stages = self.records()
        self.assertEqual(record["status"], "failed")
        self.assertEqual(stages, [("stage_started", "dependencies"), ("stage_failed", "dependencies")])

    def test_missing_step_script_and_invalid_steps_are_rejected(self):
        broken = copy.deepcopy(STEPS)
        broken["targets"]["ios"]["steps"][1]["command"][1] = "{repo}/scripts/missing.sh"
        self.commit(broken)
        with self.assertRaisesRegex(ValueError, "scripts/missing.sh"):
            validate(self.args)
        duplicate = copy.deepcopy(STEPS)
        duplicate["targets"]["ios"]["steps"][1]["stage"] = "dependencies"
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_manifest(duplicate)
        both = copy.deepcopy(STEPS)
        both["targets"]["ios"]["command"] = ["/bin/true"]
        with self.assertRaisesRegex(ValueError, "not both"):
            validate_manifest(both)

    def test_step_environment_receives_placeholders(self):
        manifest = copy.deepcopy(STEPS)
        manifest["targets"]["ios"]["steps"][1] = {
            "stage": "package", "command": ["/bin/bash", "{repo}/scripts/package-env.sh"],
            "env": {"SYNTHETIC_OUTPUT": "{output}"}}
        source = shlex.quote(str(Path(self.temp.name).resolve() / "synthetic.ipa"))
        (self.repo / "scripts/package-env.sh").write_text(f'cp {source} "$SYNTHETIC_OUTPUT"\n')
        self.commit(manifest)
        repo, disc = validate(self.args)
        self.assertEqual(execute(self.args, repo, disc), 0)
        record, _stages = self.records()
        self.assertEqual(record["status"], "completed")
        bad = copy.deepcopy(manifest)
        bad["targets"]["ios"]["steps"][1]["env"] = {"lower": "x"}
        with self.assertRaisesRegex(ValueError, "UPPER_CASE"):
            validate_manifest(bad)

    def test_steps_receive_the_job_cap(self):
        seen = Path(self.temp.name).resolve() / "jobs"
        (self.repo / "scripts/fetch.sh").write_text(
            'printf %%s "$CMAKE_BUILD_PARALLEL_LEVEL" > %s\ntouch %s\n'
            % (shlex.quote(str(seen)), shlex.quote(str(self.marker))))
        self.commit(STEPS)
        repo, disc = validate(self.args)
        self.assertEqual(execute(self.args, repo, disc), 0)
        self.assertEqual(seen.read_text(), "2")

    def test_build_record_carries_the_game_version(self):
        (self.repo / "version.json").write_text('{"version": "0.6.0", "build": 240}\n')
        self.commit(STEPS)
        repo, disc = validate(self.args)
        self.assertEqual(execute(self.args, repo, disc), 0)
        record, _stages = self.records()
        self.assertEqual(record["game_version"], {"version": "0.6.0", "build": 240})

    def test_history_summarizes_records(self):
        repo, disc = validate(self.args)
        self.assertEqual(execute(self.args, repo, disc), 0)
        from padmint.cli import history
        import io
        stream = io.StringIO()
        self.assertEqual(history(self.repo, stream), 0)
        self.assertIn("completed", stream.getvalue())
        self.assertIn("starshippad", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
