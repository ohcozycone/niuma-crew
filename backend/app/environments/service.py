import asyncio
import logging
import threading
from datetime import timedelta

from sqlalchemy import select

from app.environments.models import SandboxResource
from app.environments.open_sandbox import OpenSandboxProvider, load_verification
from app.errors import ConflictError, ServiceUnavailableError
from app.infrastructure.database.transactions import reserve_writer
from app.values import digest, utc_now

logger = logging.getLogger(__name__)


class RunSandbox:
    def __init__(self, service, run_id, inputs, read_file):
        self.service, self.run_id, self.inputs, self.read_file = service, run_id, inputs, read_file
        self.handle = None
        self.closed = False
        self.lock = threading.RLock()

    def acquire(self):
        with self.lock:
            if self.closed:
                raise ConflictError("runtime_interrupted", "沙箱工作已停止。")
            if self.handle is None:
                self.handle = self.service.acquire(self.run_id, self.inputs, self.read_file)
            return self.handle

    def release(self):
        with self.lock:
            self.closed = True
            try:
                self.service.release(self.run_id)
            finally:
                # 远端清理或其记账失败，仍须关闭本地 HTTP 连接。
                handle, self.handle = self.handle, None
                if handle is not None:
                    try:
                        handle.close()
                    except Exception:
                        logger.warning("sandbox.connection_close_failed")


