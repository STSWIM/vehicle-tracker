from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import FuelEntry, Vehicle
from app.schemas import VehicleCreate, VehicleOut

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


def _normalized_data(payload: VehicleCreate) -> dict:
    data = payload.model_dump()
    if data.get("bot_codewort"):
        data["bot_codewort"] = data["bot_codewort"].strip().lower()
    return data


def _ensure_unique_kennzeichen(db: Session, kennzeichen: str, exclude_id: int | None = None) -> None:
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
def list_vehicles(db: Session = Depends(get_db)):
    return db.execute(select(Vehicle)).scalars().all()


@router.post("", response_model=VehicleOut, status_code=201)
def create_vehicle(payload: VehicleCreate, db: Session = Depends(get_db)):
    _ensure_unique_kennzeichen(db, payload.kennzeichen)
    vehicle = Vehicle(**_normalized_data(payload))
    db.add(vehicle)
    _commit_or_400(db)
    db.refresh(vehicle)
    return vehicle


@router.get("/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(404, "Fahrzeug nicht gefunden")
    return vehicle


@router.put("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(vehicle_id: int, payload: VehicleCreate, db: Session = Depends(get_db)):
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(404, "Fahrzeug nicht gefunden")
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


@router.delete("/{vehicle_id}", status_code=204)
def deactivate_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    """Fahrzeuge werden nicht geloescht (Kostenhistorie bleibt erhalten),
    sondern nur deaktiviert."""
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(404, "Fahrzeug nicht gefunden")
    vehicle.aktiv = False
    db.commit()
