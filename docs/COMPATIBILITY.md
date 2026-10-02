# Build compatibility

Public recipe snapshot: **3 October 2026**, checked with PadMint **v0.2.9**.
The table describes the recipe shipped with each game's latest public release.
It does not promote a declared host to tested gameplay support. See
[catalog-wide compatibility work](https://github.com/chrissotraidis/padmint/issues/75)
for the remaining implementation and acceptance work.

**Choose by the game and device you want to play on.** A Windows or Linux
PadMint download does not make a Mac-only game recipe portable.

- **Experimental:** the recipe permits this combination; check the limitations
  below before downloading tools. This label alone is not proof of a completed build.
- **Planned:** no runnable player route for that combination.
- **Unavailable:** the recipe does not permit the host, or does not declare it.
- Host pairs are **x64 / ARM64**, in that order. Mac here means **Apple Silicon**;
  Intel Mac is listed separately where declared. iOS means iPhone/iPad output,
  subject to each game's device requirements.

## Current player recipes

Every release link is the exact version checked. macOS targets marked planned
are omitted. KartPad's declared macOS target is included for completeness;
guided setup offers its Android and iOS targets only.

| Project and release | Output | Mac ARM64 | Windows x64 / ARM64 | Linux x64 / ARM64 |
|---|---|---|---|---|
| [AgePad v0.1.0](https://github.com/chrissotraidis/agepad/releases/tag/v0.1.0) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [AnnePad v0.2.1](https://github.com/chrissotraidis/annepad/releases/tag/v0.2.1) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [BallPad v1.1.1](https://github.com/chrissotraidis/ballpad/releases/tag/v1.1.1) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [BananaPad v0.2.1](https://github.com/chrissotraidis/bananapad/releases/tag/v0.2.1) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [BarrelPad v0.2.0](https://github.com/chrissotraidis/barrelpad/releases/tag/v0.2.0) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [BearBirdPad v0.2.2](https://github.com/chrissotraidis/bearbirdpad/releases/tag/v0.2.2) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [BellPad v0.2.0](https://github.com/chrissotraidis/bellpad/releases/tag/v0.2.0) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [BlueWake v0.1.0](https://github.com/chrissotraidis/bluewake/releases/tag/v0.1.0) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [BrawlerPad v0.2.0](https://github.com/chrissotraidis/brawlerpad/releases/tag/v0.2.0) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [DinoPad v0.2.0](https://github.com/chrissotraidis/dinopad/releases/tag/v0.2.0) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [GoldenPad v0.2.2](https://github.com/chrissotraidis/goldenpad/releases/tag/v0.2.2) | iOS IPA | Experimental | Planned / Unavailable | Planned / Unavailable |
| [HarkinianPad v0.2.0](https://github.com/chrissotraidis/harkinianpad/releases/tag/v0.2.0) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [KartPad v0.7.3](https://github.com/chrissotraidis/kartpad/releases/tag/v0.7.3) | iOS IPA | Experimental | Experimental / Experimental | Experimental / Experimental |
| [KartPad v0.7.3](https://github.com/chrissotraidis/kartpad/releases/tag/v0.7.3) | macOS app | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [KartPad v0.7.3](https://github.com/chrissotraidis/kartpad/releases/tag/v0.7.3) | Android game pack | Experimental | Experimental / Experimental | Experimental / Experimental |
| [MaskPad v0.2.0](https://github.com/chrissotraidis/maskpad/releases/tag/v0.2.0) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [MeleePad v0.2.1](https://github.com/chrissotraidis/meleepad/releases/tag/v0.2.1) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [PaperPad v0.2.1](https://github.com/chrissotraidis/paperpad/releases/tag/v0.2.1) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [SpaghettiPad v0.2.1](https://github.com/chrissotraidis/spaghettipad/releases/tag/v0.2.1) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [StarshipPad v0.2.0](https://github.com/chrissotraidis/starshippad/releases/tag/v0.2.0) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |
| [SunPad v0.2.0](https://github.com/chrissotraidis/sunpad/releases/tag/v0.2.0) | iOS IPA | Experimental | Unavailable / Unavailable | Unavailable / Unavailable |

**Android as the build host:** only KartPad's phone route is offered, through
Termux and a Linux ARM64 environment. It remains experimental: the recorded
build/export/import check used a phone-sized emulator, not physical Android
hardware or verified racing. Allow about 25 GB free and 8 GB RAM; follow the
[phone guide](../README.md#android-phone-only-experimental). Linux ARM64 CI
does not establish Android/Termux acceptance.

**Intel Mac:** KartPad's Android recipe declares it experimental. The other
Mac build routes in this snapshot require Apple Silicon.

**Direct previews:** [DevilTouch](https://github.com/chrissotraidis/deviltouch/releases/tag/v1.5.5-preview.1)
and [VaultPad](https://github.com/chrissotraidis/vaultpad/releases/tag/v0.1.0-preview.1)
use existing unsigned previews with your own data added in the app. They do
not require a PadMint build; VaultPad is iPad-only. **SnapPad** downloads
remain paused and no public PadMint recipe is available.

## Recorded Android pack builds

On 3 October, the public PadMint **v0.2.9** packages completed the normal
`make kartpad android` command with the public **KartPad v0.7.3 / build 246**
recipe and Europe **RMCP01 revision 0** WBFS input, using two build jobs.
The release selected source `9f973c4ecc46284edfba06eb7dede67f629eb4c5`.

| Build host | Setup | Result |
|---|---|---|
| macOS 26.6.2, ARM64, Apple Python 3.9.6 | Cached tools; fresh game checkout and build | Pack and data export completed |
| Ubuntu 24.04, ARM64, Python 3.12.3 | Provisioned container; fresh PadMint home and tool downloads | Pack and data export completed |
| Windows 11, ARM64, bundled Python 3.13.15 | VM with a fresh PadMint home; Windows x64 NDK compiler under emulation | Pack and data export completed; build phase about 96 minutes |

All three outputs passed ELF/AArch64 and 16 KB alignment checks. Each set of
**2,043** exported game-data files matched the build-cache hashes, and the recomputed
pack interface matched the actual published Android app. The runtime-state
symbol check also passed. Generated personal outputs remain private.

These are completed player commands and static output checks. None of the outputs
was played on a physical Android device in this run. They do not establish
Windows x64, Linux x64, Intel Mac or Android/Termux acceptance. The timings are
observations from different environments, not a performance comparison.

## Known limits and useful evidence

| Route | What is established | What remains |
|---|---|---|
| PadMint v0.2.9 | Released Windows/macOS/Linux ZIPs and checksums; packaged player-flow tests on Windows and Linux | These checks use fixtures and do not build every game |
| KartPad iOS off a Mac | Experimental route previously tried on Windows 11 ARM and Ubuntu with iPhone 14; a Windows 11 Surface Laptop 2 user [reports a v0.7.3 IPA build and updates on iPhone/iPad](https://github.com/chrissotraidis/kartpad/issues/310#issuecomment-5961520278) | The Surface report has no gameplay check and reports an exit opening the import menu; independent Intel/AMD build-and-play and broader device acceptance remain open |
| KartPad iOS folder import | [Reporter confirmed the app-folder workaround](https://github.com/chrissotraidis/kartpad/issues/380#issuecomment-5945178374) on an M2 iPad Air | The disabled Files-picker Open button remains an app bug |
| SpaghettiPad v0.2.1 | [Reporter confirmed both iPhone and iPad work](https://github.com/chrissotraidis/spaghettipad/issues/26#issuecomment-5955452885) after the SDK 27 startup fix | This validates those reported devices, not every host or device |
| SpaghettiPad off-Mac work | [Draft #29](https://github.com/chrissotraidis/spaghettipad/pull/29): native Windows/Linux x64 and ARM64 module builds, resource generation and portable package fixtures | Complete released PadMint recipe, matching runtime delivery and target-device acceptance of each host's output |
| HarkinianPad | [Merged #35](https://github.com/chrissotraidis/harkinianpad/pull/35): resources on five native hosts and full Mac-hosted iOS CI at the reviewed candidate | Portable resources do not establish complete off-Mac apps; published v0.2.0 still uses its old prerequisites |
| StarshipPad | Public v0.2.0 has a reproduced CoreVideo SDK-selection failure; [merged #22](https://github.com/chrissotraidis/starshippad/pull/22) passes candidate and main-branch full CI | Repair is not yet delivered in the public recipe |
| SunPad | Public v0.2.0 SDK 27 app lacks required scene startup for iOS/iPadOS 27; [merged #55](https://github.com/chrissotraidis/sunpad/pull/55) passes full iOS/tvOS compilation and a UIKit lifecycle probe with a stub controller | Public app update and physical iOS 27/game/save acceptance; [#54](https://github.com/chrissotraidis/sunpad/issues/54) reporter OS and crash cause are unconfirmed |
| AgePad | Packages a matching supported Mac Steam installation without Xcode | Updated Steam client was rejected in prior checks; exact-profile support required. Do not bypass fingerprint checks |
| Other Mac recipes | Release manifests declare experimental Mac ARM64 iOS builds | Per-project tools, source/input requirements and device acceptance still apply; no blanket fresh-host or gameplay claim |

For KartPad's confirmed workaround, keep your original data and put a complete
copy inside **Files → On My iPad → KartPad**, for example `KartPad/DATA` with
`sys` and `files` directly inside. Return to **Game Data Required** and tap
**Import from Extracted Folder…**. Do not replace existing app files or saves.

## Before calling a route verified

Record three distinct checks, against the same candidate:

1. **Player path:** the packaged PadMint version, game release/recipe, host OS
   and architecture, input profile, actual command, result and safe rerun.
2. **Output:** architecture, target platform/minimum OS, package integrity,
   source/tool provenance and required content checks. Keep personal outputs private.
3. **Device:** install/update with data preserved, launch, meaningful gameplay,
   audio/input and save/relaunch on the intended device. Record limitations.

After merging, verify the default branch and release-selected recipe again.
A source fix does not change an older release's recipe. Content scans are
technical checks, not rights clearance.

To refresh this table, read the latest public release and its checksummed
`*-padmint.json` for every [catalog entry](../catalog/), including host
architecture and target. Compare with the source manifest and any pending PR,
but keep unreleased capabilities separate. Use the explicit preview links
above for preview-only projects; a missing latest release is not proof of no
preview. Keep unsupported combinations unavailable until their real route is ready.
