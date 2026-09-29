import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from padforge.cli import with_python_path


class PythonPathTests(unittest.TestCase):
    def test_module_step_runs_when_python_ignores_pythonpath(self):
        # -E ignores PYTHONPATH, as the ._pth file does for Windows' embedded Python.
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / "builder" / "demo_builder"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("")
            (package / "names.py").write_text("NAME = 'demo'\n")
            (package / "cli.py").write_text(
                "import sys\nfrom .names import NAME\nprint(NAME, sys.argv[1:])\n")
            env = dict(os.environ, PYTHONPATH=str(package.parent))
            argv = with_python_path([sys.executable, "-m", "demo_builder.cli", "bootstrap", "--x"], env)
            argv.insert(1, "-E")
            result = subprocess.run(argv, env=env, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), "demo ['bootstrap', '--x']")

    def test_other_steps_are_unchanged(self):
        env = {"PYTHONPATH": "/somewhere"}
        for argv in ([sys.executable, "script.py"], ["/bin/bash", "-m", "x"], [sys.executable, "-m"]):
            self.assertEqual(with_python_path(list(argv), env), argv)
        self.assertEqual(with_python_path([sys.executable, "-m", "x"], {}), [sys.executable, "-m", "x"])


if __name__ == "__main__":
    unittest.main()
