import sys
import os
import asyncio
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from api.db.database import Base
from api.db.url import build_async_url
from api.v1.models import *
from dotenv import load_dotenv

load_dotenv()

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

db_url = os.getenv("DB_URL") or os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DB_URL not found in environment.")

db_url, ssl_mode = build_async_url(db_url)
config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    kwargs = {"connect_args": {"ssl": ssl_mode}} if ssl_mode else {}
    connectable = create_async_engine(db_url, poolclass=pool.NullPool, **kwargs)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
