from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    import discord


def format_emoji_sync_summary(actions: dict[str, int]) -> str:
    parts = [f"{key}: {value}" for key, value in actions.items() if value > 0]
    summary = ", ".join(parts) if parts else "No changes needed."
    return f"✅ Emoji sync complete. {summary}"


async def sync_emojis_from_api(
    bot: discord.Client,
    emoji_links_path: Path,
) -> tuple[dict[str, int], list[str]]:
    actions = {"Updated": 0, "Added": 0, "Skipped": 0}
    errors: list[str] = []

    local_links: dict[str, str] = {}
    if emoji_links_path.exists():
        with open(emoji_links_path, encoding="utf-8") as f:
            local_links = json.load(f)

    remote_emojis = await bot.fetch_application_emojis()
    if not remote_emojis:
        return actions, errors

    updated_links = local_links.copy()
    for emoji in remote_emojis:
        url_str = str(emoji.url)
        if emoji.name in updated_links:
            if updated_links[emoji.name] != url_str:
                actions["Updated"] += 1
                updated_links[emoji.name] = url_str
            else:
                actions["Skipped"] += 1
        else:
            actions["Added"] += 1
            updated_links[emoji.name] = url_str

    if actions["Updated"] > 0 or actions["Added"] > 0:
        emoji_links_path.parent.mkdir(parents=True, exist_ok=True)
        with open(emoji_links_path, "w", encoding="utf-8") as f:
            json.dump(updated_links, f, indent=2, ensure_ascii=False, sort_keys=True)

    return actions, errors


async def sync_emojis_to_discord(
    bot: discord.Client,
    emoji_links_path: Path,
) -> tuple[dict[str, int], list[str]]:
    actions = {"Created": 0, "Replaced": 0, "Skipped": 0, "Deleted": 0, "Errors": 0}
    errors: list[str] = []

    with open(emoji_links_path, encoding="utf-8") as f:
        local_links: dict[str, str] = json.load(f)

    remote_emojis = {e.name: e for e in await bot.fetch_application_emojis()}

    async with aiohttp.ClientSession() as session:
        for name, url in local_links.items():
            if name in remote_emojis:
                actions["Skipped"] += 1
                continue

            actions["Created"] += 1

            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        errors.append(f"Failed to download {name} (HTTP {resp.status})")
                        actions["Errors"] += 1
                        continue
                    image_bytes = await resp.read()

                await bot.create_application_emoji(name=name, image=image_bytes)
            except Exception as exc:
                errors.append(f"Failed to create {name}: {exc}")
                actions["Errors"] += 1

    return actions, errors
