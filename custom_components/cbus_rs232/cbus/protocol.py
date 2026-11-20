"""Wire formats from CBUS-SIUG 1.17 and CBUS-APP/02 1.5."""

from dataclasses import dataclass
from enum import IntEnum

from .applications import (
    DEFINITIONS,
    LOAD_APPLICATIONS,
    ApplicationEvent,
    decode_application,
)

RAMP_SECONDS = (0, 4, 8, 12, 20, 30, 40, 60, 90, 120, 180, 300, 420, 600, 900, 1020)
PAIRS = {5: 3, 6: 2, 9: 1, 10: 0}


class Status(IntEnum):
    ABSENT = 0
    ON = 1
    OFF = 2
    ERROR = 3


@dataclass(frozen=True)
class LightingCommand:
    group: int
    opcode: int
    data: bytes = b""

    @property
    def level(self) -> int | None:
        if self.opcode == 0x01:
            return 0
        if self.opcode == 0x79:
            return 255
        if self.opcode < 0x80 and self.opcode & 7 == 2:
            return self.data[0]
        return None

    @property
    def ramp_seconds(self) -> int:
        if self.opcode < 0x80 and self.opcode & 7 == 2:
            return RAMP_SECONDS[self.opcode >> 3]
        return 0


@dataclass(frozen=True)
class LightingEvent:
    application: int
    commands: tuple[LightingCommand, ...]


@dataclass(frozen=True)
class GroupStatus:
    group: int
    status: Status
    level: int | None = None


@dataclass(frozen=True)
class StatusReport:
    application: int
    groups: tuple[GroupStatus, ...]
    levels: bool = False


def byte(value: int, maximum: int = 255) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"Expected an integer from 0 to {maximum}")
    return value


def lighting_application(application: int) -> int:
    if not 0x30 <= byte(application) <= 0x5F:
        raise ValueError("Lighting application must be from 48 to 95")
    return application


def load_application(application: int) -> int:
    if byte(application) not in LOAD_APPLICATIONS:
        raise ValueError("Not a load-control application")
    return application


def checksum(data: bytes) -> bytes:
    return data + bytes([-sum(data) & 255])


def frame(data: bytes, tag: str) -> bytes:
    if len(tag) != 1 or not "g" <= tag <= "z":
        raise ValueError("Confirmation tag must be from g to z")
    encoded = checksum(data).hex().upper().encode() + tag.encode()
    if len(encoded) > 45:
        raise ValueError("PCI command exceeds 45 characters")
    return b"\\" + encoded + b"\r"


def encode_commands(application: int, commands: tuple[LightingCommand, ...]) -> bytes:
    payload = b"".join(bytes([c.opcode, byte(c.group, 254)]) + c.data for c in commands)
    # Validate the whole batch before sending any of it to the bus.
    if decode_commands(payload) != commands:
        raise ValueError("Cannot transmit reserved lighting commands")
    return bytes([5, load_application(application), 0]) + payload


def level_command(group: int, level: int, ramp_index: int = 0) -> LightingCommand:
    return LightingCommand(
        byte(group, 254), (byte(ramp_index, 15) << 3) | 2, bytes([byte(level)])
    )


def status_request(application: int, start: int = 0, *, levels: bool = False) -> bytes:
    load_application(application)
    if byte(start) % 32:
        raise ValueError("Status block must start at a multiple of 32")
    command = b"\x73\x07" if levels else b"\x7a"
    return b"\x05\xff\x00" + command + bytes([application, start])


