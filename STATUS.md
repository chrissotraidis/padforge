# PadMint status

PadMint was named PadForge until 0.2.0 (padforge#25); older entries below use
the current name.

Resumable record for the overnight goal loop. Source of truth for decisions and
per-repo state is the Notion "Public Repo Proprietary-Content Audit" and its
tracker; this file mirrors progress so work can resume after interruption.

## Loop 2: formula, KartPad 0.6.0, then every repo (started 29 Sep 09:05)

Plan and owner decisions: Notion "PadMint release formula and pilot plan".

- **Step 1 done (09:20).** Windows 11 VM at 16 GB / 8 cores, commands run
  inside it; Docker Desktop runs Linux containers (image pulls work).
- **Step 2 done (09:55).** #336 merged (`87467f3`); main's GitHub source
  archive passes the content check. iOS (11m44s) and Mac (10m42s) builds
  complete through PadMint at 0.6.0/240. CI `boundaries` has failed on main
  since 26 Sep (unrelated pipeline-budget probe). Details:
  KartPad #336 now passes the content check:
  REL guard fixture built from the guard's own anchors; synthetic g6/g7
  translator fixtures generated in tests and checked by SHA-256; translated-build
  log and candidate record moved to private scratch; translator pinned as fork
  branch `kartpad-translator` (same tree). One version file, `version.json`
  (0.6.0 / build 240), read by Android, Mac, the iOS builder and PadMint's
  build record. Verification builds (iOS, Mac) running.
- **Step 3 design notes.** Translated code self-registers through static
  registrars, so a separately loaded game library can register itself if the
  runtime exports its API. Game-derived pieces: shards, registration and
  dispatch tables, `data_sections_init` + blobs, guest symbol table and
  `RuntimeConfig.h` (SDA bases). Next: link the runtime without them to list
  the exact interface.
- **Step 3 progress (10:20).** Android emulator probe proved a library in app
  storage can load and bind to one in the APK (S3). Runtime fork branch
  `codex/game-pack` (android): `MKW_GAME_PACK=APP` builds the runtime without
  game code, a small loader (`src/game_pack.cpp`) loads the pack named by
  `KARTPAD_GAME_PACK`, checks its version and supplies data-init and the SDA
  bases; eight HLE calls into specific translated functions resolve through the
  registry. Standalone `runtime/game_pack` project builds the pack with only
  the NDK. KartPad: launcher "Add your game pack" step, `scripts/build-android-app.sh`,
  `scripts/build-game-pack.sh`, shared `translated-definitions.txt`. First
  empty APK builds (47.6 MB) but the content check FAILS it: (1) Dolphin's
  Android disc-import library carries both Wii common keys (previous public
  APKs likely did too); (2) 559 exported `func_*` HLE override names. Fixes in
  progress: export list without `func_*`; Android disc import rebuilt coreless
  with the player's own key file, like iOS (#335).
- **Step 3, Android done (11:10).** Both content-check failures fixed: Android
  disc import asks once for the player's own `common-key.bin` (an extracted
  folder needs no key); the empty APK exports 0 `func_*` names and passes the
  gate. Empty 0.6.0 APK + pack chosen in the app's Choose File screen reached an
  active race (Luigi Circuit, lap 1/3, 60 FPS, API 36 emulator on the Mac GPU),
  existing licence and save intact. Fixes found on the way, now D6 rules: header
  state lives once in the app (`MKW_GAME_PACK_MODULE`, checked by KartPad's
  `scripts/check-game-pack-state.py` in every pack build); the pack hands the
  app its 8 wrapped original functions (pack interface v2); one pack per app
  version. Pack build ~5 min at 8 jobs on this Mac. Next: iPhone half (empty IPA
  + pack in `Frameworks/`), then Windows/Linux hosts (step 4).
- **Step 3, iPhone half (11:45).** Empty 0.6.0 IPA passes the content check
  (0 address-named functions) and installs in place on the iPhone 14 with data
  intact; the iPhone pack builds and passes the state check. The iPhone race
  waits on iPhone Mirroring, which needs the phone locked once by hand.
- **Step 4 (12:45 to 15:00).** `padmint tools` (pinned, digest-checked
  Git, .NET 8, CMake, Ninja, NDK, nodtool), `padmint get` and
  `padmint make GAME PLATFORM --disc FILE`. KartPad's pack build is now
  pure Python (no bash, perl, rsync). Windows fixes: Git by full path,
  forward-slash paths, nodtool.EXE version text, blob symbol spellings, paths
  under 260 characters, llvm-cxxfilt instead of c++filt.
- **Android gate PASS (15:00).** A clean `padmint make kartpad android` in
  the Windows 11 VM made a pack (SHA-256 `c248cb3c...30c3`) that the
  release-signed empty APK imported and raced with (Luigi Circuit, lap 1/3).
  Windows timing on this ARM VM: tools ~2 min, extract + translate ~3 min,
  compile ~45 min under x64 emulation. Same Release code as the Mac pack
  (116.4 vs 116.6 MB). App fix found on the way (KartPad `b6348e92`): a
  failed import, e.g. a full device, now shows a dialog instead of vanishing.
  Next: rebuild the release APK from `b6348e92`, Linux run in Docker,
  iPhone race, then publish.
- **Linux gate PASS, releases staged (17:00).** Clean Ubuntu x86_64: `padforge
  make kartpad android` 21 min end to end; its pack raced in the final APK.
  Fixes found: Git hint, .NET invariant globalization, NDK symlinks, published
  app name. Mac: `padmint make kartpad ios` from a fresh home, 9 min; the IPA
  boots on the iPhone 14 with saves intact. Players get three ZIPs with a
  launcher and a guided start (D8); Windows and Linux downloads checked. KartPad
  v0.6.0 and PadMint v0.1.0 staged and gate-checked. Waiting on the iPhone
  race (the phone must be locked once, or the UI Automation passcode entered).
