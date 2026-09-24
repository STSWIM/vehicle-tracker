"""
Zustandsverwaltung fuer laufende Erfassungen: ein Nutzer schickt i.d.R.
zwei Fotos (Tacho + Beleg), die zu EINEM Tankeintrag zusammengehoeren.

Bewusst einfach gehalten (In-Memory, pro Prozess) – reicht fuer den
persoenlichen Gebrauch mit wenigen gleichzeitigen Unterhaltungen. Falls
die ExApp mal mit mehreren Worker-Prozessen laeuft, muesste das durch
eine DB-Tabelle ersetzt werden.
"""
from __future__ import annotations

import datetime
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.access import CurrentUser, accessible_vehicles_query
from app.i18n import t
from app.models import FuelEntry, Quelle, Vehicle
from app.ocr.parser import BelegVorschlag, TachoVorschlag
from app.validation import pruefe_kilometerstand

SESSION_TIMEOUT_SECONDS = 15 * 60


@dataclass
class CaptureSession:
    conversation_token: str
    # Talk-Absender ("users/<uid>"): pro Raum UND Absender eine eigene
    # Erfassung, damit sich Fotos zweier Familienmitglieder im selben Raum
    # nicht vermischen.
    actor_id: str = ""
    vehicle_id: int | None = None
    tacho: TachoVorschlag | None = None
    beleg: BelegVorschlag | None = None
    # Originalfotos bis zur Bestaetigung im Speicher halten; abgelegt werden
    # sie erst beim Speichern des Eintrags (app/photo_storage.py).
    tacho_foto: bytes | None = None
    beleg_foto: bytes | None = None
    last_update: float = field(default_factory=time.time)

    @property
    def is_complete(self) -> bool:
        return self.tacho is not None and self.beleg is not None

    @property
    def is_expired(self) -> bool:
        return time.time() - self.last_update > SESSION_TIMEOUT_SECONDS


_sessions: dict[tuple[str, str], CaptureSession] = {}


def _purge_expired() -> None:
    # Sessions halten Fotos im Speicher - abgelaufene nicht ewig mitschleppen.
    for key in [k for k, s in _sessions.items() if s.is_expired]:
        del _sessions[key]


def get_or_create_session(conversation_token: str, actor_id: str) -> CaptureSession:
    _purge_expired()
    key = (conversation_token, actor_id)
    existing = _sessions.get(key)
    if existing:
        existing.last_update = time.time()
        return existing
    session = CaptureSession(conversation_token=conversation_token, actor_id=actor_id)
    _sessions[key] = session
    return session


def clear_session(conversation_token: str, actor_id: str) -> None:
    _sessions.pop((conversation_token, actor_id), None)


def resolve_vehicle_by_codewort(db: Session, codewort: str, user: CurrentUser) -> Vehicle | None:
    """Nur Fahrzeuge, auf die der Absender Zugriff hat - sonst koennte jeder,
    der das Codewort kennt, Eintraege fuer fremde Fahrzeuge anlegen."""
    return db.execute(
        accessible_vehicles_query(user).where(Vehicle.bot_codewort == codewort.strip().lower())
    ).scalar_one_or_none()


def format_confirmation_message(session: CaptureSession, vehicle: Vehicle) -> str:
    beleg = session.beleg
    tacho = session.tacho
    warnungen = (beleg.warnungen if beleg else []) + (tacho.warnungen if tacho else [])
    unbekannt = t("unknown_value")

    zeilen = [
        t("confirmation_header", hersteller=vehicle.hersteller, modell=vehicle.modell,
          kennzeichen=vehicle.kennzeichen),
        f"- {t('field_datum')}: {beleg.datum if beleg else unbekannt}",
        f"- {t('field_kilometerstand')}: {tacho.kilometerstand if tacho else unbekannt}",
        f"- {t('field_kraftstoff')}: "
        f"{beleg.kraftstoffart.value if beleg and beleg.kraftstoffart else unbekannt}",
        f"- {t('field_menge')}: {beleg.fuellmenge_liter if beleg else unbekannt} l",
        f"- {t('field_preis_pro_liter')}: {beleg.preis_pro_liter if beleg else unbekannt} €",
        f"- {t('field_gesamtpreis')}: {beleg.gesamtpreis if beleg else unbekannt} €",
    ]
    if warnungen:
        zeilen.append("")
        zeilen.append("⚠️ " + " / ".join(sorted(set(warnungen))))
    zeilen.append("")
    zeilen.append(t("confirmation_prompt"))
    return "\n".join(zeilen)


def fehlende_pflichtfelder(session: CaptureSession) -> list[str]:
    """Prueft, ob alle fuer einen FuelEntry noetigen Felder erkannt wurden.
    Wird vor dem Speichern aufgerufen, damit bei fehlgeschlagener OCR nicht
    stillschweigend Nullwerte/Standardwerte gebucht werden."""
    beleg, tacho = session.beleg, session.tacho
    fehlend = []
    if not tacho or tacho.kilometerstand is None:
        fehlend.append(t("field_kilometerstand"))
    if not beleg or beleg.kraftstoffart is None:
        fehlend.append(t("field_kraftstoff"))
    if not beleg or beleg.fuellmenge_liter is None:
        fehlend.append(t("field_menge"))
    if not beleg or beleg.preis_pro_liter is None:
        fehlend.append(t("field_preis_pro_liter"))
    if not beleg or beleg.gesamtpreis is None:
        fehlend.append(t("field_gesamtpreis"))
    return fehlend


def pruefe_kilometerstand_fuer_session(db: Session, session: CaptureSession) -> None:
    """Wirft KilometerstandUnplausibelError, falls der erkannte
    Kilometerstand der bestehenden Fahrhistorie widerspricht. Nur
    aufzurufen, wenn fehlende_pflichtfelder() bereits leer ist."""
    datum = (session.beleg.datum if session.beleg else None) or datetime.date.today()
    pruefe_kilometerstand(db, session.vehicle_id, datum, session.tacho.kilometerstand)


def build_fuel_entry(session: CaptureSession, erfasst_von: str | None = None) -> FuelEntry:
    """Wandelt eine bestaetigte Session in ein FuelEntry-Objekt um. Wird
    erst nach expliziter Bestaetigung im Chat aufgerufen, wenn
    fehlende_pflichtfelder() bereits leer ist - deshalb hier keine
    Fallback-/Nullwerte mehr wie in frueheren Versionen."""
    assert session.is_complete and session.vehicle_id is not None
    beleg = session.beleg
    tacho = session.tacho
    assert tacho.kilometerstand is not None
    assert beleg.kraftstoffart is not None
    assert beleg.fuellmenge_liter is not None
    assert beleg.preis_pro_liter is not None
    assert beleg.gesamtpreis is not None

    return FuelEntry(
        vehicle_id=session.vehicle_id,
        datum=beleg.datum or datetime.date.today(),
        kilometerstand=tacho.kilometerstand,
        kraftstoffart=beleg.kraftstoffart,
        fuellmenge_liter=beleg.fuellmenge_liter,
        preis_pro_liter=beleg.preis_pro_liter,
        gesamtpreis=beleg.gesamtpreis,
        quelle=Quelle.CHAT_BOT,
        ocr_konfidenz=min(beleg.konfidenz, tacho.konfidenz),
        erfasst_von=erfasst_von,
    )
