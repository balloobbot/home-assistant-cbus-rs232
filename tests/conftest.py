"""PCI simulator at the serialx boundary."""

import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.cbus_rs232.cbus.client import CBus
from custom_components.cbus_rs232.cbus.protocol import checksum
from custom_components.cbus_rs232.const import DOMAIN


class PCI:
    def __init__(self) -> None:
        self.reader = asyncio.StreamReader()
        self.writes: list[bytes] = []
        self.result = b"."
        self.silent = False
        self.closed = False
        self.report_status = True
        self.drain = AsyncMock()
        self.wait_closed = AsyncMock()

    def write(self, data: bytes) -> None:
        self.writes.append(data)
        if data == b"~~~\r" or self.silent:
            return
        tag = data[-2:-1]
        self.reader.feed_data(tag + self.result)
        # Examples from CBUS-QS section 5.2, including inline confirmations.
        if data.startswith(b"@A321"):
            self.reader.feed_data(b"322100AD\r\n")
        elif data.startswith(b"@A342"):
            self.reader.feed_data(b"3242008C\r\n")
        elif data.startswith(b"@A330"):
            self.reader.feed_data(b"86999900323000E6\r\n")
        elif data.startswith(b"\\05FF007307") and self.report_status:
            application, start = bytes.fromhex(data[11:15].decode())
            for offset, size in ((0, 11), (11, 11), (22, 10)):
                payload = bytes(
                    [0xE0 + 3 + size * 2, 7, application, start + offset]
                ) + bytes(size * 2)
                self.reader.feed_data(
                    checksum(payload).hex().upper().encode() + b"\r\n"
                )

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def pci() -> Iterator[PCI]:
    simulator = PCI()
    with patch(
        "serialx.open_serial_connection",
        new=AsyncMock(return_value=(simulator.reader, simulator)),
    ):
        yield simulator


@pytest.fixture
async def client(pci: PCI) -> CBus:
    client = CBus("esphome://proxy/uart0")
    await client.connect()
    yield client
    await client.disconnect()


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data={"port": "esphome://proxy/uart0", "application": 56}
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture(autouse=True)
def dependencies(hass):
    hass.http = Mock()
    with (
        patch("homeassistant.setup.async_process_deps_reqs", return_value=None),
        patch(
            "homeassistant.config_entries.async_process_deps_reqs", return_value=None
        ),
    ):
        yield
