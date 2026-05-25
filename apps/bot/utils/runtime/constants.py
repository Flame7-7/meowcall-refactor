from __future__ import annotations

import ast
import logging
import os
import re
from pathlib import Path
from typing import Final

import redis.asyncio as redis_async
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)


# Converts human input to True / False
def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

def _parse_shard_ids(value: str | None) -> list[int]:
    if not value:
        return [0]
    return [int(s.strip()) for s in value.split(',')]

class MeowcallConstants:
    # Primary
    CLIENT_ID: int = int(os.getenv("CLIENT_ID") or "0")
    PRODUCTION: Final[bool] = (
        str(os.getenv("ENVIRONMENT") or "development").lower() == "production"
    )
    IS_CLUSTERED: Final[bool] = _to_bool(os.getenv("CORE_IS_CLUSTERED"), default=False)
    CLUSTER_SHARD_COUNT: Final[int] = int(os.getenv("CORE_SHARD_COUNT") or 0)
    CLUSTER_SHARD_IDS: Final[list[int]] = _parse_shard_ids(os.getenv('CORE_SHARD_IDS'))
    ORCHESTRATOR_WS: Final[str] = os.getenv("CORE_ORCHESTRATOR_WS", "ws://orchestrator:8080")
    HOLD_SHARDS_CLOSED: Final[bool] = _to_bool(os.getenv("CORE_HOLD_SHARDS_CLOSED"), default=False)

    CLUSTER_ID: Final[str] = os.getenv("CORE_CLUSTER_ID") or "cluster-0"
    DEBUG: Final[bool] = _to_bool(os.getenv("DEBUG"), default=False)
    TOKEN: Final[str] = str(os.getenv("TOKEN") or os.getenv("DISCORD_TOKEN") or "")
    DATABASE_URL: Final[str] = str(
        os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN") or ""
    )
    REDIS_URI: Final[str] = str(os.getenv("REDIS_URI") or "redis://localhost:6379/1")
    PREFIX: Final[str] = (
        prefix
        if (prefix := os.getenv("PREFIX")) is not None
        and prefix.strip().lower() != "none"
        else "m."
    )

    # URLs
    SUPPORT_INVITE: Final[str] = str(os.getenv("SUPPORT_INVITE"))
    OFFICIAL_SERVER_INVITE: Final[str] = str(
        os.getenv("OFFICIAL_SERVER_INVITE") or SUPPORT_INVITE
    )
    STARTUP_ANNOUNCEMENT_ENABLED: Final[bool] = _to_bool(
        os.getenv("STARTUP_ANNOUNCEMENT_ENABLED"), default=False
    )
    STARTUP_ANNOUNCEMENT_MESSAGE: Final[str] = str(
        os.getenv("STARTUP_ANNOUNCEMENT_MESSAGE")
        or f"Official Server of Meowcall has been changed to {OFFICIAL_SERVER_INVITE}."
    )
    DONATE_LINK: Final[str] = str(os.getenv("DONATE_LINK"))
    VOTE_URL: Final[str] = "https://top.gg/bot/769921109209907241/vote"
    TOPGG_TOKEN: Final[str] = str(os.getenv("TOPGG_TOKEN") or "")

    # Staff Mapping
    DEVELOPER_GUILD_ID: Final[int] = int(os.getenv("DEVELOPER_GUILD_ID") or 0)
    STAFF_ROLE_ID: Final[int] = int(os.getenv("STAFF_ROLE_ID") or 0)
    STAFF_REPORT_CHANNEL_ID: Final[int] = int(os.getenv("STAFF_REPORT_CHANNEL_ID") or 0)

    # Redis Performance
    POOL_WARMING: Final[bool] = _to_bool(os.getenv("POOL_WARMING"), default=True)
    REDIS_MAX_CONNECTIONS: Final[int] = int(os.getenv("REDIS_MAX_CONNECTIONS") or "150")

    # Sentry
    SENTRY_DSN: Final[str] = str(os.getenv("SENTRY_DSN"))
    SENTRY_SEND_DEFAULT_PII: Final[bool] = _to_bool(
        os.getenv("SENTRY_PII"), default=True
    )

    # NSFW Detection
    NSFW_DETECTOR_URL: Final[str] = str(
        os.getenv("NSFW_DETECTOR_URL") or "http://localhost:3000/v1/detect/urls"
    )
    ENABLE_NSFW_DETECTION: Final[bool] = _to_bool(
        os.getenv("ENABLE_NSFW"), default=True
    )

    # Rate limits
    RATE_LIMITS: Final[dict] = {
        "premium": {
            "commands": {"limit": 5, "period": 5},  # 2 commands/sec
            "webhook": {"limit": 10, "period": 300},  # 1 webhook / 30 sec average
        },
        "standard": {
            "commands": {"limit": 2.5, "period": 5},  # 2 command/sec
            "webhook": {"limit": 5, "period": 300},  # 1 webhook / 60 sec average
        },
    }

    @property
    def version(self):
        from utils.parsing import parse_version_from_toml

        version: Final[str] = str(parse_version_from_toml() or "0.0.0-dev")
        if str(os.getenv("ENVIRONMENT")).lower() == "development":
            return f"{version}-dev"
        return version

    def __init__(self):
        self.developers: Final[list[int]] = self._get_auth_users()

    def _get_auth_users(self) -> list[int]:

        raw = os.getenv("AUTH")
        if not raw:
            return []
        try:
            parsed = ast.literal_eval(raw)
            return [int(x) for x in parsed] if isinstance(parsed, (list, tuple)) else []
        except Exception as exc:
            logger.debug("Failed to parse AUTH environment variable: %s", exc)
            return []


