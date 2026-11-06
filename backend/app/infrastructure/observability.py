"""Correlate request/run logs and report failure locations without private values."""

import logging
import re
import traceback
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from uuid import uuid4

request_id_context = ContextVar("request_id", default="-")
run_id_context = ContextVar("run_id", default="-")
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}", re.ASCII)


def request_id(supplied: list[str]) -> str:
    return supplied[0] if len(supplied) == 1 and REQUEST_ID.fullmatch(supplied[0]) else uuid4().hex


def failure_frames(error: Exception) -> str:
    return " <- ".join(
        f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
        for frame in traceback.extract_tb(error.__traceback__)
    )


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        record.run_id = run_id_context.get()
        return True


def correlate_run(function):
    @wraps(function)
    async def correlated(self, *args, **kwargs):
        token = run_id_context.set(self.run_id)
        try:
            return await function(self, *args, **kwargs)
        finally:
            run_id_context.reset(token)

    return correlated


class ExecutionLogs:
    """Bounded, rotating technical logs indexed at read time by the existing Run ID."""

    def __init__(self, directory: Path):
        self.directory = directory

    def install(self):
        import json
        from datetime import datetime, timezone
        from logging.handlers import RotatingFileHandler

        directory = self.directory

        class Handler(RotatingFileHandler):
            def emit(self, record):
                run_id = run_id_context.get()
                if not re.fullmatch(r"\d{12}", run_id) or not record.name.startswith(
                    "app.execution."
                ):
                    return
                # Never copy formatted messages, exception strings or arbitrary extras.
                event = str(record.msg).split(" ")[0]
                if not re.fullmatch(r"[a-zA-Z0-9_.]+", event):
                    event = "execution.event"
                item = {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "run_id": run_id,
                    "action_key": getattr(record, "action_key", None),
                    "event": event,
                    "error_code": getattr(record, "error_code", None),
                    "error_type": getattr(record, "error_type", None),
                    "source": f"{Path(record.pathname).name}:{record.lineno}:{record.funcName}",
                    "frames": getattr(record, "failure_frames", None),
                }
                try:
                    clean = logging.makeLogRecord(
                        {"msg": json.dumps(item, ensure_ascii=False), "args": ()}
                    )
                    super().emit(clean)
                except Exception:
                    # Technical diagnostics must never interrupt a business operation.
                    pass

        try:
            directory.mkdir(parents=True, exist_ok=True)
            handler = Handler(
                directory / "execution.jsonl",
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
        except OSError:
            logging.getLogger(__name__).warning("execution.logging_unavailable")
            return lambda: None
        logger = logging.getLogger("app")
        logger.addHandler(handler)
        return lambda: (logger.removeHandler(handler), handler.close())

    def read(self, run_id: str):
        import json
        from collections import deque

        items = deque(maxlen=200)
        available = False
        for suffix in (".3", ".2", ".1", ""):
            path = self.directory / ("execution.jsonl" + suffix)
            try:
                with path.open("rb") as stream:
                    available = True
                    # Rotation races and malformed lines do not affect evidence queries.
                    for line in stream.read(5 * 1024 * 1024 + 16384).splitlines():
                        try:
                            item = json.loads(line)
                            if item.get("run_id") == run_id:
                                items.append(item)
                        except (ValueError, AttributeError):
                            continue
            except OSError:
                continue
        return {
            "items": list(items),
            "limit": 200,
            "status": "available" if items else "not_retained" if available else "not_collected",
        }