- **Published (17:40).** iPhone gate PASS (PadMint-made IPA raced on the
  iPhone 14); KartPad v0.6.0 and PadMint v0.1.0 released and verified by
  anonymous download; pinned KartPad issue #338.
- **Step 7 to 9 (18:30).** D9: iPhone builds target iOS 15 (Xcode 27).
  PadMint: games whose file is added in the app need no `--disc`.
  - BlueWake: formula PR #4 (empty IPA via `build.sh --app-only`; the module
    via `--app`); `padmint make bluewake ios` compiling the module.
  - SunPad: formula PR #50 (app-only build, module added to the published
    IPA, "no game code yet" message); build after BlueWake.
  - HarkinianPad: #30 and #31 merged (0.2.0, recipe only); play-test next.
  - Recipe-only PRs: MaskPad #10, SpaghettiPad #20, StarshipPad #16,
    BallPad #9, BellPad #17, BrawlerPad #9 (fix: the recipe built an app
    that cannot run on a device).
  - Open engines released: DevilTouch v1.5.5-preview.1, VaultPad
    v0.1.0-preview.1 (all assets pass the content check).
  - PaperBoat #1 and PaperPad #11 merged (Torch URL); BananaPad, SnapPad and
    DinoPad still pin an older PaperPad.
  - Owner calls: N64 split vs recipe-only, HarkinianPad #28, SnapPad,
    GalaxyPad and F0X gate policy, UTP, KidPad listing, AltStore #5, CTRPad
    Actions billing.
- **Status (20:10).** Done means three things per repo: a public release in
  the formula's shape, a README "Get it" section that matches it, and the
  Notion row linking both (new tracker columns: Release, README ready).
  - KartPad on a real Android phone: the public PadMint v0.1.0 made the pack
    on this Mac (19 min); added through Choose file on a Pixel 9 Pro XL, it
    raced at 60 FPS. Gap for 0.6.1: no button to replace an added pack.
  - BlueWake: `padmint make bluewake ios` PASS (2 h 19 min including
    tuning; 412 MB module). Installed in place on the iPhone; the console
    shows the module loading, disc reads and 30 FPS at full speed. The
    gameplay screenshot waits for the iPhone's screen to be woken.
  - Merged: StarshipPad #16, BallPad #9, BrawlerPad #9, DevilTouch #8
    (README points to the release). MaskPad #10: release check reads
    version.json. VaultPad #8 (README) waits for CI.
  - HarkinianPad: `padmint make harkinianpad ios --ref main` building; then
    iPhone gameplay and the recipe-only v0.2.0 release. Then a PadMint build
    check and release for BellPad, SpaghettiPad, StarshipPad, BallPad,
    BrawlerPad and MaskPad.
- **Status (21:50).** The iPhone was dark because iPhone Mirroring was still
  attached (closed at 20:28); it is now locked and needs the owner's unlock
  before any gameplay screenshot. Until then:
  - Built through PadMint and installed in place (saves kept): HarkinianPad
    0.2.0 (main; loads oot.o2r, opening scene), GoldenPad 0.2.0 (#40 branch).
  - Built through PadMint from main, recipe-only release staged (content
    check PASS): HarkinianPad, BellPad, SpaghettiPad, StarshipPad, BallPad
    1.1.0. BrawlerPad and MaskPad building. `recipe-release.sh` stages each
    release the same way (recipe from the built commit, version.json check,
    SHA256SUMS, audit, notes).
  - D10 (N64 ports publish the recipe only). Release PRs in the same shape:
    GoldenPad #40, BearBirdPad #16, BananaPad #10, AnnePad #7, DinoPad #7,
    BarrelPad #15 (also fixes the build under stock bash 3.2). Build checks
    queued after MaskPad.
  - PadMint main: guided start handles games whose manifest lives in their
    repository and takes a per-game help link (64 tests). A v0.1.1 release
    with `player_targets` for each released game follows the first recipe
    releases (v0.1.0 offers only KartPad and asks every game for a disc).
  - Merged: MaskPad #10, VaultPad #8 (README).
- **Status (00:00, 30 Sep).** Released after a PadMint build and iPhone 14
  gameplay with the owner's data: BlueWake 0.1.0 (empty app + module),
  HarkinianPad, MaskPad, SpaghettiPad, StarshipPad, BallPad 1.1.0, BrawlerPad,
  BellPad, GoldenPad, BearBirdPad, AnnePad, BarrelPad (recipe only). All twelve
  are in the catalog's guided start. v0.1.1 is the other chat's Windows hotfix;
  main is 0.1.2 (player hardening, PR #5). Before publishing 0.1.2: Windows
  gate with the bundled Python (KartPad build in the VM, C:\\pffix-full.log)
  and a Mac run through PadMint.command (Apple's Python).
  - BananaPad #10: fresh clones failed verify-sources (submodule fingerprint
    included git describe text); fixed, rebuilding. DinoPad #7: catalogued;
    build next. Then SunPad #50 and MeleePad.
- **Status (02:15, 30 Sep).** Released since 00:00: PadMint 0.1.2 (Windows
  and Mac builds passed; Linux: the container starts) and BananaPad 0.2.0. Every released repo was
  re-checked on GitHub: the release has the formula's assets, the README points
  to PadMint, and the Notion row has Release, README ready and L5 set; stale
  "Next action" text on those rows was rewritten.
  - DinoPad #7 builds through PadMint (0.2.0 build 4) and is installed in
    place on the iPhone (ROM and save kept). Gameplay check waits for the
    phone: XCTest shows an "Enable UI Automation" passcode prompt.
  - SunPad #50: the empty app failed the content check (Wii retail and Korean
    common keys from Dolphin's IOSC defaults; two license test ZIPs). Fixed
    with D11 (RecompCore `da96175`, ModernGekko `8f49c55` on
    `codex/sunpad-apple`), notices skip archives, and build-ios-app.sh now
    merges the fresh core (it linked a stale `libSunPadCore.a`). The empty
    IPA passes; a fresh-home PadMint build from the branch is running.
  - MeleePad #35: same fix cherry-picked (RecompCore `3f2a51f`, ModernGekko
    `9be2c5b` on `codex/meleepad-slippi-preview5`); empty-app build next.
- **Status (04:00, 30 Sep).** Four more ports build end to end through
  PadMint from fresh homes and run on the iPhone 14 (installed in place,
  saves kept); each release is staged with the content check passing, and each
  PR names its one remaining step: controlled gameplay on the phone, which
  waits for the phone's UI automation to be re-enabled with the passcode.
  - SunPad #50: title screen reached. Also moved the iOS module build into the
    checkout (a shared /tmp CMake cache broke a second checkout).
  - MeleePad #35: launcher; disc import pending. Fixes: Slippi link inputs
    built before provisioning, `-DHAVE_PIPE2=OFF` (macOS 27 SDK), rustup listed.
  - PaperPad #12 (new recipe: version.json, build-ios-device.sh, padforge.json,
    README Get PaperPad): 12.8 min build, opening scene plays.
  - DinoPad #7: launcher, ROM and save kept.
  - Catalog entries for MeleePad and PaperPad: PR #10 (draft until released).
  - Phone: CoreDevice file copies from the phone stall (AFC works); XCTest hangs
    or asks for the passcode. Installs, launches and screenshots work.
