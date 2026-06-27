# MCP Integration

MCP (Model Context Protocol) lets AI coding tools use browser-goat as a search tool. Connect once, then use `search`, `extract`, and `verify` from any MCP-compatible client.

## Available Tools

| Tool | Description |
|------|-------------|
| `search` | Full pipeline: pre-search → SearXNG → ranking → extraction → reliability. Set `reliability_mode` to `"high"` for multi-rollout consensus voting or `"maximum"` for LLM-verified answers |
| `extract` | Fetch and extract content from a single URL with anti-bot bypass |
| `verify` | Verify answer quality by running multiple search rollouts and breaking ties via LLM evaluation |

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
