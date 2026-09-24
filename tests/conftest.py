"""
Pytest-Fixtures. Setzt DATABASE_URL auf eine temporaere SQLite-Datei,
BEVOR app.db (und damit die Engine) importiert wird - deshalb passiert
das hier ganz oben in conftest.py statt in einer Fixture.
"""
import os
import tempfile

_tmp_dir = tempfile.mkdtemp(prefix="vehicle_tracker_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"
os.environ["STANDALONE_MODE"] = "true"
os.environ.setdefault("LLM_FALLBACK_ENABLED", "false")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import (  # noqa: E402
    FuelEntry,
    LogbookEntry,
    MaintenanceReminder,
    OtherCost,
    Trip,
    Vehicle,
    VehicleShare,
)


@pytest.fixture()
def db_session():
    init_db()
    session = SessionLocal()
    try:
        # Tabellen zwischen Tests leeren statt jedes Mal eine neue DB
        # anzulegen - reicht fuer den ueberschaubaren Testumfang hier.
        session.query(FuelEntry).delete()
        session.query(OtherCost).delete()
        session.query(MaintenanceReminder).delete()
        session.query(LogbookEntry).delete()
        session.query(Trip).delete()
        session.query(VehicleShare).delete()
        session.query(Vehicle).delete()
        session.commit()
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    from main import app

    return TestClient(app)
