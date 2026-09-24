"""erfasst_von (#6), Talk-Anhaenge (#2) und Belegfotos beim Fahrzeugbesitzer (#3)."""
import asyncio
import datetime
import json
import logging

import pytest

from app.access import CurrentUser, get_current_user
from app.db import SessionLocal
from app.models import FuelEntry, Kraftstoffart
from app.ocr.engine import OcrResult
from app.ocr.parser import BelegVorschlag, TachoVorschlag
from app.photo_storage import PhotoStorageError, load_photo
from app.talk_bot import session as capture_session
from app.talk_bot import webhook

ALICE = CurrentUser("alice")
CAROL = CurrentUser("carol")
DAVE = CurrentUser("dave")

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"x" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"y" * 200


@pytest.fixture()
def as_user(client):
    from main import app

    def switch(user):
        app.dependency_overrides[get_current_user] = lambda: user
        return client

    yield switch
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def photo_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PERSISTENT_STORAGE", str(tmp_path))
    return tmp_path


def _shared_vehicle(as_user, codewort=None):
    body = {"kennzeichen": "RT-WI 14", "hersteller": "Toyota", "modell": "Previa"}
    if codewort:
        body["bot_codewort"] = codewort
    response = as_user(ALICE).post("/api/vehicles", json=body)
    assert response.status_code == 201, response.text
    vehicle = response.json()
    response = as_user(ALICE).put(
        f"/api/vehicles/{vehicle['id']}/shares", json=[{"share_type": "user", "share_with": "carol"}]
    )
    assert response.status_code == 200, response.text
    return vehicle


def _fuel_payload(vehicle_id, **extra):
    return {
        "vehicle_id": vehicle_id, "datum": "2024-01-01", "kilometerstand": 1000, "kraftstoffart": "LPG",
        "fuellmenge_liter": 30, "preis_pro_liter": 1, "gesamtpreis": 30, **extra,
    }


# --- #6 erfasst_von ------------------------------------------------------------


def test_erfasst_von_wird_bei_allen_eintraegen_gesetzt(as_user):
    vehicle = _shared_vehicle(as_user)
    carol = as_user(CAROL)
    vid = vehicle["id"]

    created = [
        carol.post("/api/fuel-entries", json=_fuel_payload(vid, erfasst_von="mallory")),
        carol.post("/api/other-costs", json={"vehicle_id": vid, "datum": "2024-01-01", "kategorie": "Waschen",
                                             "betrag": 10, "erfasst_von": "mallory"}),
        carol.post("/api/logbook", json={"vehicle_id": vid, "datum": "2024-01-01", "eintrag": "Ölwechsel"}),
        carol.post("/api/trips", json={"vehicle_id": vid, "datum": "2024-01-01", "start": "A", "ziel": "B",
                                       "km_start": 1000, "km_ende": 1010}),
    ]
    for response in created:
        assert response.status_code == 201, response.text
        # Nicht ueber die API setzbar - kommt immer vom angemeldeten Nutzer.
        assert response.json()["erfasst_von"] == "carol"

    alice = as_user(ALICE)
    for path in ("/api/fuel-entries", "/api/other-costs", "/api/logbook", "/api/trips"):
        assert [e["erfasst_von"] for e in alice.get(f"{path}?vehicle_id={vid}").json()] == ["carol"]


# --- #2 Talk-Anhaenge ----------------------------------------------------------

TALK_FILE_CONTENT = {
    "message": "{file}",
    "parameters": {
        "actor": {"type": "user", "id": "alice", "name": "Alice"},
        "file": {
            "type": "file", "id": "123", "name": "IMG_0001.jpg", "size": 204800,
            "path": "Talk/IMG_0001.jpg", "link": "https://cloud.example.com/index.php/f/123",
            "etag": "abc", "permissions": 27, "mimetype": "image/jpeg", "preview-available": "yes",
        },
    },
}


def test_extract_talk_attachment_aus_beispielpayload():
    assert webhook.extract_talk_attachment(TALK_FILE_CONTENT) == ("123", "Talk/IMG_0001.jpg", "image/jpeg")


@pytest.mark.parametrize(
    "content",
    [
        {"message": "previa", "parameters": []},  # PHP: leere Parameter als Liste
        {"message": "hallo"},
        {"message": "{mention}", "parameters": {"mention": {"type": "user", "id": "bob", "name": "Bob"}}},
        {"message": "{file}", "parameters": {"file": {"type": "file", "id": "x1", "path": "../geheim.jpg"}}},
        {},
    ],
)
def test_extract_talk_attachment_ohne_datei(content):
    assert webhook.extract_talk_attachment(content) is None


def test_extract_talk_attachment_randfaelle():
    nur_pfad = {"parameters": {"file": {"type": "file", "path": "/Talk/a.png", "mimetype": "IMAGE/PNG"}}}
    assert webhook.extract_talk_attachment(nur_pfad) == (None, "Talk/a.png", "image/png")

    pdf = {"parameters": {"file": {"type": "file", "id": 7, "path": "Talk/r.pdf", "mimetype": "application/pdf"}}}
    assert webhook.extract_talk_attachment(pdf) == ("7", "Talk/r.pdf", "application/pdf")


