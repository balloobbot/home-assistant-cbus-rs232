"""Protocol conformance vectors and malformed wire input."""

import pytest

from custom_components.cbus_rs232.cbus.protocol import (
    RAMP_SECONDS,
    GroupStatus,
    LightingCommand,
    LightingEvent,
    Status,
    byte,
    checksum,
    decode_commands,
    decode_line,
    encode_commands,
    frame,
    level_command,
    lighting_application,
    status_request,
)


def wire(data: bytes) -> bytes:
    return checksum(data).hex().upper().encode()


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (LightingCommand(0x88, 0x79), b"\\0538007988C2g\r"),
        (LightingCommand(0x20, 0x79), b"\\05380079202Ag\r"),
        (LightingCommand(0x14, 1), b"\\0538000114AEg\r"),
    ],
)
def test_published_commands(command: LightingCommand, expected: bytes) -> None:
    assert frame(encode_commands(56, (command,)), "g") == expected


@pytest.mark.parametrize("index", range(16))
@pytest.mark.parametrize("level", [0, 1, 127, 254, 255])
def test_all_ramp_rates(index: int, level: int) -> None:
    command = level_command(8, level, index)
    assert decode_commands(bytes([index * 8 + 2, 8, level])) == (command,)
    assert command.level == level
    assert command.ramp_seconds == RAMP_SECONDS[index]


@pytest.mark.parametrize(("opcode", "level"), [(1, 0), (0x79, 255), (9, None)])
def test_switch_commands(opcode: int, level: int | None) -> None:
    (command,) = decode_commands(bytes([opcode, 8]))
    assert command.level == level
    assert command.ramp_seconds == 0


@pytest.mark.parametrize("application", range(48, 96))
def test_lighting_applications(application: int) -> None:
    assert lighting_application(application) == application


@pytest.mark.parametrize("value", [-1, 256, True, "56", 1.5])
def test_invalid_bytes(value: object) -> None:
    with pytest.raises(ValueError):
        byte(value)


@pytest.mark.parametrize("value", [0, 47, 96, 255])
def test_invalid_applications(value: int) -> None:
    with pytest.raises(ValueError):
        lighting_application(value)


@pytest.mark.parametrize("tag", ["", "gg", "f", "A", "{"])
def test_invalid_tags(tag: str) -> None:
    with pytest.raises(ValueError):
        frame(b"\x05", tag)


def test_frame_limit() -> None:
    assert len(frame(bytes(21), "z")) == 47
    with pytest.raises(ValueError, match="45 characters"):
        frame(bytes(22), "g")


def test_status_request() -> None:
    assert frame(status_request(56), "g") == b"\\05FF007A38004Ag\r"
    assert status_request(56, 32, levels=True) == bytes.fromhex("05FF0073073820")
    with pytest.raises(ValueError):
        status_request(56, 1)


@pytest.mark.parametrize("routing", [b"\x00", b"\x01\x00"])
@pytest.mark.parametrize("header", [5, 0x45, 0x85])
def test_received_commands(routing: bytes, header: int) -> None:
    assert decode_line(
        wire(bytes([header, 1, 56]) + routing + b"\x79\x08")
    ) == LightingEvent(56, (LightingCommand(8, 0x79),))


def test_published_binary_mmi() -> None:
    report = decode_line(b"D8380068AA0140550550001000000014000000000000000000CF")
    assert report.application == 56
    assert report.groups[:9] == (
        GroupStatus(0, Status.ABSENT),
        GroupStatus(1, Status.OFF, 0),
        GroupStatus(2, Status.OFF, 0),
        GroupStatus(3, Status.ON),
        GroupStatus(4, Status.OFF, 0),
        GroupStatus(5, Status.OFF, 0),
        GroupStatus(6, Status.OFF, 0),
        GroupStatus(7, Status.OFF, 0),
        GroupStatus(8, Status.ON),
    )
    assert (
        decode_line(b"D838580000000000000000000000000000000000000000000098")
        .groups[0]
        .group
        == 88
    )
    assert (
        decode_line(b"D638B000000000FF00000000000000000000000000000043")
        .groups[-1]
        .group
        == 255
    )


def test_published_level_mmi() -> None:
    report = decode_line(b"F9073800AAAA000095990000000055550000000000005555555548")
    assert report.groups[:6] == (
        GroupStatus(0, Status.OFF, 0),
        GroupStatus(1, Status.ABSENT),
        GroupStatus(2, Status.ON, 0x57),
        GroupStatus(3, Status.ABSENT),
        GroupStatus(4, Status.ABSENT),
        GroupStatus(5, Status.ON, 255),
    )
    assert decode_line(
        b"F907380B0000000000005555000000000000000000000000000013"
    ).groups[3] == GroupStatus(14, Status.ON, 255)
    assert (
        decode_line(b"F70738160000000000000000000000000000000000000000B4")
        .groups[-1]
        .group
        == 31
    )


