from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import (
    CurrentUser,
    accessible_vehicles_query,
    claim_ownerless_vehicles,
    get_accessible_vehicle,
    get_current_user,
    require_owner,
)
from app.db import get_db
from app.models import FuelEntry, Vehicle, VehicleShare
from app.schemas import ShareIn, ShareOut, VehicleCreate, VehicleOut

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


def _normalized_data(payload: VehicleCreate) -> dict:
    data = payload.model_dump()
    if data.get("bot_codewort"):
        data["bot_codewort"] = data["bot_codewort"].strip().lower()
    return data


def _ensure_unique_kennzeichen(db: Session, kennzeichen: str, exclude_id: int | None = None) -> None:
    # Bewusst ueber alle Fahrzeuge, nicht nur die zugaenglichen: das
    # Kennzeichen ist in der DB eindeutig.
    q = select(Vehicle).where(Vehicle.kennzeichen == kennzeichen)
    if exclude_id is not None:
        q = q.where(Vehicle.id != exclude_id)
    if db.execute(q).scalar_one_or_none() is not None:
        raise HTTPException(400, "Kennzeichen bereits vorhanden")


def _commit_or_400(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(400, "Talk-Bot-Codewort ist bereits einem anderen Fahrzeug zugeordnet") from exc


@router.get("", response_model=list[VehicleOut])
def list_vehicles(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    claim_ownerless_vehicles(db, user)
    return db.execute(accessible_vehicles_query(user).order_by(Vehicle.id)).scalars().all()


@router.post("", response_model=VehicleOut, status_code=201)
def create_vehicle(
    payload: VehicleCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    _ensure_unique_kennzeichen(db, payload.kennzeichen)
    vehicle = Vehicle(**_normalized_data(payload), owner=user.uid)
    db.add(vehicle)
    _commit_or_400(db)
    db.refresh(vehicle)
    return vehicle


@router.get("/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    return get_accessible_vehicle(db, vehicle_id, user)


@router.put("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(
    vehicle_id: int,
    payload: VehicleCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    vehicle = get_accessible_vehicle(db, vehicle_id, user)
    _ensure_unique_kennzeichen(db, payload.kennzeichen, exclude_id=vehicle_id)

    if payload.kaufkilometerstand is not None:
        min_km = db.execute(
            select(func.min(FuelEntry.kilometerstand)).where(FuelEntry.vehicle_id == vehicle_id)
        ).scalar_one()
        if min_km is not None and payload.kaufkilometerstand > min_km:
            raise HTTPException(
                400,
                f"km-Stand bei Kauf ({payload.kaufkilometerstand} km) liegt ueber dem "
                f"niedrigsten erfassten Tank-Kilometerstand ({min_km} km).",
            )

    for key, value in _normalized_data(payload).items():
        setattr(vehicle, key, value)
    _commit_or_400(db)
    db.refresh(vehicle)
    return vehicle


@router.put("/{vehicle_id}/shares", response_model=list[ShareOut])
def replace_shares(
    vehicle_id: int,
    payload: list[ShareIn],
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Ersetzt alle Freigaben des Fahrzeugs (nur Besitzer)."""
    vehicle = get_accessible_vehicle(db, vehicle_id, user)
    require_owner(vehicle, user)
    unique = {(s.share_type, s.share_with.strip()) for s in payload if s.share_with.strip()}
    vehicle.shares = [
        VehicleShare(share_type=share_type, share_with=share_with)
        for share_type, share_with in sorted(unique)
        if not (share_type.value == "user" and share_with == vehicle.owner)
    ]
    db.commit()
    db.refresh(vehicle)
    return vehicle.shares


@router.delete("/{vehicle_id}", status_code=204)
def deactivate_vehicle(
    vehicle_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    """Fahrzeuge werden nicht geloescht (Kostenhistorie bleibt erhalten),
    sondern nur deaktiviert."""
    vehicle = get_accessible_vehicle(db, vehicle_id, user)
    require_owner(vehicle, user)
    vehicle.aktiv = False
    db.commit()
