# PadMint status

Updated **4 October 2026**. The [compatibility page](docs/COMPATIBILITY.md) has
the per-game detail, including **Status by game**, which is where the
compatibility work resumes.

## Which games use PadMint

- **KartPad ships ready-to-play builds again from v0.7.9**: an Android APK with
  the game code built in, a full iPhone/iPad IPA and a Mac app, on
  [KartPad's releases](https://github.com/chrissotraidis/kartpad/releases/latest).
  PadMint is optional for KartPad. The page and terminal say so when KartPad is
  chosen, and the Android phone setup says so before it downloads anything.
  On Android, PadMint's useful output is now the `KartPad game data` folder.
- **BlueWake on Windows** downloads its ready-to-play build from
  [BlueWake's releases](https://github.com/chrissotraidis/bluewake/releases/latest).
  PadMint's Windows route for BlueWake
  ([draft #46](https://github.com/chrissotraidis/bluewake/pull/46)) is parked.
  This exception may change.
- **Every other Pad game** builds through PadMint, or is a no-build download
  listed in PadMint.

## PadMint itself

- **v0.3.5**: alphabetical game list with console filters and search, language
  switching that keeps your choices, release lookup that skips releases
  without a PadMint recipe, and the KartPad ready-to-play notice.
- The player page (0.3.4 and later) shows each step as it happens: release,
  source, every tool download with its size and source, the build stages and
  where the result is saved. English, Spanish and Portuguese.
- Checks: source tests, packaged player-flow CI on Windows, Mac and Linux, and
  the packages' content gate.

## Where the compatibility work stands

Families, in order; one game proves each family. Details and next steps per game
are in [Status by game](docs/COMPATIBILITY.md#status-by-game).

1. **GameCube and Wii** (reference BlueWake): BlueWake's iPhone module builds
   without Xcode on Linux ([draft #42](https://github.com/chrissotraidis/bluewake/pull/42));
   its Mac run is in progress. Next: SunPad (same recipe change, needs the
   `cpp-ipc` submodule), then MeleePad.
2. **N64** (reference GoldenPad): Mac only. Needs a published app without game
   code that loads a module.
3. **Engine ports** (reference SpaghettiPad): iPhone modules build on Windows and
   Linux in [draft #29](https://github.com/chrissotraidis/spaghettipad/pull/29);
   needs a released recipe.

Open, not started: a data-only Android target in KartPad's recipe (skips the
1 GB NDK), physical Android and x64 Windows acceptance, and StarshipPad's and
SunPad's updated public recipes ([#22](https://github.com/chrissotraidis/starshippad/pull/22),
[#55](https://github.com/chrissotraidis/sunpad/pull/55)).
[Issue #75](https://github.com/chrissotraidis/padmint/issues/75) tracks the
catalog-wide work.

Personal game outputs stay private. Content scans are technical checks;
publication and rights decisions are reviewed separately.

## Earlier evidence

The [historical status record](STATUS-HISTORY.md) keeps earlier versions of this
page verbatim.
