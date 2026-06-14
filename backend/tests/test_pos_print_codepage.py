"""Tests for ESC/POS thermal printer code-page encoding + hardware status.

Task #605. Real thermal printers consume single-byte code pages, NOT UTF-8, so
Turkish glyphs (ç ş ğ ü ö ı ...) must be encoded with CP857/CP1254 and preceded
by the matching "ESC t n" code-table command. We also decode the printer's
real-time status (DLE EOT) so paper-out / cover-open surfaces in print_jobs.

Task #614. _send_tcp's write-then-read-status sequence is exercised end-to-end
against a real asyncio loopback socket (a fake ESC/POS printer) so a regression
in the byte-write ordering, the DLE EOT status read, or the timeout fallback is
caught — not just the pure-function decode (_interpret_status) and dispatch
branch (_dispatch) covered above.
"""
import asyncio

import pytest

import domains.pms.pos_extensions.pos_print_spool as spool


def test_select_codepage_command_cp857():
    # ESC t n  (1B 74 n) — cp857 maps to code table 13.
    assert spool._select_codepage_cmd("cp857") == b"\x1b\x74\x0d"


def test_select_codepage_command_cp1254():
    assert spool._select_codepage_cmd("cp1254") == b"\x1b\x74\x2f"


def test_select_codepage_table_id_override():
    # A model-specific override wins over the preset (set during certification).
    assert spool._select_codepage_cmd("cp857", table_id=30) == b"\x1b\x74\x1e"


def test_norm_codepage_falls_back_to_cp857():
    assert spool._norm_codepage("bogus") == "cp857"
    assert spool._norm_codepage(None) in spool._CODEPAGE_TABLE_ID
    assert spool._norm_codepage("CP1254") == "cp1254"


def test_enc_turkish_is_single_byte_cp857():
    # Each Turkish glyph must be ONE byte, not the multi-byte UTF-8 sequence.
    for ch in "çşğüöıİŞĞÜÖÇ":
        assert len(spool._enc(ch, "cp857")) == 1, ch
    # And it must round-trip back to the same character.
    assert spool._enc("çşğ", "cp857").decode("cp857") == "çşğ"


def test_enc_is_not_utf8():
    # The whole point: "ç" must NOT be the 2-byte UTF-8 0xC3 0xA7.
    assert spool._enc("ç", "cp857") != "ç".encode("utf-8")


def test_enc_translit_fallback_for_unmappable():
    # cp437 has no "ş" — it should transliterate to ASCII "s", never blow up.
    out = spool._enc("şeker", "cp437")
    assert out == b"seker"


def test_render_receipt_emits_codepage_and_single_byte_turkish():
    payload = {
        "header": "Çay Bahçesi",
        "items": [{"name": "Köfte", "quantity": 2, "price": 50.0}],
        "total": 100.0,
        "footer": "Teşekkürler",
    }
    out = spool._render_receipt(payload, "cp857")
    # Code-table command present right after init.
    assert b"\x1b\x74\x0d" in out
    # Turkish header round-trips via cp857 (no UTF-8 garbage).
    assert "Çay Bahçesi".encode("cp857") in out
    assert "Köfte".encode("cp857") in out
    # UTF-8 multi-byte form must be ABSENT.
    assert "Çay".encode("utf-8") not in out


def test_render_kitchen_turkish_codepage():
    payload = {
        "station": "Sıcak Mutfak",
        "items": [{"name": "Şiş Köfte", "quantity": 1,
                   "special_instructions": "Az pişmiş"}],
    }
    out = spool._render_kitchen(payload, "cp1254")
    assert b"\x1b\x74\x2f" in out
    assert "Sıcak Mutfak".encode("cp1254") in out
    assert "Şiş Köfte".encode("cp1254") in out


def test_render_test_ticket_contains_turkish_charset():
    out = spool._render("test", {}, "cp857")
    assert b"\x1b\x74\x0d" in out
    assert "ç ş ğ ü ö ı".encode("cp857") in out


def test_interpret_status_paper_end():
    # DLE EOT 4 paper byte with bits 5,6 set => paper end (blocking).
    status = spool._interpret_status(offline=None, paper=0x60 | 0x12)
    assert "paper_end" in status["conditions"]
    assert status["blocking"] is True


