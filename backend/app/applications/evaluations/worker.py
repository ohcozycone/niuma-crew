import asyncio
import logging

from app.applications.evaluations.progression import EvaluationProgression

logger = logging.getLogger(__name__)


class EvaluationWorker:
    def __init__(self, service: EvaluationProgression, interval: float = 0.5) -> None:
        self.service, self.interval = service, interval
        self.task: asyncio.Task | None = None

    async def _loop(self) -> None:
        while True:
            step = asyncio.create_task(asyncio.to_thread(self.service.sweep))
            try:
                await asyncio.shield(step)
            except asyncio.CancelledError:
                await asyncio.gather(step, return_exceptions=True)
                raise
            except Exception as error:
                logger.warning("evaluation.scan_failed type=%s", type(error).__name__)
            await asyncio.sleep(self.interval)

    async def start(self) -> None:
        self.task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
