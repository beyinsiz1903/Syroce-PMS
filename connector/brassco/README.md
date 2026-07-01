# Brassco Lock Connector

Brassco is an offline RFID keycard system. There is **no public cloud API** — the
hotel runs the **BKY** software (BKY 12.1 / BKY Pro 12.1) on a reception Windows
PC, and integration happens through a local **DLL** (Delphi/VB, MIFARE sector 15).

Because of that, the Syroce cloud cannot talk to the lock directly. Instead:

```
Syroce cloud  ──(authenticated HTTPS)──>  this connector (reception Windows PC)  ──(BKY DLL)──>  card encoder / lock
```

The Syroce side (already built) emits vendor-neutral lock commands
(`encode_card` / `revoke_card`) into a per-hotel, idempotent queue whenever a
physical keycard is issued, deactivated, on check-out, or on a room move. This
connector pulls those commands, drives the BKY DLL, and acknowledges each one.

## Setup

1. **Register the connector** (on the server / Replit shell), once per hotel PC:

   ```
   python -m scripts.provision_lock_connector --tenant <TENANT_ID> --name "Resepsiyon PC"
   ```

   Copy the printed `KEY` — it is shown only once. Do not paste it into chat/commits.

2. **On the reception Windows PC**, install Python + `pip install requests`, copy
   `brassco_connector.py`, and set environment variables:

   - `SYROCE_BASE_URL`  — e.g. `https://your-hotel.replit.app`
   - `LOCK_BRIDGE_KEY`  — the key from step 1
   - `BRASSCO_DLL_PATH` — full path to the Brassco integration DLL
   - `POLL_INTERVAL`    — optional, seconds (default 5)

3. **Wire the DLL**: implement `drive_brassco_dll(...)` using the Brassco BKY
   SDK / DLL documentation (the encode/cancel function names and the MIFARE
   sector-15 argument layout). This is the only vendor-specific code. Until it is
   wired in, the connector reports failure and the cloud keeps commands queued
   (nothing is silently dropped).

4. Run it (and set it to auto-start, e.g. as a Windows service / Task Scheduler):

   ```
   python brassco_connector.py
   ```

## If you cannot get the Brassco BKY SDK / DLL

The Syroce side works regardless — commands queue up and wait. To complete the
physical link you need one of:

- **Brassco BKY SDK / DLL + docs** from Brassco or your installer (best path;
  enables `EncodeCard` / `CancelCard` style calls and MIFARE sector-15 layout).
- **A PMS-integration build of BKY** — some BKY Pro setups expose a file/folder
  or serial "card request" interface the connector can write to instead of the
  raw DLL.
- **A certified Brassco integrator** to supply or build the local bridge.
- **Online Bluetooth Brassco locks** (if the hotel upgrades) — a different,
  possibly network-capable model; would need its own adapter.

In all cases only `drive_brassco_dll(...)` changes; the cloud contract stays the
same.
