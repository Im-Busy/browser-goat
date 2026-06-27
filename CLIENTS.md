# browser-goat -- MCP Client Configuration

Per-platform MCP configuration snippets for browser-goat. Copy the appropriate block into your tool's MCP config file.

**Prerequisites**: Python 3.13+ and a SearXNG instance running on your machine.

The `SEARXNG_URL` environment variable defaults to `http://localhost:8082` (the Docker Compose port). Set it if your SearXNG runs elsewhere.

## Claude Desktop

Config file: `claude_desktop_config.json`

### npx method (zero-install)
```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "npx",
      "args": ["browser-goat"],
      "env": { "SEARXNG_URL": "http://localhost:8082" }
    }
  }
}
```

### uvx method
```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "uvx",
      "args": ["browser-goat-mcp"],
      "env": { "SEARXNG_URL": "http://localhost:8082" }
    }
  }
}
```

### Local Docker method
```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "uvx",
      "args": ["browser-goat-mcp", "--searxng-url", "http://localhost:8082"],
      "env": {}
    }
  }
}
```

## Cursor / VS Code

Config file: `.cursor/mcp.json`

### npx method (zero-install)
```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "npx",
      "args": ["browser-goat"],
      "env": { "SEARXNG_URL": "http://localhost:8082" }
    }
  }
}
```

### uvx method
```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "uvx",
      "args": ["browser-goat-mcp"],
      "env": { "SEARXNG_URL": "http://localhost:8082" }
    }
  }
}
```

### Local Docker method
```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "uvx",
      "args": ["browser-goat-mcp", "--searxng-url", "http://localhost:8082"],
      "env": {}
    }
  }
}
```

## OpenCode

Config file: `opencode.jsonc` under `"mcpServers"`

### npx method (zero-install)
```json
{
  "browser-goat": {
    "command": "npx",
    "args": ["browser-goat"],
    "env": { "SEARXNG_URL": "http://localhost:8082" }
  }
}
```

### uvx method (recommended)
```json
{
  "browser-goat": {
    "command": "uvx",
    "args": ["browser-goat-mcp"],
    "env": { "SEARXNG_URL": "http://localhost:8082" }
  }
}
```

### Local Docker method
```json
{
  "browser-goat": {
    "command": "uvx",
    "args": ["browser-goat-mcp", "--searxng-url", "http://localhost:8082"],
    "env": {}
  }
}
```

## GitHub Copilot

Config: `.github/copilot-instructions.md` or VS Code `settings.json`

### npx method (zero-install)
```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "npx",
      "args": ["browser-goat"],
      "env": { "SEARXNG_URL": "http://localhost:8082" }
    }
  }
}
```

### uvx method
```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "uvx",
      "args": ["browser-goat-mcp"],
      "env": { "SEARXNG_URL": "http://localhost:8082" }
    }
  }
}
```

### Local Docker method
```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "uvx",
      "args": ["browser-goat-mcp", "--searxng-url", "http://localhost:8082"],
      "env": {}
    }
  }
}
```

## Windsurf

Config file: `.windsurf/mcp.json`

### npx method (zero-install)
```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "npx",
      "args": ["browser-goat"],
      "env": { "SEARXNG_URL": "http://localhost:8082" }
    }
  }
}
```

### uvx method
```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "uvx",
      "args": ["browser-goat-mcp"],
      "env": { "SEARXNG_URL": "http://localhost:8082" }
    }
  }
}
```

### Local Docker method
```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "uvx",
      "args": ["browser-goat-mcp", "--searxng-url", "http://localhost:8082"],
      "env": {}
    }
  }
}
```

## SearXNG Setup

### Docker Compose (recommended)
```bash
docker compose up   # SearXNG at localhost:8082, API at localhost:8000
```

### Standalone SearXNG
```bash
docker run -d -p 8082:8080 searxng/searxng
```

If using a different port, update `SEARXNG_URL` in your MCP config accordingly.

## MCP Tools

| Tool | Description |
|------|-------------|
| `search` | Full pipeline: intent detection -> SearXNG -> hybrid ranking -> extraction -> reliability -> answer |
| `extract` | Fetch and extract a single URL with anti-bot bypass (Cloudflare Turnstile) |

Parameters for `search`: `time_range` (day/week/month/year), `max_sources`, `strategy` (default/auto/explore/decompose).
