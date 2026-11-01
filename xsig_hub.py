"""Low level TCP server implementing the Crestron XSIG symbol protocol.

This class knows nothing about Home Assistant entities. It only:
  * Opens a TCP server that a Crestron processor connects to.
  * Decodes/encodes digital, analog and serial joins per the XSIG protocol.
  * Notifies registered callbacks when a join value changes, and when the
    connection becomes available/unavailable.

Kept intentionally independent of hass so it is easy to unit test.
"""

import asyncio
import struct
import logging

_LOGGER = logging.getLogger(__name__)

# XSIG join ranges (docs/Xsig documentation.docx): digital joins travel in
# 12 bits (1..4096), analog and serial joins in 10 bits (1..1024).
DIGITAL_JOIN_MAX = 4096
ANALOG_JOIN_MAX = 1024
SERIAL_JOIN_MAX = 1024

# Serial payloads sit between the 2-byte header and the 0xFF terminator and
# are limited to 252 *bytes* (not characters).
SERIAL_MAX_BYTES = 252


class CrestronXsigHub:
    """Handles the raw XSIG TCP connection and join state."""

    def __init__(self, unique_id: str):
        self.unique_id = unique_id
        self._digital: dict[int, bool] = {}
        self._analog: dict[int, int] = {}
        self._serial: dict[int, str] = {}
        self._last_sent_digital: dict[int, bool] = {}
        self._writer: asyncio.StreamWriter | None = None
        self._callbacks: set = set()
        self._server: asyncio.base_events.Server | None = None
        self._available = False
        self._sync_all_joins_callback = None
        self._warned_no_connection = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def listen(self, port: int) -> None:
        """Start the TCP server. Retries forever on failure."""
        while True:
            try:
                _LOGGER.info("Starting XSIG TCP server on port %s", port)
                server = await asyncio.start_server(
                    self._handle_connection, "0.0.0.0", port
                )
                self._server = server
                addr = server.sockets[0].getsockname()
                _LOGGER.info("Listening for Crestron processor on %s", addr)
                asyncio.create_task(server.serve_forever())
                return
            except Exception as err:  # noqa: BLE001 - want to retry on anything
                _LOGGER.error("Error starting XSIG TCP server: %s", err)
                await asyncio.sleep(5)

    async def stop(self) -> None:
        """Stop the server and notify listeners we are unavailable.

        Closing the *listening* socket alone is not enough: if a Crestron
        processor is already connected, that connection stays open and the
        processor has no reason to reconnect. On a config entry reload (e.g.
        after adding an entity from the UI) this left the processor talking
        to an orphaned hub instance with no entities attached, while the
        newly created hub sat waiting for a connection that would never
        come until the processor's connection was closed by hand.

        So: explicitly close the active connection too. The processor's
        XSIG symbol is expected to reconnect automatically, at which point
        it lands on the freshly (re)started server with the current set of
        entities already registered.
        """
        self._available = False
        await self._notify("available", "False")

        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
            self._writer = None

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        _LOGGER.info("XSIG TCP server stopped")

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------
    def register_sync_all_joins_callback(self, callback) -> None:
        """Register an async callback for the processor's full-sync request.

        The callback is awaited when the processor sends the documented XSIG
        single-byte command ``\xFD`` (Send Status) from its ISC symbol.
        """
        self._sync_all_joins_callback = callback

    def register_callback(self, callback) -> None:
        self._callbacks.add(callback)

    def remove_callback(self, callback) -> None:
        self._callbacks.discard(callback)

    async def _notify(self, cbtype: str, value) -> None:
        for callback in list(self._callbacks):
            try:
                await callback(cbtype, value)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Error in Crestron XSIG callback")

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------
    async def _handle_connection(self, reader, writer):
        self._writer = writer
        peer = writer.get_extra_info("peername")
        _LOGGER.info("Crestron processor connected from %s", peer)

        # The XSIG "update all" dump sent on connect only carries digital
        # joins that are HIGH — low ones are simply omitted (analog and
        # serial joins are always sent). Clear the digital cache so that
        # joins changed to low while the connection was down don't stay
        # stale: missing from the dump now means low. (KI-024)
        self._digital.clear()

        self._available = True
        await self._notify("available", "True")

        try:
            writer.write(b"\xfd")  # Request a full update from the processor
            while True:
                data = await reader.readexactly(1)

                # Single-byte XSIG commands. Bytes 0xF8-0xFF can never
                # start a digital (10xxxxxx), analog (110xxxxx, bit 3 = 0)
                # or serial (11001xxx) packet, so they are consumed one
                # byte at a time: reading a second byte here would eat the
                # first byte of the next real packet and desync the stream.
                # The XSIG documentation defines exactly two of them:
                #   \xFD Send Status  = "evaluate all inputs and re-transmit
                #     any digital, analog and permanent serial signals not
                #     set to 0" -> the processor wants our full state, so we
                #     push every HA -> Crestron expose.
                #   \xFC Clear Outputs = "force all outputs to 0". On a
                #     processor reboot, it clears our cached join values so
                #     omitted zeroes in the following 0xFD sync are reflected
                #     in HA before non-zero values arrive.
                if data[0] >= 0xF8:
                    if data[0] == 0xFD:
                        _LOGGER.info("Processor requested full sync (0xFD Send Status)")
                        if self._sync_all_joins_callback is not None:
                            await self._sync_all_joins_callback()
                    elif data[0] == 0xFB:
                        # Expected marker after a full sync; intentionally no handling.
                        _LOGGER.info("Processor sent expected 0xFB marker (ignored)")
                    elif data[0] == 0xFC:
                        await self._clear_output_state()
                        _LOGGER.info(
                            "Processor requested 0xFC Clear Outputs; cleared cached join state"
                        )
                    else:
                        _LOGGER.warning(
                            "Unknown XSIG command byte: 0x%02x (ignored)", data[0]
                        )
                    continue

                data += await reader.readexactly(1)

                # Digital join
                if data[0] & 0b11000000 == 0b10000000 and data[1] & 0b10000000 == 0:
                    header = struct.unpack("BB", data)
                    join = ((header[0] & 0b00011111) << 7 | header[1]) + 1
                    value = ~header[0] >> 5 & 0b1
                    bool_value = value == 1
                    self._digital[join] = bool_value
                    _LOGGER.debug("Received digital join %s = %s", join, bool_value)
                    await self._notify(f"d{join}", str(bool_value))

                # Analog join
                elif data[0] & 0b11001000 == 0b11000000 and data[1] & 0b10000000 == 0:
                    data += await reader.readexactly(2)
                    header = struct.unpack("BBBB", data)
                    join = ((header[0] & 0b00000111) << 7 | header[1]) + 1
                    value = (header[0] & 0b00110000) << 10 | header[2] << 7 | header[3]
                    self._analog[join] = value
                    _LOGGER.debug("Received analog join %s = %s", join, value)
                    await self._notify(f"a{join}", str(value))

                # Serial join
                elif data[0] & 0b11111000 == 0b11001000 and data[1] & 0b10000000 == 0:
                    try:
                        data += await reader.readuntil(b"\xff")
                    except asyncio.LimitOverrunError:
                        # No 0xFF terminator within the stream limit: the
                        # frame is corrupt and the stream is desynced beyond
                        # recovery. Drop the connection (cleanly).
                        _LOGGER.warning(
                            "Corrupt XSIG serial frame from %s: no 0xFF "
                            "terminator before the stream limit; disconnecting",
                            peer,
                        )
                        break
                    header = struct.unpack("BB", data[:2])
                    join = ((header[0] & 0b00000111) << 7 | header[1]) + 1
                    # Crestron strings are raw 8-bit bytes (CP1252/Latin-1),
                    # not UTF-8: never let a decode error kill the TCP
                    # connection. latin-1 is byte-preserving for 0x80-0xFF.
                    string = data[2:-1].decode("latin-1", errors="replace")
                    self._serial[join] = string
                    _LOGGER.debug("Received serial join %s = %s", join, string)
                    await self._notify(f"s{join}", string)

                else:
                    _LOGGER.debug("Unknown XSIG packet: %s", data.hex())

        except asyncio.IncompleteReadError:
            # EOF (clean or mid-frame): a normal disconnect, not an error.
            _LOGGER.info("Crestron processor disconnected (%s)", peer)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error in XSIG connection: %s", err)
        finally:
            self._available = False
            self._writer = None
            await self._notify("available", "False")
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
            _LOGGER.info("XSIG connection closed, ready for a new connection")

    # ------------------------------------------------------------------
    # State readers
    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        return self._available

    async def _clear_output_state(self) -> None:
        """Clear cached join state and refresh entities without faking joins.

        The processor sends 0xFC after a reboot to clear its outputs before
        requesting/sending a full status sync. Do not emit per-join callbacks:
        those represent received traffic and can trigger actions or events.
        """
        self._digital.clear()
        self._analog.clear()
        self._serial.clear()
        self._last_sent_digital.clear()
        # Entity listeners refresh from the cleared caches; actions, expose
        # rules and raw-join events ignore this non-join callback type.
        await self._notify("state_reset", "0")

    def get_analog(self, join: int) -> int:
        return self._analog.get(join, 0)

    def get_digital(self, join: int) -> bool:
        return self._digital.get(join, False)

    def get_serial(self, join: int) -> str:
        return self._serial.get(join, "")

    def update_digital(self, join: int, value: bool) -> None:
        """Update the local digital state without sending (optimistic UI)."""
        self._digital[join] = value

    def update_analog(self, join: int, value: int) -> None:
        """Update the local analog state without sending (optimistic UI)."""
        self._analog[join] = value

    def update_serial(self, join: int, value: str) -> None:
        """Update the local serial state without sending (optimistic UI)."""
        self._serial[join] = value

    def last_sent_digital(self, join: int) -> bool | None:
        """Last digital value actually sent to the processor, or None."""
        return self._last_sent_digital.get(join)

    # ------------------------------------------------------------------
    # State writers
    # ------------------------------------------------------------------
    def set_analog(self, join: int, value: int) -> bool:
        """Send an analog join. Return True if the frame was actually written."""
        if not 1 <= join <= ANALOG_JOIN_MAX:
            _LOGGER.warning(
                "Cannot send analog join %s: out of range (1..%s)",
                join,
                ANALOG_JOIN_MAX,
            )
            return False
        if not self._writer:
            self._warn_no_connection()
            return False
        data = struct.pack(
            ">BBBB",
            0b11000000
            | (value >> 10 & 0b00110000)
            | ((join - 1) >> 7 & 0b00000111),
            (join - 1) & 0b01111111,
            value >> 7 & 0b01111111,
            value & 0b01111111,
        )
        self._writer.write(data)
        _LOGGER.debug("Sending analog join %s = %s", join, value)
        self._warned_no_connection = False
        return True

    def set_digital(self, join: int, value: bool) -> bool:
        """Send a digital join. Return True if the frame was actually written."""
        if not 1 <= join <= DIGITAL_JOIN_MAX:
            _LOGGER.warning(
                "Cannot send digital join %s: out of range (1..%s)",
                join,
                DIGITAL_JOIN_MAX,
            )
            return False
        if not self._writer:
            self._warn_no_connection()
            return False
        data = struct.pack(
            ">BB",
            # The high join bits occupy bits 0-4 only (bit 5 is the value
            # bit, bits 6-7 the 0b10 digital prefix): mask them so an
            # out-of-range join can never corrupt the header.
            0b10000000 | (~value << 5 & 0b00100000) | ((join - 1) >> 7 & 0b00011111),
            (join - 1) & 0b01111111,
        )
        self._writer.write(data)
        self._last_sent_digital[join] = value
        _LOGGER.debug("Sending digital join %s = %s", join, value)
        self._warned_no_connection = False
        return True

    def set_serial(self, join: int, string: str) -> bool:
        """Send a serial join. Return True if the frame was actually written."""
        if not 1 <= join <= SERIAL_JOIN_MAX:
            _LOGGER.warning(
                "Cannot send serial join %s: out of range (1..%s)",
                join,
                SERIAL_JOIN_MAX,
            )
            return False
        # Crestron expects raw 8-bit bytes (CP1252/Latin-1), not UTF-8
        # multi-byte sequences. The length limit is on *bytes*.
        payload = string.encode("latin-1", errors="replace")
        if len(payload) > SERIAL_MAX_BYTES:
            _LOGGER.warning(
                "Cannot send serial join %s: string too long (%s bytes > %s)",
                join,
                len(payload),
                SERIAL_MAX_BYTES,
            )
            return False
        if not self._writer:
            self._warn_no_connection()
            return False
        data = struct.pack(
            ">BB",
            0b11001000 | ((join - 1) >> 7 & 0b00000111),
            (join - 1) & 0b01111111,
        )
        data += payload
        data += b"\xff"
        self._writer.write(data)
        _LOGGER.debug("Sending serial join %s = %s", join, string)
        self._warned_no_connection = False
        return True

    def _warn_no_connection(self) -> None:
        if not self._warned_no_connection:
            _LOGGER.info("Cannot send: no connection to the Crestron processor")
            self._warned_no_connection = True
