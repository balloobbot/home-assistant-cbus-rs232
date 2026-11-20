"""Run serialx against a TCP serial server, without mocking its transport."""

import asyncio

import pytest

from custom_components.cbus_rs232.cbus.client import CBus


@pytest.mark.usefixtures("socket_enabled")
async def test_real_serialx_socket() -> None:
    received: list[bytes] = []
    finished = asyncio.Event()
    errors: list[BaseException] = []

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while raw := await reader.readuntil(b"\r"):
                received.append(raw)
                if raw == b"~~~\r":
                    continue
                tag = raw[-2:-1]
                if raw.startswith(b"\\"):
                    packet = bytes.fromhex(raw[1:-2].decode())
                    assert sum(packet) % 256 == 0
                    assert len(raw) <= 47
                # Bytewise writes exercise the real stream transport's buffering.
                writer.write(tag)
                await writer.drain()
                await asyncio.sleep(0)
                writer.write(b".")
                if raw.startswith(b"\\05FF007307"):
                    start = int(raw[13:15], 16)
                    for offset, size in ((0, 11), (11, 11), (22, 10)):
                        body = bytearray([0xE0 + 3 + size * 2, 7, 56, start + offset])
                        body.extend(bytes(size * 2))
                        if start == offset == 0:
                            body[20:22] = bytes.fromhex("9599")
                        body.append(-sum(body) & 255)
                        writer.write(body.hex().upper().encode() + b"\r\n")
                if raw.startswith(b"\\05D1000901"):
                    # APP/06 section 6.11.2: 56312 kWh, from source address 23.
                    packet = bytearray.fromhex("0517D1000D810000DBF8")
                    packet.append(-sum(packet) & 255)
                    writer.write(packet.hex().upper().encode() + b"\r\n")
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        except BaseException as error:
            errors.append(error)
        finally:
            writer.close()
            await writer.wait_closed()
            finished.set()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = CBus(f"socket://127.0.0.1:{port}")
    try:
        await client.connect()
        assert client.groups[8].level == 87
        await client.set_level(8, 255)
        assert client.groups[8].level == 255
        assert received[-1].startswith(b"\\0538000208FF")
        report = asyncio.Event()
        unsubscribe = client.subscribe(report.set)
        await client.send_application(0xD1, "request_electricity", {})
        await asyncio.wait_for(report.wait(), 1)
        unsubscribe()
        reading = client.applications.devices[0xD1, "source_23"].readings["electricity"]
        assert reading.value == 56312
        assert reading.unit == "kWh"
        await client.send_application(0xCB, "set_enable", {"group": 7, "value": 99})
        assert client.applications.devices[0xCB, "group_7"].values["value"] == 99
    finally:
        await client.disconnect()
        server.close()
        await server.wait_closed()
        await asyncio.wait_for(finished.wait(), 1)
    assert not errors
