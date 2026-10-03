# Adding a game to PadMint

A game joins PadMint with two small files and no PadMint code changes.

## 1. Add `padmint.json` to the game repository

List the scripts the repository already uses, in order. PadMint runs each one
as a stage, shows progress, stops at the first failure and audits the result.

```json
{
  "schema_version": 1,
  "id": "examplepad",
  "name": "ExamplePad",
  "game": "Example Game (N64)",
  "kind": "decomp-patches",
  "status": "draft-untested",
  "inputs": [{"type": "n64-rom", "formats": ["z64"], "when": "in-app",
              "description": "Your own ROM, chosen in the app."}],
  "targets": {
    "ios": {
      "hosts": {"macos-arm64": "experimental"},
      "output": "ipa",
      "check": "ipa",
      "steps": [
        {"stage": "preflight", "command": ["{repo}/scripts/check-repo-safety.sh"]},
        {"stage": "compile", "command": ["{repo}/scripts/build-ios.sh", "--device"]},
        {"stage": "package", "command": ["{repo}/scripts/package-ios.sh",
                                         "{repo}/build-ios/Release-iphoneos/ExamplePad.app", "{output}"]}
      ]
    }
  },
  "requirements": {"disk_gb": 10, "tools": [{"name": "xcodebuild", "version_args": ["-version"]}]},
  "publication": {"public_binaries": false, "reason": "Personal builds contain game code."}
}
```

- **Placeholders** fill whole arguments only: `{repo}`, `{disc}`, `{work}`,
  `{output}`, `{jobs}`. Values never become shell text. A step may also set
  `"env": {"NAME": "{output}"}` when a script reads its output path from the
  environment.
- **Job cap:** every step runs with `CMAKE_BUILD_PARALLEL_LEVEL` set to
  `--jobs`, which `cmake --build` honors. Scripts that call `ninja`, `make`
  or `xcodebuild` directly should pass `{jobs}` themselves. Check the actual
  backend commands; setting the environment alone does not cap those tools.
- **Inputs:** use `"when": "build"` when a script reads the player's disc or ROM
  (then `--disc` is required and passed as `{disc}`), or `"in-app"` when the
  player chooses it after installing (then `--disc` is refused).
- **Kinds:** `disc-translation`, `emulator-shell`, `decomp-patches`,
  `upstream-engine`, `clean-engine`.
- **Hosts and states:** `verified` (a recorded complete build from that host,
  accepted on the target device), `experimental` (runnable, not yet accepted),
  `planned`, `unsupported`. Only verified and experimental hosts run.
- A game with its own one-command builder can use a single `command` with
  `modes` (`full`, `source-only`) and `options` instead of `steps`.
- Run executable scripts directly so their own `#!/usr/bin/env bash` shebang
  applies. On macOS `/bin/bash` is bash 3.2, which some scripts do not support.
- If a step needs submodules, add a first step
  `["git", "-C", "{repo}", "submodule", "update", "--init", "--recursive"]`: fresh
  worktrees start with empty submodule folders.
- Make sure the repository ignores `build/`: PadMint writes its private
  workspace to `build/padmint/`.

Check it:

```sh
python3 -m padmint check-manifest /path/to/examplepad
python3 -m padmint plan examplepad --repo /path/to/examplepad --revision FULL_COMMIT
```

### iPhone modules on any computer

If the game publishes an iPhone app with no game code and loads its game code from a
library inside the app, let PadMint build that library's surroundings on Windows,
Linux and Macs alike, with no Xcode:

```json
"ios": {
  "hosts": {"macos-arm64": "experimental", "windows-x86_64": "experimental", "linux-x86_64": "experimental"},
  "output": "ipa", "check": "ipa",
  "tools": ["libcxx", "cmake", "ninja"],
  "published_app": "ExamplePad-v{version}-ios-unsigned.ipa",
  "ios_module": {"file": "{work}/module/libexample_game.dylib", "into": "Frameworks/libexample_game.dylib"},
  "steps": [
    {"stage": "compile", "command": ["{python}", "-m", "example_builder", "--toolchain", "{ios_toolchain}",
                                     "--out", "{work}/module/libexample_game.dylib"]}
  ]
}
```

Before the steps, PadMint assembles an iPhone SDK from Apple's open-source headers and
LLVM's libc++ (`{ios_sdk}`) and a CMake toolchain file for its LLVM (`{ios_toolchain}`),
with stubs for the published app's thread-local exports. Your steps compile only the game
library. Afterwards PadMint checks that every name the library imports comes from the
app or the device's C and C++ libraries, strips it, names it `@rpath/<file>` and puts it at
`into` inside a copy of the published app. `scripts/ios-module-probe.py` runs the whole
pipeline with a small probe library and no game code.

## 2. Add a catalog entry to PadMint

`catalog/examplepad.json`:

```json
{"schema_version": 1, "id": "examplepad",
 "repo_url": "https://github.com/chrissotraidis/examplepad",
 "reviewed_revision": null, "notes": "Manifest owned by the game repository.",
 "manifest": null}
```

To offer the game in guided setup, add `player_targets` and a positive whole
number for `free_space_gb`. Measure the first player build, including downloaded
tools, fetched sources, temporary build files and the exported output; allow
headroom. The catalog estimate is used by player `doctor` and the initial source
download check. The recipe's `requirements.disk_gb` applies to checkout `doctor`
and may allow more room for development builds.

For tools the player must install, set `player: true` and an actionable `note`
on the recipe requirement. Probe the tool or SDK the backend actually uses;
finding an unrelated Python executable or Xcode's command-line tools is not
enough. PadMint-supplied tools belong in the target's `tools` list instead.

## 3. Promote it

1. Run `python3 -m padmint build` from a clean checkout. The record shows each
   stage, the output check and the release gate result.
2. After a complete build, set `status` to `experimental`; after a build is
   accepted on a device, mark the host `verified` and pin `reviewed_revision`.
3. Before anything is published, every public file must pass
   `python3 -m padmint audit`. Personal builds are never published.
