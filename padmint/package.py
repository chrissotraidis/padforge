"""Minimal IPA structure/provenance checks, not signing or gameplay acceptance."""
import hashlib
import json
from pathlib import PurePosixPath
import plistlib
import stat
import zipfile
from xml.parsers.expat import ExpatError
from .apple import SCENE_CALLBACK, linked_sdks, validate_scene_startup


def validate_ipa(path, game, revision, disc_sha256):
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("IPA has duplicate entries")
            for name in names:
                if name.startswith("/") or ".." in PurePosixPath(name).parts or "\\" in name:
                    raise ValueError("IPA contains an unsafe entry path")
            if archive.testzip() is not None:
                raise ValueError("IPA failed ZIP integrity validation")
            plists = [name for name in names if name.startswith("Payload/")
                      and len(name.split("/")) == 3 and name.endswith(".app/Info.plist")]
            if len(plists) != 1:
                raise ValueError("IPA must contain exactly one top-level app Info.plist")
            app = plists[0].rsplit("/", 1)[0]

            def member(name):
                info = archive.getinfo(name)
                if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16) or info.file_size == 0:
                    raise ValueError("Required IPA member must be a nonempty regular file")
                return info

            def metadata(name):
                if member(name).file_size > 1024 * 1024:
                    raise ValueError("IPA metadata exceeds 1 MiB")
                return archive.read(name)

            def executable_hash(name):
                member(name)
                with archive.open(name) as stream:
                    magic = stream.read(4)
                    if magic not in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf",
                                     b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
                                     b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"):
                        raise ValueError("IPA executable/module has no supported Mach-O header")
                    digest = hashlib.sha256(magic)
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                    return digest.hexdigest()

            info = plistlib.loads(metadata(plists[0]))
            if not isinstance(info, dict):
                raise ValueError("IPA Info.plist must be a dictionary")
            executable = info.get("CFBundleExecutable")
            if (not isinstance(executable, str) or not executable
                    or executable in (".", "..") or "/" in executable or "\\" in executable):
                raise ValueError("IPA has no valid declared executable")
            if not isinstance(info.get("CFBundleIdentifier"), str) or not info["CFBundleIdentifier"]:
                raise ValueError("IPA has no bundle identifier")
            binary_hash = executable_hash(app + "/" + executable)
            with archive.open(app + "/" + executable) as stream:
                slices = linked_sdks(stream, archive.getinfo(app + "/" + executable).file_size)
            # A configuration callback can supply scenes for a declared scene manifest.
            # Its presence is a static declaration, not proof that launch succeeds.
            with archive.open(app + "/" + executable) as stream:
                has_callback, tail = False, b""
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    data = tail + chunk
                    if SCENE_CALLBACK in data:
                        has_callback = True
                        break
                    tail = data[-len(SCENE_CALLBACK):]
            apple = validate_scene_startup(info, slices, has_callback)
            if game is None:
                return {"check": "minimal-ipa-structure", "executable_sha256": binary_hash,
                        "apple_compatibility": apple}
            provenance_name = (app + "/BuilderProvenance.json" if game == "bluewake"
                               else "KartPadBuilderProvenance.json")
            provenance = json.loads(metadata(provenance_name))
            if not isinstance(provenance, dict):
                raise ValueError("IPA provenance must be an object")
            if game == "bluewake":
                if (provenance.get("profile") != "bluewake"
                        or provenance.get("source_commit") != revision
                        or provenance.get("source_modified") is not False
                        or provenance.get("local_training") is not True
                        or provenance.get("containsTranslatedGameCode") is not True
                        or provenance.get("packaging_commit", revision) != revision):
                    raise ValueError("BlueWake provenance does not match the requested build")
                # Fixed adapter contract, not an arbitrary path from the archive.
                module_hash = executable_hash(app + "/Frameworks/gGZLE01_recomp.dylib")
                if module_hash != provenance.get("module_sha256"):
                    raise ValueError("BlueWake module hash does not match provenance")
            elif (provenance.get("schemaVersion") != 1
                  or provenance.get("profileId") != "mkwii-rmcp01-rev0"
                  or provenance.get("imageSHA256") != disc_sha256
                  or provenance.get("containsUserSuppliedTranslatedCode") is not True):
                raise ValueError("KartPad provenance does not match the requested disc/profile")
            return {"check": "minimal-ipa-structure-and-provenance", "executable_sha256": binary_hash,
                    "apple_compatibility": apple,
                    "provenance_sha256": hashlib.sha256(archive.read(provenance_name)).hexdigest()}
    except (zipfile.BadZipFile, KeyError, plistlib.InvalidFileException,
            json.JSONDecodeError, UnicodeError, RuntimeError, ExpatError) as error:
        raise ValueError("IPA is malformed or missing required package metadata") from error
