# PadMint status

Updated **3 October 2026**. This page summarizes current delivery and open
limits; the [compatibility matrix](docs/COMPATIBILITY.md) records individual
release recipes and verified host/output combinations.

## Available and checked

- **PadMint v0.2.9** is public for Windows, macOS and Linux. The catalog contains
  22 projects, including 19 with public player recipes and three direct-preview
  or paused entries.
- The released v0.2.9 packages completed KartPad v0.7.3 Android pack builds on
  **macOS ARM64, Ubuntu ARM64 and Windows 11 ARM64**. All three outputs passed
  architecture, 16 KB alignment, app-interface and exported-file hash checks.
  See [recorded builds](docs/COMPATIBILITY.md#recorded-android-pack-builds) for
  the exact environments and their limits.
- Focused setup fixes have merged across the game repositories: required-tool
  checks, SDK selection, selected build-job limits and package verification.
  Existing release recipes remain pinned to their published source versions.
- PadMint source checks and packaged player-flow CI exercise validation,
  recovery and packaging. These checks complement actual game builds.

## Open work

- Physical Android play with the three newly built outputs remains unchecked.
  Native Windows x64, Linux x64 and Intel Mac acceptance also remains open.
  Android phone-only building is experimental.
- StarshipPad's public v0.2.0 recipe still has the reproduced SDK-selection
  failure. [Source fix #22](https://github.com/chrissotraidis/starshippad/pull/22)
  has merged and passed full CI; an updated public recipe is still needed.
- SunPad's public v0.2.0 app lacks scene startup required for its SDK 27 build
  on iOS/iPadOS 27. [Source fix #55](https://github.com/chrissotraidis/sunpad/pull/55)
  passed full iOS/tvOS compilation and a UIKit lifecycle probe. A verified app
  update, physical iOS 27 acceptance and the new crash reporter's cause remain open.
- Most iOS recipes require Apple Silicon and Xcode. Portable resource tools
  alone do not provide a complete Windows or Linux player route.
- AgePad requires an exact supported Steam installation; an updated client was
  rejected in prior checks. SpaghettiPad's off-Mac module work remains a draft.
- [Issue #75](https://github.com/chrissotraidis/padmint/issues/75) tracks wider
  catalog compatibility. Per-game runtime and device issues remain in their
  respective repositories.

Personal game outputs stay private. Content scans are technical checks;
publication and rights decisions require their own review.

## Earlier evidence

The [historical status record](STATUS-HISTORY.md) preserves the previous file
verbatim. Its dated draft, release and pause states describe earlier
checkpoints; use this page and the compatibility matrix for current status.
