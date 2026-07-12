"""app/services/nostr_publish.py — best-effort relay publishing.

Pure asyncio tests against a fake websocket seam (nostr_publish.ws_connect);
no network, no DB. The invariants under test are the safety properties the
proof endpoints rely on: publish_event NEVER raises, one relay's failure
never affects another relay's result, and every attempt yields one honest
result entry.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.services import nostr_publish
from app.services.nostr_publish import publish_event

pytestmark = pytest.mark.asyncio

EVENT = {
    "id": "ab" * 32,
    "pubkey": "cd" * 32,
    "created_at": 1_780_000_000,
    "kind": 2718,
    "tags": [["t", "opensplit-proof"]],
    "content": '{"spec":"opensplit-split-proof/v1"}',
    "sig": "ff" * 64,
}

OK_TRUE = json.dumps(["OK", EVENT["id"], True, ""])
OK_FALSE_SPAM = json.dumps(["OK", EVENT["id"], False, "blocked: spam"])


class FakeRelay:
    """Async-context websocket double for one relay."""

    def __init__(self, replies=None, *, connect_error: Exception | None = None):
        self.replies = list(replies or [])
        self.connect_error = connect_error
        self.sent: list[str] = []

    async def __aenter__(self):
        if self.connect_error is not None:
            raise self.connect_error
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, raw: str):
        self.sent.append(raw)

    async def recv(self) -> str:
        if self.replies:
            return self.replies.pop(0)
        await asyncio.Event().wait()  # silent relay: never answers


def wire_relays(monkeypatch, relays: dict[str, FakeRelay]):
    """Point the ws_connect seam at per-URL fakes."""

    def connect(url, **kwargs):
        return relays[url]

    monkeypatch.setattr(nostr_publish, "ws_connect", connect)


# ── Single-relay outcomes ──────────────────────────────────────────────────
async def test_accepting_relay_yields_ok_and_sends_nip01_event(monkeypatch):
    relay = FakeRelay([OK_TRUE])
    wire_relays(monkeypatch, {"wss://good.test": relay})

    results = await publish_event(EVENT, ["wss://good.test"])

    assert results == [
        {"relay": "wss://good.test", "ok": True, "at": results[0]["at"]}
    ]
    assert "error" not in results[0]
    # Exactly one standard NIP-01 EVENT frame carrying the event verbatim.
    assert [json.loads(raw) for raw in relay.sent] == [["EVENT", EVENT]]


async def test_relay_rejection_records_the_relays_message(monkeypatch):
    wire_relays(monkeypatch, {"wss://strict.test": FakeRelay([OK_FALSE_SPAM])})

    results = await publish_event(EVENT, ["wss://strict.test"])

    assert results[0]["ok"] is False
    assert results[0]["error"] == "blocked: spam"


async def test_relay_rejection_without_message_still_gets_an_error(monkeypatch):
    wire_relays(
        monkeypatch,
        {"wss://terse.test": FakeRelay([json.dumps(["OK", EVENT["id"], False])])},
    )

    results = await publish_event(EVENT, ["wss://terse.test"])

    assert results[0]["ok"] is False
    assert results[0]["error"] == "rejected by relay"


async def test_silent_relay_times_out_as_a_failure(monkeypatch):
    wire_relays(monkeypatch, {"wss://silent.test": FakeRelay()})

    results = await publish_event(EVENT, ["wss://silent.test"], timeout=0.05)

    assert results[0]["ok"] is False
    assert "no OK ack" in results[0]["error"]


async def test_refused_connection_is_a_result_not_an_exception(monkeypatch):
    wire_relays(
        monkeypatch,
        {"wss://down.test": FakeRelay(connect_error=OSError("connection refused"))},
    )

    results = await publish_event(EVENT, ["wss://down.test"])

    assert results[0]["ok"] is False
    assert "connection refused" in results[0]["error"]


async def test_non_websocket_url_is_rejected_without_connecting(monkeypatch):
    def never(url, **kwargs):  # any connect attempt would blow the test up
        raise AssertionError("must not connect to a non-websocket URL")

    monkeypatch.setattr(nostr_publish, "ws_connect", never)

    results = await publish_event(EVENT, ["https://relay.example"])

    assert results[0]["ok"] is False
    assert "wss://" in results[0]["error"]


# ── Protocol details ───────────────────────────────────────────────────────
async def test_interleaved_frames_and_foreign_oks_are_skipped(monkeypatch):
    chatty = FakeRelay(
        [
            json.dumps(["NOTICE", "rate limits apply"]),
            json.dumps(["AUTH", "challenge-string"]),
            json.dumps(["OK", "00" * 32, False, "some other event"]),
            OK_TRUE,
        ]
    )
    wire_relays(monkeypatch, {"wss://chatty.test": chatty})

    results = await publish_event(EVENT, ["wss://chatty.test"])

    assert results[0]["ok"] is True


async def test_garbage_frame_becomes_a_recorded_failure(monkeypatch):
    wire_relays(monkeypatch, {"wss://garbage.test": FakeRelay(["not json"])})

    results = await publish_event(EVENT, ["wss://garbage.test"])

    assert results[0]["ok"] is False
    assert "JSONDecodeError" in results[0]["error"]


async def test_overlong_relay_error_text_is_truncated(monkeypatch):
    long_msg = json.dumps(["OK", EVENT["id"], False, "x" * 5000])
    wire_relays(monkeypatch, {"wss://verbose.test": FakeRelay([long_msg])})

    results = await publish_event(EVENT, ["wss://verbose.test"])

    assert len(results[0]["error"]) <= 200


# ── Isolation & input hygiene ──────────────────────────────────────────────
async def test_one_bad_relay_never_sinks_the_others(monkeypatch):
    wire_relays(
        monkeypatch,
        {
            "wss://down.test": FakeRelay(connect_error=OSError("refused")),
            "wss://silent.test": FakeRelay(),  # will time out
            "wss://good.test": FakeRelay([OK_TRUE]),
        },
    )

    results = await publish_event(
        EVENT, ["wss://down.test", "wss://silent.test", "wss://good.test"], timeout=0.05
    )

    # One result per relay, in input order, each judged independently.
    assert [r["relay"] for r in results] == [
        "wss://down.test",
        "wss://silent.test",
        "wss://good.test",
    ]
    assert [r["ok"] for r in results] == [False, False, True]


async def test_empty_and_blank_relay_lists_publish_nowhere(monkeypatch):
    def never(url, **kwargs):
        raise AssertionError("must not connect")

    monkeypatch.setattr(nostr_publish, "ws_connect", never)

    assert await publish_event(EVENT, []) == []
    assert await publish_event(EVENT, ["", "   "]) == []


async def test_duplicate_relays_are_attempted_once(monkeypatch):
    relay = FakeRelay([OK_TRUE])
    wire_relays(monkeypatch, {"wss://good.test": relay})

    results = await publish_event(EVENT, ["wss://good.test", " wss://good.test "])

    assert len(results) == 1
    assert len(relay.sent) == 1
