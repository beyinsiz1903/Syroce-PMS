"""Brassco on-prem lock connector (reference implementation).

This program runs on the hotel's reception Windows PC where the Brassco BKY
software, the card encoder, and the vendor DLL are installed. It is the bridge
between the Syroce cloud and the physical lock system:

    Syroce cloud  --(authenticated HTTPS pull/ack)-->  this connector  --(BKY DLL)-->  card encoder / lock

Flow (repeats on an interval):
  1. Pull pending lock commands for this hotel from the cloud (X-Lock-Bridge-Key).
  2. For each command, drive the Brassco BKY DLL to encode / revoke the card.
  3. Acknowledge success (or failure -> the cloud re-queues it for retry).

The ONLY vendor-specific part is `drive_brassco_dll(...)`. Its exact DLL name,
function names, and argument layout (MIFARE sector 15 encoding per Brassco's
integration kit) come from the Brassco BKY SDK / DLL documentation, which must be
obtained from Brassco or your installer. Everything else is vendor-neutral.

Config via environment variables (no secrets in code):
  SYROCE_BASE_URL   e.g. https://your-hotel.replit.app
  LOCK_BRIDGE_KEY   the connector key from provision_lock_connector.py
  POLL_INTERVAL     seconds between polls (default 5)
  BRASSCO_DLL_PATH  full path to the Brassco integration DLL (Windows)
"""
import os
import sys
import time

try:
    import requests
except ImportError:
    print("Install dependency first:  pip install requests", file=sys.stderr)
    raise


BASE_URL = os.environ.get("SYROCE_BASE_URL", "").rstrip("/")
LOCK_BRIDGE_KEY = os.environ.get("LOCK_BRIDGE_KEY", "")
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "5"))
BRASSCO_DLL_PATH = os.environ.get("BRASSCO_DLL_PATH", "")

HEADERS = {"X-Lock-Bridge-Key": LOCK_BRIDGE_KEY}


def drive_brassco_dll(command: dict) -> tuple[bool, str]:
    """Encode or revoke a physical card via the Brassco BKY DLL.

    >>> REPLACE THIS BODY using the Brassco BKY SDK / DLL documentation. <<<

    Reference sketch (Windows, Delphi/VB DLL via ctypes) — names are placeholders
    until the real SDK signatures are known:

        import ctypes
        dll = ctypes.WinDLL(BRASSCO_DLL_PATH)
        if command["command"] == "encode_card":
            rc = dll.EncodeCard(
                command["room_number"].encode("ascii"),
                command["valid_from"].encode("ascii"),
                command["valid_until"].encode("ascii"),
            )
        else:  # revoke_card
            rc = dll.CancelCard(command["card_number"].encode("ascii"))
        return (rc == 0, f"dll_rc={rc}")

    Until the SDK is wired in, we fail (return False) so the cloud keeps the
    command queued rather than silently dropping a physical-card action.
    """
    if not BRASSCO_DLL_PATH:
        return (False, "BRASSCO_DLL_PATH not configured / BKY SDK not wired in")
    # TODO: load BRASSCO_DLL_PATH and call the real encode/cancel functions.
    return (False, "Brassco DLL call not implemented — supply BKY SDK signatures")


def poll_once() -> int:
    resp = requests.get(f"{BASE_URL}/api/internal/lock-bridge/commands", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    commands = resp.json().get("commands", [])
    for cmd in commands:
        try:
            success, detail = drive_brassco_dll(cmd)
        except Exception as e:  # noqa: BLE001
            success, detail = False, f"connector exception: {e.__class__.__name__}"
        ack = requests.post(
            f"{BASE_URL}/api/internal/lock-bridge/commands/{cmd['id']}/ack",
            headers=HEADERS,
            json={"success": success, "detail": detail},
            timeout=15,
        )
        ack.raise_for_status()
    return len(commands)


def main() -> None:
    if not BASE_URL or not LOCK_BRIDGE_KEY:
        print("Set SYROCE_BASE_URL and LOCK_BRIDGE_KEY environment variables.", file=sys.stderr)
        sys.exit(2)
    print(f"Brassco connector started. Polling {BASE_URL} every {POLL_INTERVAL}s.")
    while True:
        try:
            n = poll_once()
            if n:
                print(f"Processed {n} command(s).")
        except Exception as e:  # noqa: BLE001 - keep the connector alive
            print(f"poll error: {e.__class__.__name__}: {e}", file=sys.stderr)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
