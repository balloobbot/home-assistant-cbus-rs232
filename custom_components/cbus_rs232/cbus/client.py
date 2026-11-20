"""Async PCI connection through serialx, including ESPHome serial proxies."""

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from time import monotonic

import serialx

from .protocol import (
    LightingCommand,
    LightingEvent,
    Status,
    StatusReport,
    decode_line,
    encode_commands,
    frame,
    level_command,
    lighting_application,
    status_request,
)

_LOGGER = logging.getLogger(__name__)
ACK_TIMEOUT = 5.0
POLL_INTERVAL = 60
CONNECT_TIMEOUT = 30


class CommandError(ConnectionError):
    """The PCI could not deliver a command."""


@dataclass
class Group:
    address: int
    status: Status = Status.ABSENT
    level: int | None = None
    label: str | None = None
    target: int | None = None
    ramp_start: float = 0
    ramp_duration: float = 0

    @property
    def brightness(self) -> int | None:
        if self.target is None:
            return self.level
        fraction = min(1, (monotonic() - self.ramp_start) / self.ramp_duration)
        return round(self.level + (self.target - self.level) * fraction)


class CBus:
    def __init__(self, port: str, application: int = 56) -> None:
        self.port = port
        self.application = lighting_application(application)
        self.groups: dict[int, Group] = {}
        self.connected = False
        self._writer = None
        self._reader_task: asyncio.Task | None = None
        self._poll_task: asyncio.Task | None = None
        self._tick_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._pending: tuple[str, asyncio.Future] | None = None
        self._on_confirm: Callable[[], None] | None = None
        self._status_pending: tuple[set[int], asyncio.Future] | None = None
        self._refresh_lock = asyncio.Lock()
        self._tag = 0
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    async def connect(self) -> None:
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                reader, self._writer = await serialx.open_serial_connection(
                    self.port,
                    baudrate=9600,
                    bytesize=8,
                    parity=serialx.Parity.NONE,
                    stopbits=serialx.StopBits.ONE,
                )
                self._reader_task = asyncio.create_task(self._read(reader))
                self._writer.write(b"~~~\r")
                await self._writer.drain()
                # Configure volatile options only; do not change PCI EEPROM.
                await self._send(f"@A32100{self.application:02X}".encode())
                await self._send(b"@A3420006")  # LOCAL_SAL and power-up notification
                await self._send(
                    b"@A3300079"
                )  # SMART, checksum, SAL and MMI monitoring
                self.connected = True
                await self.refresh()
        except BaseException:
            await self.disconnect()
            raise
        self._poll_task = asyncio.create_task(self._poll())
        self._tick_task = asyncio.create_task(self._tick())

    async def disconnect(self) -> None:
        self.connected = False
        for task in (self._poll_task, self._tick_task, self._reader_task):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        self._poll_task = self._tick_task = self._reader_task = None
        if self._writer is not None:
            self._writer.close()
            with suppress(OSError):
                await self._writer.wait_closed()
            self._writer = None

    def _lost(self, message: str) -> None:
        self.connected = False
        if self._pending is not None:
            _, future = self._pending
            if not future.done():
                future.set_exception(ConnectionError(message))
        if self._status_pending is not None:
            _, future = self._status_pending
            if not future.done():
                future.set_exception(ConnectionError(message))
        self._notify()

    async def _send(
        self,
        data: bytes,
        *,
        bus: bool = False,
        on_confirm: Callable[[], None] | None = None,
    ) -> None:
        async with self._lock:
            if self._writer is None:
                raise ConnectionError("PCI is disconnected")
            tag = chr(ord("g") + self._tag)
            self._tag = (self._tag + 1) % 20
            wire = frame(data, tag) if bus else data + tag.encode() + b"\r"
            future = asyncio.get_running_loop().create_future()
            self._pending = (tag, future)
            self._on_confirm = on_confirm
            try:
                self._writer.write(wire)
                await self._writer.drain()
                async with asyncio.timeout(ACK_TIMEOUT):
                    await future
            except TimeoutError, OSError:
                # A retry could override a later wall-switch action.
                self._lost("PCI command confirmation was lost")
                raise
            except asyncio.CancelledError:
                self._lost("PCI command was cancelled before confirmation")
                raise
            finally:
                self._pending = None
                self._on_confirm = None
                future.cancel()
                with suppress(asyncio.CancelledError):
                    future.exception()

    async def command(self, *commands: LightingCommand) -> None:
        if not self.connected:
            raise ConnectionError("PCI is disconnected")
        await self._send(
            encode_commands(self.application, commands),
            bus=True,
            on_confirm=lambda: self._apply(LightingEvent(self.application, commands)),
        )

    async def set_level(self, group: int, level: int, ramp_index: int = 0) -> None:
        await self.command(level_command(group, level, ramp_index))

    async def refresh(self) -> None:
        async with self._refresh_lock:
            await self._send(status_request(self.application), bus=True)
            for start in range(0, 256, 32):
                future = asyncio.get_running_loop().create_future()
                self._status_pending = (set(range(start, start + 32)), future)
                try:
                    await self._send(
                        status_request(self.application, start, levels=True), bus=True
                    )
                    async with asyncio.timeout(ACK_TIMEOUT):
                        await future
                finally:
                    self._status_pending = None
                    future.cancel()
                    with suppress(asyncio.CancelledError):
                        future.exception()

    async def _poll(self) -> None:
        try:
            while True:
                await asyncio.sleep(POLL_INTERVAL)
                await self.refresh()
        except OSError, TimeoutError:
            self._lost("PCI status refresh failed")

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(1)
            active = False
            for group in self.groups.values():
                if group.target is not None:
                    active = True
                    if monotonic() >= group.ramp_start + group.ramp_duration:
                        group.level = group.target
                        group.status = Status.ON if group.level else Status.OFF
                        group.target = None
            if active:
                self._notify()

    async def _read(self, reader: asyncio.StreamReader) -> None:
        buffer = bytearray()
        discard = False
        try:
            while chunk := await reader.read(256):
                for value in chunk:
                    if value in (10, 13):
                        if buffer and not discard:
                            self._line(bytes(buffer))
                        buffer.clear()
                        discard = False
                    elif not discard:
                        buffer.append(value)
                        # Confirmations have no delimiter and can precede a frame.
                        if (
                            len(buffer) >= 2
                            and 103 <= buffer[-2] <= 122
                            and value in b".#$%"
                        ):
                            self._confirm(chr(buffer[-2]), chr(value))
                            buffer.clear()
                        elif len(buffer) > 512:
                            buffer.clear()
                            discard = True
        except OSError:
            self._lost("Serial read failed")
        else:
            self._lost("Serial connection closed")

    def _confirm(self, tag: str, result: str) -> None:
        if self._pending is None or self._pending[0] != tag:
            return
        future = self._pending[1]
        if future.done():
            return
        if result == ".":
            if self._on_confirm is not None:
                self._on_confirm()
            future.set_result(None)
        else:
            reasons = {
                "#": "Too many bus retries",
                "$": "Checksum rejected",
                "%": "C-Bus clock lost",
            }
            future.set_exception(CommandError(reasons[result]))

    def _line(self, line: bytes) -> None:
        if line.endswith(b"+"):
            self._lost("PCI restarted")
            return
        try:
            event = decode_line(line)
        except ValueError:
            _LOGGER.debug("Discarded invalid PCI frame: %r", line)
            return
        if event is not None and event.application == self.application:
            self._apply(event)

    def _apply(self, event: LightingEvent | StatusReport) -> None:
        if isinstance(event, StatusReport):
            if event.levels and self._status_pending is not None:
                remaining, future = self._status_pending
                remaining.difference_update(value.group for value in event.groups)
                if not remaining and not future.done():
                    future.set_result(None)
            for value in event.groups:
                if value.group == 255 or (
                    value.status == Status.ABSENT and value.group not in self.groups
                ):
                    continue
                group = self.groups.setdefault(value.group, Group(value.group))
                group.status = value.status
                if value.level is not None:
                    group.level = value.level
                    group.target = None
                elif value.status != Status.ON or group.level == 0:
                    group.level = None
                    group.target = None
        else:
            for command in event.commands:
                if command.group == 255:
                    continue
                group = self.groups.setdefault(command.group, Group(command.group))
                if command.level is not None:
                    current = group.brightness
                    group.target = None
                    if (
                        command.ramp_seconds
                        and current is not None
                        and current != command.level
                    ):
                        group.level = current
                        group.target = command.level
                        group.ramp_start = monotonic()
                        group.ramp_duration = (
                            command.ramp_seconds * abs(current - command.level) / 255
                        )
                        group.status = Status.ON
                    else:
                        group.level = command.level
                        group.status = Status.ON if group.level else Status.OFF
                elif command.opcode == 9:
                    group.level = group.brightness
                    group.target = None
                else:
                    options, language = command.data[:2]
                    if options == 0 and language == 1:
                        group.label = (
                            command.data[2:].decode("ascii", errors="replace") or None
                        )
        self._notify()