def test_interpret_status_paper_near_end():
    status = spool._interpret_status(offline=None, paper=0x0C | 0x12)
    assert status["conditions"] == ["paper_near_end"]
    assert status["blocking"] is False


def test_interpret_status_cover_open():
    status = spool._interpret_status(offline=0x04 | 0x12, paper=None)
    assert "cover_open" in status["conditions"]
    assert status["blocking"] is True


def test_interpret_status_healthy():
    # Fixed bits only, no fault flags.
    status = spool._interpret_status(offline=0x12, paper=0x12)
    assert status["conditions"] == []
    assert status["blocking"] is False


@pytest.mark.asyncio
async def test_dispatch_escpos_surfaces_paper_out_as_failure(monkeypatch):
    """A successful TCP write but a paper-out status must mark the job failed so
    it is clearly visible in print_jobs status (not a silent green)."""
    async def _fake_send(host, port, data, **kw):
        return {"conditions": ["paper_end"], "blocking": True,
                "paper_byte": 0x72, "offline_byte": None}

    monkeypatch.setattr(spool, "_send_tcp", _fake_send)

    class _Printers:
        async def find_one(self, flt, proj=None):
            return {"printer_id": "kot1", "driver": "escpos_tcp",
                    "host": "10.0.0.9", "port": 9100, "enabled": True}

    monkeypatch.setattr(spool.db, "pos_printers", _Printers(), raising=False)

    job = {"rendered_bytes": b"x", "tenant_id": "t1", "printer_id": "kot1"}
    result = await spool._dispatch(job)
    assert result["driver"] == "escpos_tcp"
    assert result["ok"] is False
    assert "paper_end" in result["reason"]
    assert result["printer_status"]["blocking"] is True


