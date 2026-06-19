# Docker Deployment

Run browser-goat with SearXNG and Redis as a single stack.

## Quick Start

```bash
docker compose up
```

SearXNG starts at `localhost:8080`. The browser-goat API and MCP server start at `localhost:8000`.

## Services

| Service | Port | Description |
|---------|------|-------------|
| SearXNG | 8080 | Privacy-respecting metasearch engine |
| browser-goat | 8000 | Search pipeline API and MCP server |
| Redis | (internal) | Rate limiting and result caching, provided via Valkey 8 |

## Custom SearXNG Configuration

Edit `docker/searxng/settings.yml` to configure search engines, instance settings, and UI preferences. The file is mounted read-only into the container. Rebuild after changes:

```bash
docker compose up --build
```

## Production Considerations

- Change `SEARXNG_SECRET_KEY` in `.env` to a random value.
- Edit `server.limiter` in `docker/searxng/settings.yml` to adjust rate limiting.
- Put a reverse proxy (nginx, Caddy) in front for HTTPS.
- Set `SEARXNG_BASE_URL` to your public-facing domain.

## Health Checks

```bash
curl http://localhost:8080/health   # SearXNG
curl http://localhost:8000/health    # browser-goat
```

## Using the API

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "quantum computing", "max_sources": 3}'
```

## Volumes

| Volume | Purpose |
|--------|---------|
| `valkey-data` | Redis/Valkey persistent data |
| `searxng-cache` | SearXNG result cache |

## Troubleshooting

Services depend on each other with health checks. Valkey starts first. SearXNG waits for Valkey to be healthy. browser-goat waits for SearXNG to be healthy.

If SearXNG fails to start, check that your `settings.yml` is valid YAML. Invalid search engine configs are the most common cause of startup failures.
