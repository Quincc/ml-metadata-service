import time
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import get_settings


_settings = get_settings()
DATABASE_URL = _settings.database_url

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    future=True,
    connect_args=connect_args,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def wait_for_database(max_attempts: int | None = None, delay_seconds: int | None = None) -> None:
    settings = get_settings()
    attempts = max_attempts if max_attempts is not None else settings.db_wait_max_attempts
    delay = delay_seconds if delay_seconds is not None else settings.db_wait_delay_seconds
    last_error: OperationalError | None = None

    for _ in range(attempts):
        try:
            with engine.connect():
                return
        except OperationalError as exc:
            last_error = exc
            time.sleep(delay)

    if last_error is not None:
        raise last_error


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