def decode_commands(payload: bytes) -> tuple[LightingCommand, ...]:
    if not payload:
        raise ValueError("Empty lighting message")
    commands = []
    while payload:
        opcode = payload[0]
        length = opcode & (31 if opcode & 128 else 7)
        if len(payload) < length + 1:
            raise ValueError("Truncated lighting command")
        args, payload = payload[1 : length + 1], payload[length + 1 :]
        if opcode in (1, 9, 0x79) or opcode < 128 and opcode & 7 == 2:
            commands.append(LightingCommand(args[0], opcode, args[1:]))
        elif opcode & 0xE0 == 0xA0:
            if length < 3 or length > 19 or payload:
                raise ValueError("Label must be last and contain 3 to 19 arguments")
            options = args[1]
            kind = options & 6
            icon_control = options == 8 and args[2:] in (
                b"\x00\x20",
                b"\x00\x21",
                b"\x00\x22",
            )
            if not icon_control and (options & 0x19 or options & 0x80 and kind != 4):
                raise ValueError("Reserved label options")
            if kind == 2 and (length != 6 or args[3] != 1):
                raise ValueError("Invalid predefined icon")
            if kind == 6 and length != 3:
                raise ValueError("Preferred language cannot contain text")
            commands.append(LightingCommand(args[0], opcode, args[1:]))
        # Reserved commands are skipped by their encoded length (APP/02 2.9.2).
    return tuple(commands)


def _status(data: bytes) -> StatusReport:
    header = data[0]
    extended = header >= 0xE0
    # The CAL length excludes both its header and the serial checksum.
    if len(data) != (header & 31) + 2:
        raise ValueError("Invalid status length")
    if extended:
        if len(data) < 6 or data[1] not in (0, 0x40, 7, 0x47):
            raise ValueError("Invalid extended status coding")
        coding, application, start = data[1:4]
        payload = data[4:-1]
    else:
        if len(data) < 5:
            raise ValueError("Truncated status report")
        coding = 0
        application, start = data[1:3]
        payload = data[3:-1]
    groups = []
    if coding & 7 == 7:
        if len(payload) % 2:
            raise ValueError("Truncated level status")
        for offset in range(0, len(payload), 2):
            low, high = payload[offset : offset + 2]
            nibbles = (low >> 4, low & 15, high >> 4, high & 15)
            level = None
            if low == high == 0:
                status = Status.ABSENT
            elif all(n in PAIRS for n in nibbles):
                a, b, c, d = (PAIRS[n] for n in nibbles)
                level = a << 2 | b | c << 6 | d << 4
                status = Status.ON if level else Status.OFF
            else:
                status = Status.ERROR
            groups.append(GroupStatus(start + offset // 2, status, level))
    else:
        for offset, value in enumerate(payload):
            for pair in range(4):
                status = Status((value >> (pair * 2)) & 3)
                groups.append(
                    GroupStatus(
                        start + offset * 4 + pair,
                        status,
                        0 if status == Status.OFF else None,
                    )
                )
    if groups[-1].group > 255:
        raise ValueError("Status exceeds group address range")
    return StatusReport(application, tuple(groups), coding & 7 == 7)


def decode_line(line: bytes) -> LightingEvent | StatusReport | ApplicationEvent | None:
    # bytes.fromhex accepts whitespace; wire frames must not contain it.
    if (
        not line
        or len(line) % 2
        or any(c not in b"0123456789ABCDEFabcdef" for c in line)
    ):
        raise ValueError("Invalid hexadecimal frame")
    data = bytes.fromhex(line.decode())
    if sum(data) & 255:
        raise ValueError("Invalid checksum")
    if data[0] >= 0xC0:
        return _status(data)
    if data[0] == 0x86:
        if len(data) < 6:
            raise ValueError("Truncated CAL reply")
        # EXSTAT includes addressing. Only the attached network is supported.
        if data[3] != 0:
            return None
        if data[4] >= 0xC0:
            return _status(checksum(data[4:-1]))
        return None
    if data[0] & 7 != 5:
        return None
    if len(data) < 7:
        raise ValueError("Truncated SAL message")
    application, routing = data[2:4]
    if routing == 0:
        payload = data[4:-1]
    elif routing == 1 and data[4] == 0:
        payload = data[5:-1]
    else:
        return None
    if application in LOAD_APPLICATIONS:
        return LightingEvent(application, decode_commands(payload))
    if application in DEFINITIONS:
        return ApplicationEvent(
            application, data[1], decode_application(application, payload)
        )
    return None
