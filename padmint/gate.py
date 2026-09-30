"""Release gate: fail if an artifact contains console keys, translated game code,
embedded original program sections, or provenance saying it contains translated
game code.

Ported from the maintainer's private release_gate.py (28 Sep 2026 revision).
Difference: console keys are *not* stored here. Each key is identified by a
4-byte prefix plus the SHA-256 of the full 16-byte key, so this repository can
be published without containing any key. Raw bytes, hex text and C-style byte
lists (including lists wrapped across lines) are detected when all 16 bytes are
present; a list holding only part of a key is not detected.

A PASS means no configured finding was detected. It is a heuristic inspection,
not a provenance database or copyright clearance.

Exit 0 = PASS, 1 = FAIL, 2 = usage error.
"""
import bz2
import hashlib
import io
import json
import lzma
import os
import re
import sys
import tarfile
import zipfile
import zlib

# name: (first four key bytes as hex, SHA-256 of the complete 16-byte key)
KEY_FINGERPRINTS = {
    "Wii retail common key": ("ebe42a22", "de38aeab4fe0c36d828a47e6fd315100e7ce234d3b00aa25e6ad6f5ff2824af8"),
    "Wii Korean common key": ("63b82bb4", "b9f42ca27a1e178f0f14ebf1a05d486fa8db8d08875336c4e6e8dfae29f2901c"),
    "vWii common key": ("30bfc76e", "d830ec964297fdd5a23862d8c8ac851b41ec071e0039abae10f51d5cc8e74308"),
}
# Recompiler-style function names carrying original guest addresses (PowerPC/MIPS),
# including overlay/segment prefixes (func_global_asm_8060..., sub_GAME_7F00...).
TRANSLATED_FN = re.compile(rb"(?<![A-Za-z0-9])_?(?:func|fn|sub|lbl|recomp)_(?:[A-Za-z0-9]+_){0,3}(?:0x)?(?:8[0-9A-Fa-f]{7}|7[Ff][0-9A-Fa-f]{6})(?![0-9A-Za-z])")
TRANSLATED_FN_LIMIT = 50
# Joined at runtime (not constant-folded) so this detector's own source and
# bytecode do not match themselves.
SECTION_MARKERS = [b" ".join(parts) for parts in ((b"Initializing", b"embedded", b"data", b"sections"),)]
SECTION_MARKERS += [b"_".join((b"kData", suffix)) for suffix in (b"_text", b"_rodata", b"StaticR")]
SOURCE_EXTENSIONS = {".c", ".h", ".cc", ".cpp", ".hpp", ".cxx", ".hxx",
                     ".m", ".mm", ".cs", ".rs", ".ll", ".s", ".asm",
                     ".patch", ".diff", ".md", ".rst", ".txt", ".json"}
BYTE_LIST = re.compile(rb"0x[0-9a-f]{2}(?:\s*,\s*0x[0-9a-f]{2}){15,}")
UNREADABLE = b"__release_gate_unreadable__"
EXPANDED_LIMIT = 1 << 30  # largest decompressed stream the gate reads (1 GiB)


def _raw_key_hits(data, fingerprints):
    hits = set()
    for name, (prefix, digest) in fingerprints.items():
        needle = bytes.fromhex(prefix)
        position = data.find(needle)
        while position != -1:
            if hashlib.sha256(data[position:position + 16]).hexdigest() == digest:
                hits.add(name)
                break
            position = data.find(needle, position + 1)
    return hits


def key_findings(data, fingerprints=None):
    """Names of keys present as raw bytes, hex text or a 16-byte C-style list."""
    fingerprints = fingerprints or KEY_FINGERPRINTS
    hits = _raw_key_hits(data, fingerprints)
    low = data.lower()
    for name, (prefix, digest) in fingerprints.items():
        position = low.find(prefix.encode())
        while position != -1 and name not in hits:
            try:
                if hashlib.sha256(bytes.fromhex(low[position:position + 32].decode())).hexdigest() == digest:
                    hits.add(name)
            except ValueError:
                pass
            position = low.find(prefix.encode(), position + 1)
    if b"0x" in low:
        for match in BYTE_LIST.finditer(low):
            values = bytes(int(token, 16) for token in re.findall(rb"0x([0-9a-f]{2})", match.group()))
            hits |= _raw_key_hits(values, fingerprints)
    return sorted(hits)