def build_redis_client(redis_uri: str):
    return redis_async.from_url(
        redis_uri,
        max_connections=constants.REDIS_MAX_CONNECTIONS,
        health_check_interval=20,  # Seconds
        socket_connect_timeout=3,  # Seconds
        socket_timeout=5,  # Seconds
        retry_on_timeout=True,
        decode_responses=True,
    )


constants = MeowcallConstants()

redis_client = build_redis_client(constants.REDIS_URI)
CALL_LOG_CHANNEL_ID = 1508007964559147086
REPORTS_CHANNEL_ID = 1508007964559147085
HEADQUARTERS_SERVER_ID = 1508007962931888128

# ── Role names ────────────────────────────────────────────────────────────────
MOD_ROLE_NAMES = ["Admin", "Moderator", "Trial Moderator"]  # Case-sensitive

# ── Invite / links ────────────────────────────────────────────────────────────
BOT_INVITE_LINK = "https://discord.com/api/oauth2/authorize?client_id=1355389597818945639&permissions=277025769536&scope=bot%20applications.commands"

# ── Misc settings ─────────────────────────────────────────────────────────────
WARNING_DELETE_TIME = 10  # seconds
TRUSTED_DOMAINS = [
    "youtube.com",
    "youtu.be",
    "tenor.com",
    "giphy.com",
    "open.spotify.com",
]

# ── Moderation thresholds ─────────────────────────────────────────────────────
WARN_THRESHOLD_MUTE = 3
WARN_THRESHOLD_BAN = 5

# ── Preset reasons ────────────────────────────────────────────────────────────
PRESET_REASONS = [
    "Hate speech / slurs",
    "NSFW content in calls",
    "Harassment or bullying",
    "Spam or flooding",
    "Sharing personal information",
    "Evading a previous ban",
    "Inappropriate username/avatar",
    "No reason provided",
]

QUICK_BAN_DURATIONS = {
    "1 hour": "1h",
    "6 hours": "6h",
    "1 day": "1d",
    "3 days": "3d",
    "1 week": "7d",
    "Permanent": None,
}

# ── Tips ──────────────────────────────────────────────────────────────────────
TIPS = [
    "💡 Tip: Vote for us on [top.gg](<https://top.gg/bot/1355389597818945639>) to support the bot! 😽",
    "💡 Tip: Use `/friendrequest` or `m.fr` to exchange Discord usernames with the other server!",
    "💡 Tip: Found inappropriate behavior? Use `/report` to notify our moderators!",
    "💡 Tip: Use `/skip` if you want to connect to a different server!",
    "💡 Tip: Love MeowCall? Support us with a coffee! ☕ [Donate here](<https://buymeacoffee.com/meowcall>) ❤️",
    "💡 Tip: Need help? Use `/help` to see all available commands!(M.help)",
    "💡 Tip: You can use prefix commands with 'm.' (like m.c or m.hang)",
    "💡 Tip: Keep conversations appropriate - inappropriate behavior may result in warnings or bans!",
    "💡 Tip: Only tenor and giphy gifs allowed !",
    "💡 Tip: Join MeowCall's official server [invite](<https://discord.gg/BxNnGC8TAs>)! O(∩_∩)O!",
    "💡 Tip: Use `M.meme` for fun random memes",
    "💡 Tip: Use `M.waifu` for waifus (M.w)",
    "💡 Tip: Use `M.smashorpass` for fun (M.sop)",
    "💡 Tip: Use `M.random` for shipping 💖 (M.rnd)",
]

