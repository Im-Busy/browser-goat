# Installation

## Prerequisites

* Python 3.13 or later
* SearXNG running (Docker is the quickest way):

```bash
docker compose up -d redis searxng
```

Check your Python version before proceeding:

```bash
python --version
```

## pip

```bash
pip install browser-goat
```

The package and all its dependencies land in your current environment.

## uv

```bash
uv add browser-goat
```

Adds the package to your project's dependencies. If you're just trying it out,
run it directly:

```bash
uvx browser-goat --help
```

## Docker (full stack)

```bash
docker compose up
```

Builds the API and starts the three-service stack. SearXNG listens on host port 8082 and the
browser-goat API on host port 8003. No Python install needed on the host.

## Verify

```bash
browser-goat --version
```

If everything is wired up, you'll see the version number.

## Troubleshooting

### "Connection refused to localhost:8082"

SearXNG isn't running. Start it with Docker:

```bash
docker compose up -d redis searxng
```

### "Python 3.13+ required"

You're on an older Python. Check with `python --version`, then install 3.13+
with [uv](https://docs.astral.sh/uv/) or [pyenv](https://github.com/pyenv/pyenv).

### "browser-goat: command not found"

After a pip install, your Python scripts directory may not be on PATH. Either
add it or use `uv run` instead:

```bash
uv run browser-goat --version
```

### Browser-backed tiers

Package dependencies include Scrapling's `fetchers` extra. Install browser
binaries separately in the same environment:

```bash
uv run playwright install chromium
uv run patchright install chromium
```

On Linux, install Playwright system dependencies with `playwright install
--with-deps chromium`. Direct HTTP extraction works without browser binaries.
For a custom SearXNG installation, enable `json` in `search.formats`; a plain
upstream container may not enable the JSON API by default.

On Windows, stop a running `browser-goat-mcp` process before `uv sync` if its
executable is locked (error 32), then restart it. Updating source files does
not reload an already running Python process.
