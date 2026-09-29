# PadForge

Make your own copy of a Pad game on your Windows, Mac or Linux computer, from
your own disc or ROM, in one command. PadForge downloads the tools it needs,
runs the game's own builder, and checks the result. Nothing from your disc is
uploaded and no game files are downloaded.

## Make a game

Games you can make today:

- **KartPad**: Android game pack on Windows, Mac or Linux; iPhone/iPad on an
  Apple Silicon Mac with Xcode.
- On an Apple Silicon Mac with Xcode, for iPhone/iPad: **AnnePad**,
  **BallPad**, **BananaPad**, **BarrelPad**, **BearBirdPad**, **BellPad**,
  **BlueWake**, **BrawlerPad**, **GoldenPad**, **HarkinianPad**, **MaskPad**,
  **SpaghettiPad** and **StarshipPad**. Some need build libraries from
  Homebrew first; each game's release notes list them.

You need your own copy of the game; see the game's README for exactly which
one. Games whose file is chosen in the app (HarkinianPad, MaskPad and others)
do not ask for it in PadForge.

Download PadForge for your computer from the
[latest release](https://github.com/chrissotraidis/padforge/releases/latest),
unzip it and start it:

- **Windows:** double-click `PadForge.cmd` (Python is included). If Windows
  says it protected your PC, choose **More info**, then **Run anyway**.
- **Mac:** once, run `xcode-select --install` in Terminal (Apple's command
  line tools; iPhone builds also need Xcode). Then double-click
  `PadForge.command`. The first time, macOS says Apple could not verify it:
  choose **Done**, open **System Settings → Privacy & Security**, scroll down,
  choose **Open Anyway** next to PadForge.command and confirm. (Or, in
  Terminal, type `sh `, drag `PadForge.command` into the window and press
  Return.)
- **Linux:** in the folder, run `sh padforge.sh` (needs Python 3.9+ and Git).

PadForge asks which game and platform, then for your own game file (drag it
into the window and press Enter) and where to save (Enter for Downloads). The
first run downloads about 4 GB of tools, needs about 16 GB free in total, and
can take from about 10 minutes to an hour, depending on the computer. Running
it again for the same game version takes seconds. If a build stops, PadForge
shows the reason and where to ask for help. The same thing as one command:

```
python -m padforge make kartpad android --disc "Mario Kart Wii.wbfs"
```

PadForge picks the game's latest release, downloads its source, its pinned
tools (into its own folder, never system-wide) and its published app, then
builds your copy, for example `KartPad-v0.6.0-android-personal.so` or
`KartPad-v0.6.0-ios-personal.ipa`. Keep it to yourself: it contains game code
made from your copy. The game's README says what to do with it, for example
KartPad's [Get KartPad](https://github.com/chrissotraidis/kartpad#get-kartpad).

**Experimental.** See [STATUS.md](STATUS.md) for what has been verified on
each system and [docs/DECISIONS.md](docs/DECISIONS.md) for why it works this way.

## All commands

Python 3.9 or newer; no packages needed. On Windows PadForge downloads Git
itself; on a Mac or Linux it uses the system's Git (`xcode-select --install`,
or your package manager, for example `sudo apt install git`). From this
repository:

```sh
python3 -m padforge list                      # supported games and platforms
python3 -m padforge make kartpad android --disc 'your disc.wbfs'   # the one-step path
python3 -m padforge ui                        # local browser page (same commands)
python3 -m padforge doctor kartpad            # check this computer (installs nothing)
python3 -m padforge tools kartpad --target android --repo /path/to/kartpad   # get pinned tools
python3 -m padforge get kartpad /path/to/kartpad   # download a game's source
python3 -m padforge doctor bluewake --repo /path/to/bluewake
python3 -m padforge audit path/to/file-or-folder   # release gate
python3 -m padforge history --repo /path/to/game-repo   # recorded builds
python3 -m padforge check-manifest /path/to/game-repo
python3 -m padforge plan bluewake --repo /path/to/bluewake \
  --revision FULL_REVIEWED_COMMIT --disc '/path/to/your disc.iso'
```

`plan` validates paths, checkout state and platform support and prints the
exact backend command without building. Change `plan` to `build` to run it.
Use `--target` to choose a platform the game declares (default `ios`),
`--source-only`/`--no-mods` where the game supports them, and `--jobs 1-8`.

Builds run on the platforms each game marks *verified* or *experimental*;
`list` shows the rest as *planned*. Android game packs build on Windows (x64
and ARM64), Linux (x86_64) and macOS; iPhone/iPad builds need an Apple Silicon
Mac. See [STATUS.md](STATUS.md) for what has been verified on each.

The catalog covers the Pad ports whose repositories declare a build. Only
games listed under [Make a game](#make-a-game) are offered to players; the
others are still being tested, and [STATUS.md](STATUS.md) lists how far each
has got.

## How games plug in

Each game repository declares a `padforge.json` manifest (schema in
[padforge/manifest.py](padforge/manifest.py)): accepted inputs, platforms and
their status, the backend command, stages, requirements and publication
policy. PadForge's [catalog](catalog/) pins each supported game and carries an
interim manifest for repositories that do not have one yet. Game-specific
translation, patches and packaging stay in the game repository.
See [Adding a game](docs/ADDING_A_GAME.md) for a complete example.

## What a build does and does not do

This describes `plan`/`build` on a checkout you provide (`make` and the
guided start do the downloading for you).

- Keep the game checkout clean at a commit you have reviewed. `plan` and
  `build` do not download repositories or install tools; follow `doctor`'s
  suggestions or use `tools` and `get`.
- Builds, logs and records stay under the game's ignored `build/padforge/`.
  One PadForge build runs per checkout; Ctrl-C cancels and keeps finished work.
- Every personal output is checked for structure and provenance, then run
  through the release gate. The record labels it *personal build, not
  publishable* regardless of the gate result.
- Nothing is installed on a device or uploaded. A personal IPA still needs
  your own signing (AltStore, SideStore, Sideloadly or Xcode).

## The release gate

`padforge audit` scans files, folders and ZIP-based packages for console keys,
address-named translated game functions, embedded original program sections
and provenance declaring translated game code. It fails closed on archives it
cannot inspect. Keys are identified by a short prefix and a SHA-256 hash; this
repository contains no keys. A PASS is a heuristic result, not copyright or
licensing clearance.

Game inputs, generated game code, saves, keys, personal builds and optimization
profiles never belong in this repository.

## Tests

```sh
python3 -m unittest discover -s tests -v
```