@pytest.mark.parametrize("level", range(256))
def test_all_level_encodings(level: int) -> None:
    # Independent lookup from SIUG 7.4, least significant nibble first.
    table = bytes.fromhex("AAA9A6A59A9996956A6966655A595655")
    payload = bytes([0xE5, 7, 56, 8, table[level & 15], table[level >> 4]])
    report = decode_line(wire(payload))
    assert report.groups[0].level == level


@pytest.mark.parametrize("coding", [0, 0x40, 7, 0x47])
def test_extended_coding(coding: int) -> None:
    payload = b"\x55\x55"
    report = decode_line(wire(bytes([0xE5, coding, 56, 8]) + payload))
    assert report.groups[0].status == Status.ON


def test_long_status_and_cal() -> None:
    report = decode_line(
        b"86999900F9003800A8AA0200000000000000000000000000000000000000C3"
    )
    assert report.groups[0] == GroupStatus(0, Status.ABSENT)
    assert report.groups[1] == GroupStatus(1, Status.OFF, 0)
    assert decode_line(b"8604990082300328") is None
    assert decode_line(wire(bytes.fromhex("8604990100"))) is None


@pytest.mark.parametrize("nibble", [0, 1, 2, 3, 4, 7, 8, 11, 12, 13, 14, 15])
def test_corrupted_level(nibble: int) -> None:
    report = decode_line(wire(bytes([0xE5, 7, 56, 0, 0x50 | nibble, 0x55])))
    assert report.groups == (GroupStatus(0, Status.ERROR),)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x02\x08",
        b"\xa2\x08\x00",
        b"\xa3\x08\x00\x01\x01\x08",
        b"\xb4" + bytes(20),
        b"\xa3\x08\x01\x01",
        b"\xa3\x08\x80\x01",
        b"\xa3\x08\x02\x01",
        b"\xa6\x08\x02\x01\x00\x00\x00",
        b"\xa4\x08\x06\x01X",
    ],
)
def test_invalid_commands(payload: bytes) -> None:
    with pytest.raises(ValueError):
        decode_commands(payload)


@pytest.mark.parametrize(
    "payload",
    [
        b"\xa3\x08\x00\x01",
        b"\xa6\x08\x00\x01Hi!",
        b"\xa6\x08\x02\x01\x01\x12\x34",
        b"\xa3\x08\x06\x01",
        b"\xa5\x08\x84\x01\x00\x01",
        b"\xb3\x08\x04\x01" + bytes(16),
    ],
)
def test_label_formats(payload: bytes) -> None:
    (command,) = decode_commands(payload)
    assert command.group == 8
    assert command.level is None
    assert command.ramp_seconds == 0


def test_concatenated_and_reserved_commands() -> None:
    assert decode_commands(b"\x79\x01\x11\xaa\x01\x02") == (
        LightingCommand(1, 0x79),
        LightingCommand(2, 1),
    )
    assert decode_commands(b"\x00") == ()
    with pytest.raises(ValueError, match="reserved"):
        encode_commands(56, (LightingCommand(8, 0x11),))


@pytest.mark.parametrize(
    "payload",
    [
        "A401080020",
        "A80104CA00130C0600",
        "A401080021",
        "A80104AAF05500FF50",
        "A801040000F0F00F00",
        "A401080022",
        "A60102CA010013",
    ],
)
def test_published_dynamic_icon_sequence(payload: str) -> None:
    (command,) = decode_commands(bytes.fromhex(payload))
    assert encode_commands(56, (command,)) == bytes.fromhex("053800" + payload)


def test_reject_inconsistent_published_long_status_length() -> None:
    # SIUG 9.1 uses F8 for 25 bytes; F9 and checksum C3 match SIUG 7.4.
    with pytest.raises(ValueError, match="status length"):
        decode_line(b"86999900F8003800A8AA0200000000000000000000000000000000000000C4")


@pytest.mark.parametrize("line", [b"", b"F", b"GG", b"00 00", b"01", b"FF00"])
def test_invalid_lines(line: bytes) -> None:
    with pytest.raises(ValueError):
        decode_line(line)


@pytest.mark.parametrize(
    "payload",
    [
        bytes.fromhex("C23800"),
        bytes.fromhex("E3073800"),
        bytes.fromhex("E401380055"),
        bytes.fromhex("E407380055"),
        bytes.fromhex("C338FF55"),
        bytes.fromhex("860100"),
        bytes.fromhex("05013800"),
    ],
)
def test_malformed_packets(payload: bytes) -> None:
    with pytest.raises(ValueError):
        decode_line(wire(payload))


@pytest.mark.parametrize(
    "payload",
    [
        bytes.fromhex("05013802007908"),
        bytes.fromhex("05013801017908"),
        bytes.fromhex("0501CA007908"),
        b"\x32\x21\x00",
    ],
)
def test_other_networks_and_applications(payload: bytes) -> None:
    assert decode_line(wire(payload)) is None
