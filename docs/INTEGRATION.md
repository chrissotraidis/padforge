# Backend integration, 28 September 2026

PadMint owns a small CLI, subprocess execution, checkout locking, local attempt
records and progress display. BlueWake and KartPad retain their existing build
implementations. No backend source has been copied, and no license has been
inferred for upstream code. There is no plugin loading or arbitrary command option.

**29 Sep update:** backend commands now come from each game's `padmint.json`
(or the interim manifest in `catalog/`), not from code. A manifest can only
fill the fixed placeholders `{repo}`, `{disc}`, `{work}`, `{output}` and
`{jobs}` inside an argument list; values never become shell text. Personal
outputs are run through `padmint audit` automatically and the result is
stored in the attempt record. The table below still describes the backends.

## Current interface

Only an explicitly selected local checkout at a full reviewed commit can run.
Tracked modifications and untracked files cause rejection. This verifies the
selected revision; it does not establish that its code or dependencies are safe.
HEAD and dirty state are rechecked immediately before launching (after disc
hashing), after backend exit and before saving the final result. Changes reject
the attempt and are recorded. This catches persistent concurrent changes, not
edits restored between checks; it is not an immutable checkout or a sandbox.
The caller must trust that checkout and the tools it executes. Ignored dependency
trees are still the backend's responsibility. PadMint never fetches a backend.

An attempt gets a private output directory under the backend's ignored
`build/padmint/`. The reusable workspace key includes a workspace-schema version,
game, complete disc hash, backend commit, target and mod selection. Job count and
source-only/full mode are attempt controls: changing them reuses the same backend
work directory. The complete options, PadMint version and workspace identity/key
remain recorded in every attempt. A new attempt log and output path prevent stale output
from being mistaken for a new successful build. The backend validates its cache.
PadMint does not certify those validations or skip stages itself.

Revision policy is deliberately conservative: a new backend commit selects a new
workspace, including documentation-only commits. Cross-revision reuse requires
adapter-specific proof that all affected outputs are invalidated correctly; the
wrapper does not guess which files are build inputs or use a docs-path exclusion
list. This remains a performance limitation for ordinary app updates. Changes to
disc, target or mods also select separate workspaces. Workspace schema changes
can intentionally invalidate reuse without coupling it to every PadMint version.

The revised key does not automatically migrate or delete workspaces made with the
old all-options key (including the recorded source-only integration below). Their
private outputs remain preserved. Reuse applies to attempts made with the new key
and the same workspace root. No live BlueWake build was started for this change.
Synthetic tests prove source-preflight/full reuse, changed-jobs reuse with separate
records, and revision isolation; real-game timing savings have not been measured.

The checkout-wide advisory lock coordinates PadMint processes, including
shared dependency caches. It cannot stop builds started directly or by another
tool. Do not run those concurrently in the same checkout. Use a separate clean
checkout when another agent is editing or building there.

Backend events are nested under `backend_event` without pretending all stages
implement the proposed contract. Wrapper events describe the whole attempt;
their elapsed time is separate from backend stage time. Logs/events are local
and may contain personal paths; no diagnostic export is implemented. The small
record contains identifiers and hashes, not full backend/toolchain provenance.
The final event stream is drained to EOF after success, failure or cancellation,
including bursts larger than 64 KiB. Live polls remain bounded.
Cancellation sends TERM to the process group, allowing 20 seconds for cleanup.
BlueWake's nested stage/training sessions must forward cancellation correctly;
arbitrary detached descendants cannot be guaranteed terminated by this wrapper.

Before recording a packaged result, PadMint checks ZIP integrity, unambiguous
app metadata, the declared executable's Mach-O load commands and backend
provenance. BlueWake additionally requires its fixed module and matching hash,
clean source revision and local-training marker. KartPad provenance must match
the disc hash and known profile; its translated code is linked into the app
executable rather than a separately declared BlueWake-style module. These are
minimal structural checks, not signing, loadability, training-quality or runtime
validation. Synthetic executable fixtures intentionally are not runnable apps.

