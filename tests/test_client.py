"""Connection lifecycle, serial framing, and state tracking."""

import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.cbus_rs232.cbus.client import CBus, CommandError, Group
from custom_components.cbus_rs232.cbus.protocol import (
    GroupStatus,
    LightingCommand,
    LightingEvent,
    Status,
    StatusReport,
    checksum,
)

from .conftest import PCI


def line(data: bytes) -> bytes:
    return checksum(data).hex().upper().encode() + b"\r\n"


async def settle() -> None:
    for _ in range(3):
        await asyncio.sleep(0)


async def test_connect(client: CBus, pci: PCI) -> None:
    assert client.connected
    assert pci.writes[:4] == [
        b"~~~\r",
        b"@A3210038g\r",
        b"@A3420006h\r",
        b"@A3300079i\r",
    ]
    assert len(pci.writes) == 13
    assert pci.writes[4] == b"\\05FF007A38004Aj\r"
    assert pci.writes[-1].startswith(b"\\05FF00730738E0")
    await client.disconnect()
    assert pci.closed
    assert not client.connected
    await client.disconnect()


async def test_commands_and_tags(client: CBus, pci: PCI) -> None:
    await asyncio.gather(*(client.set_level(8, level) for level in range(25)))
    assert client.groups[8].level == 24
    assert pci.writes[-1].startswith(b"\\053800020818")
    assert pci.writes[-1][-2:] == b"w\r"


@pytest.mark.parametrize("result", [b"#", b"$", b"%"])
async def test_negative_ack(client: CBus, pci: PCI, result: bytes) -> None:
    pci.result = result
    with pytest.raises(CommandError):
        await client.set_level(8, 128)
    assert 8 not in client.groups
    assert not client.connected


async def test_timeout_does_not_retry(client: CBus, pci: PCI) -> None:
    pci.silent = True
    count = len(pci.writes)
    with (
        patch("custom_components.cbus_rs232.cbus.client.ACK_TIMEOUT", 0.01),
        pytest.raises(TimeoutError),
    ):
        await client.set_level(8, 128)
    assert len(pci.writes) == count + 1
    assert not client.connected
    assert client._pending is None


async def test_connect_failure_closes(pci: PCI) -> None:
    pci.result = b"#"
    client = CBus("test")
    with pytest.raises(CommandError):
        await client.connect()
    assert pci.closed
    assert client._reader_task is None


async def test_open_failure() -> None:
    client = CBus("test")
    with (
        patch("serialx.open_serial_connection", side_effect=OSError),
        pytest.raises(OSError),
    ):
        await client.connect()
    assert not client.connected


async def test_connect_cancellation(pci: PCI) -> None:
    pci.silent = True
    client = CBus("test")
    task = asyncio.create_task(client.connect())
    await settle()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert pci.closed


async def test_disconnected_send() -> None:
    client = CBus("test")
    with pytest.raises(ConnectionError):
        await client.set_level(8, 0)
    with pytest.raises(ConnectionError):
        await client.refresh()


async def test_write_failure(client: CBus, pci: PCI) -> None:
    pci.drain.side_effect = OSError
    with pytest.raises(OSError):
        await client.set_level(8, 0)
    assert not client.connected


async def test_cancelled_command(client: CBus, pci: PCI) -> None:
    pci.silent = True
    task = asyncio.create_task(client.set_level(8, 0))
    await settle()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client._pending is None


async def test_fragmented_input(client: CBus, pci: PCI) -> None:
    callback = Mock()
    unsubscribe = client.subscribe(callback)
    for char in line(bytes.fromhex("050138007908")):
        pci.reader.feed_data(bytes([char]))
        await asyncio.sleep(0)
    assert client.groups[8].level == 255
    assert callback.call_count == 1
    unsubscribe()
    pci.reader.feed_data(line(bytes.fromhex("050138000108")))
    await settle()
    assert client.groups[8].level == 0
    assert callback.call_count == 1


async def test_noise_and_other_application(client: CBus, pci: PCI) -> None:
    pci.reader.feed_data(b"invalid\r\n" + b"X" * 600 + b"\r\n")
    pci.reader.feed_data(line(bytes.fromhex("050139007908")))
    pci.reader.feed_data(line(bytes.fromhex("050138007909")))
    await settle()
    assert set(client.groups) == {9}


async def test_ack_after_basic_mode_echo(client: CBus, pci: PCI) -> None:
    pci.silent = True
    task = asyncio.create_task(client.set_level(8, 128))
    await settle()
    tag = pci.writes[-1][-2:-1]
    pci.reader.feed_data(b"@A3210038" + tag + b".\r")
    await task
    assert client.groups[8].level == 128


async def test_stale_and_duplicate_ack(client: CBus, pci: PCI) -> None:
    client._confirm("g", ".")
    pci.silent = True
    task = asyncio.create_task(client.set_level(8, 128))
    await settle()
    tag = pci.writes[-1][-2:].decode()[0]
    client._confirm("g", ".")
    assert not task.done()
    client._confirm(tag, ".")
    client._confirm(tag, ".")
    await task


async def test_wall_switch_after_ack_wins(client: CBus, pci: PCI) -> None:
    pci.silent = True
    task = asyncio.create_task(client.set_level(8, 255))
    await settle()
    tag = pci.writes[-1][-2:-1]
    pci.reader.feed_data(tag + b"." + line(bytes.fromhex("050138000108")))
    await task
    assert client.groups[8].level == 0


