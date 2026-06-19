# MCP Integration

MCP (Model Context Protocol) lets AI coding tools use browser-goat as a search tool. Connect once, then use `search` and `extract` from any MCP-compatible client.

## Available Tools

| Tool | Description |
|------|-------------|
| `search` | Full pipeline search with intent detection, ranking, extraction, and verification |
| `extract` | Fetch and extract content from a single URL with anti-bot bypass |

## Platform Configs

Add the `browser-goat` entry to your client's `mcpServers` block.

### Claude Desktop

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "npx",
      "args": ["browser-goat"],
      "env": { "SEARXNG_URL": "http://localhost:8080" }
    }
  }
}
```

### Cursor

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "npx",
      "args": ["browser-goat"],
      "env": { "SEARXNG_URL": "http://localhost:8080" }
    }
  }
}
```

### OpenCode

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "uvx",
      "args": ["browser-goat-mcp"],
      "env": { "SEARXNG_URL": "http://localhost:8080" }
    }
  }
}
```

### GitHub Copilot

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "npx",
      "args": ["browser-goat"],
      "env": { "SEARXNG_URL": "http://localhost:8080" }
    }
  }
}
```

### Windsurf

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "npx",
      "args": ["browser-goat"],
      "env": { "SEARXNG_URL": "http://localhost:8080" }
    }
  }
}
```

Ready-to-copy config files are available in the [distribution](../distribution/) directory.
