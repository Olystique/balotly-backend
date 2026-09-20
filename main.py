import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_200_OK

from api.core import mq
from api.core.redis_client import redis_client
from api.db.database import engine
from api.utils.logger import logger, silence_noisy_loggers
from api.utils.settings import settings
from api.utils.success_response import success_response
from api.v1.routes import api_version_one
from workers.runtime import EmbeddedWorkerRuntime, build_default_worker_runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_runtime: EmbeddedWorkerRuntime | None = None
    app.state.worker_runtime = None
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection OK")

        await redis_client.ping()
        logger.info("Redis connection OK")

        # The broker carries work that is retried from its own queue, so a
        # broker outage at startup must not take the HTTP API offline.
        try:
            await mq.connect()
            logger.info("RabbitMQ connection OK")
        except Exception as exc:
            logger.warning(
                "RabbitMQ unreachable at startup (%s); the embedded workers "
                "will retry independently",
                exc,
            )

        if settings.RUN_EMBEDDED_WORKERS:
            worker_runtime = build_default_worker_runtime()
            if worker_runtime is not None:
                await worker_runtime.start()
                app.state.worker_runtime = worker_runtime
                logger.info("Embedded worker supervisors started")
            else:
                logger.info("No embedded workers registered yet")
        else:
            logger.info(
                "Embedded workers disabled; expecting separately deployed workers"
            )

        yield
    finally:
        # Stop background services before shared clients. A worker failure is
        # isolated while serving, and shutdown cannot race a task still using
        # RabbitMQ or SQLAlchemy.
        try:
            if worker_runtime is not None:
                await worker_runtime.stop()
        finally:
            app.state.worker_runtime = None
            try:
                await mq.close()
            finally:
                try:
                    await redis_client.aclose()
                finally:
                    await engine.dispose()


# Setup FastAPI app
app = FastAPI(
    lifespan=lifespan,
)

# CORS
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

# Must run after basicConfig, which would otherwise re-enable httpx at INFO and
# write Paystack request lines into stdout.
silence_noisy_loggers()


# Sessions (for auth, email, etc.)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)


# Mount routes
app.include_router(api_version_one)

# Health & Root Check
@app.get("/", tags=["Health"])
def read_root():
    return success_response(
        status_code=HTTP_200_OK,
        message="Balotly API is running",
    )



@app.get("/health", tags=["Health"])
def health_check(request: Request):
    runtime: EmbeddedWorkerRuntime | None = getattr(
        request.app.state, "worker_runtime", None
    )
    return {
        "status": "healthy",
        # Worker degradation is diagnostic information, not API liveness. Each
        # failed service is restarted independently by its own supervisor.
        "worker_mode": "embedded" if runtime is not None else "external",
        "workers": runtime.status_snapshot() if runtime is not None else {},
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.APP_PORT,
        reload=settings.DEBUG,
    )
