FROM python:3.14-slim

# COMBINED PYTHONPATH: All paths are separated by a colon (:)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONPATH="/app:/app/packages/db/src:/app/packages/dbSupport/src:/app/apps/bot"

WORKDIR /app

# Optional: Only needed if you are NOT using psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 1. Copy the ENTIRE repository first. 
# This ensures uv can find BOTH db and dbSupport during the sync.
COPY . .

# 2. Sync everything (uv will install all workspaces and dependencies)
RUN uv sync --frozen --no-dev --no-editable

# 3. Start the bot directly using the exact path
CMD ["/app/.venv/bin/python", "apps/bot/main.py"]