# ── Coin flip GIFs ────────────────────────────────────────────────────────────
COIN_FLIP_GIFS = [
    "https://media.tenor.com/gcBDVr-ZNgUAAAAC/lucky-anime.gif",
]

# ── Ship GIFs ─────────────────────────────────────────────────────────────────
SHIP_GIFS = {
    "low": [
        "https://media.tenor.com/TQeKG-fM2PIAAAAC/mob-psycho100-crying.gif",
        "https://media.tenor.com/6EQ2aeffrU0AAAAC/anime-sad.gif",
        "https://media.tenor.com/LompdqfJLYYAAAAC/sad-anime.gif",
        "https://media.tenor.com/9RuzyPx3j3sAAAAC/anime-sorrow.gif",
        "https://media.tenor.com/WmFFdzCVdiMAAAAC/depressed-anime.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255201878474822/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255204030283837/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255209361375263/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255212142198876/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255214612381823/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255228172566568/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255232438304798/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255239023362138/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255243503009902/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255257121783858/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255261546905740/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255279582281748/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255286712467546/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255291976581220/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255295038160937/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255301916950588/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255314126438400/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255317897248778/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255326398971944/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255330215788714/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255333911101501/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255344954572841/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255350591717386/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255357063790723/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255363741122660/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255377737384067/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255386889486408/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255403574427739/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255416689885355/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255422050336809/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255442233196584/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255448461607022/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255472474128444/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255476962033675/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255486961385572/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255498277355570/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255505856462909/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255514102595694/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499171133816843/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499230135353384/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499242089381928/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499267179577394/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499333281546240/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499347046596618/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499375421587476/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499419737948160/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499431994097674/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499447861018654/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499460058841128/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499472363880518/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499498419814430/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499510604136498/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499535790145546/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499550445699072/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499563993300992/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499591880572958/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499603398262815/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499614153506896/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499627687477248/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499639411605554/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/838516530265980968/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/881893079093768222/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/881893227391778876/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/881893404198436906/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/1295028454127042600/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/1295028547970142332/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255251346227210/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255266105851954/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255274045669487/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255339728732170/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255369969532970/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255433274032192/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255452538470410/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255463347322990/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255492841537546/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255509644050543/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/741227824823664650/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/816323891181256744/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499184086351962/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499206445400074/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499218130993192/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499254650798101/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499279594586132/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499292097151020/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499305213395014/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499364067999754/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499389393076264/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499404836634684/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499485261758484/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499522175697036/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499576785535067/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/839471288501665852/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/881893675502821396/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/1295028060512587817/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/1295028352675090463/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/1295029281231208499/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/1295029874100273152/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/1295030071123509278/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/736255436612960286/cry.gif",
        "https://cdn.discordapp.com/attachments/736255198808375307/834499195162984478/cry.gif",
    ],
    "medium": [
        "https://media.tenor.com/cPaYXVEbEcQAAAAC/delphita-delph.gif",
        "https://media.tenor.com/D05kuhjm9rUAAAAC/jjk-anime.gif",
        "https://media.tenor.com/2DB6eQl33-8AAAAC/anime-couple.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277583767011368/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277606994804866/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277610958684220/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277652653998110/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277657896878121/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277668835885076/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277688381341797/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277721272942702/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277760049152040/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277769209774190/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277779372572783/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277834343120996/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277965591281684/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508606530781245/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508715729485874/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/840657468051816510/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/1011397991594209380/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277568629506146/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277578633183293/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277588615626813/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277592553816174/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277597377265674/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277600053493770/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277617833017364/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277628217983087/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277637873270935/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277645699973190/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277665115275465/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277680328015882/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277685034287213/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277693779279913/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277706383032339/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277717816836197/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277727979634718/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277749949268048/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277752080236604/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277774616100954/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277783218749510/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277791644975104/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277800251818154/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277813442642060/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277819969110097/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277845776793771/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277851216806057/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277857684160583/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277861974933584/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277881524715560/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277952894861352/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508552797814815/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508565360279592/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508579141976114/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508592752623616/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508619792908378/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508630862725190/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508688806772746/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508727704617000/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508740031938617/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508753704321044/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508768305872907/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508782738079814/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508794733920266/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508808033665034/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508820084293652/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508831765430342/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/871035982810603540/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/881895870746996766/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/881895989374488617/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/881896230525992991/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/893594251961700372/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/938231448211697684/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/1012359377849679892/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/1046370316210937928/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277671260061846/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277724397830184/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277796568957000/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277871139618917/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736278192850993192/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508646049644574/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508661291352114/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508675119841320/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277731561570848/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277804412436567/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277876034371594/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736278197426978907/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/834508700487516210/hug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/736278344986918954/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/736278350959607949/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/736278355015630868/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/736278366818271302/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/736278374993100840/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/736278379849973780/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/736278403434676224/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/736278410568925315/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/736278429510533176/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/736278434866790532/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/741227684587241503/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/834717466424901652/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/877645631051665519/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/881896699277238282/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/1150478633740271687/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/1334543487915524247/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736278340733894710/1366354345246855258/yaoihug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277786779451483/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277840466542632/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/736277746157617152/hug.gif",
        "https://cdn.discordapp.com/attachments/736277561373491265/904068109302915072/hug.gif",
    ],
    "high": [
        "https://media.tenor.com/wbIgzBYY-cEAAAAC/anime-love.gif",
        "https://media.tenor.com/8XOQxYJM2boAAAAC/highschool-dxd.gif",
        "https://media.tenor.com/IgM8Kbd3omAAAAAC/in-love-anime.gif",
        "https://media.tenor.com/mAURxRyZXdAAAAAC/nene-nene-yashiro.gif",
        "https://media.tenor.com/NaJIRcVnWloAAAAC/sao-sword-art-online.gif",
        "https://media.tenor.com/FfSuovWnabYAAAAC/haze-lena.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511426348777503/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511453821468692/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511717265309746/kiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/736281096764784780/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/736281104201285732/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/736281115098087506/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/736281124774346822/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/736281133649756273/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/736281140683604080/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/736281151748047088/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/736281161139093544/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/736281165736181860/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/736281173185265794/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/736281183738003456/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/736281204617248848/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/834849779824853023/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/834849792659947520/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/834849805246660608/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/834849818278887435/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/834849832022704158/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/863573727069077545/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/892166330340499506/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736281091534618674/925455445311782973/yurikiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280301571145769/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280306797248512/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280315030667384/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280319036227704/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280328020295740/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280332910854175/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280338548129841/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280345195970570/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280349406920844/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280358382731394/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280365886341159/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280370638749776/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280375222861976/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280377659883550/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280389391220776/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280393720004618/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280400212525066/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280406634266659/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280415978913822/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280426380918955/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280431967862964/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280438217244752/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280447813681232/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280454843465798/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280461310951504/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280466927255602/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280470999924874/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280473978011699/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280490931257497/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280495012315295/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280499919519824/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280505825361930/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280520312225873/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280529049223279/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280534602481714/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280547206234202/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280554512711680/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280563887112262/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/768080405668167680/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511341606928444/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511355506982972/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511368614051940/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511382585802832/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511396309434368/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511439065645056/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511467377328168/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511481617383454/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511507374735390/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511521337573396/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511535048097812/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511549024567346/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511562890543175/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511579105853560/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511594099703898/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511608750669825/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511636072759316/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511651582771231/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511663347531776/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511678011473951/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511693001523228/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511729211080814/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511742083268659/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511753823387678/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511768863768596/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511781333696592/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511797158936576/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511811309994044/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511828507295824/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511841174093844/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511854775959632/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511869464150046/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511884580946000/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511898649165824/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511910580912188/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/860585235124977664/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/881896934787403846/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/881897386094501928/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/881897560376213504/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/881897897812193360/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/925455200121131059/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/1063135577421119488/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/1065650002162094080/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511409584537610/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511494083117076/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511620428005377/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/834511704565481522/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/839773786684915722/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/868914744185208852/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280751187689482/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280753842683994/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280757068234823/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280762189348965/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280765754769488/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280775162593280/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280778094411776/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280780505874502/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280783437955083/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280786956976168/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280798512152617/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280803624878210/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280806497976360/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280812973981786/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280816711106710/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280822331473930/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280826047889448/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280832011927622/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280839658143805/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280845991542824/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280852501233674/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280860105506816/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280871895695480/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280880162537472/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280893903077466/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280897053130844/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280901410881653/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280907043831869/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280913641734216/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280917433253928/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280925477928960/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736280930292989952/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736284287359254599/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/736284502275522670/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/774620635997011978/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/783699292757164102/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/783755433126264912/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/834848898065104946/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/834852296596783154/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/845981040148348998/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/912100600999723018/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/991345678464856094/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/1091393370502467664/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/1200732629784338442/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280745601007737/1365344023430303754/yaoikiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280379862024443/kiss.gif",
        "https://cdn.discordapp.com/attachments/736280297171058759/736280477849092166/kiss.gif",
    ],
}

