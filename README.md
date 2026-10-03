# PadMint

<p align="center">
  <strong>Make your own copy of a Pad game, like KartPad, from your own disc.</strong><br>
  On your Windows, Mac or Linux computer, or on an Android phone. Nothing from your disc is uploaded.
</p>

<p align="center">
  <a href="https://github.com/chrissotraidis/padmint/releases/latest"><img alt="Latest PadMint" src="https://img.shields.io/github/v/release/chrissotraidis/padmint?label=PadMint&color=34C759"></a>
  <a href="https://github.com/chrissotraidis/padmint/actions/workflows/windows-package-check.yml"><img alt="Packaged player checks" src="https://github.com/chrissotraidis/padmint/actions/workflows/windows-package-check.yml/badge.svg"></a>
  <img alt="Windows, Mac and Linux" src="https://img.shields.io/badge/runs%20on-Windows%20%7C%20Mac%20%7C%20Linux-0A84FF">
  <img alt="Android phone, experimental" src="https://img.shields.io/badge/Android%20phone-experimental-3DDC84?logo=android">
  <img alt="Game files not included" src="https://img.shields.io/badge/game%20files-not%20included-FF453A">
  <a href="https://discord.gg/xwHfUD2bxW"><img alt="Ask in the KartPad Discord" src="https://img.shields.io/badge/Discord-ask%20for%20help-5865F2?logo=discord&amp;logoColor=white"></a>
</p>

