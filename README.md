# PadMint

<p align="center">
  <strong>Make your own copy of a Pad game, like KartPad, from your own disc.</strong><br>
  On your Windows, Mac or Linux computer, or on an Android phone. Nothing from your disc is uploaded.
</p>

<p align="center">
  <a href="https://github.com/chrissotraidis/padmint/releases/latest"><img alt="Latest PadMint" src="https://img.shields.io/github/v/release/chrissotraidis/padmint?label=PadMint&color=34C759"></a>
  <img alt="Windows, Mac and Linux" src="https://img.shields.io/badge/runs%20on-Windows%20%7C%20Mac%20%7C%20Linux-0A84FF">
  <img alt="Android phone, experimental" src="https://img.shields.io/badge/Android%20phone-experimental-3DDC84?logo=android">
  <img alt="Game files not included" src="https://img.shields.io/badge/game%20files-not%20included-FF453A">
  <a href="https://discord.gg/xwHfUD2bxW"><img alt="Ask in the KartPad Discord" src="https://img.shields.io/badge/Discord-ask%20for%20help-5865F2?logo=discord&amp;logoColor=white"></a>
</p>

**Why you need it:** the KartPad app contains no game code. The game part is
made from your own copy of the game, on your own device. PadMint does that:
you give it your disc image, it builds your copy and tells you what to do with
it.

## Start here

