# Installation

## Prerequisites

* Python 3.13 or later
* SearXNG running (Docker is the quickest way):

```bash
docker run -d -p 8080:8080 searxng/searxng
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

Pulls and starts both services. SearXNG listens on port 8080 and the
browser-goat API on port 8000. No Python install needed on the host.

## Verify

```bash
browser-goat --version
```

If everything is wired up, you'll see the version number.

## Troubleshooting

### "Connection refused to localhost:8080"

SearXNG isn't running. Start it with Docker:

```bash
docker run -d -p 8080:8080 searxng/searxng
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
