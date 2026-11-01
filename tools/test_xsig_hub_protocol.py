"""Mini test for the Lotto 1 protocol robustness fixes in xsig_hub.py.

Runs without Home Assistant: it spins up the hub on an ephemeral port and
plays the Crestron processor side with asyncio streams.

Usage: python tools/test_xsig_hub_protocol.py
Also collectable by pytest (each test_* is an asyncio coroutine).
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xsig_hub import CrestronXsigHub  # noqa: E402

logging.basicConfig(level=logging.DEBUG)


class _Probe:
    def __init__(self):
        self.values = {}
        self.available_events = []

    async def __call__(self, cbtype, value):
        if cbtype == "available":
            self.available_events.append(value)
        else:
            self.values[cbtype] = value


async def _connected_pair():
    hub = CrestronXsigHub("test")
    probe = _Probe()
    hub.register_callback(probe)
    await hub.listen(0)
    port = hub._server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    # let the server-side handler start and emit the 0xFD request
    await asyncio.sleep(0.1)
    await reader.readexactly(1)  # swallow the hub's initial \xfd
    return hub, probe, reader, writer


async def test_serial_non_utf8_keeps_connection_open():
    hub, probe, reader, writer = await _connected_pair()
    try:
        # serial join 5 = "a" 0xE9 "b"  (byte 0xE9 = e-acute, not valid UTF-8)
        writer.write(bytes([0b11001000, 4]) + b"a\xe9b" + b"\xff")
        await writer.drain()
        await asyncio.sleep(0.2)
        assert probe.values.get("s5") == "a\xe9b", probe.values
        assert hub.is_available()
    finally:
        writer.close()
        await asyncio.sleep(0.1)
        await hub.stop()


async def test_set_serial_lengths():
    hub, probe, reader, writer = await _connected_pair()
    try:
        # 250 accented chars = 250 bytes in latin-1 -> must be sent as-is
        assert hub.set_serial(1, "\u00e9" * 250) is True
        frame = await asyncio.wait_for(reader.readexactly(2 + 250 + 1), 1)
        assert frame[0] == 0b11001000 and frame[1] == 0
        assert frame[2:-1] == b"\xe9" * 250 and frame[-1] == 0xFF

        # More than the 252-byte limit -> rejected with warning, no bytes written
        assert hub.set_serial(1, "x" * 253) is False
        await asyncio.sleep(0.1)
        assert reader._buffer == b"", reader._buffer  # noqa: SLF001
    finally:
        writer.close()
        await asyncio.sleep(0.1)
        await hub.stop()


async def test_out_of_range_joins_rejected():
    hub, probe, reader, writer = await _connected_pair()
    try:
        assert hub.set_digital(0, True) is False
        assert hub.set_digital(5000, True) is False
        assert hub.set_analog(0, 1) is False
        assert hub.set_analog(2000, 1) is False
        assert hub.set_serial(0, "x") is False
        assert hub.set_serial(2000, "x") is False
        await asyncio.sleep(0.1)
        assert reader._buffer == b"", reader._buffer  # noqa: SLF001

        # valid boundary joins are accepted
        assert hub.set_digital(4096, True) is True
        assert hub.set_analog(1024, 1) is True
        assert hub.set_serial(1024, "x") is True
        frame = await asyncio.wait_for(reader.read(10), 1)
        assert frame[0] == 0b10000000 | 0b00011111  # digital 4096, high bits intact
    finally:
        writer.close()
        await asyncio.sleep(0.1)
        await hub.stop()


async def test_mid_frame_disconnect_is_clean():
    hub, probe, reader, writer = await _connected_pair()
    try:
        # analog frame: send only 1 of the 4 bytes, then drop the connection
        writer.write(bytes([0b11000000]))
        await writer.drain()
        await asyncio.sleep(0.1)
        writer.close()
        await asyncio.sleep(0.3)
        assert hub.is_available() is False
        assert probe.available_events == ["True", "False"], probe.available_events
    finally:
        await hub.stop()


async def test_monobyte_command_still_consumed_as_one_byte():
    """Regression: 0xFC/0xFD/0xFB commands must not desynchronize frames."""
    hub, probe, reader, writer = await _connected_pair()
    synced = []
    log_records = []

    class _CaptureLogs(logging.Handler):
        def emit(self, record):
            log_records.append(record)

    logger = logging.getLogger("xsig_hub")
    capture = _CaptureLogs()
    logger.addHandler(capture)

    async def _on_sync():
        synced.append(1)

    hub.register_sync_all_joins_callback(_on_sync)
    try:
        # Commands immediately before/after frames must not consume frame bytes.
        # 0xFC clears cached state; expected 0xFB is ignored at INFO;
        # 0xFD requests full sync. Digital join 1 = high, then analog join 1 = 0x1234.
        writer.write(
            bytes(
                [
                    0xFC,
                    0b10000000,
                    0x00,
                    0xFB,
                    0b11000000 | (0x1234 >> 10 & 0b00110000),
                    0x00,
                    0x1234 >> 7 & 0x7F,
                    0x1234 & 0x7F,
                    0xFD,
                ]
            )
        )
        await writer.drain()
        await asyncio.sleep(0.2)
        assert synced == [1], synced
        assert probe.values.get("d1") == "True", probe.values
        assert probe.values.get("a1") == str(0x1234), probe.values
        assert hub.get_digital(1) is True
        assert any(
            record.levelno == logging.INFO
            and "expected 0xFB marker" in record.getMessage()
            for record in log_records
        ), log_records
        assert any(
            record.levelno == logging.INFO
            and "0xFC Clear Outputs; cleared cached join state" in record.getMessage()
            for record in log_records
        ), log_records
    finally:
        logger.removeHandler(capture)
        writer.close()
        await asyncio.sleep(0.1)
        await hub.stop()


async def test_fc_clears_cached_values_and_then_allows_full_sync():
    hub, probe, reader, writer = await _connected_pair()
    synced = []

    async def _on_sync():
        synced.append(True)

    hub.register_sync_all_joins_callback(_on_sync)
    hub._digital[1] = True
    hub._analog[2] = 1234
    hub._serial[3] = "stale"
    hub._last_sent_digital[1] = True
    try:
        writer.write(b"\xfc\xfd")
        await writer.drain()
        await asyncio.sleep(0.1)
        assert hub.get_digital(1) is False
        assert hub.get_analog(2) == 0
        assert hub.get_serial(3) == ""
        assert hub.last_sent_digital(1) is None
        assert probe.values.get("state_reset") == "0", probe.values
        assert not {"d1", "a2", "s3"} & probe.values.keys(), probe.values
        assert synced == [True], synced
    finally:
        writer.close()
        await asyncio.sleep(0.1)
        await hub.stop()


async def _run_all():
    tests = [
        test_serial_non_utf8_keeps_connection_open,
        test_set_serial_lengths,
        test_out_of_range_joins_rejected,
        test_mid_frame_disconnect_is_clean,
        test_monobyte_command_still_consumed_as_one_byte,
        test_fc_clears_cached_values_and_then_allows_full_sync,
    ]
    failed = 0
    for test in tests:
        try:
            await test()
            print(f"PASS {test.__name__}")
        except Exception as err:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {err!r}")
    print("ALL PASS" if not failed else f"{failed} FAILED")
    return failed


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run_all()))
