"""Synthetic package structure; no runnable game code."""
import hashlib
import json
import plistlib
import struct
import zipfile


def macho(sdk=26, platform=2, symbols=(), swiftui=False):
    # Structurally valid metadata only; this fixture is deliberately not runnable.
    commands = struct.pack("<6I", 0x32, 24, platform, 15 << 16, sdk << 16, 0)
    count = 1
    if swiftui:
        name = b"/System/Library/Frameworks/SwiftUI.framework/SwiftUI\0"
        length = (24 + len(name) + 7) // 8 * 8
        commands += struct.pack("<6I", 0xC, length, 24, 0, 0, 0) + name.ljust(length - 24, b"\0")
        count += 1
    data, strings = b"", b"\0"
    if symbols:
        for name, kind, section in symbols:
            data += struct.pack("<IBBHQ", len(strings), kind, section, 0, 0x1000)
            strings += name + b"\0"
        # One synthetic four-byte code section, then the symbol and string tables.
        code_offset = 32 + len(commands) + 152 + 24
        commands += struct.pack("<2I16s4Q4I", 0x19, 152, b"__TEXT", 0x1000, 4, code_offset, 4, 7, 5, 1, 0)
        commands += struct.pack("<16s16s2Q8I", b"__text", b"__TEXT", 0x1000, 4, code_offset, 2, 0, 0, 0x80000400, 0, 0, 0)
        offset = code_offset + 4
        commands += struct.pack("<6I", 0x2, 24, offset, len(symbols), offset + len(data), len(strings))
        count += 2
        data = b"\0" * 4 + data + strings
    return (struct.pack("<8I", 0xFEEDFACF, 0x100000C, 0, 2, count, len(commands), 0, 0)
            + commands + data + b"synthetic non-runnable fixture")


def legacy_macho(sdk=27):
    return macho(sdk, symbols=((b"-[TestDelegate application:didFinishLaunchingWithOptions:]", 0x0E, 1),))


def entries(game="kartpad", revision="a" * 40, disc=b"synthetic input, not game data"):
    app = "Payload/Synthetic.app/"
    binary = macho()
    result = {app + "Info.plist": plistlib.dumps({"CFBundleExecutable": "Synthetic",
                                               "CFBundleIdentifier": "invalid.test.synthetic"}),
              app + "Synthetic": binary}
    if game == "kartpad":
        provenance = {"schemaVersion": 1, "profileId": "mkwii-rmcp01-rev0",
                      "imageSHA256": hashlib.sha256(disc).hexdigest(),
                      "containsUserSuppliedTranslatedCode": True}
        name = "KartPadBuilderProvenance.json"
    else:
        result[app + "Frameworks/gGZLE01_recomp.dylib"] = binary
        provenance = {"profile": "bluewake", "source_commit": revision,
                      "source_modified": False, "local_training": True,
                      "containsTranslatedGameCode": True,
                      "module_sha256": hashlib.sha256(binary).hexdigest()}
        name = app + "BuilderProvenance.json"
    result[name] = json.dumps(provenance).encode()
    return result


def write_ipa(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
