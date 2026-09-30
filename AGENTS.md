# Agent instructions

- This repository holds only the shared Builder: its pipeline, profiles, tests and docs. Never commit or upload game code (translated or decompiled), disc images, ROMs, extracted game files, saves, console keys or personal builds.
- Before any public release, every asset must pass `python3 -m padmint audit <asset>` (and the private `~/.codex/release-gate/release_gate.py` while it remains the reference). A failure is a stop, not a note.
- Never commit key bytes, key hex or key byte lists, even in tests or gate code. Identify keys by prefix + SHA-256 only (see `padmint/gate.py`). Build detector strings at runtime so this repository passes its own gate.
- Game-specific logic stays in each game's repository behind its `padmint.json`; PadMint owns validation, running, progress, records and the gate. There must be only one Builder.
- Only document commands that exist. Label platforms as verified, experimental or planned and do not upgrade a label without a recorded run.
- Keep it simple: a generic runner plus one small manifest per game.
