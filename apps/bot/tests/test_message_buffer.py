from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
if str(BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_ROOT))

DB_SUPPORT_ROOT = Path(__file__).resolve().parents[3] / "packages" / "dbSupport" / "src"
if str(DB_SUPPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(DB_SUPPORT_ROOT))

UTILS_ROOT = BOT_ROOT / "utils"
if str(UTILS_ROOT) not in sys.path:
    sys.path.insert(0, str(UTILS_ROOT))

repositories_pkg = types.ModuleType("repositories")
repositories_pkg.__path__ = []
sys.modules.setdefault("repositories", repositories_pkg)
for module_name, class_name in (
    ("repositories.messageRepository", "MessageRepository"),
    ("repositories.userRepository", "UserRepository"),
):
    module = types.ModuleType(module_name)
    setattr(module, class_name, object)
    sys.modules.setdefault(module_name, module)

MESSAGE_BUFFER_PATH = UTILS_ROOT / "message_buffer.py"
spec = importlib.util.spec_from_file_location("message_buffer", MESSAGE_BUFFER_PATH)
assert spec is not None and spec.loader is not None
message_buffer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(message_buffer)


class _FakeResult:
    def __init__(self, rowcount: int = 0):
        self.rowcount = rowcount


class _FakeMessageRepository:
    def __init__(self, session):
        self._session = session

    async def bulk_create_messages(self, messages: list[dict]) -> int:
        self._session.inserted_messages = list(messages)
        return len(messages)


class _FakeUserRepository:
    def __init__(self, session):
        self._session = session

    async def bulk_increment_message_counts(self, author_counts: dict[str, dict[str, int]]) -> None:
        self._session.author_counts = author_counts


class _FakeSession:
    def __init__(self):
        self.execute_calls: list[object] = []
        self.flush_calls = 0
        self.inserted_messages: list[dict] = []
        self.author_counts: dict[str, dict[str, int]] = {}

    async def execute(self, statement):
        self.execute_calls.append(statement)
        return _FakeResult(rowcount=2)

    async def flush(self):
        self.flush_calls += 1


class _FakeGuild:
    def __init__(self, name: str):
        self.name = name


class _FakeChannel:
    def __init__(self, channel_id: int, name: str, guild_name: str):
        self.id = channel_id
        self.name = name
        self.guild = _FakeGuild(guild_name)


def _reset_buffers() -> None:
    message_buffer._buffers.clear()  # noqa: SLF001
    message_buffer._author_counts.clear()  # noqa: SLF001


def test_buffer_snapshot_orders_messages_across_channels() -> None:
    async def run() -> list[dict]:
        _reset_buffers()
        await message_buffer.buffer_message_for_channel(
            1,
            {
                "id": "m2",
                "author_id": "200",
                "author_name": "Later",
                "author_avatar": None,
                "content": "second",
                "images_url": [],
                "channel_id": "1",
                "guild_id": "9",
                "referred_message_id": None,
                "status": "ACTIVE",
                "retention_until": None,
                "timestamp": (datetime.now(UTC) + timedelta(seconds=10)).isoformat(),
            },
        )
        await message_buffer.buffer_message_for_channel(
            2,
            {
                "id": "m1",
                "author_id": "100",
                "author_name": "Earlier",
                "author_avatar": None,
                "content": "first",
                "images_url": [],
                "channel_id": "2",
                "guild_id": "9",
                "referred_message_id": None,
                "status": "ACTIVE",
                "retention_until": None,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        return await message_buffer.get_buffered_messages_for_channels([1, 2])

    snapshot = asyncio.run(run())
    assert [message["id"] for message in snapshot] == ["m1", "m2"]
    _reset_buffers()


def test_flush_channel_messages_persists_batch_and_clears_buffer(monkeypatch) -> None:
    async def run() -> tuple[int, _FakeSession, list[dict]]:
        _reset_buffers()
        session = _FakeSession()
        monkeypatch.setattr(message_buffer, "MessageRepository", _FakeMessageRepository)
        monkeypatch.setattr(message_buffer, "UserRepository", _FakeUserRepository)

        await message_buffer.buffer_message_for_channel(
            7,
            {
                "id": "msg-1",
                "author_id": "42",
                "author_name": "Alice",
                "author_avatar": None,
                "content": "hello",
                "images_url": [],
                "channel_id": "7",
                "guild_id": "9",
                "referred_message_id": None,
                "status": "ACTIVE",
                "retention_until": None,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        await message_buffer.buffer_message_for_channel(
            7,
            {
                "id": "msg-2",
                "author_id": "42",
                "author_name": "Alice",
                "author_avatar": None,
                "content": "world",
                "images_url": [],
                "channel_id": "7",
                "guild_id": "9",
                "referred_message_id": None,
                "status": "ACTIVE",
                "retention_until": None,
                "timestamp": (datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
            },
        )

        inserted = await message_buffer.flush_channel_messages(session, 7)
        remaining = await message_buffer.get_buffered_messages_for_channels([7])
        return inserted, session, remaining

    inserted, session, remaining = asyncio.run(run())
    assert inserted == 2
    assert len(session.inserted_messages) == 2
    assert session.author_counts == {"42": 2}
    assert remaining == []
    _reset_buffers()


def test_build_report_replay_messages_uses_buffered_reply_data() -> None:
    source = _FakeChannel(1, "source", "Guild A")
    target = _FakeChannel(2, "target", "Guild B")
    buffered_messages = [
        {
            "id": "root",
            "author_id": "100",
            "author_name": "Alice",
            "author_avatar": "https://example.com/a.png",
            "content": "root message",
            "images_url": [],
            "channel_id": "1",
            "guild_id": "9",
            "referred_message_id": None,
            "status": "ACTIVE",
            "retention_until": None,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        {
            "id": "reply",
            "author_id": "200",
            "author_name": "Bob",
            "author_avatar": "https://example.com/b.png",
            "content": "reply message",
            "images_url": [],
            "channel_id": "2",
            "guild_id": "9",
            "referred_message_id": "root",
            "status": "ACTIVE",
            "retention_until": None,
            "timestamp": (datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
        },
    ]

    captured = message_buffer.build_report_replay_messages(buffered_messages, source, target)

    assert captured[0]["channel_label"] == "source (Guild A)"
    assert captured[1]["channel_label"] == "target (Guild B)"
    assert captured[1]["reply_to"]["author"] == "Alice"
    assert captured[1]["reply_to"]["content"] == "root message"
