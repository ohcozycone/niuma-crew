from contextlib import AsyncExitStack, asynccontextmanager

from app.bootstrap.services import build_services


@asynccontextmanager
async def application_lifespan(settings, app):
    async with AsyncExitStack() as cleanup:
        acceptance, retained_files = build_services(app, settings, cleanup)
        # 先登记停止再启动，以覆盖部分启动失败；生产任务须先于资源服务停止。
        async with AsyncExitStack() as resources, AsyncExitStack() as workers:
            if settings.runtime.enabled:
                workers.push_async_callback(app.state.run_worker.stop)
                await app.state.run_worker.start()
                workers.push_async_callback(acceptance.stop)
                await acceptance.start()
                workers.push_async_callback(app.state.evaluation_worker.stop)
                await app.state.evaluation_worker.start()
                workers.push_async_callback(app.state.knowledge_worker.stop)
                await app.state.knowledge_worker.start()
                resources.push_async_callback(app.state.sandboxes.stop)
                await app.state.sandboxes.start()
                resources.push_async_callback(app.state.file_cleanup.stop)
                await app.state.file_cleanup.start(retained_files)
            yield
