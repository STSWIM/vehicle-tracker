import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base


def _default_database_url() -> str:
    # AppAPI mountet unter APP_PERSISTENT_STORAGE ein Volume, das Redeploys
    # ueberlebt - ohne das waeren alle Daten bei jedem Container-Neustart weg.
    storage = os.environ.get("APP_PERSISTENT_STORAGE")
    if storage:
        return f"sqlite:///{storage}/vehicle_tracker.db"
    return "sqlite:///./data/vehicle_tracker.db"


DATABASE_URL = os.environ.get("DATABASE_URL") or _default_database_url()

# SQLite legt die DB-Datei nicht selbststaendig in einem noch fehlenden
# Ordner an ("unable to open database file") - Zielordner daher vorab
# sicherstellen.
if DATABASE_URL.startswith("sqlite:///"):
    db_path = Path(DATABASE_URL.removeprefix("sqlite:///"))
    db_path.parent.mkdir(parents=True, exist_ok=True)

# check_same_thread=False wird nur fuer SQLite gebraucht (FastAPI nutzt
# mehrere Threads); bei Postgres/MySQL einfach ignorieren.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def add_missing_columns(target_engine: Engine) -> None:
    """Fehlende (nullable) Spalten bestehender Tabellen nachziehen.

    create_all() legt nur neue Tabellen an. Da die DB im persistenten Volume
    Redeploys ueberlebt, braucht es fuer neue Modellfelder diesen Minimal-Ersatz
    fuer ein Migrations-Tool - sonst scheitert jede Abfrage mit "no such column".
    """
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())
    with target_engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing or not column.nullable:
                    continue
                col_type = column.type.compile(dialect=target_engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    add_missing_columns(engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