- **Status (04:30, 30 Sep).** PadMint 0.1.3 published: BananaPad in the
  guided start (it was released but not offered), and the gate reads gzip,
  bzip2, xz and tar contents (#11), which let PeonPad #8 merge. Checked on Mac,
  Windows 11 VM (bundled Python) and Linux (Python 3.9); anonymous downloads
  match SHA256SUMS. SunPad and MeleePad staged empty IPAs rebuilt from fresh
  clones; the phone copies use them. EctoPad's one blocker recorded: no build
  from a fresh clone yet.

## Morning handoff (30 Sep, written 04:25)

**Update 08:15:** the phone recovered after restarting its `dtfileserviced`
and `testmanagerd` from the Mac (`devicectl device process signal`). Played on
the iPhone 14 and released: SunPad, MeleePad, PaperPad, DinoPad (0.2.0 each);
DevilTouch's published app reached Tristram (L5). PadMint 0.1.4 offers all 18
games. VaultPad (iPad-only) and the owner decisions below remain.

**Update 09:20:** player path verified end to end: the published PadMint 0.1.4
from an empty home downloaded the published SunPad 0.2.0 app and recipe and
built a personal IPA in 47.6 min; it boots on the iPhone with the save kept.
PadMint 0.1.5 published with the PadMint-experience chat's #13-#16, a quieter
end-of-build message and safe output names. VaultPad #6 merged after a
fresh-home build. KartPad #343 (game_ids for #14's check) waits for the next
KartPad release.

**Re-audit 10:30:** all 41 public release downloads account-wide pass the
content check; every tracker release link resolves. Fixed: PaperPad 0.2.0's
recipe built PaperPad Original, not the PaperBoat app its README describes, so
PaperPad 0.2.1 builds PaperBoat (played on the iPhone); six READMEs still said
"a new version is in progress" (fixed or merging); GalaxyPad #15 merged.
`catalog/paperpad.json`'s note still names build-ios-device.sh (cosmetic).

**Update 12:10:** PadMint 0.1.6 (Windows long paths), 0.1.7 (Android packs on
ARM Linux, raced in the emulator) and 0.1.8 published. 0.1.8 carries the
PadMint-experience chat's #22 (`PADFORGE_CACHE`, one download cache for
every game version) and #23 (a backend's game data folder saved once for the
player), and `padmint list` now shows player targets instead of the
built-in fallback manifests. Each checked on Mac, Linux (Docker) and the
Windows 11 VM; anonymous downloads match SHA256SUMS. KartPad #343-#348 merged;
KartPad 0.6.1 (kartpad#349) is being built and gated. kartpad#347 (packs that
survive app updates) approved with notes for 0.7.0. OpenMobileTTS
v3.1.0-preview.2 published. The PaperPad catalog note now names PaperBoat's
scripts.

**Update 13:50:** KartPad 0.6.1 published (Latest): Replace Game Pack, the
shared Retro Rewind download and the PadMint game data folder. Gates with the
public PadMint 0.1.8 from fresh homes: iPhone 14 race (Mac IPA, 12 min);
emulator update from 0.6.0 raced with the Mac pack (6 min, Retro Rewind from
the cache), then with Replace Game Pack, then with the Windows 11 VM pack
(about 60 min, Defender slows the ARM VM); a new emulator install imported
"KartPad game data" with no key and raced. Pinned #338 is version-free now.
Open: padforge#25 asked us to rename the project (done in PadMint 0.2.0); kartpad#350
(ABI 3 packs, 0.7.0), #351 (stale tests) and #352 (fresh-install status line)
from the PadMint-experience chat.