> **Playing KartPad?** KartPad has ready-to-play downloads again for Android,
> iPhone, iPad and Mac. Get them from the
> [latest KartPad](https://github.com/chrissotraidis/kartpad/releases/latest)
> and follow [KartPad's guide](https://github.com/chrissotraidis/kartpad#get-kartpad):
> you don't need PadMint. PadMint stays available if you'd rather build your
> own copy, or to make the `KartPad game data` folder from your disc.
>
> **Playing BlueWake on Windows?** Download the ready-to-play Windows build from
> [BlueWake's releases](https://github.com/chrissotraidis/bluewake/releases/latest).
> PadMint makes BlueWake for Mac, iPhone and iPad.

**Why you need it:** the other Pad apps contain no game code. The game part is
made from your own copy of the game, on your own device. PadMint does that: you
give it your disc image, it builds your copy and tells you what to do with it.

**What PadMint does on your computer**, step by step, and the page shows each
one as it happens:

1. Finds the game's latest release on GitHub and downloads its source code.
2. Downloads the free build tools that game needs (for KartPad on Android:
   Google's Android NDK, about 1 GB, plus CMake, Ninja and .NET), once, into
   a `.padmint` folder in your home folder. Each download is checked against a
   pinned checksum.
3. Downloads the game's published app, which has no game code in it.
4. Builds your copy on this computer from your disc image.
5. Saves the result in your Downloads folder.

Your disc image never leaves your computer, and PadMint uploads nothing. Before
you start, the page lists every download, where it comes from and how big it
is, and how much free space the build needs.

**What you get, and what to do with it:**

| You make it for | PadMint gives you | Then |
|---|---|---|
| Android | a `KartPad game data` folder (and a `KartPad-v…-android-personal.so` game pack, which KartPad 0.7.9 and newer don't need) | Install KartPad's APK from its release page (it has the game code) and import the folder in the app |
| iPhone or iPad | `KartPad-v…-ios-personal.ipa` (the complete app, with your game inside) and a `KartPad game data` folder | Install the `-personal.ipa` with Sideloadly, AltStore or SideStore, then import the folder in the app |

The `…-ios-unsigned.ipa` on a game's release page is PadMint's starting point,
not something to install by itself: it has no game code, so it can't play.

## Start here

| You want KartPad on | You have | Follow |
|---|---|---|
| **Android** | a Windows, Mac or Linux computer | [Android, with a computer](#android-with-a-computer) |
| **Android** | only the phone | [Android, phone only](#android-phone-only-experimental) (experimental) |
| **iPhone or iPad** | a Mac with Apple Silicon (M1 or newer) | [iPhone or iPad](#iphone-or-ipad) |
| **iPhone or iPad** | a Windows or Linux computer | [iPhone or iPad](#iphone-or-ipad) (experimental) |

Other Pad games: see [Other Pad games](#other-pad-games).
Check your project's [build compatibility](docs/COMPATIBILITY.md) before downloading
tools. It lists the released recipes, host architectures and known blockers.

**You need** your own Mario Kart Wii disc image: the European (PAL) version,
game ID **RMCP01**, as an ISO, WBFS or RVZ file. Other regions don't work yet.
On a computer, keep about 16 GB free.

**Versions:** always use the [latest PadMint](https://github.com/chrissotraidis/padmint/releases/latest)
and the [latest KartPad](https://github.com/chrissotraidis/kartpad/releases/latest).
PadMint always builds for the latest KartPad.

## Android, with a computer

### 1. Start PadMint

Download the ZIP for your computer from the
[latest PadMint](https://github.com/chrissotraidis/padmint/releases/latest)
and unzip it.

- **Windows:** right-click the ZIP and choose **Extract All**. In the folder
  it makes, open the `PadMint-v…` folder and double-click the **PadMint**
  file (`PadMint.cmd`), not the `padmint` folder. If Windows says it
  protected your PC, choose **More info**, then **Run anyway**.
- **Mac:** once, run `xcode-select --install` in Terminal. Then double-click
  `PadMint.command`. The first time, macOS says Apple could not verify it:
  choose **Done**, then **System Settings → Privacy & Security → Open Anyway**.
- **Linux:** run `sh padmint.sh` in the folder (needs Python 3.9+ and Git).

PadMint opens in your web browser. The page is served by your own computer and
nothing is uploaded. It speaks English, Spanish and Portuguese: pick one from
the **Language** menu at the top.

### 2. Choose your disc image

In the PadMint page:

1. Under **1. Choose a game**, click **KartPad**.
2. Under **2. Your own game file**, click **Choose file…** and pick your disc
   image. Disc images already in Downloads are listed, so you can also click one
   of those. PadMint checks the file at once and says **Ready** or what is wrong.
3. Under **3. Make it for**, choose **Android phone or tablet**. That is where
   you will play, whichever computer you use.
4. Read **What PadMint will do on this computer**: the downloads, where they
   come from, their sizes and the free space needed. Then click **Make my copy**.

The page then shows a checklist: finding the release, downloading the source,
each tool with its progress, the build with its current step, and saving your
copy. Keep the page and the PadMint window open, and keep the computer
plugged in; PadMint keeps it awake while it builds. The first build downloads
tools and sources and can take an hour or longer, especially on Windows on ARM.
Finished work is cached, so later runs can be quicker; a game update may need a
full rebuild. When it finishes, the page lists exactly what to do next. If it
stops, it says why; open **Technical log** and use **Copy log for a bug report**
when asking for help. See the [recorded build results](docs/COMPATIBILITY.md#recorded-android-pack-builds)
for the exact hosts and versions checked.

Prefer the terminal? Start PadMint with `start` (for example `PadMint.cmd start`
on Windows or `sh padmint.sh start` on Linux), then drag your disc image into
the window and answer the questions there. A computer without a web browser
gets these questions automatically.

### 3. Find two things in Downloads

| | What it is |
|---|---|
| `KartPad game data` folder | the game's tracks, music and menus |
| `KartPad-v…-android-personal.so` | a **game pack**: the game code, made from your disc. KartPad 0.7.9 and newer already include it, so you can ignore this file |

Both are made from your disc: keep them to yourself.

### 4. Put them on your phone

1. Install the `KartPad-v…-android.apk` from the
   [latest KartPad](https://github.com/chrissotraidis/kartpad/releases/latest).
   It updates an older KartPad and keeps your saves; don't uninstall first.
   It already has the game code.
2. Copy the `KartPad game data` folder to the phone (USB cable, Google Drive,
   Quick Share).
3. Open KartPad and tap **Import Game** on the Mario Kart Wii card. At
   **Game Data & Saves**, tap **Import from Extracted Game Data Folder…**, pick
   the `KartPad game data` folder, tap **Use this folder** and **Allow**, then
   **Done**.
4. Tap **Play Game**. For Retro Rewind, tap **Set Up Game** on its card.

**Updates:** install the new APK over your KartPad and keep playing; your saves
and game data stay. You don't need PadMint again.

## Android, phone only (experimental)

**For KartPad, install its ready-to-play APK instead**
([latest KartPad](https://github.com/chrissotraidis/kartpad/releases/latest)).
This route is only for making the `KartPad game data` folder on the phone,
without a computer or Dolphin.

A 64-bit Android phone or tablet can run PadMint. It has only been
tried on a phone-sized emulator so far. It needs about
8 GB of memory, 25 GB free, Wi-Fi for about 6 GB of downloads, and an hour or
more. **Most phones are easier with a computer:** if you have any Windows, Mac or
Linux computer, use [Android, with a computer](#android-with-a-computer) instead.
The setup line below checks the phone first and tells you, before downloading
anything, if it is not 64-bit or lacks the memory or space.

1. Install **Termux** from [F-Droid](https://f-droid.org/packages/com.termux/)
   or its [GitHub releases](https://github.com/termux/termux-app/releases)
   (the `arm64-v8a` APK). Open it once. If Android or Play Protect blocks the
   installation, do not bypass the warning or disable security settings. This
   experimental route does not work on every phone; use a computer instead if
   installation is blocked. Get every Termux part from the same place; the
   Google Play version is a different build that PadMint hasn't been tried with.
2. Copy your disc image into the phone's **Download** folder.
3. In Termux, paste this line and press Enter:

   ```
   curl -fsSL https://raw.githubusercontent.com/chrissotraidis/padmint/main/launchers/padmint-android.sh | sh
   ```

   If setup stops, it says where and what to do; running the same line again
   keeps the finished steps. It works with older Termux packages too (an
   `unknown option '--name'` error came from an earlier version of this line).

4. Tap **Allow** if Android asks about access to your files. Wait for setup to
   finish; the first run downloads tools before it asks you to choose a file.
5. PadMint opens in the phone's browser. Choose **KartPad**, tap your disc image
   in the list of game files found in **Download**, and tap **Make my copy**.
   The page shows each step. Keep Termux open in the background, with the screen
   on, until the page says your copy is ready.
6. Install the `KartPad-v…-android.apk` from the
   [latest KartPad](https://github.com/chrissotraidis/kartpad/releases/latest).
   In KartPad, tap **Import Game** on the Mario Kart Wii card. At **Game Data &
   Saves**, tap **Import from Extracted Game Data Folder…**, choose the
   `KartPad game data` folder in Download and tap **Done**. Tap **Play Game**.

**No page opened?** If Termux shows only a `$` prompt, type `padmint` and press
Enter. To answer in Termux instead, type `padmint start`: it lists the game
files in **Download** with numbers; type the number beside the **filename**
(not a disc ID like `RMCP01`). If setup stopped with an error, share that error
text in a [PadMint issue](https://github.com/chrissotraidis/padmint/issues).

Next time, type `padmint` in Termux. If Android stops the build ("Process
completed (signal 9)"), turn on **Settings → System → Developer options →
Disable child process restrictions** and run `padmint` again; finished steps
are kept. To free the space: `proot-distro remove padmint` (your game pack
stays).

## iPhone or iPad

- **On a Mac** with Apple Silicon and
  [Xcode](https://apps.apple.com/app/xcode/id497799835) installed.
- **On Windows or Linux** (experimental): no Xcode needed. Tried so far on
  Windows 11 on ARM and on Ubuntu, each with an iPhone 14. A Windows 11 Surface
  Laptop 2 user [reports building v0.7.3 and updating both devices](https://github.com/chrissotraidis/kartpad/issues/310#issuecomment-5961520278),
  but has not tested gameplay and reports an exit when opening the import menu.
  That report is not an independently verified Intel/AMD build-and-play result.

1. Start PadMint as in [step 1](#1-start-padmint), choose your disc image and,
   under **Make it for**, choose **iPhone or iPad**.
2. PadMint saves `KartPad-v…-ios-personal.ipa` and a `KartPad game data`
   folder in Downloads.
3. Install the `.ipa` with Sideloadly, AltStore or SideStore. Updating? Install
   it over your KartPad with the same tool and Apple ID to keep your saves.
4. First time only: get the `KartPad game data` folder onto the device.
   AirDrop it from a Mac, or put it in iCloud Drive, on a USB drive or in a
   cloud drive app. In KartPad, tap **Import Game** on the Mario Kart Wii card,
   then **Import from Extracted Folder…**, and pick the folder in the Files
   window that opens.

**Updates:** run PadMint again for each new KartPad. It reuses compatible cached
work, but a new game release may need a full rebuild.

## Build hosts and game devices

The computer or phone running PadMint is the **build host**. The device you
play on is the **output target**. Installing PadMint on Windows or Linux does
not make every game recipe available on that host.

| What you want to build | Build host | Current scope |
|---|---|---|
| KartPad for Android (game data folder; the APK has the game code) | Windows, Linux or macOS | Available; follow the Android computer guide above |
| KartPad for Android (game data folder) | Android phone | Experimental; free space and phone restrictions can prevent completion |
| KartPad iPhone/iPad app | Apple Silicon Mac with Xcode | Available |
| KartPad iPhone/iPad app | Windows or Linux | Experimental; see the tested-host limits above |
| Other source-build recipes listed below | Apple Silicon Mac with Xcode | Per-game prerequisites and known blockers apply; no general Windows, Linux or Android-phone build support |
| AgePad | Mac with a matching Steam installation | Packages your supported copy without Xcode; exact compatibility profile required |
| DevilTouch / VaultPad previews | No PadMint build needed | Download, sign and sideload; add your own data in the app |

A completed build does not establish gameplay on every device. The recipe
selected from each game's release determines which hosts and targets can run.
An Android phone building a KartPad pack does not imply an Android version of
every Pad game.

See the [per-project compatibility matrix](docs/COMPATIBILITY.md) for the exact
public recipe versions and the evidence behind the current limitations.

## Other Pad games

**No build needed:** **CaesarPad**, **DaggerPad**, **DevilTouch**, **Emerald
Tablet**, **KidPad**, **PeonPad** and **VaultPad** publish apps that contain no
game files, so there is nothing to build. Choose one in PadMint (under **No build
needed**) or run `padmint list` to see the steps: download the IPA from the
game's releases page, check its checksum, sign and sideload it with your own
Apple ID, then add your own game files inside the app. These are preview
releases, not App Store builds.

**SnapPad:** public downloads remain paused. Its `see repo` catalog entry is
not an available PadMint build recipe or a playable download.

On a Mac with Apple Silicon and Xcode, PadMint also offers iPhone and iPad build
recipes for **AnnePad**, **BallPad**, **BananaPad**, **BarrelPad**, **BearBirdPad**,
**BellPad**, **BlueWake**, **BrawlerPad**, **DinoPad**, **GoldenPad**,
**HarkinianPad**, **MaskPad**, **MeleePad**, **PaperPad**, **SpaghettiPad**,
**StarshipPad** and **SunPad**. Choose the game in the PadMint page, then your
game file (games that ask for it inside the app skip this). Each game's README
says which file it needs and how to install the result.

**Current blocker:** StarshipPad's published v0.2.0 recipe fails with an iOS SDK
selection error. The [checked fix](https://github.com/chrissotraidis/starshippad/pull/22)
has merged and passed full CI. The public v0.2.0 recipe still needs an updated release.

**SunPad on iOS/iPadOS 27:** its public v0.2.0 app was built with SDK 27
without the required UIKit scene startup. [Source fix #55](https://github.com/chrissotraidis/sunpad/pull/55)
has merged and passed full iOS/tvOS compilation; the published app still needs
a separately verified update. Physical iOS 27 acceptance remains open.

See [STATUS.md](STATUS.md) for the build checks and remaining limits.

**AgePad** (iPad with 8 GB or more) works differently: on a Mac with Age of
Empires II: DE installed through Steam, PadMint adds your own supported Steam
copy to the AgePad release without Xcode. The installed files must match the
release's exact compatibility profile. AgePad v0.1.0 rejected an updated Steam
beta client in our latest check; support for that version is not yet validated.
Do not change the fingerprints or disable those checks to force a build.
After a successful build, copy the game data to
the iPad; see [Get AgePad](https://github.com/chrissotraidis/agepad#get-agepad).

## Questions

**Do I need PadMint for KartPad?**
No. From KartPad 0.7.9, its Android, iPhone, iPad and Mac downloads are ready to
play: install one and add your own game data. PadMint is the option for building
your own copy. It also makes the `KartPad game data` folder from your disc, which
is the easiest way to add game data: importing a disc image in the app works
too, but needs your own Wii key file (`common-key.bin`); the folder doesn't.

**Do I run PadMint again for every KartPad update?**
No. Install the new KartPad over the old one; your saves and game data stay. If
you build your own iPhone copy with PadMint, run it again for each new KartPad.

**I don't have a computer.**
On Android, try [Android, phone only](#android-phone-only-experimental), or use
a friend's computer with your own disc image; the game pack isn't tied to the
computer that made it.

**Can someone send me their game pack or IPA?**
No. It's made from their copy of the game, so sharing it means sharing the
game. Please don't ask for one or post yours.

**Windows or macOS warns me about PadMint.**
Expected for a free tool without a paid certificate. Windows: **More info →
Run anyway**. Mac: **System Settings → Privacy & Security → Open Anyway**.
Only download PadMint from its
[releases page](https://github.com/chrissotraidis/padmint/releases/latest).

**It says a download was blocked, or it stops early.**
PadMint names the server it couldn't reach. Check your internet connection
and whether that server is accessible. On a managed network, ask its
administrator to check access, or retry on another trusted network. For a
certificate error, check the device's date and time and available certificate
updates. Keep certificate verification and security software enabled.
Run PadMint again after resolving the error; finished downloads are kept.

**It says my file is the wrong version.**
KartPad needs the European (PAL) disc, game ID RMCP01.

**It says my file is stored only in iCloud (Mac).**
In Finder, right-click the file, choose **Download Now**, wait, then choose it
again.

**Linux asks me to install libxml2.**
Run the command PadMint shows, for example `sudo apt install libxml2`, then
start PadMint again.

**What was PadForge?**
PadForge is PadMint's old name. PadMint moves your old PadForge folder over and
keeps the tools you already downloaded.

**Still stuck?**
Ask in the [KartPad Discord](https://discord.gg/xwHfUD2bxW) or open a
[PadMint issue](https://github.com/chrissotraidis/padmint/issues) for setup,
downloads or build failures. Include the game and release, PadMint version,
host OS and architecture, intended device and the last error lines. Review
logs for personal paths first; keep game files, keys and personal builds private.
For a game that builds but fails while playing, use that game's issue tracker.

---

*The rest of this page is for developers and game maintainers.*

## All commands

Python 3.9 or newer; no packages needed. On Windows PadMint downloads Git
itself; on a Mac or Linux it uses the system's Git (`xcode-select --install`,
or your package manager, for example `sudo apt install git`). From this
repository:

```sh
python3 -m padmint list                      # supported games and platforms
python3 -m padmint make kartpad android --disc 'your disc.wbfs'   # the one-step path
python3 -m padmint                           # the PadMint page in your browser (start: terminal)
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
`list` shows the rest as *planned*. KartPad's Android game pack builds on
Windows, Linux and macOS (x64 and ARM64) and, experimentally, on an Android
phone; iPhone/iPad builds need an Apple Silicon Mac, or, experimentally,
Windows or Linux. See [STATUS.md](STATUS.md) for what has been
verified on each.

The catalog covers the Pad ports whose repositories declare a build. Only
games listed under [Start here](#start-here) and [Other Pad games](#other-pad-games) are offered to players; the
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