| You want KartPad on | You have | Follow |
|---|---|---|
| **Android** | a Windows, Mac or Linux computer | [Android, with a computer](#android-with-a-computer) |
| **Android** | only the phone | [Android, phone only](#android-phone-only-experimental) (experimental) |
| **iPhone or iPad** | a Mac with Apple Silicon (M1 or newer) | [iPhone or iPad](#iphone-or-ipad) |
| **iPhone or iPad** | a Windows or Linux computer | [iPhone or iPad](#iphone-or-ipad) (experimental) |

Other Pad games: see [Other Pad games](#other-pad-games).

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

### 2. Drag in your disc image

Drag your disc image into the PadMint window and press Enter:

```
Game: KartPad
Make it for: Android phone or tablet
Drag your own KartPad game file into this window, then press Enter: Mario Kart Wii.rvz
Your copy will be saved in C:\Users\you\Downloads
```

If PadMint asks which device to build for, choose **Android phone or tablet**.
That choice describes where you will play, regardless of which computer you use.

Keep the window open. Keep the computer plugged in; PadMint keeps it awake while
it builds. The first build takes about 15 minutes to an hour, while
PadMint downloads about 4 GB of tools; later builds take a few minutes. If it
stops, it says why and what to do.

### 3. Find two things in Downloads

| | What it is |
|---|---|
| `KartPad-v…-android-personal.so` | your **game pack**: the game code, made from your disc |
| `KartPad game data` folder | the game's tracks, music and menus |

Both are made from your disc: keep them to yourself.

### 4. Put them on your phone

1. Install the `KartPad-v…-android.apk` from the
   [latest KartPad](https://github.com/chrissotraidis/kartpad/releases/latest).
   It updates an older KartPad and keeps your saves; don't uninstall first.
2. Copy the `.so` file **and** the `KartPad game data` folder to the phone
   (USB cable, Google Drive, Quick Share).
3. Open KartPad and tap the button on the Mario Kart Wii card (**Import Game**,
   or **Play Game** if you played before). At **Add your game pack**, tap
   **Choose file** and pick the `.so`.
4. At **Game Data & Saves**, tap **Import from Extracted Game Data Folder…**,
   pick the `KartPad game data` folder, then tap **Done**.
5. Tap **Play Game**. For Retro Rewind, tap **Set Up Game** on its card.

**Updates:** install the new APK and keep playing; your game pack keeps
working. If an update ever needs a new one, KartPad says **This KartPad needs a
new game pack**: run PadMint again and choose the new `.so`.

## Android, phone only (experimental)

A 64-bit Android phone or tablet can make its own game pack. It has only been
tried on a phone-sized emulator so far. It needs about
8 GB of memory, 25 GB free, Wi-Fi for about 6 GB of downloads, and an hour or
more.

1. Install **Termux** from [F-Droid](https://f-droid.org/packages/com.termux/)
   or its [GitHub releases](https://github.com/termux/termux-app/releases)
   (the `arm64-v8a` APK). Open it once. On newer Android, Play Protect may say
   **Unsafe app blocked** because Termux is built for an older Android version
   on purpose: tap **More details**, then **Install anyway**. Get every Termux
   part from the same place; the Google Play version is a different build that
   PadMint hasn't been tried with.
2. Copy your disc image into the phone's **Download** folder.
3. In Termux, paste this line and press Enter:

   ```
   curl -fsSL https://raw.githubusercontent.com/chrissotraidis/padmint/main/launchers/padmint-android.sh | sh
   ```

4. Tap **Allow** if Android asks about access to your files. Wait for setup to
   finish; the first run downloads tools before it asks you to choose a file.
5. PadMint lists the game files in **Download**, for example `1. Mario Kart Wii.rvz`.
   When it asks for a number, type `1` for that example and press Enter.
   This is the number beside the **filename**, not a disc ID like `RMCP01`.
   If there is no list yet, do not type a number. Wait for setup to finish.
   Keep Termux open with the screen on until it says your game is ready.
6. In KartPad, tap **Import Game** (or **Play Game**) on the Mario Kart Wii
   card. At **Add your game pack**, tap **Choose file** and select the
   `KartPad-v…-android-personal.so` in Download. Then, at **Game Data & Saves**,
   tap **Import from Extracted Game Data Folder…**, choose the `KartPad game data`
   folder in Download and tap **Done**. Tap **Play Game**.

**Typed a number and nothing happened?** PadMint needs to be showing its file
list and number prompt first. If Termux shows only a `$` prompt, type `padmint`
and press Enter to start it. If setup stopped with an error, share that error
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
  Windows 11 on ARM and on Ubuntu, each with an iPhone 14; ordinary Intel and
  AMD Windows PCs haven't been tried yet.

1. Start PadMint as in [step 1](#1-start-padmint), drag in your disc image and,
   when asked which device to build for, choose **iPhone or iPad**.
2. PadMint saves `KartPad-v…-ios-personal.ipa` and a `KartPad game data`
   folder in Downloads.
3. Install the `.ipa` with Sideloadly, AltStore or SideStore. Updating? Install
   it over your KartPad with the same tool and Apple ID to keep your saves.
4. First time only: get the `KartPad game data` folder onto the device.
   AirDrop it from a Mac, or put it in iCloud Drive, on a USB drive or in a
   cloud drive app. In KartPad, tap **Import Game** on the Mario Kart Wii card,
   then **Import from Extracted Folder…**, and pick the folder in the Files
   window that opens.

**Updates:** run PadMint again for each new KartPad; it reuses your earlier
work, so it takes a few minutes.

## Other Pad games

On a Mac with Apple Silicon and Xcode, PadMint also makes iPhone and iPad apps
for **AnnePad**, **BallPad**, **BananaPad**, **BarrelPad**, **BearBirdPad**,
**BellPad**, **BlueWake**, **BrawlerPad**, **DinoPad**, **GoldenPad**,
**HarkinianPad**, **MaskPad**, **MeleePad**, **PaperPad**, **SpaghettiPad**,
**StarshipPad** and **SunPad**. Drag in your game file (or press Enter for
games that ask for it inside the app) and pick the game. Each game's README
says which file it needs and how to install the result.

**AgePad** (iPad with 8 GB or more) works differently: on a Mac with Age of
Empires II: DE installed through Steam, PadMint adds your own Steam copy to
the AgePad release in seconds, without Xcode. You then copy the game data to
the iPad; see [Get AgePad](https://github.com/chrissotraidis/agepad#get-agepad).

## Questions

**I used to import my disc image straight into KartPad. Why PadMint now?**
The app no longer includes game code, so the game pack has to be made from
your disc on your device. For the tracks and music, PadMint's `KartPad game
data` folder is easiest. Importing a disc image in the app still works, but
it needs your own Wii key file (`common-key.bin`); the folder doesn't.

**Do I run PadMint again for every KartPad update?**
Android: no, just install the new APK. KartPad tells you if a new game pack is
ever needed. iPhone and iPad: yes, and it takes a few minutes.

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
PadMint names the server it couldn't reach. A VPN, firewall or antivirus web
filter is the usual cause: turn it off for the build or try another network,
then run PadMint again. Finished downloads are kept.

**It says my file is the wrong version.**
KartPad needs the European (PAL) disc, game ID RMCP01.

**It says my file is stored only in iCloud (Mac).**
In Finder, right-click the file, choose **Download Now**, wait, then drag it in
again.

**Linux asks me to install libxml2.**
Run the command PadMint shows, for example `sudo apt install libxml2`, then
start PadMint again.

**What was PadForge?**
PadForge is PadMint's old name. PadMint moves your old PadForge folder over and
keeps the tools you already downloaded.

**Still stuck?**
Ask in the [KartPad Discord](https://discord.gg/xwHfUD2bxW) or open a
[KartPad issue](https://github.com/chrissotraidis/kartpad/issues) with your
computer (Windows, Mac or Linux), your phone model and the last lines PadMint
printed.

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