**Update 14:45:** KartPad 0.7.0 published (Latest): pack ABI 3, so game packs
survive app updates (kartpad#347/#350, merged via #353). Gates: emulator update
from 0.6.1 (prompt, 0.6.1 pack refused, 0.7.0 pack imported, old file removed,
raced); iPhone 14 race; a version-only test build kept the pack and raced with
no PadMint run, and PadMint reused the pack (Android compile skipped with an
identical file, iPhone IPA in 72 s); a header-change test build refused the
pack. Open: Pixel 9 Pro XL check (not connected); padforge#25 (renamed to PadMint).

**Update 15:45:** Renamed to PadMint (padforge#25; committed there for 7 Oct).
#26 merged (package, `padmint` command, launchers, ~/.padforge moved to
~/.padmint once; padforge.json and PADFORGE_* still accepted); repo renamed
to chrissotraidis/padmint; PadMint 0.2.0 published and checked on Mac (full
KartPad Android build from the published 0.7.0 in 132 s, pack reused),
Windows 11 VM (real old home moved, no downloads) and Linux. The 0.1.x
PadForge releases are drafts now (tags kept). Game repos: 17 rename PRs
merged, MaskPad, MeleePad and SunPad wait on CI; KartPad 0.7.1 carries the
in-app wording and the runtime's pack messages (fingerprints unchanged).

**Android phone, no computer (30 Sep, 21:00; draft, codex/pm-android-phone):**
`launchers/padmint-android.sh` sets up Ubuntu 24.04 in Termux (proot-distro)
and runs PadMint there (host linux-arm64). Experimental, one recorded run: an
API 36 arm64 emulator (8 GB, 8 cores, 32 GB) typed the one line into Termux
0.118.3, built KartPad 0.7.2's pack from mkw.rvz (pack SHA-256
`a30d62ea...f839`) and the published 0.7.2 APK raced with it (Luigi Circuit,
lap 1/3, 59 FPS). Paste to pack: 58 min (setup 4, tools 15, build 37:
compile 25 at 5 jobs). Peak: 4.1 GB in Termux, 2.4 GB still free, no
process kills; about 22 GB of storage including the disc. Fixes found: .NET
needs a heap limit under Android's address space; proot's emulated hard links
break copytree (PadMint's game data copy here; KartPad's export on reruns,
kartpad `codex/android-phone-build`). Not tried on a real phone.

