import os
from pathlib import Path

from sqlalchemy import create_engine
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


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
