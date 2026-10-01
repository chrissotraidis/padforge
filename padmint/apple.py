"""Inspect the linked Apple platform and SDK, without invoking host tools."""
import struct


PLATFORMS = {2: "ios", 3: "tvos", 11: "visionos"}
SCENE_CALLBACK = b"application:configurationForConnectingSceneSession:options:"


def version(value):
    return f"{value >> 16}.{(value >> 8) & 255}.{value & 255}"


def linked_sdks(stream, size):
    def read(offset, length, end):
        if offset < 0 or length < 0 or offset + length > end:
            raise ValueError("Mach-O load commands exceed the executable bounds")
        stream.seek(offset)
        data = stream.read(length)
        if len(data) != length:
            raise ValueError("Mach-O executable is truncated")
        return data

    def thin(start, length):
        end = start + length
        magic = read(start, 4, end)
        endian = {b"\xcf\xfa\xed\xfe": "<", b"\xfe\xed\xfa\xcf": ">"}.get(magic)
        if endian is None:
            raise ValueError("IPA requires a supported 64-bit Mach-O executable")
        header = struct.unpack(endian + "8I", read(start, 32, end))
        if header[1] != 0x100000C or header[3] != 2:
            raise ValueError("IPA main executable must be an arm64 device executable")
        count, command_bytes = header[4:6]
        if command_bytes > 16 * 1024 * 1024 or count > command_bytes // 8:
            raise ValueError("Mach-O load command table is invalid")
        commands_end = start + 32 + command_bytes
        if commands_end > end:
            raise ValueError("Mach-O load command table is truncated")
        offset, found = start + 32, []
        for _ in range(count):
            command, length = struct.unpack(endian + "2I", read(offset, 8, commands_end))
            if length < 8 or offset + length > commands_end:
                raise ValueError("Mach-O load command size is invalid")
            if command == 0x32:  # LC_BUILD_VERSION
                platform, minimum, sdk, tools = struct.unpack(endian + "4I", read(offset + 8, 16, offset + length))
                if 24 + tools * 8 > length:
                    raise ValueError("Mach-O build version tools are truncated")
                found.append((platform, minimum, sdk))
            elif command in (0x25, 0x2F):  # LC_VERSION_MIN_IPHONEOS / TVOS
                minimum, sdk = struct.unpack(endian + "2I", read(offset + 8, 8, offset + length))
                # Legacy commands distinguish simulator by CPU architecture.
                simulator = header[1] in (7, 0x1000007)
                found.append((7 if simulator else 2 if command == 0x25 else 3, minimum, sdk))
            offset += length
        if offset != commands_end or len(found) != 1 or not found[0][2]:
            raise ValueError("Mach-O must declare exactly one linked platform and SDK per slice")
        platform, minimum, sdk = found[0]
        if platform not in PLATFORMS:
            raise ValueError("IPA executable targets a simulator or unsupported Apple platform; build for a physical device")
        return {"platform": PLATFORMS[platform], "minimum_os": version(minimum), "sdk": version(sdk)}

    magic = read(0, 4, size)
    fats = {b"\xca\xfe\xba\xbe": (">", False), b"\xbe\xba\xfe\xca": ("<", False),
            b"\xca\xfe\xba\xbf": (">", True), b"\xbf\xba\xfe\xca": ("<", True)}
    if magic not in fats:
        return [thin(0, size)]
    endian, wide = fats[magic]
    count = struct.unpack(endian + "I", read(4, 4, size))[0]
    if not 1 <= count <= 32:
        raise ValueError("Mach-O universal architecture count is invalid")
    stride = 32 if wide else 20
    table_end = 8 + count * stride
    slices, spans = [], []
    for index in range(count):
        values = struct.unpack(endian + ("2I2Q2I" if wide else "5I"), read(8 + index * stride, stride, size))
        start, length = values[2:4]
        if start < table_end or start + length > size or any(start < b and a < start + length for a, b in spans):
            raise ValueError("Mach-O universal slices overlap or exceed the executable bounds")
        spans.append((start, start + length))
        slices.append(thin(start, length))
    if len({item["platform"] for item in slices}) != 1:
        raise ValueError("Mach-O executable slices target different Apple platforms")
    return slices


def validate_scene_startup(info, slices, has_callback):
    manifest = info.get("UIApplicationSceneManifest")
    configs = manifest.get("UISceneConfigurations", {}) if isinstance(manifest, dict) else {}
    application = configs.get("UIWindowSceneSessionRoleApplication", []) if isinstance(configs, dict) else []
    declared = isinstance(application, list) and any(
        isinstance(config, dict) and (config.get("UISceneDelegateClassName") or config.get("UISceneStoryboardFile"))
        for config in application)
    programmatic = isinstance(manifest, dict) and has_callback
    if any(int(item["sdk"].split(".")[0]) >= 27 for item in slices) and not (declared or programmatic):
        raise ValueError("Apple SDK 27+ requires UIKit scene startup. This IPA has no application scene "
                         "configuration or scene manifest with a configuration callback; it can terminate at launch "
                         "on OS 27. Update the game's UIKit/SDL integration and rebuild. "
                         "Changing the minimum OS or installing a different PadMint version does not fix this IPA.")
    return {"linked_slices": slices, "scene_startup": "declared" if declared else
            "manifest-and-configuration-callback-present" if programmatic else "legacy", "runtime_launch": "not-tested"}
