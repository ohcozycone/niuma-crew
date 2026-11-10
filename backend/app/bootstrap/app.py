import logging
from functools import partial

from fastapi import FastAPI

from app import __version__
from app.api.errors import register_error_handlers
from app.api.failure_boundary import FailureBoundaryMiddleware
from app.api.frontend_delivery import mount_frontend
from app.api.oauth_logging import install_oauth_access_filter
from app.api.router import router
from app.api.security import BrowserSecurityMiddleware
from app.bootstrap.lifecycle import application_lifespan
from app.config import AppConfig, load_config
from app.infrastructure.observability import CorrelationFilter


def create_app(config: AppConfig | None = None) -> FastAPI:
    settings = config if config is not None else load_config()
    install_oauth_access_filter()
    application_logger = logging.getLogger("app")
    if not application_logger.handlers:
        handler = logging.StreamHandler()
        handler.addFilter(CorrelationFilter())
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s run_id=%(run_id)s %(message)s"
            )
        )
        application_logger.addHandler(handler)
    application_logger.setLevel(logging.INFO)

    app = FastAPI(
        version=__version__,
        title="NiumaCrew Platform API",
        description="NiumaCrew 数字员工管理平台 API，提供员工配置、技能管理、技能装配和健康检查。",
        redoc_url=None,
        openapi_url=None if settings.auth.cookie_secure else "/openapi.json",
        docs_url=None if settings.auth.cookie_secure else "/docs",
        lifespan=partial(application_lifespan, settings),
    )
    app.include_router(router)
    app.add_middleware(BrowserSecurityMiddleware, config=settings.auth)
    app.add_middleware(FailureBoundaryMiddleware)
    register_error_handlers(app)
    mount_frontend(app, settings.frontend_dist)
    return app
