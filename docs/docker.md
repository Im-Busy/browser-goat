# Docker Deployment

Run browser-goat with SearXNG and Redis as a single stack.

## Quick Start

```bash
docker compose up
```

SearXNG starts at `localhost:8082` on the host (container port 8080, mapped via `docker-compose.yml`). The browser-goat HTTP JSON API starts at `localhost:8003`.
Compose does not expose an MCP endpoint. Run the stdio server separately as
described in [MCP integration](mcp.md).

## Services

| Service | Port | Description |
|---------|------|-------------|
| SearXNG | 8082 (host) → 8080 (container) | Privacy-respecting metasearch engine |
| browser-goat | 8003 (host) → 8000 (container) | HTTP JSON search API, not MCP |
| Redis | (internal) | Valkey 8, configured as SearXNG's Redis backend |

The browser-goat HTML cache is separate: it lives in memory in each
`BrowserGoat` instance, with a default TTL of 900 seconds and a 256-entry limit.
Valkey and its volume do not persist that cache or browser-goat answers.
The bundled SearXNG settings have `server.limiter: false`.

## Custom SearXNG Configuration

Edit `docker/searxng/settings.yml` to configure search engines, instance settings, and UI preferences. The file is mounted read-only into the container. Rebuild after changes:

```bash
docker compose up --build
```

## Production Considerations

- Change `SEARXNG_SECRET_KEY` in `.env` to a random value.
- Edit `server.limiter` in `docker/searxng/settings.yml` to adjust rate limiting.
- Put a reverse proxy (nginx, Caddy) in front for HTTPS.
- For a public-facing SearXNG deployment, edit its `SEARXNG_BASE_URL` value in
  `docker-compose.yml`. The supplied Compose file sets it directly; it does
  not read a host `SEARXNG_BASE_URL` override.

## Health Checks

```bash
curl http://localhost:8082/config     # SearXNG (returns JSON config)
curl http://localhost:8003/health      # browser-goat
```

## Using the API

```bash
curl -X POST http://localhost:8003/search \
  -H "Content-Type: application/json" \
  -d '{"query": "quantum computing", "max_sources": 3}'
```

## Volumes

| Volume | Purpose |
|--------|---------|
| `valkey-data` | Redis/Valkey persistent data |
| `searxng-cache` | SearXNG data mounted at `/var/cache/searxng` |

## Troubleshooting

Services depend on each other with health checks. Valkey starts first. SearXNG waits for Valkey to be healthy. browser-goat waits for SearXNG to be healthy.

If SearXNG fails to start, check that your `settings.yml` is valid YAML. Invalid search engine configs are the most common cause of startup failures.

`All connection attempts failed` or `Cannot connect to SearXNG` indicates a
backend connection failure, not a browser extraction failure. Check `docker
compose ps` and `http://localhost:8082/config`; an API `/health` response only
proves that the API listener is alive. A custom SearXNG must enable JSON in
`search.formats` or search requests can return HTTP 403.

The image copies package metadata and installs Chromium binaries plus Linux
browser libraries for Playwright and Scrapling/Patchright. Rebuild the image
after package or source changes. Browser launch success does not guarantee
that a target site's anti-bot challenge can be solved.

The API has no authentication. Keep the loopback port binding unless a trusted,
authenticated reverse proxy and access policy are in place.
