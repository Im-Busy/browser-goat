"""Keep the default suite offline; real search engines require explicit opt-in."""

from __future__ import annotations

import socket
from typing import Any

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--live", action="store_true", help="Enable external integration tests")
    parser.addoption("--browser-local", action="store_true", help="Exercise real browser tiers on localhost")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--live"):
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="requires --live and a running SearXNG"))
    if not config.getoption("--browser-local"):
        for item in items:
            if "browser_local" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="requires --browser-local and browser binaries"))


@pytest.fixture(autouse=True)
def offline_by_default(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    # Never inherit a developer's configured LLM provider in tests.
    monkeypatch.delenv("BROWSER_GOAT_LLM", raising=False)
    if request.config.getoption("--live") and "integration" in request.node.keywords:
        return
    original = socket.getaddrinfo

    def local_only(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host not in (None, "localhost", "127.0.0.1", "::1", b"localhost", b"127.0.0.1"):
            raise OSError(f"External network disabled in tests: {host}")
        return original(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", local_only)
