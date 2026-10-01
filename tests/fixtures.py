"""Synthetic package structure; no runnable game code."""
import hashlib
import json
import plistlib
import struct
import zipfile


def macho(sdk=26, platform=2):
    # Structurally valid metadata only; this fixture is deliberately not runnable.
    return (struct.pack("<8I", 0xFEEDFACF, 0x100000C, 0, 2, 1, 24, 0, 0)
            + struct.pack("<6I", 0x32, 24, platform, 15 << 16, sdk << 16, 0)
            + b"synthetic non-runnable fixture")


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