def _talk_message(actor, text=None, content=None, token="raum1"):
    from nc_py_api.talk_bot import TalkBotMessage

    content = content if content is not None else {"message": text, "parameters": []}
    return TalkBotMessage({
        "type": "Create",
        "actor": {"type": "Person", "id": f"users/{actor}", "name": actor},
        "object": {"type": "Note", "id": 1, "name": "message", "content": json.dumps(content),
                   "mediaType": "text/markdown"},
        "target": {"type": "Collection", "id": token, "name": "Familie"},
    })


@pytest.fixture()
def talk(monkeypatch, photo_dir, db_session):
    """Talk-Flow ohne Nextcloud: Antworten, Download und OCR ersetzt."""
    capture_session._sessions.clear()
    replies, downloads = [], []

    async def fake_reply(message, text):
        replies.append((message.actor_id, text))

    async def fake_download(uid, attachment):
        downloads.append((uid, attachment))
        return JPEG

    monkeypatch.setattr(webhook, "_reply", fake_reply)
    monkeypatch.setattr(webhook, "download_talk_attachment", fake_download)
    monkeypatch.setattr(webhook, "run_ocr", lambda path: OcrResult(lines=[]))
    monkeypatch.setattr(webhook, "extract_gps_from_photo", lambda path: None)
    monkeypatch.setattr(webhook, "parse_tacho", lambda ocr: TachoVorschlag(kilometerstand=1500, konfidenz=0.9))
    monkeypatch.setattr(
        webhook,
        "parse_beleg",
        lambda ocr: BelegVorschlag(datum=datetime.date(2024, 3, 1), gesamtpreis=40.0, preis_pro_liter=1.0,
                                   fuellmenge_liter=40.0, kraftstoffart=Kraftstoffart.LPG, konfidenz=0.8),
    )

    def send(message):
        db = SessionLocal()
        try:
            asyncio.run(webhook._handle_message(message, db))
        finally:
            db.close()

    send.replies = replies
    send.downloads = downloads
    yield send
    capture_session._sessions.clear()


def test_talk_sessions_je_absender_getrennt(as_user, talk):
    _shared_vehicle(as_user, codewort="previa")

    talk(_talk_message("carol", "previa"))
    talk(_talk_message("carol", content=TALK_FILE_CONTENT))  # Tacho von carol
    talk(_talk_message("bob", content=TALK_FILE_CONTENT))    # bob im selben Raum

    carol = capture_session._sessions[("raum1", "users/carol")]
    bob = capture_session._sessions[("raum1", "users/bob")]
    assert carol.tacho is not None and carol.beleg is None and carol.vehicle_id is not None
    # bobs Foto landet NICHT als Beleg in carols Erfassung
    assert bob.tacho is not None and bob.vehicle_id is None
    # heruntergeladen wird als der jeweilige Absender
    assert [uid for uid, _ in talk.downloads] == ["carol", "bob"]

    capture_session.clear_session("raum1", "users/bob")
    assert ("raum1", "users/carol") in capture_session._sessions


def test_talk_eintrag_mit_erfasst_von_und_fotos_beim_besitzer(as_user, talk, photo_dir):
    vehicle = _shared_vehicle(as_user, codewort="previa")

    talk(_talk_message("carol", "previa"))
    talk(_talk_message("carol", content=TALK_FILE_CONTENT))
    talk(_talk_message("carol", content=TALK_FILE_CONTENT))
    talk(_talk_message("carol", "ja"))

    assert talk.replies[-1][1].startswith("✅")
    db = SessionLocal()
    try:
        entry = db.query(FuelEntry).one()
        assert entry.erfasst_von == "carol"
        assert entry.beleg_foto_pfad == f"Fahrzeuge/RT-WI 14/Belege/2024-03-01_beleg_{entry.id}.jpg"
        assert entry.tacho_foto_pfad == f"Fahrzeuge/RT-WI 14/Belege/2024-03-01_tacho_{entry.id}.jpg"
    finally:
        db.close()
    # Ablage im Bereich der Besitzerin alice, nicht bei carol
    assert (photo_dir / "fotos" / "alice" / entry.beleg_foto_pfad).read_bytes() == JPEG
    assert not (photo_dir / "fotos" / "carol").exists()
    assert ("raum1", "users/carol") not in capture_session._sessions

    response = as_user(CAROL).get(f"/api/fuel-entries/{entry.id}/foto?art=tacho")
    assert response.status_code == 200
    assert response.content == JPEG
    assert vehicle["id"] == entry.vehicle_id


