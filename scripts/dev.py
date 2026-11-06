"""Start and supervise the local backend and Vite without changing configuration files."""

import argparse
import errno
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
FRONTEND_PORT = 3000
PORT_ATTEMPTS = 100
STOP_TIMEOUT = 5


class StartupError(Exception):
    """A process could not be started or did not become ready."""


def listen(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, port))
        sock.listen(128)
        return sock
    except BaseException:
        sock.close()
        raise


def backend_socket(preferred):
    for port in range(preferred, min(65536, preferred + PORT_ATTEMPTS)):
        if port == FRONTEND_PORT:
            continue
        try:
            return listen(port)
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
    raise StartupError(f"从 {preferred} 开始没有可用的后端端口。")


def group_exists(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


class DevLauncher:
    def __init__(self, backend_port=8000, startup_timeout=30):
        self.backend_port = backend_port
        self.startup_timeout = startup_timeout
        self.children = []
        self.stopping = False
        self.http = build_opener(ProxyHandler({}))

    def backend_command(self, fd, port):
        return [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--fd",
            str(fd),
            "--host",
            HOST,
            "--port",
            str(port),
            "--no-proxy-headers",
            "--reload",
            "--reload-dir",
            str(ROOT / "backend/app"),
        ]

    def frontend_command(self):
        return [
            "pnpm",
            "dev",
            "--host",
            HOST,
            "--port",
            str(FRONTEND_PORT),
            "--strictPort",
        ]

    def spawn(self, name, command, cwd, env, pass_fds=()):
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            pass_fds=pass_fds,
            start_new_session=True,
        )
        self.children.append((name, process))

    def request_stop(self, _signum, _frame):
        self.stopping = True

    def check_children(self):
        for name, process in self.children:
            code = process.poll()
            if code is not None:
                raise StartupError(f"{name}进程已退出（状态 {code}）。")

    def ready(self, url, backend=False):
        try:
            with self.http.open(url, timeout=0.3) as response:
                if backend:
                    data = json.loads(response.read(4096))
                    return data.get("status") == "ok" and data.get("service") == "backend"
                return response.status == 200 and "javascript" in response.headers.get(
                    "Content-Type", ""
                )
        except (OSError, URLError, ValueError):
            return False

    def wait_ready(self, url, name, backend=False):
        deadline = time.monotonic() + self.startup_timeout
        while not self.stopping:
            self.check_children()
            if self.ready(url, backend):
                self.check_children()
                return True
            if time.monotonic() >= deadline:
                raise StartupError(
                    f"{name}未在 {self.startup_timeout:g} 秒内就绪，请检查服务日志。"
                )
            time.sleep(0.1)
        return False

    def stop_children(self):
        # A leader may have exited while descendants still hold the socket or Runner lock.
        for _, process in reversed(self.children):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + STOP_TIMEOUT
        while time.monotonic() < deadline:
            for _, process in self.children:
                process.poll()
            if not any(group_exists(process.pid) for _, process in self.children):
                break
            time.sleep(0.05)
        for _, process in self.children:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()

    def run(self):
        previous = {
            signum: signal.signal(signum, self.request_stop)
            for signum in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            try:
                with listen(FRONTEND_PORT):
                    pass
            except OSError as error:
                if error.errno == errno.EADDRINUSE:
                    raise StartupError(
                        f"前端端口 {FRONTEND_PORT} 已占用，请先停止占用服务。"
                    ) from None
                raise
            if self.stopping:
                return 0
            with backend_socket(self.backend_port) as sock:
                port = sock.getsockname()[1]
                if port != self.backend_port:
                    print(
                        f"[dev] 后端首选端口 {self.backend_port} 不可用，改用 {port}。",
                        flush=True,
                    )
                self.spawn(
                    "后端",
                    self.backend_command(sock.fileno(), port),
                    ROOT / "backend",
                    os.environ.copy(),
                    (sock.fileno(),),
                )
            backend_url = f"http://{HOST}:{port}"
            if not self.wait_ready(backend_url + "/health", "后端", backend=True):
                return 0
            print(f"[dev] 后端已就绪：{backend_url}", flush=True)
            if self.stopping:
                return 0
            self.spawn(
                "前端",
                self.frontend_command(),
                ROOT / "frontend",
                {**os.environ, "BACKEND_URL": backend_url},
            )
            frontend_url = f"http://{HOST}:{FRONTEND_PORT}"
            if not self.wait_ready(frontend_url + "/@vite/client", "前端"):
                return 0
            print(
                f"[dev] 开发环境已就绪：{frontend_url} → {backend_url}；Ctrl+C 结束。",
                flush=True,
            )
            while not self.stopping:
                self.check_children()
                time.sleep(0.1)
            return 0
        except (StartupError, OSError) as error:
            print(f"[dev] {error}", file=sys.stderr, flush=True)
            return 0 if self.stopping else 1
        finally:
            self.stop_children()
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="启动完整开发环境，退出时清理本次服务进程。")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--startup-timeout", type=float, default=30)
    args = parser.parse_args(argv)
    if not 1 <= args.backend_port <= 65535:
        parser.error("后端端口必须为 1～65535。")
    if not 0 < args.startup_timeout < float("inf"):
        parser.error("启动等待时间必须为有限正数。")
    return DevLauncher(args.backend_port, args.startup_timeout).run()


if __name__ == "__main__":
    sys.exit(main())