**Update 18:10:** KartPad 0.7.1 and 0.7.2 published; both keep players' game
packs (fingerprints unchanged; in 0.7.2 the new app-only vi_pacing.h lives in
runtime/app_only/ so it is not a pack-interface input). 0.7.2 carries the fixes
promised on 27 Sep (#330 measured on the emulator, #327, #329/#316 Automatic on
Adreno 8xx, #104 with the S24 option). PadMint 0.2.0 reused packs for both
iPhone builds (compile 2-3 s). All published *-padforge.json recipe assets
renamed to *-padmint.json with SHA256SUMS updated and verified; release notes
say PadMint. MeleePad #36 and SunPad #51 merged; MaskPad #12 waits on a UI test
that also fails on MaskPad's main (testControlPressReleaseToggleAndLifecycleCancellation).

**Update 18:45:** MaskPad #12 merged after that UI test passed on re-run
(flaky), so all 20 game repos use padmint.json. Player replies posted on
kartpad #104, #316, #327, #329, #330 and #357. iPhone players without a Mac
(#327) cannot build today; that is the most requested gap.

**Update 21:00:** PadMint 0.2.1 published: #28, #30, #31, #32, #33, #34 (see
release notes). Checked on Mac, Ubuntu 26.04 ARM64 and the Windows 11 VM.
Player builds of KartPad 0.7.2 with 0.2.0 on clean Ubuntu 24.04 (plus
libxml2) and 26.04 (libxml2.so.16 shim) were byte-identical and raced on the
emulator. Seven game repos now declare their real build tools (goldenpad#42
and bearbirdpad#18 use PadMint's LLVM, so they need new releases built with
0.2.1). Parallel work: Android builds on the phone (Carson), iPhone IPAs
without a Mac (Hubble).

**Update 00:50, 1 Oct (0.2.4):** PadMint 0.2.3 published 1 Oct 00:20 (Latest,
checked on Mac, Linux and the Windows VM). town3r's GoldenPad build next
stopped on Xcode's Metal Toolchain (downloaded separately since Xcode 26).
0.2.4: #55 a version check that exits non-zero counts as missing, and
requirements can carry a label, so a recipe can require the Metal Toolchain
(xcrun metal --version); #54 README: Play Protect "Unsafe app blocked" for
Termux on Android 17 (More details, Install anyway). Metal census (player
path of each latest release): AnnePad, BananaPad, BearBirdPad, DinoPad and
GoldenPad compile RT64's Metal shaders on the Mac; the libultraship games,
KartPad, BlueWake, MeleePad, SunPad, BallPad, BellPad and BarrelPad do not.
Recipes marked (annepad#11, bananapad#14, bearbirdpad#21, dinopad#11,
goldenpad#47); those games get recipe-only releases next.

**Update 00:10, 1 Oct (0.2.3):** PadMint 0.2.2 and KartPad 0.7.3 published
30 Sep (both Latest, anonymous downloads verified; KartPad fingerprints
unchanged, emulator and iPhone 14 in-place updates raced). GoldenPad and
BearBirdPad 0.2.1 published (recipes use PadMint's LLVM). 0.2.3: #50 README
after the release; #51 N64 ROMs and GameCube/Wii discs recognized from their
header (town3r's GoldenEye .z64 on padmint#7 had to be picked from a list of
18); #52 recipes mark programs the player installs ("player": true), checked
before any download (GoldenPad needs Homebrew SDL2 for its shader step; our
Macs had it, town3r's didn't; goldenpad#46 marks cmake, ninja, xdelta3 and
sdl2-config). Open: Pixel 9 Pro XL Termux run (phone locked), full 0.2.2
build sweep of every game (James).

**Update 22:55 (0.2.2):** merged #36 (import button named per platform), #37
(Android phone via Termux, experimental), #38 (failure messages with the fix),
#39 (iPhone packs on Windows and Linux: LLVM, libc++ and Apple open-source
headers pinned; D12), #40 (time left), #41 (doctor reads the release recipe
and checks only the player path), #42 (newer recipe says "get the latest
PadMint"), #43 (player-first README), #44 (game data copy on Windows: no "."
in extended-length paths), #45 (CMake caches left by the .padforge move are
set up again, padmint#7), #46 (unzip-first message, "Reading your file"), #47
(keep awake; QuickEdit off while building), #48 (guided start offers
iPhone/iPad on Windows and Linux for ios_off_mac games: KartPad). Off-Mac
proof: KartPad 0.7.2 iPhone pack built on Ubuntu 24.04 arm64 (13.5 min) and
on the Windows 11 ARM64 VM with native arm64 Python (29 min), fingerprint
35ccf81c both, state check PASS, each raced on the iPhone 14 with the save
byte-identical. KartPad main had drifted to iOS fingerprint ad53234e (a comment
in build-ios-device-game-app.sh); kartpad#365 restored 35ccf81c. KartPad 0.7.3
(kartpad#361, #363) follows this release: its recipe names libcxx.

- **Done** (release + README + tracker): KartPad 0.6.0, BlueWake 0.1.0,
  HarkinianPad, MaskPad, SpaghettiPad, StarshipPad, BallPad 1.1.0, BrawlerPad,
  BellPad, GoldenPad, BearBirdPad, AnnePad, BarrelPad, BananaPad; PadMint 0.1.3.
- **Needs 5 minutes with the iPhone, then publish** (runbook:
  `~/.codex/scratch/release-staging/READY-30sep.md`): SunPad #50 (press Start),
  MeleePad #35 (Import Game Data → On My iPhone → MeleePad → the .iso),
  PaperPad #12 (press Start), DinoPad #7 (Start Dinosaur Planet). Each is the
  PadMint build, installed in place with saves kept; releases are staged and
  pass the content check. Then PadMint PR #10 + 0.1.4 for the guided start.
- **Phone:** XCTest needs "Enable UI Automation" (passcode) and now stalls at
  "waiting for workers to materialize"; CoreDevice file copies from the phone
  stall too (AFC works). Unplugging and replugging the cable, then entering the
  passcode at the prompt, should clear both.
- **Device checks open:** DevilTouch (published IPA plays its intro with your
  MPQ; tap into town); VaultPad is iPad-only.
- **Your decisions:** AltStore #5 and the clean engines (mark Clear), SnapPad #7
  test stub, GalaxyPad #15 anchors (spread across research scripts), F0X and
  HarkinianPad #28 patch context, UTP, CTRPad, KidPad listing. EctoPad needs a
  bootstrap script first.
- **Notes:** the local `~/.codex/release-gate/release_gate.py` that AGENTS
  rules cite is an older copy of PadMint's gate (no compressed-file support).
  KartPad's pinned #338 is closed (still pinned). Phone copies to tidy: Melee ISO
  in MeleePad Documents (for the import), DK64.v64 and Animal Crossing.iso in
  BlueWake Documents, a stray copy in BellPad's Library.
- **Disk (165 GB free):** cleanup candidates, not deleted: scratch
  padforge-mac-home 64 GB, worktrees/kartpad-padforge/build 44 GB,
  bluewake-public-cold 15 GB, kp060-phone 15 GB, padforge-fresh-home 11 GB,
  bluewake-fresh 9.8 GB, pack-e2e-mac 6.6 GB, tonight's padforge-*-home and
  *-fresh-020 folders (about 20 GB together).

## Overnight run 28–29 Sep (complete)

## Morning handoff (06:15)

- **Complete personal builds through PadMint (16 games):** KartPad (iOS and
  Mac), GoldenPad, SunPad, AnnePad, SnapPad, MaskPad, HarkinianPad, DevilTouch,
  BarrelPad, VaultPad, StarshipPad, BrawlerPad, SpaghettiPad, BearBirdPad,
  BellPad, BallPad. The gate rejects every output as personal. On `main`:
  GoldenPad and the six earlier ones; the rest wait on PRs (merge queue below).
- **Not verified:** no device install or gameplay (no L5); no non-Mac host build.
- **Nothing published, nothing deleted.** Moved-aside folders and cleanup
  candidates with sizes are in the Notion morning summary.
- **Next session:** owner decisions below; then device tests; then the PadMint
  follow-ups (job cap, Homebrew leak warning).

## Rules for this run

- Nothing public may contain translated or decompiled game code, keys, disc/ROM
  images or extracted assets. A positive gate result is a stop.
- No releases, tags, uploads, AltStore changes, visibility changes, posts or
  comments. No deleting drafts, forks, repos, branches or history.
- Game repos are changed only in worktrees under `~/.codex/worktrees`. Primary
  checkouts with other agents' uncommitted work are not touched.
- Public game-repo PRs merge only for docs/manifest/wrapper/AGENTS changes whose
  tree passes the gate and the repo's own checks. Everything else stays a PR.
- Public READMEs do not mention PadMint while it is private.
- One heavy build at a time, none while another agent's build runs, `-j8` max.
  No new full build below 50 GB free; stop below 30 GB. Nothing is deleted for space.

## Levels

| Level | Meaning |
|---|---|
| L0 | Contained: affected downloads hidden |
| L1 | Docs accurate, dead release links fixed, gate rule present, source tree passes gate |
| L2 | Validated `padforge.json`; `padmint plan` succeeds |
| L3 | Source stages run through PadMint with verified outputs |
| L4 | Personal build through PadMint; gate rejects output as personal, passes source |
| L5 | Verified on a physical device (owner) |

## Log

- 23:49 Environment: BlueWake cold trained build compiling (other agent, read-only
  for this run); 71 GB free; load ~230. Active agents: BlueWake, YomiBoy.
- 23:55 PadMint PR #1 merged to `main` (`5361f33`); 26 tests pass.
- 00:10 Decisions + feasibility in `docs/DECISIONS.md` (iPhone module links
  without Apple SDK for one real chunk; Android host-neutral is conditional).
  Core on main `70de086`: manifests, catalog, list/doctor/check-manifest/audit,
  keyless gate (byte-identical results to the private gate), automatic gate on
  every personal output.
- 00:15 Owner decision: KartPad v0.1.0 and v0.2.0-preview.1 releases are still
  public and their tag source archives contain both Wii common keys (not acted on).
- 00:20 KartPad draft PR #336: build-it-yourself docs, retired links, common-key
  note, Builder stage events, padforge.json. Source gate FAILS on existing
  fixtures; `tests/fixtures/rel_report/function.cpp` shares all 3 labels and 11
  non-trivial lines with the translated game function (owner review).
- 00:25 `c21c595`: in-app inputs (no --disc), generic IPA check, MaskPad entry.
- 00:30 GoldenPad PR #38 merged (draft padforge.json, all targets planned).
  Sweep of 23 repos; retired-link PRs merged for HarkinianPad #27, SpaghettiPad
  #17, BrawlerPad #6, BearBirdPad #13, VaultPad #3; open for SunPad #49,
  MeleePad #34, AnnePad #7, CTRPad #40, GalaxyPad #15, SnapPad #7 (see Notion).
- 00:35 MaskPad fresh build through PadMint failed at configure on Xcode 27
  (upstream caches a 10.15 deployment target; Xcode 27 minimum iOS is 15.0).
  Fixed on the MaskPad branch; rebuild running.
- 00:45 HarkinianPad fork → patches: three patches against upstream Shipwright,
  libultraship and ZAPDTR reproduce the fork trees exactly; gate PASS.
  Draft PR #28 (decompiled context lines need owner policy).
- 00:47 MaskPad complete build through PadMint: 17m28s, exit 0, 17.7 MB personal
  IPA, gate FAIL on the IPA as expected, source PASS (draft PR #9, L4 on branch).
- 00:50 PadMint: `steps` manifests, per-step env, `padmint ui` (checked live).
- 00:55 L2 merged: StarshipPad #14, BrawlerPad #7, SpaghettiPad #18,
  DevilTouch #5, BellPad #15, BearBirdPad #14, BarrelPad #13, VaultPad #4.
  Manifests on open PRs: AnnePad #7, SnapPad #7, SunPad #49.
- 01:00 KartPad bootstrap verified; StarshipPad complete build running.
- 01:08 StarshipPad complete build through PadMint from main: 13m38s, exit 0,
  6.9 MB IPA, gate FAIL as expected → L4; manifest marked experimental (#15).
- 01:10–01:27 KartPad through PadMint: fixed two Builder bugs on #336
  (interrupted-bootstrap recovery; work-root vs shared download cache), then a
  complete build: 17m25s, exit 0, 64.8 MB IPA, provenance check passed, gate
  FAIL as intended, **no Wii key in the personal IPA** (confirms #335).
- 01:30 KartPad accepts other dumps after verified extraction (ISO and RVZ
  converted from the pinned WBFS pass; Wind Waker ISO refused). On #336.
- 01:30 Xcode 27 finding: iOS deployment target 14.0 fails CMake's
  try-compile. Affects MaskPad (#9) and HarkinianPad (#30, draft); all other
  ports target iOS 15+ (remaining 14.0/13.0/11.0 values are macOS targets).
- 01:33 Build queue (scratch runner): BrawlerPad running; then HarkinianPad
  (#30 branch), SpaghettiPad, BearBirdPad, DevilTouch, BellPad, BarrelPad,
  VaultPad, BallPad, BananaPad, AnnePad (#7), SnapPad (#7), DinoPad (#7).
- 01:40 BrawlerPad complete build from main (9m47s) → L4; manifest experimental.
- 01:54 HarkinianPad complete build on #30 (13m50s) → L4 on branch; from main
  it fails on Xcode 27, so #30 is required.
- 02:00 GoldenPad L2 blocker: pinned GoldenEye64Recomp fork lacks `us.toml` and
  the TLB-free patch; maintainer builds used a local upstream checkout.
- 02:10 `padmint history --repo` added. Clean engines' public IPAs all pass
  the gate.
- 02:14 SpaghettiPad complete build from main (19m55s) → L4; manifest experimental.
- 02:26 BearBirdPad complete build from main with the owner's ROM (11m48s) → L4.
- 02:28 BellPad complete build from main (1m27s) → L4. Its personal IPA *passes*
  the gate: decompilation code has named functions. Recorded as a gate limit.
- 02:28 Early failures fixed and re-queued: DevilTouch (Xcode 27 target; draft
  #6), BarrelPad (manifest used macOS /bin/bash 3.2; #14 merged), VaultPad
  (empty submodule in worktrees; #5 merged).
- 02:33 BallPad complete build from main (5m02s) → L4 (gate PASS, decompilation).
  Manifests marked experimental: BearBirdPad #15, BellPad #16, BallPad #8.
- 02:30 KartPad build-only Mac target added to #336 (queued for a real build).
- 02:37 BananaPad failed: PaperBoat's Torch submodule repo (JeodC/Torch-LH) was
  deleted upstream; pinned commit still in JeodC/Torch. Draft PaperBoat#1
  (URL only). Blocks fresh clones of PaperPad, BananaPad, SnapPad, DinoPad.
- 02:54–03:10 Fresh-build failures, all diagnosed and fixed on PR branches:
  AnnePad release audit list stale since 5 Aug (fix on #7, verified on the
  built core); SnapPad manifest missed host tools (#7); DinoPad manifest ran its
  safety check too early (#7); BarrelPad `clone-refs.sh` breaks under macOS
  bash 3.2 — the only bash on stock macOS (draft #15); VaultPad host build uses
  macOS 10.13, Xcode 27 needs 12.0+ (draft #6). All re-queued.
- Queue chain: DevilTouch (#6) → KartPad Mac target (#336) → AnnePad (#7) →
  SunPad (#49) → BarrelPad (#15), SnapPad (#7), DinoPad (#7) → VaultPad (#6).
- 03:10 DevilTouch complete build on #6 (6m06s) → L4 on branch (gate PASS).
- 03:15 KartPad Mac target stopped on a missing macOS Dawn archive that
  bootstrap never fetched; fixed on #336 (`217aa57`, hash from the lock).
  AnnePad fix commit had landed on a detached HEAD; recovered and pushed
  (`26ccdd2`). AnnePad patches fetched deps in place (rebuild blocker; noted).
  Re-queued after VaultPad: AnnePad, KartPad Mac.
- 03:22 BarrelPad complete build on #15 (45 s) → L4 on branch.
- 03:21 SunPad: dependencies bootstrapped (8m46s), then Dolphin desktop tools
  failed on the macOS 27 SDK (curl pipe2 availability). Fix on #49
  (`-DHAVE_PIPE2=OFF`); MeleePad has the same configure. Re-queued last.
- 03:27 SnapPad: iOS configure fails on Xcode 27 (SDL2 try-compiles cannot find
  AvailabilityMacros.h) — needs investigation. DinoPad manifest rewritten to the
  README order; re-queued before SunPad.
- 03:37 VaultPad complete build on #6 (9m17s) → L4 on branch (gate PASS on the
  personal output; decompilation-style source).
- 03:57 AnnePad on #7: dependencies, ROM preparation, translation and the iOS
  device build all succeeded (20m25s), then packaging stopped on a missing
  macOS host tool (`build-macos/file_to_c`). The manifest now builds the Mac
  host tools first (#7, `7836a74`); re-queued.
- 04:08 KartPad Mac target on #336: compiled, linked, signed and packaged
  `KartPad.app`, then the package audit failed. Cause: the packager still
  stamped 0.4.17/build 39 while the audit expects the public 0.4.22/build 43.
  Packager defaults updated (`cbf6818`); a copy of that app re-stamped to
  0.4.22/43 with its original Bluetooth entitlement passes the full audit.
  Clean rebuild queued last.
- 04:10 Queue: DinoPad (#7) → SunPad (#49) → AnnePad (#7) → KartPad Mac (#336).
- 04:13 DinoPad on #7: through bootstrap, safety check, host tools and base
  translation, then the Mac host configure demanded restored-edition files.
  Manifest now configures the host with restoration off and builds only the
  two host shader tools (both verified to build; `b460bd6`).
- 04:40 **Xcode 27 root cause for SnapPad:** RT64's CMake forces a 10.15
  (macOS) deployment target on every Apple platform; Xcode 27 rejects it for
  iOS, so every configure check under RT64 fails (the AvailabilityMacros.h
  error was a red herring). One-hunk RT64 patch keeps 10.15 for macOS only.
  With it SnapPad's full iOS configure completes (#7, `779583e`). DinoPad had
  the same unguarded line; same patch added (#7, `c065d01`). AnnePad,
  BearBirdPad, BananaPad and GoldenPad already carry an equivalent fix.
- 04:42 KartPad Mac runner had died with its launching shell; folded into a new
  queue: SunPad (running) → AnnePad → KartPad Mac → DinoPad → SnapPad.
- 04:30 EctoPad (never released, source passes): gate rule merged (#4) → L1.
- 04:30 SunPad passed the step that failed before (Dolphin tools on the macOS
  27 SDK); now translating. Its module build runs `ninja -j 16` internally,
  ignoring the PadMint job cap (noted, harmless tonight).
- 04:35 Clean engines: full git history (all refs) passes the gate for KidPad,
  CaesarPad, EmeraldTablet, RAtouch and DaggerPad; PeonPad passes after
  decompressing its upstream .gz/.bz2 fixtures. Scanner positive control:
  KartPad's flagged fixture fails. Gate rule merged for EmeraldTablet (#1) and
  DaggerPad (#5); PeonPad #8 left open (tree fails closed on the compressed
  fixtures). **Not touched:** CaesarPad (CI uploads IPA artifacts on PRs and
  pushes), KidPad (release-public job on push to main), RAtouch (inherited
  workflows run on any push and include a "latest" development-release job).
  Pushing there could publish, so the rule is an owner item.
- 04:37 **GoldenPad correction:** the recorded L2 blocker was wrong — the
  pinned fork (`7c56979`) contains `us.toml` and both TLB-free patch files,
  byte-identical to upstream `a787fe0` (an ancestor). Draft #39 adds
  `scripts/build-personal-ipa.sh` chaining the maintained steps plus a
  byte-order/SHA-1-checked ROM conversion (verified on the owner's V64: exact
  TLB-free hash) and points `padforge.json` at it. Queued for a full build.
- 04:40 Queue runners launched from a tool shell die when the call ends; the
  surviving ones run in their own session. Relaunched that way. Order:
  SunPad (running) → AnnePad → KartPad Mac → GoldenPad (#39) → DinoPad → SnapPad.
- 04:43 SunPad on #49: past the macOS 27 SDK failure, translated and linked the
  game module (29.5 min), then provisioning failed: pkg-config handed the iOS
  core Homebrew's macOS minizip-ng, so the bundled archive was never built.
  Host leak fixed with `-DUSE_SYSTEM_MINIZIP-NG=OFF` (`eb6a17b`; fresh configure
  confirms bundled). Old iOS core folder renamed aside. Re-queued after GoldenPad.
  PadMint lesson: builds should not depend on what Homebrew has installed;
  worth a doctor warning later.
- 05:17 AnnePad on #7 (33m42s): every stage ran through PadMint and AnnePad's
  own app audit passed; the packager then refused because it only writes under
  `artifacts/`. Manifest fixed (`89208c4`: package there, then export). The
  corrected packaging run on that build produced an 84.7 MB personal IPA; gate
  FAIL as intended → **L3** (L4 needs a clean rerun). AnnePad's iOS step runs
  ninja with no job limit (~38 compilers). KartPad Mac build started 05:17.
- 05:28 **KartPad Mac target complete through PadMint** (#336 at `cbf6818`):
  11m05s, exit 0, 168 MB `KartPad.app` passes the repo's own Mac package audit,
  gate FAIL as intended, no Wii key. KartPad now builds iOS and Mac personal
  copies through PadMint. GoldenPad (#39) build started.
- 05:31 **GoldenPad complete personal build through PadMint** (#39 at
  `fd92db5`): 2m45s, exit 0, all 91 objects fresh (63 recompiled-function
  files), primary IPA audit passed, 7.2 MB IPA, gate FAIL as intended. Repo
  checks pass; tree passes the gate. #39 merged (`8617c3d`), manifest
  experimental → **L4 on main** (was L1 blocked). SunPad (#49) build started.
- 05:34 **SunPad complete personal build through PadMint** (#49 at
  `eb6a17b`): exit 0, bundled minizip-ng, module provisioned, SunPad's own iOS
  package audit passed, 26.8 MB IPA, gate FAIL as intended; check-repository
  passes → **L4 on branch** (script fixes, so #49 is the owner's to merge).
  DinoPad (#7) build started.
- 05:34 DinoPad stopped in 10 s: its safety check pins a checksum of the whole
  patch set, which the new RT64 patch changed. Lock and docs updated
  (`6ed8618`); safety check clean. SnapPad stopped in 20 s: its build folder
  had cached the failed checks from the broken Xcode 27 configure (a fresh
  folder configures fine); stale folder renamed aside. Queue: AnnePad clean
  rerun (running) → DinoPad → SnapPad.
- 06:02 **AnnePad complete personal build through PadMint** (#7 at
  `89208c4`): 26m07s, exit 0, all stages including packaging and export,
  84.7 MB IPA, gate FAIL as intended → **L4 on branch**. DinoPad started.
- 06:02 DinoPad reached the iOS compile, then the base-edition preparation
  demanded the restoration dispatch map, which only the DinoMod restoration
  step creates. It is only needed to undo restoration renames; a base-only
  generation has none. Fixed on #7 (`b8f864a`: skip when nothing to undo,
  still refuse renamed code without the map); base preparation verified.
  Re-queued after SnapPad (running).
- 06:10 **SnapPad complete personal build through PadMint** (#7 at
  `779583e`): 7m42s, exit 0, Xcode 27 configure passes with the RT64 patch,
  7.7 MB IPA, gate FAIL as intended. Formal level stays L0 (source-gate test
  stub policy). Finding: SnapPad's packager prints "Public unsigned SnapPad IPA
  audit passed" for this personal IPA — misleading label. DinoPad started.
- 06:18 DinoPad (#7 at `b8f864a`): Xcode 27 configure passes and the base app
  compiles ("unsigned iOS base app ready"), then the device safety audit fails:
  the compiled-dependency (license notice) inventory only defines the restored
  edition's build folder. Adding a base target changes license-notice data, so
  it is left for owner review → **L3**. Queue finished; no runners remain.

## Level snapshot (01:00)

| Level | Repos |
|---|---|
| L4 (branch) | MaskPad (#9 unmerged) |
| L2 | StarshipPad, BrawlerPad, SpaghettiPad, DevilTouch, BellPad, BearBirdPad, BarrelPad, VaultPad |
| L1 | GoldenPad, HarkinianPad, PaperPad, BallPad, BananaPad, DinoPad, UTP |
| L0, PR open | KartPad #336, SunPad #49, MeleePad #34, AnnePad #7, CTRPad #40, GalaxyPad #15, SnapPad #7 |
| L0, gate policy | KartPad, GalaxyPad, SnapPad, F0X |

## Repo queue

1. PadMint core  2. KartPad  3. MaskPad  4. GoldenPad  5. HarkinianPad
6. StarshipPad, BrawlerPad, F0X  7. MeleePad (review only)  8. SunPad, GalaxyPad,
AnnePad, BearBirdPad, SnapPad, BananaPad, BarrelPad, DinoPad  9. SpaghettiPad,
PaperPad, BellPad, BallPad, DevilTouch  10. VaultPad, UTP  11. CTRPad (private,
PR only)  12. Clean engines  13. Supporting repos (status only)

## Owner decisions pending

1. **KartPad keys in two still-public releases:** v0.1.0 and v0.2.0-preview.1
   are published; their tag source archives contain both Wii common keys.
   Drafting them is reversible; tags/history stay downloadable either way.
2. **Gate policy for references to game functions** (the gate has no exemptions):
   KartPad guard skeleton + synthetic tests + log/record markers; SnapPad test
   stub; GalaxyPad signature anchors in scripts; F0X and HarkinianPad
   (PR #28) decompiled context lines inside patches.
3. **iOS 15 minimum** (Xcode 27 cannot target iOS 14): MaskPad #9,
   HarkinianPad #30, DevilTouch #6. Each builds completely on its branch.
4. **Runtime-only public apps:** feasible in principle (S1); BlueWake, SunPad
   and MeleePad already separate app and game module. Publishing is your call.
5. **Make PadMint public** (public READMEs cannot point to it until then).
6. **Gate rule for CaesarPad, KidPad and RAtouch:** add AGENTS.md yourself (or
   with `[skip ci]`). Their CI builds/uploads IPAs or can create a "latest"
   release on push, so nothing was pushed overnight. Full history of all six
   clean engines passes; EmeraldTablet and DaggerPad are ready to mark Clear.
7. **PeonPad #8** (gate rule): tree fails closed only on compressed upstream
   fixtures that pass when unpacked. Merge, and decide whether to unpack or
   exclude them.
8. **Torch-LH deleted upstream:** draft PaperBoat#1 (URL only) unblocks fresh
   clones of BananaPad and PaperPad.
9. Existing: delete the 157 drafts; retire forks; history rewrites.

## Follow-ups for PadMint itself

- Several repo scripts ignore the job cap (SunPad's module build `-j16`,
  AnnePad's iOS ninja unlimited). Done 06:30: every backend now gets
  `CMAKE_BUILD_PARALLEL_LEVEL` = `--jobs` (test added; 49 pass); scripts
  calling ninja/make/xcodebuild directly still need `{jobs}`.
- Host leaks: Homebrew libraries can be picked up by iOS builds (SunPad's
  minizip-ng). `padmint doctor` could warn about known offenders.
- Detached-HEAD pushes: queue runners detach worktrees; commit on the branch.

## Merge queue (PRs that need an owner or a bootstrapped check)

KartPad #336 · MaskPad #9 · HarkinianPad #30, #28 · DevilTouch #6 ·
BarrelPad #15 · VaultPad #6 · SunPad #49 · MeleePad #34 · AnnePad #7 ·
SnapPad #7 · DinoPad #7 · GalaxyPad #15 · CTRPad #40 · PeonPad #8 ·
PaperBoat #1 · BlueWake #2