# ── Popular anime IDs (Jikan API) ─────────────────────────────────────────────
POPULAR_ANIME_IDS = [
    21,  # One Piece
    20,  # Naruto
    1735,  # Naruto: Shippuden
    16498,  # Attack on Titan
    1535,  # Death Note
    11061,  # Hunter x Hunter (2011)
    31964,  # My Hero Academia
    40748,  # Jujutsu Kaisen
    38000,  # Demon Slayer
    5114,  # Fullmetal Alchemist: Brotherhood
    269,  # Bleach
    6702,  # Fairy Tail
    223,  # Dragon Ball
    20507,  # Noragami
    31240,  # Haikyuu!!
    11617,
    24703,
    34281,
    32215,  # high school sxs
    19815,  # no game no life
    18679,  # Kill la Kill
    22297,  # Fate/stay night: Unlimited Blade Works
    49785,  # Kubo Won't Let Me Be Invisible
    42897,  # Horimiya
    30831,  # Konosuba: God's Blessing on This Wonderful World!
    33206,  # Miss Kobayashi's Dragon Maid
    39783,  # The Quintessential Quintuplets
    18897,  # Nisekoi
    5081,  # Bakemonogatari
    30240,  # Prison School
    40750,  # Redo of Healer
    50265,  # Spy x Family
    44511,  # Chainsaw Man
    42069,  # Tokyo Revengers
    49596,  # Blue Lock
    37521,  # Vinland Saga
    40852,  # Dr. Stone
    34572,  # Black Clover
    31240,  # Re:Zero - Starting Life in Another World
    1575,  # Code Geass: Lelouch of the Rebellion
    9253,  # Steins;Gate
    14719,  # JoJo's Bizarre Adventure
    918,  # Gintama
    48406,  # remain
    30015,  # relife
    28677,  # Yamada-kun to 7-nin no Majo
    38680,
    40417,
    42938,  # fruits basket
    37105,
    59986,  # grand blue
    26349,
    29067,  # the way of the house husband
    6547,  # angel beats
    27775,  # plastic memories
]

