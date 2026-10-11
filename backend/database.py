import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./dev.db"


def get_async_url():
    # DATABASE_URL lets tests and fresh-migration checks use a disposable database.
    return os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL


def get_sync_url():
    # Alembic runs synchronously, so drop the async driver.
    return get_async_url().replace("+aiosqlite", "")


SQLALCHEMY_ASYNC_DATABASE_URL = get_async_url()

engine = create_async_engine(SQLALCHEMY_ASYNC_DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

Base = declarative_base()
