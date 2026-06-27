FROM python:3.13-slim

# Install system dependencies (wget for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*

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

CMD ["uv", "run", "browser-goat", "serve", "--host", "0.0.0.0", "--port", "8000"]