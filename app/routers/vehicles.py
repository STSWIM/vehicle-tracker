from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Vehicle
from app.schemas import VehicleCreate, VehicleOut

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


@router.get("", response_model=list[VehicleOut])
def list_vehicles(db: Session = Depends(get_db)):
    return db.execute(select(Vehicle)).scalars().all()


@router.post("", response_model=VehicleOut, status_code=201)
def create_vehicle(payload: VehicleCreate, db: Session = Depends(get_db)):
    existing = db.execute(
        select(Vehicle).where(Vehicle.kennzeichen == payload.kennzeichen)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(400, "Kennzeichen bereits vorhanden")

    data = payload.model_dump()
    if data.get("bot_codewort"):
        data["bot_codewort"] = data["bot_codewort"].strip().lower()
    vehicle = Vehicle(**data)
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.get("/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(404, "Fahrzeug nicht gefunden")
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
