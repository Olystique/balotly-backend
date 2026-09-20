from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    PYTHON_ENV: str = "development"
    DEBUG: bool = False
    APP_PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Auth. Organizers, candidates and admins sign in with a JWT; voters never
    # do (BALOTLY_BACKEND_SPEC.md, BE-02).
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Vault: AES-256-GCM key (base64-encoded 32 bytes) for bank account
    # numbers at rest.
    ENCRYPTION_KEY: str

    # Database
    DB_URL: str
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Infra
    REDIS_URL: str = "redis://localhost:6379/0"
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    WEBHOOK_QUEUE_NAME: str = "balotly.webhooks"

    # For the current single-container deployment, FastAPI owns independently
    # supervised background workers. Set this false only when those services
    # are deployed as separate processes later.
    RUN_EMBEDDED_WORKERS: bool = True
    EMBEDDED_WORKER_RESTART_BASE_SECONDS: float = Field(
        default=1.0, ge=0.1, le=60.0
    )
    EMBEDDED_WORKER_RESTART_MAX_SECONDS: float = Field(
        default=30.0, ge=1.0, le=300.0
    )

    @property
    def is_production(self) -> bool:
        return self.PYTHON_ENV == "production"


settings = Settings()
