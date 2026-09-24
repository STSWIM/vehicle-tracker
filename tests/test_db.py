from sqlalchemy import create_engine, inspect, text

from app.db import _default_database_url, add_missing_columns
from app.models import Base


def test_bestehende_db_bekommt_neue_spalten(tmp_path):
    """Simuliert die DB im persistenten Volume, die vor Einfuehrung von
    Vehicle.kaufkilometerstand angelegt wurde."""
    engine = create_engine(f"sqlite:///{tmp_path}/alt.db")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE vehicles DROP COLUMN kaufkilometerstand'))

    add_missing_columns(engine)

    columns = {c["name"] for c in inspect(engine).get_columns("vehicles")}
    assert "kaufkilometerstand" in columns


def test_nutzt_persistenten_appapi_speicher(monkeypatch):
    monkeypatch.setenv("APP_PERSISTENT_STORAGE", "/nc_app_vehicle_tracker_data")
    assert _default_database_url() == "sqlite:////nc_app_vehicle_tracker_data/vehicle_tracker.db"


def test_ohne_appapi_lokaler_datenordner(monkeypatch):
    monkeypatch.delenv("APP_PERSISTENT_STORAGE", raising=False)
    assert _default_database_url() == "sqlite:///./data/vehicle_tracker.db"
