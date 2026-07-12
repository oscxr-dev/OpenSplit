"""Best-effort NIP-01 publishing of signed proof events to Nostr relays.

A signed Split Proof only becomes PUBLIC proof once it can be found on the
open network: publishing sends the stored kind-2718 event (see
services/nostr_proof.py) to the operator-configured relays so anyone can
retrieve and verify it by event id, with no access to this server.

Deliberately fire-and-forget:

- ``publish_event`` NEVER raises. Every failure mode — refused connection,
  handshake error, timeout, relay rejection — becomes a per-relay result
  entry, so callers can persist and show honest outcomes without guarding.
- Relays are isolated: each gets its own connection and its own timeout and
  they run concurrently, so one dead relay can neither slow nor sink the
  others, and the whole publish is bounded by the single per-relay timeout.
- One NIP-01 exchange per relay: connect, send ``["EVENT", <event>]``, read
  frames until the relay's ``["OK", <event id>, <accepted>, <message>]`` ack
  (or the timeout), close. No subscriptions, no persistent connections, no
  reads beyond the ack.

Publishing is intentionally NOT part of any money path — routers/proof.py
calls this only after the signed event is verified and persisted, so nothing
that happens here can affect signing, payouts, or reconciliation.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

# Module-level seam (tests fake this): the new-style asyncio client, imported
# explicitly because the top-level ``websockets.connect`` alias has changed
# meaning across major versions.
from websockets.asyncio.client import connect as ws_connect

RELAY_TIMEOUT_SECONDS = 5.0
# Relay ack text / exception text is untrusted input headed for our DB and
# UI; keep recorded errors compact.
_MAX_ERROR_CHARS = 200


def _result(relay: str, ok: bool, *, error: object = None) -> dict:
    entry = {
        "relay": relay,
        "ok": ok,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if error:
        entry["error"] = str(error)[:_MAX_ERROR_CHARS]
    return entry


async def _publish_to_relay(event: dict, relay: str, timeout: float) -> dict:
    """One relay, one result. Catches everything — the caller never guards."""
    if not relay.startswith(("wss://", "ws://")):
        return _result(relay, False, error="not a websocket (wss://) URL")
    try:
        async with asyncio.timeout(timeout):
            async with ws_connect(relay, open_timeout=timeout, close_timeout=1) as ws:
                await ws.send(
                    json.dumps(["EVENT", event], separators=(",", ":"), ensure_ascii=False)
                )
                # Relays may interleave NOTICE/AUTH/other frames; only the OK
                # ack for OUR event id answers the publish (NIP-01 semantics).
                while True:
                    frame = json.loads(await ws.recv())
                    if (
                        isinstance(frame, list)
                        and len(frame) >= 3
                        and frame[0] == "OK"
                        and frame[1] == event.get("id")
                    ):
                        if bool(frame[2]):
                            return _result(relay, True)
                        message = frame[3] if len(frame) > 3 and frame[3] else None
                        return _result(relay, False, error=message or "rejected by relay")
    except TimeoutError:
        return _result(relay, False, error=f"no OK ack within {timeout:g}s")
    except Exception as exc:  # any transport/parse failure — recorded, never raised
        detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        return _result(relay, False, error=detail)


async def publish_event(
    event: dict, relays: list[str], timeout: float = RELAY_TIMEOUT_SECONDS
) -> list[dict]:
    """Publish ``event`` to every relay concurrently; one result per relay.

    Never raises. Blank entries and duplicates are dropped (a relay dedupes
    by event id anyway; one honest entry per relay is what the UI shows).
    An empty relay list publishes nowhere and returns [].
    """
    targets = list(dict.fromkeys(r.strip() for r in relays if r and r.strip()))
    if not targets:
        return []
    return list(
        await asyncio.gather(*(_publish_to_relay(event, r, timeout) for r in targets))
    )
