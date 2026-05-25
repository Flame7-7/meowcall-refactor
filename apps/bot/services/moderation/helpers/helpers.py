from __future__ import annotations

from services.moderation.types import ActionType


def parse_args_for_target_and_reason(
    args: str, action: ActionType
) -> tuple[str | None, int | None, str]:
    _ = action
    if not args:
        return None, None, ""

    reason = args.strip() or None
    return reason, None, args
