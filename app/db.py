"""RESTAMP Phase 4 — SQLAlchemy engine/session integration."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

is_sqlite = settings.DATABASE_URL.startswith("sqlite")
connect_args = {}

if is_sqlite:
    connect_args["check_same_thread"] = False
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
    )
else:
    if "aivencloud.com" in settings.DATABASE_URL or "ssl" in settings.DATABASE_URL.lower():
        connect_args["ssl"] = {"ssl_mode": "REQUIRED"}
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI dependency yielding a request-scoped session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db() -> bool:
    """Readiness probe target: True when a trivial query succeeds."""
    try:
        db: Session = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return True
    except Exception:
        return False
