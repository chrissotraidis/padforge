"""Check the player's game file before PadMint downloads anything large.

A disc game's manifest may list the disc IDs (and revisions) its builder
supports. `nodtool info` reads the disc header in milliseconds, so a player
with another region or another game hears why at once, in plain words, instead
of after gigabytes of tools and minutes of extraction.
"""
import re
import os
import shutil
import subprocess

from . import tools

DISC_TYPES = {"wii-disc", "gamecube-disc"}
# The fourth character of a Wii or GameCube disc ID is its region.
REGIONS = {"E": "USA", "P": "Europe", "J": "Japan", "K": "Korea", "W": "Taiwan",
           "D": "Germany", "F": "France", "S": "Spain", "I": "Italy", "U": "Australia"}


def region(game_id):
    return REGIONS.get(game_id[3:4], "another region")


SF_DATALESS = 0x40000000  # macOS: the file's contents are in iCloud, not on this Mac
CLOUD_ONLY = ("{name} is stored only in iCloud, so it is not on this Mac yet. In Finder, "
              "right-click it, choose Download Now, wait until it finishes, then try again.")


def cloud_only(path):
    """True for a file whose contents are not on this computer (iCloud Drive "Optimize Storage").
    Reading it would start a multi-gigabyte download with no progress shown."""
    try:
        return bool(getattr(os.stat(path), "st_flags", 0) & SF_DATALESS)
    except OSError:
        return False


def require_local(path):
    if cloud_only(path):
        raise ValueError(CLOUD_ONLY.format(name=path.name))


def expected_input(manifest):
    """The disc input that names the IDs its builder supports, if any."""
    return next((item for item in manifest["inputs"]
                 if item.get("type") in DISC_TYPES and item.get("game_ids")), None)


def read_disc(path, nodtool):
    """(title, game ID, revision) from the disc header; ValueError if unreadable."""
    try:
        result = subprocess.run([nodtool, "info", str(path)], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"PadMint could not read {path.name}: {error}") from error
    text = result.stdout
    game_id = re.search(r"^Game ID: ([0-9A-Z]{6})", text, re.M)
    if result.returncode or not game_id:
        detail = (result.stderr or text).strip().splitlines()
        raise ValueError(
            f"PadMint could not read {path.name} as a Wii or GameCube disc image"
            + (f" ({detail[-1]})" if detail else "") + ". The file may be incomplete, for example "
            "still downloading or stored only in iCloud, or it may not be a disc image.")
    title = re.search(r"^Title: (.+)$", text, re.M)
    revision = re.search(r"^Disc \d+, Revision (\d+)", text, re.M)
    return (title.group(1).strip() if title else "",
            game_id.group(1), int(revision.group(1)) if revision else None)


def check(manifest, disc, nodtool=None):
    """Stop with a plain message unless the disc is one the game's builder supports.

    Returns a one-line description of an accepted disc, or None when the
    manifest names no disc IDs (or nodtool is not available to read them).
    """
    item = expected_input(manifest)
    nodtool = nodtool or shutil.which("nodtool")
    if item is None or disc is None or nodtool is None:
        return None
    require_local(disc)
    title, game_id, revision = read_disc(disc, nodtool)
    wanted = item["game_ids"]
    name = manifest["name"]
    supported = ", ".join(f"{region(gid)} ({gid})" for gid in wanted)
    if game_id not in wanted:
        if any(game_id[:3] == gid[:3] for gid in wanted):
            raise ValueError(f"Your file is the {region(game_id)} version ({game_id}). {name} can only be "
                             f"made from this version for now: {supported}. Other versions are not supported yet.")
        raise ValueError(f"Your file is {title or 'another game'} ({game_id}), not the game {name} is made "
                         f"from. {name} needs your own {manifest['game']}.")
    revisions = item.get("revisions")
    if revisions and revision not in revisions:
        wanted_revisions = " or ".join(str(value) for value in revisions)
        raise ValueError(f"Your file is revision {revision} of {game_id}. {name} can only be made from "
                         f"revision {wanted_revisions} for now.")
    return f"{title or game_id} ({game_id}, {region(game_id)}, revision {revision})"


def check_before_tools(manifest, target, disc, host):
    """Install only nodtool (a few MB) and check the disc before the large tools."""
    if expected_input(manifest) is None or disc is None:
        return None
    if "nodtool" in target.get("tools", []):
        tools.install(["nodtool"], host)
        return check(manifest, disc, tools.executable("nodtool", host))
    return check(manifest, disc)
