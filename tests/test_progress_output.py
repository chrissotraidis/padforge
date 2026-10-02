"""Portable console regression; the backend is synthetic, not a game build."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from padmint.cli import execute


class ProgressOutputTests(unittest.TestCase):
    def test_status_and_warning_are_visible_without_changing_events(self):
        with tempfile.TemporaryDirectory(prefix="padmint progress ") as folder:
            repo = Path(folder).resolve()
            (repo / ".gitignore").write_text("build/\n")
            for args in (["init", "-q"], ["config", "user.email", "test@example.invalid"],
                         ["config", "user.name", "Test"], ["add", "."], ["commit", "-qm", "Synthetic"]):
                subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
            revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            args = argparse.Namespace(game="synthetic", revision=revision, source_only=True,
                                      no_mods=False, jobs=2)
            manifest = {"targets": {"ios": {"command": ["synthetic"]}}}

            def backend(argv, cwd, log_path, event_path, emit, **kwargs):
                kwargs["before_spawn"]()
                log_path.touch()
                emit("build_progress", status="running; see backend.log")
                emit("progress_warning", reason="Malformed backend event; see local log")
                emit("backend_event", backend={"schema_version": 1, "stage": "compile",
                     "event": "stage_progress", "completed": 3, "total": 10, "unit": "files"})
                return 0, False

            output = io.StringIO()
            with patch("padmint.cli.selection", return_value=(manifest, "ios", manifest["targets"]["ios"])), \
                 patch("padmint.cli.run_process", side_effect=backend), contextlib.redirect_stdout(output):
                self.assertEqual(execute(args, repo, None), 0)
            self.assertIn("build_progress: running; see backend.log", output.getvalue())
            self.assertIn("progress_warning: Malformed backend event; see local log", output.getvalue())
            self.assertIn("backend_event: compile stage_progress 3/10 files", output.getvalue())
            path = next((repo / "build/padmint").glob("*/runs/*/progress.jsonl"))
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(events[1]["status"], "running; see backend.log")
            self.assertEqual(events[2]["reason"], "Malformed backend event; see local log")
            self.assertEqual(events[3]["backend"]["completed"], 3)


if __name__ == "__main__":
    unittest.main()