def test_talk_lehnt_nicht_bilder_ab(talk):
    pdf = {"message": "{file}",
           "parameters": {"file": {"type": "file", "id": "9", "path": "Talk/r.pdf", "mimetype": "application/pdf"}}}
    talk(_talk_message("carol", content=pdf))
    assert talk.downloads == []
    assert "keine Bilddatei" in talk.replies[-1][1]


def test_talk_debug_payload_logging(talk, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.talk_bot.webhook")
    talk(_talk_message("carol", "hallo"))
    assert "TALK_DEBUG_PAYLOAD" not in caplog.text

    monkeypatch.setenv("TALK_DEBUG_PAYLOAD", "true")
    talk(_talk_message("carol", content=TALK_FILE_CONTENT))
    assert "TALK_DEBUG_PAYLOAD" in caplog.text
    assert "Talk/IMG_0001.jpg" in caplog.text


# --- #3 Belegfotos per Web-Upload ----------------------------------------------


def test_foto_upload_und_abruf_standalone(as_user, photo_dir):
    vehicle = _shared_vehicle(as_user)
    carol = as_user(CAROL)
    entry = carol.post("/api/fuel-entries", json=_fuel_payload(vehicle["id"])).json()
    assert entry["beleg_foto_pfad"] is None

    response = carol.post(
        f"/api/fuel-entries/{entry['id']}/foto?art=beleg", files={"datei": ("beleg.jpg", JPEG, "image/jpeg")}
    )
    assert response.status_code == 200, response.text
    pfad = response.json()["beleg_foto_pfad"]
    assert pfad == f"Fahrzeuge/RT-WI 14/Belege/2024-01-01_beleg_{entry['id']}.jpg"
    assert (photo_dir / "fotos" / "alice" / pfad).read_bytes() == JPEG

    response = carol.post(
        f"/api/fuel-entries/{entry['id']}/foto?art=tacho", files={"datei": ("t.png", PNG, "image/png")}
    )
    assert response.json()["tacho_foto_pfad"].endswith(f"_tacho_{entry['id']}.png")

    # Besitzerin und Freigegebene sehen die Fotos
    for user in (ALICE, CAROL):
        response = as_user(user).get(f"/api/fuel-entries/{entry['id']}/foto?art=beleg")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content == JPEG
    assert as_user(ALICE).get(f"/api/fuel-entries/{entry['id']}/foto?art=tacho").content == PNG


def test_foto_zugriffsschutz(as_user, photo_dir):
    vehicle = _shared_vehicle(as_user)
    alice = as_user(ALICE)
    entry = alice.post("/api/fuel-entries", json=_fuel_payload(vehicle["id"])).json()
    alice.post(f"/api/fuel-entries/{entry['id']}/foto?art=beleg", files={"datei": ("b.jpg", JPEG, "image/jpeg")})

    dave = as_user(DAVE)
    assert dave.get(f"/api/fuel-entries/{entry['id']}/foto?art=beleg").status_code == 404
    response = dave.post(
        f"/api/fuel-entries/{entry['id']}/foto?art=beleg", files={"datei": ("b.jpg", PNG, "image/png")}
    )
    assert response.status_code == 404
    assert as_user(ALICE).get(f"/api/fuel-entries/{entry['id']}/foto?art=beleg").content == JPEG


def test_foto_nur_bilder_und_groessenlimit(as_user, photo_dir):
    vehicle = _shared_vehicle(as_user)
    alice = as_user(ALICE)
    entry = alice.post("/api/fuel-entries", json=_fuel_payload(vehicle["id"])).json()
    url = f"/api/fuel-entries/{entry['id']}/foto?art=beleg"

    # Content-Type des Clients zaehlt nicht, nur der Dateiinhalt
    response = alice.post(url, files={"datei": ("x.jpg", b"%PDF-1.4 nope", "image/jpeg")})
    assert response.status_code == 400
    response = alice.post(url, files={"datei": ("x.jpg", JPEG + b"0" * (15 * 1024 * 1024), "image/jpeg")})
    assert response.status_code == 413
    assert alice.post(f"/api/fuel-entries/{entry['id']}/foto?art=kaputt",
                      files={"datei": ("x.jpg", JPEG, "image/jpeg")}).status_code == 422
    assert alice.get(url).status_code == 404  # noch kein Foto


def test_fotopfad_nicht_per_api_setzbar(as_user, photo_dir):
    vehicle = _shared_vehicle(as_user)
    response = as_user(CAROL).post(
        "/api/fuel-entries", json=_fuel_payload(vehicle["id"], beleg_foto_pfad="Dokumente/geheim.jpg")
    )
    assert response.status_code == 201
    assert response.json()["beleg_foto_pfad"] is None

    class _V:
        owner = "alice"
        kennzeichen = "RT-WI 14"

    for pfad in ("Dokumente/geheim.jpg", "Fahrzeuge/../Dokumente/Belege/x.jpg", "/Fahrzeuge/A/Belege/x.jpg"):
        with pytest.raises(PhotoStorageError):
            asyncio.run(load_photo(_V(), pfad))
