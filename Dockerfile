FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies only (frozen lock, no dev deps)
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code
COPY src/ src/

# Install the project itself
RUN uv sync --frozen --no-dev

# Expose the service port
EXPOSE 8000

# Placeholder: python http.server keeps container alive as sidecar.
# TODO: Replace with `uv run browsing-meta serve --host 0.0.0.0 --port 8000`
# once a proper serve command is added to the CLI.
# The browsing-meta CLI is available via `docker exec browsing-meta uv run browsing-meta search "..."`.
CMD ["uv", "run", "python", "-m", "http.server", "8000"]