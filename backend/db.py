"""
Database connection — SQLAlchemy engine, session factory, and FastAPI dependency.

Uses DATABASE_URL env var (MySQL / Postgres in production).
Falls back to a local SQLite file for development when DATABASE_URL is not
set — but *only* when ``ENVIRONMENT`` is unset or set to ``development`` /
``test``. In production the module refuses to import so an ops mistake can't
silently point the app at an empty local SQLite file.
"""
import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("db")

DATABASE_URL = os.getenv("DATABASE_URL")
ENVIRONMENT = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").lower()
_IS_PROD = ENVIRONMENT in {"production", "prod", "live"}

if not DATABASE_URL:
    if _IS_PROD:
        # Fail closed: a missing DATABASE_URL in production almost
        # always means an ops mistake (secret rotated, env not wired
        # through, wrong task definition). Never silently degrade to
        # a local SQLite file — real user data would go to /dev/null.
        raise RuntimeError(
            "DATABASE_URL is required in production. Set ENVIRONMENT=development "
            "if you intended to boot with the local SQLite fallback."
        )
    # Local dev fallback: SQLite file in the backend directory
    _db_path = os.path.join(os.path.dirname(__file__), "dogoods_dev.db")
    DATABASE_URL = f"sqlite:///{_db_path}"
    _connect_args = {"check_same_thread": False}
    logger.warning(
        "DATABASE_URL not set — falling back to local SQLite at %s "
        "(ENVIRONMENT=%s). Do not use this in production.",
        _db_path, ENVIRONMENT,
    )
else:
    # Supabase / Railway / Heroku supply "postgres://" — SQLAlchemy 1.4+ requires "postgresql://"
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    _connect_args = {}

# Tune the pool for real Postgres deployments; SQLite ignores these.
_pool_kwargs: dict = {}
if not DATABASE_URL.startswith("sqlite"):
    _pool_kwargs = {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),  # 30 min
    }

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    **_pool_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency that yields a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