def function_evidence(name, data):
    """Return binary symbol count, source definitions, and source references.

    Definitions are review signals, not proof of game provenance. Never exempt a
    repository, test directory, or filename: code bodies inside docs/patches count.
    Unknown formats retain conservative symbol scanning.
    """
    matches = list(TRANSLATED_FN.finditer(data))
    if not matches:
        return 0, [], 0
    text_format = os.path.splitext(name)[1].lower() in SOURCE_EXTENSIONS
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        text_format = False
    if not text_format or re.search(rb"[\x00-\x08\x0b\x0e-\x1f]", data):
        return len(matches), [], 0
    # Diff payloads can include definitions in added, removed or context lines.
    source = re.sub(rb"(?m)^[+ -](?![+-]{2})", b"", data) if name.endswith((".patch", ".diff")) else data
    space = re.compile(rb"(?:\s|/\*.*?\*/|//[^\n]*(?:\n|$))*", re.S)

    def skip(pos):
        return space.match(source, pos).end()

    def parameters(pos):
        if pos >= len(source) or source[pos:pos + 1] != b"(":
            return None
        depth = 0
        tokens = re.compile(rb'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|[()]|[^()"\x27/]+|.', re.S)
        for token in tokens.finditer(source, pos):
            value = token.group()
            if value == b"(":
                depth += 1
            elif value == b")":
                depth -= 1
                if depth == 0:
                    return token.end()
        return None

    definitions = []
    for match in TRANSLATED_FN.finditer(source):
        # Include common generated suffixes such as _budget.
        end = re.compile(rb"[A-Za-z0-9_]*").match(source, match.end()).end()
        start = skip(end)
        after = parameters(start)
        definition = False
        if after is not None:
            after = skip(after)
            while True:
                qualifier = re.match(rb"(?:__attribute__|__declspec|noexcept|const|override|final)\b", source[after:])
                if not qualifier:
                    break
                after = skip(after + qualifier.end())
                if source[after:after + 1] == b"(":
                    after = parameters(after)
                    if after is None:
                        break
                    after = skip(after)
            definition = after is not None and source[after:after + 1] == b"{"
        # LLVM IR definitions and assembly labels require review too.
        prefix = source[source.rfind(b"\n", 0, match.start()) + 1:match.start()]
        if re.search(rb"\bdefine\b[^;{}]*@_?$", prefix):
            definition = True
        if source[start:start + 1] == b":" and not prefix.strip():
            definition = True
        if definition:
            definitions.append(source[match.start():end].decode())
    return 0, definitions, max(0, len(matches) - len(definitions))


def walk_artifact(path):
    """Yield (name, bytes) for every file inside the artifact (nested ZIPs opened)."""
    if os.path.isdir(path):
        for directory, _, files in os.walk(path):
            for file in files:
                full = os.path.join(directory, file)
                if os.path.islink(full):
                    continue
                with open(full, "rb") as stream:
                    data = stream.read()
                yield from expand(os.path.relpath(full, path), data)
    else:
        with open(path, "rb") as stream:
            data = stream.read()
        yield from expand(os.path.basename(path), data)


def expand(name, data, depth=0):
    archive_suffix = name.lower().endswith((".zip", ".ipa", ".apk", ".aab"))
    if data[:2] == b"PK" or archive_suffix:
        if depth >= 3:
            yield name, UNREADABLE
            return
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            yield name, UNREADABLE
            return
        for info in archive.infolist():
            if info.is_dir():
                continue
            try:
                member = archive.read(info)
            except (NotImplementedError, RuntimeError, zipfile.BadZipFile):
                member = UNREADABLE
            yield from expand(name + "!" + info.filename, member, depth + 1)
        return
    # gzip, bzip2 and xz streams and tar archives are read in memory (never
    # extracted to disk). Anything else compressed, corrupt or over the limit
    # fails closed.
    if depth < 3:
        inner = decompress(data)
        if inner is not None:
            yield from expand(name + "!" + inner_name(name), inner, depth + 1)
            return
        if data[257:262] == b"ustar":
            try:
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
                    for member in archive:
                        if member.isfile():
                            yield from expand(name + "!" + member.name,
                                              archive.extractfile(member).read(), depth + 1)
            except tarfile.TarError:
                yield name, UNREADABLE
            return
    if (name.lower().endswith((".tar", ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".gz", ".xz", ".bz2", ".7z", ".rar"))
            or data.startswith((b"\x1f\x8b", b"\xfd7zXZ\x00", b"BZh", b"7z\xbc\xaf\x27\x1c", b"Rar!"))
            or data[257:262] == b"ustar"):
        yield name, UNREADABLE
        return
    yield name, data


