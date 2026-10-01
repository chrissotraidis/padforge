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
        offset, found, symtab, sections = start + 32, [], None, []
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
            elif command == 0x2:  # LC_SYMTAB, offsets are relative to this slice.
                if symtab is not None:
                    raise ValueError("Mach-O contains duplicate symbol tables")
                symtab = struct.unpack(endian + "4I", read(offset + 8, 16, offset + length))
            elif command == 0x19:  # LC_SEGMENT_64; symbol section indexes are 1-based.
                section_count = struct.unpack(endian + "I", read(offset + 64, 4, offset + length))[0]
                if 72 + section_count * 80 > length:
                    raise ValueError("Mach-O section table is truncated")
                for index in range(section_count):
                    sections.append(struct.unpack(endian + "2Q", read(offset + 72 + index * 80 + 32, 16, offset + length)))
            elif command in (0xC, 0x80000018, 0x8000001F):  # loaded/weak/reexported dylib
                name_offset = struct.unpack(endian + "I", read(offset + 8, 4, offset + length))[0]
                if not 24 <= name_offset < length:
                    raise ValueError("Mach-O linked framework name is invalid")
                name = read(offset + name_offset, length - name_offset, offset + length)
                if b"\0" not in name:
                    raise ValueError("Mach-O linked framework name is unterminated")
            offset += length
        if offset != commands_end or len(found) != 1 or not found[0][2]:
            raise ValueError("Mach-O must declare exactly one linked platform and SDK per slice")
        platform, minimum, sdk = found[0]
        if platform not in PLATFORMS:
            raise ValueError("IPA executable targets a simulator or unsupported Apple platform; build for a physical device")
        scene_method = False
        if symtab is not None:
            symbol_offset, symbol_count, string_offset, string_size = symtab
            symbols = read(start + symbol_offset, symbol_count * 16, end)
            strings = read(start + string_offset, string_size, end)
            for index in range(symbol_count):
                name_offset, kind, section, _, address = struct.unpack_from(endian + "IBBHQ", symbols, index * 16)
                if kind & 0xE0 or (kind & 0x0E) != 0x0E:
                    continue  # Only defined section symbols, never imports/debug records.
                if name_offset >= len(strings):
                    raise ValueError("Mach-O symbol name exceeds the string table")
                name_end = strings.find(b"\0", name_offset)
                if name_end < 0:
                    raise ValueError("Mach-O symbol name is unterminated")
                name = strings[name_offset:name_end]
                if name.startswith(b"-[") and name.endswith(b" " + SCENE_CALLBACK + b"]"):
                    if not 1 <= section <= len(sections):
                        raise ValueError("Mach-O scene callback refers to an invalid section")
                    section_address, section_size = sections[section - 1]
                    if not section_address <= address < section_address + section_size:
                        raise ValueError("Mach-O scene callback address exceeds its section")
                    scene_method = True
        return {"platform": PLATFORMS[platform], "minimum_os": version(minimum), "sdk": version(sdk),
                "defined_scene_callback": scene_method}

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


def validate_scene_startup(info, slices):
    manifest = info.get("UIApplicationSceneManifest")
    configs = manifest.get("UISceneConfigurations", {}) if isinstance(manifest, dict) else {}
    application = configs.get("UIWindowSceneSessionRoleApplication", []) if isinstance(configs, dict) else []
    declared = isinstance(application, list) and any(
        isinstance(config, dict) and any(isinstance(config.get(key), str) and config[key].strip()
                                        for key in ("UISceneDelegateClassName", "UISceneStoryboardFile"))
        for config in application)
    # Dynamic configurations need not have a plist manifest (for example SDL3).
    # Framework-provided/inherited/stripped methods cannot be ruled out from the
    # main binary alone. Lack of positive evidence is not proof of legacy startup.
    states = ["declared" if declared else "defined-configuration-callback" if item["defined_scene_callback"]
              else "unverified" for item in slices]
    return {"linked_slices": slices, "scene_startup": states[0] if len(set(states)) == 1 else "unverified",
            "runtime_launch": "not-tested"}
