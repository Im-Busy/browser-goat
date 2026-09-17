"""Bounded HTTP/1.1 JSON search adapter (one request per connection)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from browser_goat.models import SearchRequest
from browser_goat.router import BrowserGoat

MAX_BODY_BYTES = 64 * 1024
logger = logging.getLogger(__name__)


async def create_server(meta: BrowserGoat, host: str, port: int) -> asyncio.Server:
    """Create an API listener; the caller owns the server and BrowserGoat lifecycle."""
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        status, payload = "500 Internal Server Error", {"error": "Internal server error"}
        try:
            status, payload = await _dispatch(meta, reader)
        except (ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
            status, payload = "400 Bad Request", {"error": str(exc)}
        except TimeoutError:
            status, payload = "408 Request Timeout", {"error": "Request timed out"}
        except httpx.HTTPError as exc:
            status, payload = "502 Bad Gateway", {"error": str(exc)}
        except Exception:
            logger.exception("HTTP API request failed")
        finally:
            try:
                body = json.dumps(payload).encode("utf-8")
                writer.write(f"HTTP/1.1 {status}\r\nContent-Type: application/json\r\n"
                             f"Connection: close\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
                await writer.drain()
            except (ConnectionError, OSError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()

    return await asyncio.start_server(handle, host=host, port=port)


async def _dispatch(meta: BrowserGoat, reader: asyncio.StreamReader) -> tuple[str, dict[str, Any]]:
    raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=30)
    lines = raw.decode("utf-8").split("\r\n")
    method, path, version = lines[0].split()
    if version not in ("HTTP/1.0", "HTTP/1.1"):
        raise ValueError("Unsupported HTTP version")
    if method == "GET" and path in ("/", "/health"):
        return "200 OK", {"status": "ok"}
    if method != "POST" or path != "/search":
        return "404 Not Found", {"error": "not found"}
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        name, value = line.split(":", 1)
        name = name.lower()
        if name in headers:
            raise ValueError("Duplicate HTTP header")
        headers[name] = value.strip()
    if "transfer-encoding" in headers:
        raise ValueError("Chunked request bodies are not supported; send Content-Length")
    length = int(headers.get("content-length", "0"))
    if length > MAX_BODY_BYTES:
        return "413 Payload Too Large", {"error": "Body limit is 65536 bytes"}
    if length <= 0:
        raise ValueError("A non-empty JSON body is required")
    data = json.loads(await asyncio.wait_for(reader.readexactly(length), timeout=30))
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    if "reliability" in data:
        data.setdefault("reliability_mode", data.pop("reliability"))
    data.setdefault("strategy", "default")
    request = SearchRequest.model_validate(data)
    result = await meta.search(**request.model_dump(exclude={"llm_config"}))
    return "200 OK", result.model_dump(mode="json")
