"""Small real subprocesses for exercising the development supervisor."""

import json
import os
import signal
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dev


def record(role):
    with open(os.environ["DEV_TEST_RECORD"], "a") as output:
        output.write(
            json.dumps({"role": role, "pid": os.getpid(), "url": os.getenv("BACKEND_URL")}) + "\n"
        )


def serve(role, port, fd=None):
    record(role)
    if os.environ.get("DEV_TEST_FAILURE") == role:
        return 7
    child = subprocess.Popen([sys.executable, __file__, "child"])

    def stop(_signum, _frame):
        child.terminate()
        child.wait(timeout=2)
        raise SystemExit(0)

    signal.signal(
        signal.SIGTERM,
        signal.SIG_IGN if os.environ.get("DEV_TEST_FAILURE") == "stubborn" else stop,
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if role == "backend":
                status = 503 if os.environ.get("DEV_TEST_FAILURE") == "timeout" else 200
                body = json.dumps({"status": "ok", "service": "backend", "port": port}).encode()
                content_type = "application/json"
            elif self.path.startswith("/api/"):
                http = build_opener(ProxyHandler({}))
                with http.open(os.environ["BACKEND_URL"] + "/health", timeout=1) as response:
                    body = response.read()
                status, content_type = 200, "application/json"
            else:
                status, content_type, body = 200, "text/javascript", b"export {};"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = HTTPServer((dev.HOST, port), Handler, bind_and_activate=fd is None)
    if fd is not None:
        server.socket.close()
        server.socket = socket.socket(fileno=fd)
    server.serve_forever()


if __name__ == "__main__":
    role = sys.argv[1]
    if role == "child":
        record(role)
        signal.pause()
    elif role == "launcher":
        dev.FRONTEND_PORT = int(sys.argv[2])
        dev.STOP_TIMEOUT = 0.5

        class Launcher(dev.DevLauncher):
            def backend_command(self, fd, port):
                return [sys.executable, __file__, "backend", str(port), str(fd)]

            def frontend_command(self):
                return [sys.executable, __file__, "frontend", str(dev.FRONTEND_PORT)]

        sys.exit(Launcher(int(sys.argv[3]), 1.5).run())
    else:
        sys.exit(serve(role, int(sys.argv[2]), int(sys.argv[3]) if role == "backend" else None))