class SandboxService:
    def __init__(self, database, config, active_run_ids, *, provider=None):
        self.database, self.config, self.active_run_ids = database, config, active_run_ids
        self.provider = provider or OpenSandboxProvider(config)
        self.identity = digest([config.endpoint, config.image, config.deployment_id])
        self.task = None

    def for_run(self, run_id, inputs, read_file, *, profile=None):
        current = self.capture_profile()
        if profile is not None and any(profile.get(key) != value for key, value in current.items()):
            raise ConflictError("sandbox_configuration_changed")
        return RunSandbox(self, run_id, inputs, read_file)

    def capture_profile(self):
        verified = load_verification(self.config)
        return {
            "server_identity": self.identity,
            "image": self.config.image,
            "cpu": self.config.cpu,
            "memory": self.config.memory,
            "ttl_seconds": self.config.ttl_seconds,
            "command_seconds": self.config.command_seconds,
            "programs": verified.get("programs", {}),
        }

    def status(self):
        try:
            self.capture_profile()
        except ServiceUnavailableError as error:
            return {
                "workspace_mode": "virtual",
                "execute_ready": False,
                "execute_error": error.code,
            }
        return {"workspace_mode": "sandbox", "execute_ready": True, "execute_error": None}

    def resources(self):
        with self.database.transaction() as db:
            return [
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "state": row.state,
                    "expires_at": row.expires_at.isoformat(),
                    "cleanup_attempts": row.cleanup_attempts,
                    "error": row.last_error,
                }
                for row in db.scalars(
                    select(SandboxResource)
                    .where(SandboxResource.state != "destroyed")
                    .order_by(SandboxResource.created_at)
                    .limit(100)
                )
            ]

    def confirm_absent(self, id):
        with self.database.transaction() as db:
            row = db.get(SandboxResource, id)
            if (
                row is None
                or row.state != "unknown"
                or row.remote_id is not None
                or row.expires_at > utc_now()
                or row.server_identity != self.identity
            ):
                raise ConflictError(
                    "sandbox_reconciliation_denied",
                    "只能人工核对已过期、无远端 ID 且归属当前服务的未知申请。",
                )
        if self.provider.find(self.metadata(row)):
            self.release(row.run_id)
            return
        with self.database.transaction() as db:
            reserve_writer(db, SandboxResource.__table__)
            current = db.get(SandboxResource, id)
            if current.state != "unknown" or current.cleanup_attempts != row.cleanup_attempts:
                raise ConflictError(
                    "sandbox_reconciliation_denied", "核对期间资源状态改变，请重新检查。"
                )
            current.state, current.last_error = "destroyed", "absence_confirmed_by_operator"

    def metadata(self, row):
        return {
            "niuma_deployment": row.deployment_id,
            "niuma_run": row.run_id,
            "niuma_request": row.id,
        }

    def acquire(self, run_id, inputs, read_file):
        load_verification(self.config)
        with self.database.transaction() as db:
            reserve_writer(db, SandboxResource.__table__)
            existing = db.scalar(select(SandboxResource).where(SandboxResource.run_id == run_id))
            if existing is not None:
                # 已有资源属于前次尝试；远端结果未知时不隐式重建或重连。
                raise ConflictError(
                    "tool_result_unknown", "已有沙箱申请，必须核对并回收后重新发起工作。"
                )
            active = list(
                db.scalars(select(SandboxResource).where(SandboxResource.state != "destroyed"))
            )
            if len(active) >= self.config.max_concurrency:
                raise ServiceUnavailableError(
                    "sandbox_capacity_exceeded", "沙箱资源已占用或仍待回收，请稍后重试。"
                )
            row = SandboxResource(
                run_id=run_id,
                deployment_id=self.config.deployment_id,
                server_identity=self.identity,
                state="requested",
                expires_at=utc_now() + timedelta(seconds=self.config.ttl_seconds),
            )
            db.add(row)
            db.flush()
        handle = None
        try:
            handle = self.provider.create(self.metadata(row))
            with self.database.transaction() as db:
                reserve_writer(db, SandboxResource.__table__)
                current = db.get(SandboxResource, row.id)
                current.remote_id, current.state = handle.id, "ready"
            self.provider.initialize(handle, inputs, read_file)
            return handle
        except BaseException:
            # 创建失败或结果未知也保留申请标识，供后续按归属核对。
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
            self.release(run_id)
            raise

    def release(self, run_id):
        with self.database.transaction() as db:
            reserve_writer(db, SandboxResource.__table__)
            row = db.scalar(select(SandboxResource).where(SandboxResource.run_id == run_id))
            if row is None or row.state == "destroyed":
                return
            row.state = "cleanup"
        self._destroy(row)

    def _destroy(self, row):
        if row.server_identity != self.identity or row.deployment_id != self.config.deployment_id:
            return
        try:
            # 即使已有 ID 也核对 metadata，不能仅凭外部 ID 确认归属。
            ids = self.provider.find(self.metadata(row))
            if not ids and row.remote_id is None:
                # 空查询后创建仍可能完成，确认资源前继续占用容量。
                with self.database.transaction() as db:
                    current = db.get(SandboxResource, row.id)
                    current.state, current.last_error = "unknown", "sandbox_create_unknown"
                    current.cleanup_attempts += 1
                return
            for id in ids:
                self.provider.kill(id)
            with self.database.transaction() as db:
                current = db.get(SandboxResource, row.id)
                current.state, current.last_error = "destroyed", None
                current.cleanup_attempts += 1
        except Exception:
            with self.database.transaction() as db:
                current = db.get(SandboxResource, row.id)
                current.state, current.last_error = "cleanup", "sandbox_cleanup_failed"
                current.cleanup_attempts += 1
            logger.warning("sandbox.cleanup_pending resource=%s", row.id)

    def sweep(self):
        active = set(self.active_run_ids())
        with self.database.transaction() as db:
            rows = list(
                db.scalars(select(SandboxResource).where(SandboxResource.state != "destroyed"))
            )
        for row in rows:
            if row.state == "cleanup" or row.run_id not in active or row.expires_at <= utc_now():
                self.release(row.run_id)

    async def start(self):
        async def maintain():
            while True:
                try:
                    await asyncio.to_thread(self.sweep)
                except Exception:
                    logger.warning("sandbox.maintenance_failed")
                await asyncio.sleep(self.config.maintenance_seconds)

        self.task = asyncio.create_task(maintain())

    async def stop(self):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        try:
            async with asyncio.timeout(20):
                await asyncio.to_thread(self.sweep)
        except TimeoutError:
            logger.warning("sandbox.shutdown_cleanup_pending")