def decompress(data):
    """One complete gzip, bzip2 or xz stream, or None (other, corrupt, trailing data or too big)."""
    if data.startswith(b"\x1f\x8b"):
        stream = zlib.decompressobj(31)
    elif data.startswith(b"BZh"):
        stream = bz2.BZ2Decompressor()
    elif data.startswith(b"\xfd7zXZ\x00"):
        stream = lzma.LZMADecompressor()
    else:
        return None
    try:
        out = stream.decompress(data, EXPANDED_LIMIT + 1)
    except (OSError, EOFError, ValueError, zlib.error, lzma.LZMAError):
        return None
    done = stream.eof
    rest = stream.unused_data
    if not done or rest or len(out) > EXPANDED_LIMIT:
        return None
    return out


def inner_name(name):
    lower = name.lower()
    if lower.endswith(".tgz"):
        return name.rsplit("/", 1)[-1][:-4] + ".tar"
    for suffix in (".gz", ".bz2", ".xz"):
        if lower.endswith(suffix):
            return name.rsplit("/", 1)[-1][:-len(suffix)]
    return "contents"


def load_reference(reference):
    needles = {}
    for file in sorted(os.listdir(reference)):
        if file.endswith(".bin"):
            with open(os.path.join(reference, file), "rb") as stream:
                blob = stream.read()
            if len(blob) >= 4096:
                middle = len(blob) // 2
                needles[file] = blob[middle:middle + 4096]
    return needles


def check(path, needles=None):
    """Return (findings, translated_count) for one artifact path."""
    needles = needles or {}
    findings = []
    translated = 0
    binary_symbols = 0
    for name, data in walk_artifact(path):
        if data == UNREADABLE:
            findings.append(f"could not inspect {name} (fails closed)")
            continue
        for key in key_findings(data):
            findings.append(f"{key} in {name}")
        count, definitions, _references = function_evidence(name, data)
        binary_symbols += count
        translated += count + len(definitions)
        if definitions:
            findings.append(f"{len(definitions)} address-named source definitions require provenance review in {name}: {', '.join(definitions[:5])}")
        for marker in SECTION_MARKERS:
            if marker in data:
                findings.append(f"embedded original program sections marker '{marker.decode()}' in {name}")
                break
        for blob, needle in needles.items():
            if needle in data:
                findings.append(f"original section {blob} copied into {name}")
        if name.lower().endswith(".json") and b"containsTranslatedGameCode" in data:
            try:
                if json.loads(data).get("containsTranslatedGameCode") is True:
                    findings.append(f"provenance says containsTranslatedGameCode: true ({name})")
            except (ValueError, AttributeError):
                findings.append(f"unparseable provenance mentioning containsTranslatedGameCode ({name})")
    if binary_symbols >= TRANSLATED_FN_LIMIT:
        findings.append(f"{binary_symbols} address-named binary/unknown-format symbols (limit {TRANSLATED_FN_LIMIT})")
    return findings, translated


def audit(paths, reference=None, stream=None):
    stream = stream or sys.stdout
    needles = load_reference(reference) if reference else {}
    failed = False
    for path in paths:
        findings, translated = check(str(path), needles)
        if findings:
            failed = True
            print(f"FAIL {path}", file=stream)
            for finding in sorted(set(findings))[:40]:
                print(f"  - {finding}", file=stream)
        else:
            print(f"PASS {path} (address-named functions: {translated})", file=stream)
    return 1 if failed else 0
