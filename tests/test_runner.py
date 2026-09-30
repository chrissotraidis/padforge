import argparse
import json
import os
from pathlib import Path
import signal
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from padmint.cli import command, digest, execute, run_process, validate, workspace_lock
from fixtures import entries, write_ipa


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="padmint test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "backend"
        self.repo.mkdir()
        self.disc = self.root / "own disc $(do not execute).iso"
        self.disc.write_bytes(b"synthetic input, not game data")
        self.ipa = self.root / "synthetic.ipa"
        write_ipa(self.ipa, entries())
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        (self.repo / ".gitignore").write_text("build/\n")
        script = self.repo / "scripts/build-user-ipa.sh"
        script.parent.mkdir()
        script.write_text('''#!/bin/bash
while [ $# -gt 0 ]; do
  if [ "$1" = "--output" ]; then cp FIXTURE "$2"; exit 0; fi
  shift
done
exit 2
'''.replace("FIXTURE", shlex.quote(str(self.ipa))))
        self.git("add", ".")
        self.git("commit", "-qm", "Synthetic test backend")
        self.args = argparse.Namespace(game="kartpad", repo=self.repo, disc=self.disc,
            revision=self.git("rev-parse", "HEAD"), source_only=False, no_mods=False, jobs=2)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True).strip()

    def test_explicit_pin_and_clean_checkout(self):
        self.assertEqual(validate(self.args), (self.repo, self.disc))
        self.args.revision = "0" * 40
        with self.assertRaisesRegex(ValueError, "HEAD"):
            validate(self.args)
        self.args.revision = self.git("rev-parse", "HEAD")
        (self.repo / "extra.py").write_text("unreviewed")
        with self.assertRaisesRegex(ValueError, "local changes"):
            validate(self.args)

    def test_argument_paths_are_not_shell_strings(self):
        argv = command(self.args, self.repo, self.disc, self.root, self.root / "test.ipa")
        self.assertEqual(argv[3], str(self.disc))
        self.assertIn("--work-root", argv)

    def test_bluewake_requires_local_training(self):
        self.args.game = "bluewake"
        argv = command(self.args, self.repo, self.disc, self.root, self.root / "test.ipa")
        self.assertIn("--train-pgo", argv)
        self.assertNotIn("--install", argv)
        self.args.source_only = True
        argv = command(self.args, self.repo, self.disc, self.root, self.root / "test.ipa")
        self.assertIn("--source-only", argv)
        self.assertNotIn("--ipa", argv)

    def test_kartpad_rejects_unsupported_options(self):
        self.args.no_mods = True
        with self.assertRaisesRegex(ValueError, "mod selection"):
            validate(self.args)

    def test_lock_rejects_second_writer_and_releases(self):
        path = self.root / "lock"
        with workspace_lock(path):
            with self.assertRaisesRegex(ValueError, "Another"):
                with workspace_lock(path):
                    self.fail("second writer acquired lock")
        with workspace_lock(path):
            pass

    def test_execute_records_hash_and_reuses_configuration(self):
        for _ in range(2):
            self.assertEqual(execute(self.args, self.repo, self.disc), 0)
        root = self.repo / "build/padmint"
        self.assertEqual(len(list(root.glob("*/backend"))), 0)  # fake backend needs no cache
        records = list(root.glob("*/runs/*/record.json"))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].parents[2], records[1].parents[2])
        for path in records:
            data = json.loads(path.read_text())
            self.assertEqual(data["status"], "completed")
            self.assertEqual(len(data["output_sha256"]), 64)
            self.assertNotIn(str(self.root), path.read_text())

    def test_success_without_output_fails(self):
        (self.repo / "scripts/build-user-ipa.sh").write_text("exit 0\n")
        self.git("commit", "-qam", "Backend returns no output")
        self.args.revision = self.git("rev-parse", "HEAD")
        self.assertEqual(execute(self.args, self.repo, self.disc), 1)
        record = next((self.repo / "build/padmint").glob("*/runs/*/record.json"))
        self.assertEqual(json.loads(record.read_text())["status"], "failed")

    def test_changed_jobs_reuses_workspace_but_preserves_attempt_options(self):
        for jobs in (2, 8):
            self.args.jobs = jobs
            self.assertEqual(execute(self.args, self.repo, self.disc), 0)
        records = list((self.repo / "build/padmint").glob("*/runs/*/record.json"))
        data = [json.loads(path.read_text()) for path in records]
        self.assertEqual({item["jobs"] for item in data}, {2, 8})
        self.assertEqual(len({item["workspace_key"] for item in data}), 1)
        self.assertEqual(len({path.parents[2] for path in records}), 1)

    def test_source_preflight_then_full_build_reuses_backend_outputs(self):
        self.args.game = "bluewake"
        script = self.repo / "scripts/builder/build.sh"
        script.parent.mkdir()
        script.write_text('''#!/bin/bash
set -eu
out=""; ipa=""; source_only=0
while [ $# -gt 0 ]; do
  case "$1" in
    --out) out=$2; shift 2;;
    --ipa) ipa=$2; shift 2;;
    --source-only) source_only=1; shift;;
    *) shift;;
  esac
done
mkdir -p "$out"
if [ "$source_only" = 1 ]; then
  printf 'synthetic prepared source' > "$out/source-ready"
else
  test -f "$out/source-ready" || exit 9
  cp FIXTURE "$ipa"
fi
'''.replace("FIXTURE", shlex.quote(str(self.ipa))))
        self.git("add", "scripts/builder/build.sh")
        self.git("commit", "-qm", "Synthetic two-step backend")
        self.args.revision = self.git("rev-parse", "HEAD")
        write_ipa(self.ipa, entries("bluewake", revision=self.args.revision))
        for source_only in (True, False):
            self.args.source_only = source_only
            self.assertEqual(execute(self.args, self.repo, self.disc), 0)
        records = list((self.repo / "build/padmint").glob("*/runs/*/record.json"))
        data = [json.loads(path.read_text()) for path in records]
        self.assertEqual({item["source_only"] for item in data}, {True, False})
        self.assertEqual(len({item["workspace_key"] for item in data}), 1)
        self.assertEqual(len({path.parents[2] for path in records}), 1)
        self.assertEqual(sum("package_validation" in item for item in data), 1)

    def test_new_revision_stays_isolated_even_for_docs_only_change(self):
        self.assertEqual(execute(self.args, self.repo, self.disc), 0)
        (self.repo / "README.md").write_text("Documentation-only revision")
        self.git("add", "README.md")
        self.git("commit", "-qm", "Docs update")
        self.args.revision = self.git("rev-parse", "HEAD")
        self.assertEqual(execute(self.args, self.repo, self.disc), 0)
        records = list((self.repo / "build/padmint").glob("*/runs/*/record.json"))
        self.assertEqual(len({path.parents[2] for path in records}), 2)

    def test_custom_workspace_stays_ignored_and_uses_shared_lock(self):
        self.args.workspace_root = self.repo / "build/separate-check"
        self.assertEqual(execute(self.args, self.repo, self.disc), 0)
        self.assertEqual(len(list(self.args.workspace_root.glob("*/runs/*/record.json"))), 1)
        with workspace_lock(self.repo / "build/padmint/runner.lock"):
            with self.assertRaisesRegex(ValueError, "Another"):
                execute(self.args, self.repo, self.disc)
        self.args.workspace_root = self.root / "outside"
        with self.assertRaisesRegex(ValueError, "below"):
            execute(self.args, self.repo, self.disc)

    def test_mutation_during_disc_hash_prevents_launch(self):
        original = self.repo / "scripts/build-user-ipa.sh"
        def mutate(path):
            value = digest(path)
            original.write_text(original.read_text() + "\n# unreviewed edit\n")
            return value
        with patch("padmint.cli.digest", side_effect=mutate):
            self.assertEqual(execute(self.args, self.repo, self.disc), 1)
        record_path = next((self.repo / "build/padmint").glob("*/runs/*/record.json"))
        record = json.loads(record_path.read_text())
        self.assertEqual(record["checkout_check"], "before-launch-failed")
        self.assertFalse((record_path.parent / "personal.ipa").exists())

    def test_mutation_during_backend_run_rejects_output(self):
        script = self.repo / "scripts/build-user-ipa.sh"
        script.write_text("printf '\\n# changed while running\\n' >> \"$0\"\n" + script.read_text())
        self.git("commit", "-qam", "Self-mutating synthetic backend")
        self.args.revision = self.git("rev-parse", "HEAD")
        self.assertEqual(execute(self.args, self.repo, self.disc), 1)
        record_path = next((self.repo / "build/padmint").glob("*/runs/*/record.json"))
        record = json.loads(record_path.read_text())
        self.assertEqual(record["checkout_check"], "after-exit-failed")
        self.assertEqual(record["status"], "failed")
        self.assertTrue((record_path.parent / "personal.ipa").exists())
        self.assertNotIn("output_sha256", record)

    def test_plain_text_ipa_is_rejected(self):
        self.ipa.write_text("not a ZIP package")
        self.assertEqual(execute(self.args, self.repo, self.disc), 1)
        record = next((self.repo / "build/padmint").glob("*/runs/*/record.json"))
        self.assertEqual(json.loads(record.read_text())["status"], "failed")

    def test_events_skip_old_and_survive_partial_lines(self):
        events = self.root / "progress.jsonl"
        events.write_text('{"schema_version":1,"stage":"old"}\n')
        script = "import sys,time; f=open(sys.argv[1],'a'); f.write('{\"schema_version\":1,'); f.flush(); time.sleep(.3); f.write('\"stage\":\"new\"}\\ninvalid\\n'); f.close()"
        seen = []
        code, cancelled = run_process([sys.executable, "-c", script, str(events)], self.root,
                                      self.root / "out.log", events,
                                      lambda event, **kw: seen.append((event, kw)))
        self.assertEqual((code, cancelled), (0, False))
        self.assertEqual(seen[0][1]["backend"]["stage"], "new")
        self.assertEqual(seen[1][0], "progress_warning")

    def test_exit_drains_all_complete_events(self):
        for exit_code in (0, 7):
            with self.subTest(exit_code=exit_code):
                events = self.root / f"burst-{exit_code}.jsonl"
                script = (
                    "import json,sys; "
                    "f=open(sys.argv[1],'w'); "
                    "f.writelines(json.dumps(dict(schema_version=1, event='stage_progress', "
                    "sequence=i))+'\\n' for i in range(5000)); "
                    "f.write(json.dumps(dict(schema_version=1, event='build_completed' "
                    "if int(sys.argv[2]) == 0 else 'build_failed'))+'\\n'); "
                    "f.close(); sys.exit(int(sys.argv[2]))"
                )
                seen = []
                result = run_process([sys.executable, "-c", script, str(events), str(exit_code)],
                                     self.root, self.root / "burst.log", events,
                                     lambda event, **kw: seen.append(kw["backend"]))
                self.assertEqual(result, (exit_code, False))
                self.assertEqual(len(seen), 5001)
                self.assertEqual([item["sequence"] for item in seen[:-1]], list(range(5000)))
                self.assertEqual(seen[-1]["event"],
                                 "build_completed" if exit_code == 0 else "build_failed")

    def test_failed_backend_exit_preserved(self):
        result = run_process([sys.executable, "-c", "raise SystemExit(7)"], self.root,
                             self.root / "out.log", self.root / "events",
                             lambda *a, **kw: None)
        self.assertEqual(result, (7, False))

    def test_cancel_reaches_child(self):
        marker = self.root / "cancelled"
        ready = self.root / "ready"
        events = self.root / "events"
        script = """
import json, signal, time, pathlib, sys
def stop(*args):
    with open(sys.argv[3], 'w') as stream:
        for i in range(5000):
            stream.write(json.dumps(dict(schema_version=1, sequence=i)) + '\\n')
        stream.write(json.dumps(dict(schema_version=1, event='build_cancelled')) + '\\n')
    pathlib.Path(sys.argv[1]).write_text('stopped')
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
pathlib.Path(sys.argv[2]).touch()
time.sleep(30)
"""
        def cancel():
            import time
            for _ in range(100):
                if ready.exists():
                    os.kill(os.getpid(), signal.SIGINT)
                    return
                time.sleep(.02)
        thread = threading.Thread(target=cancel)
        thread.start()
        seen = []
        result = run_process([sys.executable, "-c", script, str(marker), str(ready), str(events)],
                             self.root, self.root / "out.log", events,
                             lambda event, **kw: seen.append(kw["backend"]))
        thread.join()
        self.assertEqual(result, (130, True))
        self.assertEqual(marker.read_text(), "stopped")
        self.assertEqual(len(seen), 5001)
        self.assertEqual(seen[-1]["event"], "build_cancelled")


if __name__ == "__main__":
    unittest.main()