@pytest.mark.asyncio
async def test_dispatch_escpos_ok_when_status_healthy(monkeypatch):
    async def _fake_send(host, port, data, **kw):
        return {"conditions": [], "blocking": False}

    monkeypatch.setattr(spool, "_send_tcp", _fake_send)

    class _Printers:
        async def find_one(self, flt, proj=None):
            return {"printer_id": "kot1", "driver": "escpos_tcp",
                    "host": "10.0.0.9", "port": 9100, "enabled": True}

    monkeypatch.setattr(spool.db, "pos_printers", _Printers(), raising=False)
    result = await spool._dispatch(
        {"rendered_bytes": b"x", "tenant_id": "t1", "printer_id": "kot1"}
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_dispatch_simulator_unaffected(monkeypatch):
    class _Printers:
        async def find_one(self, flt, proj=None):
            return None

    monkeypatch.setattr(spool.db, "pos_printers", _Printers(), raising=False)
    monkeypatch.setenv("POS_PRINT_DRIVER", "simulator")
    result = await spool._dispatch(
        {"rendered_bytes": b"abc", "tenant_id": "t1", "printer_id": "default"}
    )
    assert result == {"driver": "simulator", "ok": True, "bytes_len": 3}


@pytest.mark.asyncio
async def test_resolve_codepage_uses_printer_setting(monkeypatch):
    class _Printers:
        async def find_one(self, flt, proj=None):
            return {"codepage": "cp1254", "codepage_table_id": 71}

    monkeypatch.setattr(spool.db, "pos_printers", _Printers(), raising=False)
    cp, table_id = await spool._resolve_codepage("t1", "kot1")
    assert cp == "cp1254"
    assert table_id == 71


@pytest.mark.asyncio
async def test_resolve_codepage_default_when_missing(monkeypatch):
    class _Printers:
        async def find_one(self, flt, proj=None):
            return None

    monkeypatch.setattr(spool.db, "pos_printers", _Printers(), raising=False)
    cp, table_id = await spool._resolve_codepage("t1", "kot1")
    assert cp in spool._CODEPAGE_TABLE_ID
    assert table_id is None


# ── End-to-end real-socket coverage of _send_tcp (Task #614) ──────────────


class _FakeEscposPrinter:
    """A minimal ESC/POS network printer backed by a real asyncio TCP server.

    It consumes every byte the client streams (the rendered print job) and, when
    it sees a DLE EOT real-time status query (`0x10 0x04 n`), answers with a
    single status byte taken from `status_for_n` — exactly how a thermal printer
    replies on the raw 9100 port. `status_for_n` maps the query sub-command `n`
    (2 = offline cause, 4 = paper sensor) to the byte to send back; a missing or
    None entry means the printer stays silent for that query (modelling a printer
    that ignores the status request), which must drive _read_status to its
    timeout fallback.
    """

    def __init__(self, status_for_n: dict[int, int | None] | None = None):
        self.status_for_n = status_for_n or {}
        self.received = bytearray()
        self._server: asyncio.AbstractServer | None = None
        self.host = "127.0.0.1"
        self.port = 0

    async def __aenter__(self):
        self._server = await asyncio.start_server(self._handle, self.host, 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc):
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        scan = 0
        try:
            while True:
                chunk = await reader.read(256)
                if not chunk:
                    break
                self.received += chunk
                # Scan the captured stream for complete 3-byte DLE EOT queries we
                # have not yet answered, replying once per query in arrival order.
                while scan <= len(self.received) - 3:
                    if self.received[scan] == 0x10 and self.received[scan + 1] == 0x04:
                        n = self.received[scan + 2]
                        resp = self.status_for_n.get(n)
                        if resp is not None:
                            writer.write(bytes([resp & 0xFF]))
                            await writer.drain()
                        scan += 3
                    else:
                        scan += 1
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass


@pytest.mark.asyncio
async def test_send_tcp_writes_bytes_and_reads_paper_end_status():
    """_send_tcp must stream the print bytes to the socket AND read back the
    DLE EOT status, decoding a paper-end response to a blocking condition."""
    print_bytes = spool._render("test", {}, "cp857")
    # Offline query (n=2): healthy fixed bits only. Paper query (n=4): bits 5+6
    # set => paper end (blocking).
    async with _FakeEscposPrinter({2: 0x12, 4: 0x60}) as printer:
        status = await spool._send_tcp(
            printer.host, printer.port, print_bytes, status_timeout=1.0
        )
    # The rendered print payload actually reached the printer.
    assert bytes(print_bytes) in bytes(printer.received)
    # The status query bytes were also sent (write-then-read sequence ran).
    assert b"\x10\x04\x02" in bytes(printer.received)
    assert b"\x10\x04\x04" in bytes(printer.received)
    # The paper-end byte was decoded correctly.
    assert status is not None
    assert "paper_end" in status["conditions"]
    assert status["blocking"] is True
    assert status["paper_byte"] == 0x60


@pytest.mark.asyncio
async def test_send_tcp_reads_healthy_status():
    """A printer answering with no fault bits yields a non-blocking status."""
    async with _FakeEscposPrinter({2: 0x12, 4: 0x12}) as printer:
        status = await spool._send_tcp(
            printer.host, printer.port, b"\x1b\x40hello", status_timeout=1.0
        )
    assert status is not None
    assert status["conditions"] == []
    assert status["blocking"] is False


@pytest.mark.asyncio
async def test_send_tcp_silent_printer_returns_none_without_breaking_print():
    """A printer that swallows the bytes but never answers the status query must
    drive _read_status to its timeout and return None — the print itself (the
    byte write) still succeeds and is received."""
    print_bytes = b"\x1b\x40receipt-data"
    async with _FakeEscposPrinter({}) as printer:  # never replies to any query
        status = await spool._send_tcp(
            printer.host, printer.port, print_bytes, status_timeout=0.3
        )
    # No status decoded (printer stayed silent past the timeout).
    assert status is None
    # But the print bytes were still delivered — the silent status read did not
    # break the actual print.
    assert print_bytes in bytes(printer.received)


@pytest.mark.asyncio
async def test_send_tcp_without_status_query_still_writes():
    """query_status=False skips the DLE EOT round-trip entirely (returns None)
    while still streaming the print bytes."""
    print_bytes = b"\x1b\x40no-status"
    async with _FakeEscposPrinter({2: 0x12, 4: 0x12}) as printer:
        status = await spool._send_tcp(
            printer.host, printer.port, print_bytes, query_status=False
        )
    assert status is None
    assert print_bytes in bytes(printer.received)
    # No status query bytes were ever sent.
    assert b"\x10\x04" not in bytes(printer.received)
