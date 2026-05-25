from __future__ import annotations

from datetime import UTC, datetime, timedelta


def ms_to_datetime(duration_ms: int) -> datetime:
    return datetime.now(UTC) + timedelta(milliseconds=duration_ms)


def ms_to_human(ms: int, max_parts=3) -> str:
    """Convert milliseconds to human-readable duration format."""
    try:
        if ms < 60_000:
            return "< 1 minute"

        UNITS = [
            ("y", 365 * 24 * 60 * 60),
            ("mo", 30 * 24 * 60 * 60),
            ("w", 7 * 24 * 60 * 60),
            ("d", 24 * 60 * 60),
            ("h", 60 * 60),
            ("m", 60),
            ("s", 1),
        ]

        total_seconds = ms // 1000
        parts = []

        for unit_name, unit_seconds in UNITS:
            if total_seconds >= unit_seconds:
                unit_count = total_seconds // unit_seconds
                parts.append(f"{int(unit_count)}{unit_name}")
                total_seconds %= unit_seconds

                if len(parts) >= max_parts:
                    break

        return " ".join(parts) if parts else "< 1 minute"
    except ValueError:
        raise
