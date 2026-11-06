"""Exercise sockets, environment handoff and cleanup using owned processes only."""

import errno
import importlib.util
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dev", SCRIPTS / "dev.py")
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)
HELPER = Path(__file__).with_name("fake_services.py")
HTTP = build_opener(ProxyHandler({}))


def test_backend_command_loads_application_package_and_watches_its_source():
    command = dev.DevLauncher().backend_command(42, 8123)
    assert command[command.index("uvicorn") + 1] == "app.main:app"
    reload_dir = Path(command[command.index("--reload-dir") + 1])
    assert reload_dir == SCRIPTS.parent / "backend/app"
    assert (reload_dir / "main.py").is_file()


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def wait_for(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("condition did not become true before deadline")


def get(url):
    try:
        with HTTP.open(url, timeout=0.3) as response:
            return json.loads(response.read())
    except (OSError, URLError, ValueError):
        return None


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


@pytest.fixture
def launch(tmp_path):
    processes = []

    def start(backend_port, frontend_port, failure="", through_make=False):
        record = tmp_path / f"pids-{len(processes)}.jsonl"
        log = tmp_path / f"log-{len(processes)}.txt"
        command = [
            sys.executable,
            str(HELPER),
            "launcher",
            str(frontend_port),
            str(backend_port),
        ]
        env = {
            **os.environ,
            "DEV_TEST_RECORD": str(record),
            "DEV_TEST_FAILURE": failure,
            "BACKEND_URL": "http://127.0.0.1:1",
        }
        if through_make:
            tool_dir = tmp_path / "bin"
            tool_dir.mkdir(exist_ok=True)
            uv = tool_dir / "uv"
            uv.write_text("#!/bin/sh\nexec " + shlex.join(command) + "\n")
            uv.chmod(0o700)
            env["PATH"] = str(tool_dir) + os.pathsep + env["PATH"]
            command = ["make", "dev"]
        with log.open("w") as output:
            process = subprocess.Popen(
                command,
                cwd=dev.ROOT,
                env=env,
                start_new_session=True,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        processes.append((process, record))
        return process, record, log

    yield start
    for process, record in processes:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            for item in records(record):
                try:
                    os.kill(item["pid"], signal.SIGKILL)
                except ProcessLookupError:
                    pass


@pytest.fixture
def frontend_port():
    with dev.listen(0) as sock:
        return sock.getsockname()[1]


def assert_clean(process, record, frontend_port, backend_port, expected=0):
    assert process.wait(timeout=8) == expected
    wait_for(lambda: all(not alive(item["pid"]) for item in records(record)))
    for port in (frontend_port, backend_port):
        with dev.listen(port):
            pass


def test_backend_skips_consecutive_occupied_ports():
    with dev.listen(0) as occupied:
        preferred = occupied.getsockname()[1]
        if preferred == 65535:
            pytest.skip("no adjacent port above 65535")
        try:
            second = dev.listen(preferred + 1)
        except OSError:
            pytest.skip("ephemeral adjacent port already occupied")
        with second, dev.backend_socket(preferred) as selected:
            assert selected.getsockname()[1] >= preferred + 2
            assert occupied.getsockname()[1] == preferred


def test_backend_reserves_frontend_port(monkeypatch):
    with dev.listen(0) as sock:
        port = sock.getsockname()[1]
    monkeypatch.setattr(dev, "FRONTEND_PORT", port)
    with dev.backend_socket(port) as backend:
        assert backend.getsockname()[1] != port


def test_backend_exhaustion_and_unrelated_bind_errors(monkeypatch):
    monkeypatch.setattr(dev, "PORT_ATTEMPTS", 1)
    with dev.listen(0) as occupied, pytest.raises(dev.StartupError):
        dev.backend_socket(occupied.getsockname()[1])

    def denied(_port):
        raise OSError(errno.EACCES, "denied")

    monkeypatch.setattr(dev, "listen", denied)
    with pytest.raises(OSError, match="denied"):
        dev.backend_socket(8000)


@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("occupied", [False, True])
def test_proxy_handoff_and_signal_cleanup(launch, frontend_port, stop_signal, occupied):
    with dev.listen(0) as blocker:
        preferred = blocker.getsockname()[1]
        if not occupied:
            blocker.close()
        process, record, log = launch(preferred, frontend_port)
        result = wait_for(lambda: get(f"http://127.0.0.1:{frontend_port}/api/test"))
        actual = result["port"]
        assert (actual != preferred) == occupied
        frontend = next(item for item in records(record) if item["role"] == "frontend")
        assert frontend["url"] == f"http://127.0.0.1:{actual}"
        wait_for(lambda: len(records(record)) == 4)
        wait_for(lambda: "开发环境已就绪" in log.read_text())
        process.send_signal(stop_signal)
        assert_clean(process, record, frontend_port, actual)
        assert "开发环境已就绪" in log.read_text()
        if occupied:
            assert blocker.getsockname()[1] == preferred


def test_frontend_conflict_does_not_spawn_or_stop_other_services(launch):
    assert dev.FRONTEND_PORT == 3000
    with dev.listen(0) as blocker:
        port = blocker.getsockname()[1]
        process, record, log = launch(8000, port)
        assert process.wait(timeout=5) == 1
        assert not records(record)
        assert "已占用" in log.read_text()
        assert blocker.getsockname()[1] == port


@pytest.mark.parametrize("failure", ["backend", "frontend", "timeout"])
def test_startup_failure_cleans_all_started_processes(launch, frontend_port, failure):
    with dev.listen(0) as sock:
        port = sock.getsockname()[1]
    process, record, _log = launch(port, frontend_port, failure)
    assert_clean(process, record, frontend_port, port, expected=1)


@pytest.mark.parametrize("role", ["backend", "frontend"])
def test_unexpected_exit_cleans_peer_and_descendants(launch, frontend_port, role):
    with dev.listen(0) as sock:
        port = sock.getsockname()[1]
    process, record, log = launch(port, frontend_port)
    wait_for(lambda: "开发环境已就绪" in log.read_text())
    wait_for(lambda: len(records(record)) == 4)
    victim = next(item for item in records(record) if item["role"] == role)
    os.kill(victim["pid"], signal.SIGKILL)
    assert_clean(process, record, frontend_port, port, expected=1)


def test_interrupt_during_backend_startup(launch, frontend_port):
    with dev.listen(0) as sock:
        port = sock.getsockname()[1]
    process, record, _log = launch(port, frontend_port, "timeout")
    wait_for(lambda: len(records(record)) == 2)
    process.send_signal(signal.SIGINT)
    assert_clean(process, record, frontend_port, port)


def test_stubborn_service_is_killed_after_grace_period(launch, frontend_port):
    with dev.listen(0) as sock:
        port = sock.getsockname()[1]
    process, record, log = launch(port, frontend_port, "stubborn")
    wait_for(lambda: "开发环境已就绪" in log.read_text())
    wait_for(lambda: len(records(record)) == 4)
    process.terminate()
    assert_clean(process, record, frontend_port, port)


@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
def test_make_entry_propagates_exit_to_launcher(launch, frontend_port, stop_signal):
    with dev.listen(0) as sock:
        port = sock.getsockname()[1]
    process, record, log = launch(port, frontend_port, through_make=True)
    wait_for(lambda: "开发环境已就绪" in log.read_text())
    wait_for(lambda: len(records(record)) == 4)
    if stop_signal == signal.SIGINT:
        os.killpg(process.pid, stop_signal)  # A terminal sends Ctrl+C to the foreground group.
    else:
        process.send_signal(stop_signal)  # make must also forward termination of its own PID.
    code = process.wait(timeout=8)
    assert code != 0  # make reports interruption even when the launcher cleans up successfully.
    assert_clean(process, record, frontend_port, port, expected=code)


@pytest.mark.parametrize(
    "args",
    [
        ["--backend-port", "0"],
        ["--backend-port", "65536"],
        ["--startup-timeout", "nan"],
    ],
)
def test_invalid_arguments_are_rejected(args):
    assert (
        subprocess.run(
            [sys.executable, str(SCRIPTS / "dev.py"), *args], capture_output=True
        ).returncode
        == 2
    )
