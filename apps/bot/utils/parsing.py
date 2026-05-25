from __future__ import annotations

from .patterns import Patterns


def parse_version_from_toml() -> str:
    with open("pyproject.toml", encoding="utf-8") as file:
        content = file.read()
    match = Patterns.PYPROJECT_VERSION.search(content)
    if match:
        return match.group(1)
    return "0.0.0"
