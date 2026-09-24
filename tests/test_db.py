from app.db import _default_database_url


def test_nutzt_persistenten_appapi_speicher(monkeypatch):
    monkeypatch.setenv("APP_PERSISTENT_STORAGE", "/nc_app_vehicle_tracker_data")
    assert _default_database_url() == "sqlite:////nc_app_vehicle_tracker_data/vehicle_tracker.db"


def test_ohne_appapi_lokaler_datenordner(monkeypatch):
    monkeypatch.delenv("APP_PERSISTENT_STORAGE", raising=False)
    assert _default_database_url() == "sqlite:///./data/vehicle_tracker.db"