async def test_status_requires_complete_reply(pci: PCI) -> None:
    pci.report_status = False
    client = CBus("test")
    with (
        patch("custom_components.cbus_rs232.cbus.client.ACK_TIMEOUT", 0.01),
        pytest.raises(TimeoutError),
    ):
        await client.connect()
    assert pci.closed
    assert client._status_pending is None


async def test_disconnect_while_waiting_for_status(client: CBus, pci: PCI) -> None:
    pci.report_status = False
    task = asyncio.create_task(client.refresh())
    await settle()
    client._lost("connection reset")
    client._lost("connection reset")
    pci.reader.feed_eof()
    with pytest.raises(ConnectionError):
        await task
    assert client._status_pending is None


async def test_cancel_during_status_ack(client: CBus, pci: PCI) -> None:
    original_write = pci.write

    def write(data: bytes) -> None:
        original_write(data)
        if data.startswith(b"\\05FF007A"):
            pci.silent = True

    with patch.object(pci, "write", side_effect=write):
        task = asyncio.create_task(client.refresh())
        await settle()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not client.connected
    assert client._status_pending is None


async def test_cancel_during_drain(client: CBus, pci: PCI) -> None:
    pci.silent = True
    with (
        patch.object(pci, "drain", side_effect=asyncio.CancelledError),
        pytest.raises(asyncio.CancelledError),
    ):
        await client.set_level(8, 0)
    assert not client.connected


@pytest.mark.parametrize("message", [b"++\r\n", b"garbage+\r\n", b"+\r\n"])
async def test_power_up(client: CBus, pci: PCI, message: bytes) -> None:
    pci.reader.feed_data(message)
    await settle()
    assert not client.connected


async def test_eof_during_command(client: CBus, pci: PCI) -> None:
    pci.silent = True
    task = asyncio.create_task(client.set_level(8, 0))
    await settle()
    pci.reader.feed_eof()
    with pytest.raises(ConnectionError):
        await task
    assert not client.connected


async def test_read_error(client: CBus, pci: PCI) -> None:
    pci.reader.set_exception(OSError("unplugged"))
    await settle()
    assert not client.connected


def report(client: CBus, status: Status, level: int | None = None) -> None:
    client._apply(StatusReport(56, (GroupStatus(8, status, level),)))


async def test_binary_preserves_brightness(client: CBus) -> None:
    report(client, Status.ON, 87)
    report(client, Status.ON)
    assert client.groups[8].level == 87
    report(client, Status.OFF, 0)
    report(client, Status.ON)
    assert client.groups[8].level is None
    report(client, Status.ERROR)
    assert client.groups[8].status == Status.ERROR
    report(client, Status.ABSENT)
    assert 8 in client.groups


async def test_absent_and_reserved_groups(client: CBus) -> None:
    client._apply(
        StatusReport(56, (GroupStatus(7, Status.ABSENT), GroupStatus(255, Status.ON)))
    )
    client._apply(LightingEvent(56, (LightingCommand(255, 0x79),)))
    assert not client.groups


async def test_ramp_and_terminate(client: CBus) -> None:
    report(client, Status.OFF, 0)
    with patch("custom_components.cbus_rs232.cbus.client.monotonic", return_value=100):
        await client.set_level(8, 255, 1)
    with patch("custom_components.cbus_rs232.cbus.client.monotonic", return_value=102):
        assert client.groups[8].brightness == 128
        await client.command(LightingCommand(8, 9))
    assert client.groups[8].level == 128
    assert client.groups[8].target is None


async def test_wall_switch_interrupts_ramp(client: CBus) -> None:
    report(client, Status.OFF, 0)
    await client.set_level(8, 255, 1)
    client._apply(LightingEvent(56, (LightingCommand(8, 1),)))
    assert client.groups[8].brightness == 0
    assert client.groups[8].target is None


async def test_unknown_ramp_start_and_same_target(client: CBus) -> None:
    await client.set_level(8, 255, 1)
    assert client.groups[8].brightness == 255
    await client.set_level(8, 255, 1)
    assert client.groups[8].target is None


async def test_labels(client: CBus) -> None:
    await client.command(LightingCommand(8, 0xAA, b"\x00\x01Kitchen"))
    assert client.groups[8].label == "Kitchen"
    await client.command(LightingCommand(8, 0xA3, b"\x06\x01"))
    assert client.groups[8].label == "Kitchen"
    await client.command(LightingCommand(8, 0xA3, b"\x00\x01"))
    assert client.groups[8].label is None


async def test_tick(client: CBus) -> None:
    client._tick_task.cancel()
    with suppress(asyncio.CancelledError):
        await client._tick_task
    client.groups[8] = Group(
        8, Status.ON, 255, target=0, ramp_start=100, ramp_duration=4
    )
    changed = Mock()
    client.subscribe(changed)
    with (
        patch(
            "custom_components.cbus_rs232.cbus.client.asyncio.sleep",
            new=AsyncMock(side_effect=[None, None, None, asyncio.CancelledError]),
        ),
        patch(
            "custom_components.cbus_rs232.cbus.client.monotonic", side_effect=[102, 104]
        ),
    ):
        with pytest.raises(asyncio.CancelledError):
            await client._tick()
    assert changed.call_count == 2
    assert client.groups[8].level == 0
    assert client.groups[8].target is None


async def test_poll(client: CBus) -> None:
    with (
        patch(
            "custom_components.cbus_rs232.cbus.client.asyncio.sleep", new=AsyncMock()
        ),
        patch.object(
            client, "refresh", new=AsyncMock(side_effect=[None, TimeoutError])
        ) as refresh,
    ):
        await client._poll()
    assert refresh.call_count == 2
    assert not client.connected
