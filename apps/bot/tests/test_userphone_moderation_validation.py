from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
if str(BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_ROOT))

DB_SUPPORT_ROOT = Path(__file__).resolve().parents[3] / "packages" / "dbSupport" / "src"
if str(DB_SUPPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(DB_SUPPORT_ROOT))

from models import InfractionType
from services.moderation.moderationService import ModerationService
from services.userphone import validationService as validation_service_module
from services.userphone.validationService import ValidationService


class _FakeInfraction:
    def __init__(self, infraction_type, user_id=None, server_id=None, reason="old"):
        self.type = infraction_type
        self.userId = user_id
        self.serverId = server_id
        self.reason = reason


class _FakeSession:
    def __init__(self):
        self.flush_calls = 0

    async def flush(self):
        self.flush_calls += 1


def test_validation_service_delegates_ban_check(monkeypatch):
    async def run():
        captured = {}

        async def fake_check(ctx, session, cache_manager, validation_service, bot, check_username=True, check_guild_name=True):
            captured["args"] = (
                ctx,
                session,
                cache_manager,
                validation_service,
                bot,
                check_username,
                check_guild_name,
            )
            return True, None

        monkeypatch.setattr(validation_service_module, "_check_bans_and_validation", fake_check)

        service = ValidationService(session=object())
        ctx = object()
        cache_manager = object()
        bot = object()
        result = await service.check_bans_and_validation(
            ctx,
            session=None,
            cache_manager=cache_manager,
            bot=bot,
            check_username=False,
            check_guild_name=True,
        )

        assert result == (True, None)
        assert captured["args"] == (ctx, None, cache_manager, service, bot, False, True)

    asyncio.run(run())


def test_moderation_service_flushes_access_cache_for_infraction_changes(monkeypatch):
    async def run():
        fake_session = _FakeSession()
        calls: list[tuple[str | None, str | None]] = []

        class FakeModerationRepository:
            def __init__(self, session):
                self.session = session

            async def get_active_by_type(self, **kwargs):
                return []

            async def create_infraction(self, **kwargs):
                return _FakeInfraction(
                    kwargs["type"],
                    user_id=kwargs.get("user_id"),
                    server_id=kwargs.get("guild_id"),
                    reason=kwargs.get("reason", "old"),
                )

            async def get_infraction_by_id(self, infraction_id):
                return _FakeInfraction(InfractionType.BAN, user_id="123", server_id="456")

            async def update_infraction(self, *args, **kwargs):
                return None

            async def delete_infraction(self, infraction_id):
                return None

        async def fake_flush(user_id=None, guild_id=None):
            calls.append((user_id, guild_id))

        monkeypatch.setattr("services.moderation.moderationService.ModerationRepository", FakeModerationRepository)
        monkeypatch.setattr("services.moderation.moderationService.CacheManager.flush_userphone_access_cache", staticmethod(fake_flush))

        service = ModerationService(fake_session)

        await service.create_infraction(
            mod_id="1",
            user_id="123",
            server_id="456",
            infraction_type=InfractionType.BAN,
        )
        await service.revoke_infraction("inf-1", mod_id="2")
        await service.delete_infraction("inf-1")

        assert calls == [("123", "456"), ("123", "456"), ("123", "456")]
        assert fake_session.flush_calls == 3

    asyncio.run(run())