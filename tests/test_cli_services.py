"""Service lifecycle tests use fake processes and temporary PID files only."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from browser_goat import cli


def test_version_and_guide(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--version"])
    assert exc.value.code == 0
    assert "0.2.1" in capsys.readouterr().out
    with patch("sys.argv", ["browser-goat", "--guide"]):
        cli.main()
    assert "fallback" in capsys.readouterr().out


def test_native_serve_binds_only_loopback_by_default() -> None:
    assert cli.build_parser().parse_args(["serve"]).host == "127.0.0.1"
    assert cli.build_parser().parse_args(["serve", "--host", "0.0.0.0"]).host == "0.0.0.0"


async def test_service_status_custom_port() -> None:
    args = cli.build_parser().parse_args(["service", "status", "--port", "9876"])
    client = AsyncMock()
    client.get.return_value = MagicMock(status_code=200, json=lambda: {"status": "ok"})
    client.__aenter__.return_value = client
    with patch("httpx.AsyncClient", return_value=client), pytest.raises(SystemExit) as exc:
        await cli.cmd_service_status(args)
    assert exc.value.code == 0
    assert client.get.call_args_list[0].args == ("http://localhost:9876/health",)


async def test_service_start_then_stop_mocked(tmp_path: Path) -> None:
    pid_file = tmp_path / "server.pid"
    client = AsyncMock()
    client.get.return_value = MagicMock(status_code=200, json=lambda: {"status": "ok"})
    client.__aenter__.return_value = client
    proc = MagicMock(pid=12345)
    proc.poll.return_value = None
    with (
        patch.object(cli, "_PID_FILE", pid_file),
        patch("httpx.AsyncClient", return_value=client),
        patch("subprocess.Popen", return_value=proc) as popen,
        patch("subprocess.run") as run,
        patch("os.kill") as kill,
    ):
        await cli.cmd_service_start(cli.build_parser().parse_args(["service", "start", "--port", "9876"]))
        assert pid_file.read_text() == "12345"
        assert "9876" in popen.call_args.args[0]
        command = popen.call_args.args[0]
        assert command[command.index("--host") + 1] == "127.0.0.1"
        with pytest.raises(RuntimeError, match="PID file"):
            await cli.cmd_service_start(cli.build_parser().parse_args(["service", "start"]))
        await cli.cmd_service_stop(cli.build_parser().parse_args(["service", "stop"]))
        assert run.called or kill.called
        assert not pid_file.exists()


async def test_failed_start_does_not_leave_stale_pid(tmp_path: Path) -> None:
    pid_file = tmp_path / "server.pid"
    proc = MagicMock(pid=12345, returncode=2)
    proc.poll.return_value = 2
    with (
        patch.object(cli, "_PID_FILE", pid_file), patch("subprocess.Popen", return_value=proc),
        pytest.raises(RuntimeError, match="exited during startup"),
    ):
        await cli.cmd_service_start(cli.build_parser().parse_args(["service", "start"]))
    assert not pid_file.exists()