# ── Magic 8-Ball responses ────────────────────────────────────────────────────
EIGHT_BALL_RESPONSES = [
    "It is certain.",
    "It is decidedly so.",
    "Without a doubt.",
    "Yes – definitely.",
    "You may rely on it.",
    "As I see it, yes.",
    "Most likely.",
    "Outlook good.",
    "Yes.",
    "Signs point to yes.",
    "Reply hazy, try again.",
    "Ask again later.",
    "Better not tell you now.",
    "Cannot predict now.",
    "Concentrate and ask again.",
    "Don't count on it.",
    "My reply is no.",
    "My sources say no.",
    "Outlook not so good.",
    "Very doubtful.",
]

# ── Truth or Dare ─────────────────────────────────────────────────────────────
truths = [
    "What is one thing you wish you could change about yourself?",
    "Who is your crush?",
    "What is the most food you've ever eaten in a single sitting?",
    "What is the craziest pickup line you've ever used?",
    "What animal do you think you most look like?",
    "How many selfies do you take a day?",
    "What is one thing you would stand in line for an hour for?",
    "When was the last time you cried?",
    "What's the longest time you've ever gone without showering?",
    "What was your favorite childhood show?",
    "What's your biggest fear?",
    "What person do you text the most?",
    "If you could only eat one thing for the rest of your life, what would you choose?",
    "What's your favorite part of your body?",
    "Who is your celebrity crush?",
    "What's the strangest dream you've ever had?",
    "What are the top three things you look for in a boyfriend/girlfriend?",
    "What is your worst habit?",
    "What is your biggest insecurity?",
    "What is the most embarrassing nickname you have ever had?",
    "What would be your last meal if you got the death penalty?",
    "Do you have more guy friends or girl friends?",
    "Have you ever cheated in an exam?",
    "Who would you like to kiss in this chat?",
    "How many people have you kissed?",
    "What's one thing you only do when you're alone?",
    "If you had to cut one friend out of your life, who would it be?",
    "Do you have a favourite friend and who?",
    "If you could swap lives with someone in this chat, who would it be?",
    "What are your top three turn-ons?",
    "What is your biggest regret?",
    "What do most people think is true about you, but isn’t?",
    "What is the biggest thing you’ve gotten away with?",
    "What would you do if you were the opposite gender for a month?",
    "What is the most childish thing you still do?",
    "What are your real feelings about me (about the truther)?",
    "What is your biggest secret?",
    "What is something that people think you would never be into, but you are?",
    "What was the worst encounter you had with a police officer, if you did?",
    "Why did you break up with your last boyfriend or girlfriend?",
]

