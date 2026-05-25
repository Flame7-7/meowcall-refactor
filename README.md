# MeowCall

MeowCall is a Discord bot for cross-server calls, moderation, and fun commands.

## Development

1. `uv sync --dev`
2. `pre-commit install`
3. `uv run meowcall`

## Checks

Run these before pushing changes:

```bash
uv run ruff check .
uv run ruff format .
uv run pyright
```

The bot expects `DISCORD_TOKEN` and `TOPGG_TOKEN` in your environment or `.env` file.