Every IPA, including recipes with `check: none`, also records the actual linked
platform, minimum OS and SDK for every executable slice. Simulator and non-device
platforms are rejected. For SDK 27+ builds, declared application scenes or a
defined instance method implementing UIKit's scene configuration callback provide
static startup evidence. Dynamic configurations (including SDL3) do not need a
scene manifest. Raw selector strings, imported symbols and protocol metadata do
not establish an implementation.
Without positive evidence, scene startup is recorded as `unverified` and SDK 27+
builds show a warning. A launch-method symbol alone cannot prove legacy startup:
frameworks may provide inherited callbacks, and symbols may be stripped. This
includes SwiftUI-managed startup, without assuming a framework import proves
which delegate owns startup. Confirmed startup failures need game integration
fixes and runtime checks, not rejection based solely on a missing plist or symbol.
Changing the minimum OS does not remove the linked-SDK requirement. Every result
leaves runtime launch `not-tested`; signing, launch and gameplay need actual tests.

## Concrete gaps

| Backend | What can be connected now | Remaining validation or implementation |
| --- | --- | --- |
| BlueWake | `scripts/builder/build.sh`, `--out`, `--ipa`, `--jobs`, `--source-only`, `--no-mods`, local `--train-pgo`; stage events in `logs/progress.jsonl` | Stage IDs are subprocess/log names, not the full proposed stage graph. No complete result contract. Local PGO route, profile provenance, cache validation and matched hardware performance remain open. Existing suppression flags for profile mismatches need review by BlueWake owner. |
| KartPad | `scripts/build-user-ipa.sh build IMAGE --work-root DIR --output IPA --jobs N`; exact image profile selection; backend cache and IPA provenance | Jobs accepts 1–8. No structured stage events, source-only switch, mod-selection switch or platform selector. `build` verifies dependencies but does not bootstrap them; run backend bootstrap separately. Runtime/dependency work also uses repository-local build paths. Existing audit/provenance does not establish end-to-end release readiness. |

KartPad's primary checkout has extensive concurrent edits, including its Python
pipeline. The interface review used that working tree and compared the handoff
reference (`e1908b0f...`); it is not approval of a new backend revision. BlueWake
was at `0f07521fb591dddbabe8c6e612f2be8da3a565b0` with active edits to its builder.
Neither dirty primary checkout was executed or modified for this work.

BlueWake's owner subsequently reported focused SIGINT/SIGTERM tests proving
child cleanup and cancellation events, and a real CMake/Ninja test proving
profile changes trigger rebuilds under paths with spaces. Those are backend
owner results, not an end-to-end PadMint build. The owner also reports the iPad
is unavailable: current work is Mac-only and synthetic tests must not launch a
concurrent BlueWake build. Hardware acceptance remains deferred.

## Acceptance still open

### Completed source-only integration

On 28 September, one real run through PadMint used clean BlueWake revision
`36b8488e7887e4f3ea4600c7d09790a24c241021`, the owner's archived disc and a
separate ignored `build/padmint-source-check` workspace. It exited 0 with
`source_only: true`, `status: completed` and `checkout_check: before-record-passed`.
The checkout remained clean at the same revision. All seven backend stage
start/completion pairs were relayed. Elapsed time was 11.87 seconds after disc
hashing, using already established dependencies; this is not first-run timing.

Translation reported 206 DOL chunks and 415 RELs. Composite validation passed
748 chunks, 415 REL modules and 417 code ranges; digest
`54f54434c3f9c899d43a96373dc0b4c1aed0e50db8b820b9698dfa76571a770a`
matched the backend's verified tree. The private record is under configuration
`c2422a29c4c4a907f4285098de0c553624955e45a6323e55f135a0a6da35ee16`,
run `89c6fe7bfc864577a09e2b2c1336cb10`. Outputs stay local and ignored.
Helper tools built as part of the backend; no game compile, IPA packaging,
training, installation or device operation was performed by this integration.

### Remaining checks

1. BlueWake owner finishes local training and hardware acceptance, stabilizes a
   clean revision and reviews nested-process cancellation and cache reuse.
2. Exercise that revision through PadMint with an unsupported disc, interrupted
   translation/compile, then a complete fresh local build; verify IPA contents,
   embedded provenance, mod invalidation and local profile generation.
3. Add stage/result events to KartPad in a separate scoped change after its
   concurrent work settles; preserve its validation and cache logic.
4. Add and test Mac and Android target adapters. Windows support is not implemented.
   KartPad's requested four-platform relaunch remains blocked on those paths.

Synthetic runner tests establish orchestration behavior only. They do not prove
gameplay, performance, backend correctness or copyright clearance. Public
publication remains paused; personal IPAs and optimization profiles stay local.