dares = [
    "Eat a packet of hot sauce straight.",
    "Do 20 squats.",
    "Gulp down a raw egg.",
    "Put five ice cubes in your mouth (you can't chew them, you just have to let them melt—brrr).",
    "Shot gun a diet coke.",
    "Empty a glass of cold water onto your head outside.",
    "Lick a bar of soap.",
    "Eat a teaspoon of mustard.",
    "Drink apple cider vinegar.",
    "Take a shot, if of age, else shot of darers choice.",
    "Jump into snow.",
    "Show the most embarrassing photo on your phone.",
    "Eat a raw piece of garlic.",
    "Show us your screen time report.",
    "Show us your pc search history.",
    "Show us your phone search history.",
    "Put 10 different available liquids into a cup and drink it.",
    "Tell everyone an embarrassing story about yourself.",
    "Lick your own foot.",
    "Post the oldest selfie on your phone on a social media story.",
    "Try and make yourself cry in front of us in video call.",
    "Tell the group two truths and a lie, and they have to guess which one the lie is.",
    "Cut off some piece of hair.",
    "Let darer post something on your social media.",
    "Lick the floor.",
    "For a guy, put on makeup. For a girl, wash off your make up (unless you don't wear make up, put some on).",
    "Write or draw something of groups choice somewhere on your body (that can be hidden with clothing) with a sharpie.",
    "Do pushups until you can’t do any more, wait 5 seconds, and then do one more.",
    "Let the group look through your phone for 2 minute (screen share).",
    "Eat one teaspoon of the spiciest thing you have in the kitchen.",
    "Drop something in the toilet and then reach in to get it.",
    "Describe what your crush looks like and their personality?",
    "Eat a raw potato.",
    "Choose a person in the group and say what annoys you about them.",
    "Lick the bottom of your shoe.",
    "Drink 3 big cups of water without stopping.",
    "Post the last youtube video you watched.",
    "Write darers name on some body part and send the picture.",
    "List all your ex's alphabetically",
    "Break two eggs on your forehead.",
]

# ── Banned words ──────────────────────────────────────────────────────────────
banned_words = [
    # Racism / hate speech
    "nigga",
    "nigger",
    "niggers",
    "niggas",
    "niga",
    "niqqa",
    "chink",
    "kike",
    "spic",
    "faggot",
    "fag",
    "retard",
    # Sexual / explicit
    "cum",
    "cums",
    "cumming",
    "porn",
    "porns",
    "porno",
    "bdsm",
    "nude",
    "nudes",
    "pussy",
    "dick",
    "cock",
    "rape",
    "rapistpenis",
    "vagina",
    "anal",
    "anus",
    "blowjob",
    "handjob",
    "masturbate",
    "orgasm",
    "horny",
    "whore",
    # Drugs
    "meth",
    "cocaine",
    "weed",
    "marijuana",
    "heroin",
    "lsd",
    # Violence / extremism
    "hitler",
    "nazi",
    "isis",
    "rape",
    # Common bypass variations
    "p0rn",
    "pr0n",
    "c0ck",
    "d1ck",
    "pu$$y",
    "n1gger",
    "4nal",
]
# Compile the regex pattern
banned_words_regex = re.compile(
    r"(?<!\w)("
    + "|".join(
        [re.escape(word) + r"(\b|s)?" for word in banned_words]
        + [r"n[i1!][g6][g6][a@]"]
    )
    + r")(?!\w)",
    re.IGNORECASE,
)


# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
LINKED_CHANNELS_DB_PATH = BASE_DIR / "db" / "linked_channels.db"
