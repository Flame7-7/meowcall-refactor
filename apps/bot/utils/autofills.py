import discord
from discord import app_commands


async def punishment_reason_autocomplete(
    interaction: discord.Interaction,
    current: str,
):
    reasons = [
        "Spamming or flooding",
        "Toxicity",
        "NSFW Content within a call",
        "Harassment, or bullying",
        "Self promotion",
        "Slurs, or hate speech",
        "Misuse of the report system",
        "Impersonation of a Meowcall official",
        "Failure to follow Discord TOS",
        "Ban Evasion",
    ]

    return [
        app_commands.Choice(name=reason, value=reason)
        for reason in reasons
        if current.lower() in reason.lower()
    ][:25]  # Discord max is 25 choices
