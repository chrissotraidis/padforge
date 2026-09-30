# PadMint

Make your own copy of a Pad game on your Windows, Mac or Linux computer, from
your own disc or ROM, in one command. PadMint downloads the tools it needs,
runs the game's own builder, and checks the result. Nothing from your disc is
uploaded and no game files are downloaded.

## Make a game

Games you can make today:

- **KartPad**: Android game pack on Windows, Mac or Linux; iPhone/iPad on an
  Apple Silicon Mac with Xcode.
- On an Apple Silicon Mac with Xcode, for iPhone/iPad: **AnnePad**,
  **BallPad**, **BananaPad**, **BarrelPad**, **BearBirdPad**, **BellPad**,
  **BlueWake**, **BrawlerPad**, **DinoPad**, **GoldenPad**, **HarkinianPad**,
  **MaskPad**, **MeleePad**, **PaperPad**, **SpaghettiPad**, **StarshipPad**
  and **SunPad**. Some need build libraries from
  Homebrew first; each game's release notes list them.

You need your own copy of the game; see the game's README for exactly which
one. Games whose file is chosen in the app (HarkinianPad, MaskPad and others)
do not ask for it in PadMint.

Download PadMint for your computer from the
[latest release](https://github.com/chrissotraidis/padmint/releases/latest),
unzip it and start it:

- **Windows:** double-click `PadMint.cmd` (Python is included). If Windows
  says it protected your PC, choose **More info**, then **Run anyway**.
- **Mac:** once, run `xcode-select --install` in Terminal (Apple's command
  line tools; iPhone builds also need Xcode). Then double-click
  `PadMint.command`. The first time, macOS says Apple could not verify it:
  choose **Done**, open **System Settings → Privacy & Security**, scroll down,
  choose **Open Anyway** next to PadMint.command and confirm. (Or, in
  Terminal, type `sh `, drag `PadMint.command` into the window and press
  Return.)
- **Linux:** in the folder, run `sh padmint.sh` (needs Python 3.9+ and Git).
- **Android phone or tablet, no computer (experimental, KartPad only):** see
  [On an Android phone](#on-an-android-phone).

PadMint asks for your own game file (drag it into the window and press Enter)
and, where there is a choice, the game and the platform. When your file names
the game, PadMint picks it for you. Your copy is saved in Downloads. The
first run downloads about 4 GB of tools, needs about 16 GB free in total, and
can take from about 10 minutes to an hour, depending on the computer. Running
it again for the same game version takes seconds. If a build stops, PadMint
shows the reason and where to ask for help. The same thing as one command:

```
python -m padmint make kartpad android --disc "Mario Kart Wii.wbfs"
```

PadMint picks the game's latest release, downloads its source, its pinned
tools (into its own folder, never system-wide) and its published app, then
builds your copy, for example `KartPad-v0.6.0-android-personal.so` or
`KartPad-v0.6.0-ios-personal.ipa`. Keep it to yourself: it contains game code
made from your copy. The game's README says what to do with it, for example
KartPad's [Get KartPad](https://github.com/chrissotraidis/kartpad#get-kartpad).

**Experimental.** See [STATUS.md](STATUS.md) for what has been verified on
each system and [docs/DECISIONS.md](docs/DECISIONS.md) for why it works this way.

### On an Android phone

A 64-bit Android phone or tablet can make its own KartPad game pack, with no
computer. It needs about 8 GB of memory, about 25 GB free (your game file
included) and Wi-Fi for about 6 GB of downloads. The first run took about an
hour on a fast phone-sized emulator; expect longer on a real phone.

1. Install **Termux** from [F-Droid](https://f-droid.org/packages/com.termux/)
   or its [GitHub releases](https://github.com/termux/termux-app/releases)
   (the `arm64-v8a` APK; the Google Play version is a different build that
   has not been tried). Open it once.
2. Copy your own game file (for example `.rvz` or `.iso`) into the phone's
   **Download** folder.
3. In Termux, paste this line and press Enter:

   ```
   curl -fsSL https://raw.githubusercontent.com/chrissotraidis/padmint/main/launchers/padmint-android.sh | sh
   ```

   Choose **Allow** when Android asks about your files and about running in the
   background. PadMint then sets up Ubuntu inside Termux, lists the game files
   in Download (type the number of yours) and saves your game pack and the
   `KartPad game data` folder there. Keep Termux open with the screen on until
   it says your game is ready, then add both in KartPad as its README
   describes. Next time, just type `padmint`.

If Android stops the build ("Process completed (signal 9)"), turn on
**Settings → System → Developer options → Disable child process
restrictions** (Android 14 and newer) and run `padmint` again; finished steps
are kept. To free the space afterwards, in Termux: `proot-distro remove padmint`
(removes PadMint's tools and build files, not your saved game pack).

## All commands

Python 3.9 or newer; no packages needed. On Windows PadMint downloads Git
itself; on a Mac or Linux it uses the system's Git (`xcode-select --install`,
or your package manager, for example `sudo apt install git`). From this
repository:

```sh
python3 -m padmint list                      # supported games and platforms
python3 -m padmint make kartpad android --disc 'your disc.wbfs'   # the one-step path
python3 -m padmint ui                        # local browser page (same commands)
python3 -m padmint doctor kartpad            # check this computer (installs nothing)
python3 -m padmint tools kartpad --target android --repo /path/to/kartpad   # get pinned tools
python3 -m padmint get kartpad /path/to/kartpad   # download a game's source
python3 -m padmint doctor bluewake --repo /path/to/bluewake
python3 -m padmint audit path/to/file-or-folder   # release gate
python3 -m padmint history --repo /path/to/game-repo   # recorded builds
python3 -m padmint check-manifest /path/to/game-repo
python3 -m padmint plan bluewake --repo /path/to/bluewake \
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

Each game repository declares a `padmint.json` manifest (schema in
[padmint/manifest.py](padmint/manifest.py)): accepted inputs, platforms and
their status, the backend command, stages, requirements and publication
policy. PadMint's [catalog](catalog/) pins each supported game and carries an
interim manifest for repositories that do not have one yet. Game-specific
translation, patches and packaging stay in the game repository.
See [Adding a game](docs/ADDING_A_GAME.md) for a complete example.

## What a build does and does not do

This describes `plan`/`build` on a checkout you provide (`make` and the
guided start do the downloading for you).

- Keep the game checkout clean at a commit you have reviewed. `plan` and
  `build` do not download repositories or install tools; follow `doctor`'s
  suggestions or use `tools` and `get`.
- Builds, logs and records stay under the game's ignored `build/padmint/`.
  One PadMint build runs per checkout; Ctrl-C cancels and keeps finished work.
- Every personal output is checked for structure and provenance, then run
  through the release gate. The record labels it *personal build, not
  publishable* regardless of the gate result.
- Nothing is installed on a device or uploaded. A personal IPA still needs
  your own signing (AltStore, SideStore, Sideloadly or Xcode).

## The release gate

`padmint audit` scans files, folders and ZIP-based packages for console keys,
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
