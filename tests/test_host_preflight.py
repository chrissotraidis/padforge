"""Player host admission: synthetic recipes, no network, tools or backend builds."""
import copy
import io
import json
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from padmint import cli


def recipe(hosts=None):
    return {"schema_version": 1, "id": "somepad", "name": "SomePad", "game": "Synthetic",
            "kind": "clean-engine", "status": "experimental",
            "inputs": [{"type": "rom", "when": "in-app"}],
            "targets": {"ios": {"hosts": hosts or {"macos-arm64": "experimental"},
                                "command": ["synthetic-builder"], "tools": ["cmake"],
                                "published_app": "SomePad-v{version}-ios-unsigned.ipa"}},
            "publication": {"public_binaries": False}}


class HostPreflightTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stack.enter_context(redirect_stderr(io.StringIO()))
        # Any accidentally unmocked live request fails the test immediately.
        self.stack.enter_context(mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")))
        self.stack.enter_context(mock.patch.object(cli.tools, "open_url", side_effect=AssertionError("network")))
        self.host = self.patch(cli, "host_id", "macos-arm64")
        self.patch(cli, "catalog", {"somepad": {"repo_url": "https://example.invalid/somepad"}})
        self.home = self.patch(cli.tools, "tools_root", Path("/synthetic/tools"))
        self.release = ("v1.0.0", {"SomePad-v1.0.0-ios-unsigned.ipa": "https://example.invalid/base"})
        self.latest = self.patch(cli, "latest_release", self.release)
        self.published = self.patch(cli, "published_recipe", (recipe(), "release"))
        self.source = self.patch(cli, "release_source", (Path("/synthetic/source"), "v1.0.0", self.release[1]))
        self.manifest = self.patch(cli, "manifest_for", (recipe(), "repository"))
        self.install = self.patch(cli.tools, "install")
        self.app = self.patch(cli, "published_app", Path("/synthetic/base.ipa"))
        self.execute = self.patch(cli, "execute", 1)
        self.submodules = self.patch(cli, "finish_submodules")
        self.file_check = self.patch(cli.game_file, "check_before_tools")
        self.patch(cli.tools, "missing_system_library")
        self.patch(cli, "git", "a" * 40)
        self.patch(cli, "read_game_version", {"version": "1.0.0"})

    def patch(self, obj, name, value=None):
        return self.stack.enter_context(mock.patch.object(obj, name, return_value=value))

    def make(self, ref=None):
        return cli._make("somepad", "ios", None, Path("/synthetic/output"), ref=ref, jobs=2)

    def assert_no_build_inputs(self):
        for call in (self.install, self.app, self.execute, self.submodules, self.file_check):
            call.assert_not_called()

    def test_unsupported_hosts_stop_before_source_tools_app_or_execution(self):
        for host in ("macos-x86_64", "windows-x86_64", "linux-x86_64"):
            with self.subTest(host=host):
                self.host.return_value = host
                with self.assertRaisesRegex(ValueError, rf"unsupported on {host}.*macos-arm64 \(experimental\)"):
                    self.make()
                self.source.assert_not_called()
                self.manifest.assert_not_called()
                self.home.assert_not_called()
                self.assert_no_build_inputs()

    def test_planned_host_and_unimplemented_target_stop_before_source(self):
        manifest = recipe({"macos-arm64": "planned"})
        self.published.return_value = (manifest, "release")
        with self.assertRaisesRegex(ValueError, "planned on macos-arm64.*none yet"):
            self.make()
        del manifest["targets"]["ios"]["command"]
        with self.assertRaisesRegex(ValueError, "cannot be built for ios yet"):
            self.make()
        manifest["targets"] = {}
        with self.assertRaisesRegex(ValueError, "cannot be built for ios yet"):
            self.make()
        self.source.assert_not_called()
        self.assert_no_build_inputs()

    def test_verified_and_experimental_hosts_remain_available(self):
        for host in ("macos-arm64", "macos-x86_64", "windows-x86_64", "windows-arm64",
                     "linux-x86_64", "linux-arm64"):
            for state in ("verified", "experimental"):
                with self.subTest(host=host, state=state):
                    manifest = recipe({host: state})
                    self.host.return_value = host
                    self.published.return_value = (manifest, "release")
                    self.manifest.return_value = (manifest, "repository")
                    self.assertEqual(self.make(), 1)  # mocked backend, not a real build
        self.assertEqual(self.install.call_count, 12)
        self.assertEqual(self.execute.call_count, 12)

    def test_actual_source_manifest_is_rechecked_before_tools(self):
        manifest = recipe({"macos-arm64": "planned"})
        self.manifest.return_value = (manifest, "repository")
        with self.assertRaisesRegex(ValueError, "planned on macos-arm64"):
            self.make()
        self.source.assert_called_once()
        self.assert_no_build_inputs()

    def test_target_removed_in_actual_source_is_rejected(self):
        manifest = recipe()
        manifest["targets"] = {}
        self.manifest.return_value = (manifest, "repository")
        with self.assertRaisesRegex(ValueError, "cannot be built for ios yet"):
            self.make()
        self.assert_no_build_inputs()

    def test_latest_is_resolved_once_and_shared_with_recipe_source_and_app(self):
        self.latest.side_effect = [self.release, ("v2.0.0", {})]
        self.assertEqual(self.make(), 1)
        self.latest.assert_called_once()
        self.published.assert_called_once_with("somepad", release=self.release)
        self.source.assert_called_once_with("somepad", None, release=self.release)
        self.app.assert_called_once_with("SomePad-v1.0.0-ios-unsigned.ipa", self.release[1],
                                         Path("/synthetic/apps/somepad"))

    def test_explicit_ref_uses_selected_source_without_live_release_lookup(self):
        self.assertEqual(self.make(ref="codex/candidate"), 1)
        self.latest.assert_not_called()
        self.published.assert_not_called()
        self.source.assert_called_once_with("somepad", "codex/candidate", release=None)
        self.manifest.assert_called_once_with("somepad", Path("/synthetic/source"))
        self.execute.assert_called_once()

    def test_explicit_ref_still_rejects_unsupported_actual_source(self):
        self.host.return_value = "macos-x86_64"
        with self.assertRaisesRegex(ValueError, "unsupported on macos-x86_64"):
            self.make(ref="codex/candidate")
        self.latest.assert_not_called()
        self.published.assert_not_called()
        self.assert_no_build_inputs()

    def test_actual_source_requirements_not_published_recipe_are_checked(self):
        manifest = copy.deepcopy(recipe())
        manifest["requirements"] = {"tools": [{"name": "synthetic-tool", "player": True,
                                               "note": "Install the game's required tool first."}]}
        self.manifest.return_value = (manifest, "repository")
        self.patch(cli, "check_program", (False, "missing"))
        with self.assertRaisesRegex(ValueError, "Install the game's required tool first"):
            self.make()
        self.assert_no_build_inputs()


class PinnedReleaseTests(unittest.TestCase):
    def test_explicit_ref_source_does_not_look_up_a_release(self):
        with mock.patch.object(cli, "catalog", return_value={"somepad": {"repo_url": "https://example.invalid"}}), \
                mock.patch.object(cli.tools, "tools_root", return_value=Path("/synthetic/tools")), \
                mock.patch.object(cli, "source_complete", return_value=True), \
                mock.patch.object(cli, "latest_release", side_effect=AssertionError("release lookup")), \
                mock.patch.object(cli.tools, "open_url", side_effect=AssertionError("network")):
            source, ref, assets = cli.release_source("somepad", "codex/candidate")
        self.assertEqual(source, Path("/synthetic/games/somepad-codex_candidate"))
        self.assertEqual(ref, "codex/candidate")
        self.assertEqual(assets, {})

    def test_source_reuses_supplied_release_and_assets_without_latest_lookup(self):
        release = ("v1.0.0", {"base.ipa": "https://example.invalid/base"})
        with mock.patch.object(cli, "catalog", return_value={"somepad": {"repo_url": "https://example.invalid"}}), \
                mock.patch.object(cli.tools, "tools_root", return_value=Path("/synthetic/tools")), \
                mock.patch.object(cli, "source_complete", return_value=True), \
                mock.patch.object(cli, "latest_release", side_effect=AssertionError("second lookup")), \
                mock.patch.object(cli.tools, "open_url", side_effect=AssertionError("network")):
            source, ref, assets = cli.release_source("somepad", release=release)
        self.assertEqual(source, Path("/synthetic/games/somepad-v1.0.0"))
        self.assertEqual((ref, assets), release)

    def test_recipe_reuses_supplied_release_without_latest_lookup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "SomePad-v1.0.0-padmint.json"
            path.write_text(json.dumps(recipe()))
            release = ("v1.0.0", {path.name: "https://example.invalid/recipe"})
            with mock.patch.object(cli, "catalog", return_value={"somepad": {"repo_url": "https://example.invalid"}}), \
                    mock.patch.object(cli, "published_app", return_value=path) as download, \
                    mock.patch.object(cli, "latest_release", side_effect=AssertionError("second lookup")), \
                    mock.patch.object(cli.tools, "open_url", side_effect=AssertionError("network")):
                actual, origin = cli.published_recipe("somepad", release=release)
            self.assertEqual(actual, recipe())
            self.assertEqual(origin, "somepad v1.0.0 release")
            self.assertEqual(download.call_args.args[:2], (path.name, release[1]))


if __name__ == "__main__":
    unittest.main()
