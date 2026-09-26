from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import CurrentUser, accessible_vehicle_ids, get_accessible_vehicle, get_current_user
from app.db import get_db
from app.models import FuelEntry, Vehicle
from app.photo_storage import (
    MAX_PHOTO_BYTES,
    PhotoError,
    PhotoKind,
    PhotoNotFoundError,
    PhotoStorageError,
    PhotoTooLargeError,
    load_photo,
    mimetype_for_path,
    save_photo,
)
from app.schemas import FuelEntryCreate, FuelEntryOut
from app.validation import KilometerstandUnplausibelError, pruefe_kilometerstand, pruefe_verbrauch

router = APIRouter(prefix="/api/fuel-entries", tags=["fuel-entries"])


@router.get("", response_model=list[FuelEntryOut])
def list_fuel_entries(
    vehicle_id: int | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    q = select(FuelEntry).where(FuelEntry.vehicle_id.in_(accessible_vehicle_ids(user))).order_by(FuelEntry.datum)
    if vehicle_id is not None:
        q = q.where(FuelEntry.vehicle_id == vehicle_id)
    return db.execute(q).scalars().all()


@router.post("", response_model=FuelEntryOut, status_code=201)
def create_fuel_entry(
    payload: FuelEntryCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    get_accessible_vehicle(db, payload.vehicle_id, user)
    try:
        pruefe_kilometerstand(db, payload.vehicle_id, payload.datum, payload.kilometerstand)
    except KilometerstandUnplausibelError as exc:
        raise HTTPException(400, str(exc)) from exc

    entry = FuelEntry(**payload.model_dump(), erfasst_von=user.uid)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    entry.warnungen = pruefe_verbrauch(db, entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_fuel_entry(entry_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    entry = db.get(FuelEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "Eintrag nicht gefunden")
    get_accessible_vehicle(db, entry.vehicle_id, user)
    db.delete(entry)
    db.commit()


# --- Beleg-/Tachofotos -------------------------------------------------------
# Abgelegt in den Nextcloud-Dateien des Fahrzeugbesitzers (app/photo_storage.py);
# ausgeliefert ueber diese API, damit auch freigegebene Nutzer sie sehen.


def _entry_with_vehicle(db: Session, entry_id: int, user: CurrentUser) -> tuple[FuelEntry, Vehicle]:
    entry = db.get(FuelEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "Eintrag nicht gefunden")
    return entry, get_accessible_vehicle(db, entry.vehicle_id, user)


@router.post("/{entry_id}/foto", response_model=FuelEntryOut)
async def upload_fuel_entry_photo(
    entry_id: int,
    art_query: PhotoKind | None = Query(None, alias="art"),
    # Der AppAPI-Proxy verwirft bei multipart-Uploads die Query-Parameter,
    # deshalb kommt "art" aus dem Frontend als Formularfeld.
    art_form: PhotoKind | None = Form(None, alias="art"),
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    art = art_form or art_query or PhotoKind.BELEG
    entry, vehicle = _entry_with_vehicle(db, entry_id, user)
    data = await datei.read(MAX_PHOTO_BYTES + 1)
    try:
        path = await save_photo(vehicle, art, entry.datum, data, suffix=str(entry.id))
    except PhotoTooLargeError as exc:
        raise HTTPException(413, str(exc)) from exc
    except PhotoError as exc:
        raise HTTPException(400, str(exc)) from exc
    except PhotoStorageError as exc:
        raise HTTPException(502, str(exc)) from exc

    setattr(entry, f"{art.value}_foto_pfad", path)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/{entry_id}/foto")
async def get_fuel_entry_photo(
    entry_id: int,
    art: PhotoKind = Query(PhotoKind.BELEG),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    entry, vehicle = _entry_with_vehicle(db, entry_id, user)
    path = getattr(entry, f"{art.value}_foto_pfad")
    if not path:
        raise HTTPException(404, "Kein Foto vorhanden")
    try:
        data = await load_photo(vehicle, path)
    except PhotoNotFoundError as exc:
        raise HTTPException(404, "Foto nicht gefunden") from exc
    except PhotoStorageError as exc:
        raise HTTPException(502, str(exc)) from exc

    filename = path.rsplit("/", 1)[-1]
    return Response(
        content=data,
        media_type=mimetype_for_path(path),
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )
