"""Local package/docs consistency checks; no publication or external requests."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

from browser_goat import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_package_versions_agree() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    npm = json.loads((ROOT / "npm/package.json").read_text(encoding="utf-8"))
    assert project["project"]["version"] == npm["version"] == __version__


@pytest.mark.parametrize("path", [
    "README.md", "docs/index.md", "docs/cli.md", "docs/mcp.md", "docs/docker.md",
    "docs/install.md", "docs/quickstart.md", "docs/configuration.md", "docs/library.md",
    "npm/README.md",
])
def test_public_doc_relative_links_resolve(path: str) -> None:
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    for link in re.findall(r"\]\(([^)]+)\)", text):
        if link.startswith(("https://", "http://", "#")):
            continue
        assert (file.parent / link.split("#", 1)[0]).exists(), (path, link)
    assert len(re.findall(r"^```", text, flags=re.MULTILINE)) % 2 == 0


def test_docker_metadata_and_browser_install_steps() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY README.md LICENSE ./" in text
    assert "playwright install --with-deps chromium" in text
    assert "patchright install chromium" in text
    assert '"--host", "0.0.0.0"' in text  # intentional container-only binding
    assert (ROOT / "README.md").is_file() and (ROOT / "LICENSE").is_file()
