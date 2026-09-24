from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import CurrentUser, accessible_vehicle_ids, get_accessible_vehicle, get_current_user
from app.db import get_db
from app.models import Trip
from app.schemas import TripCreate, TripOut

router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.get("", response_model=list[TripOut])
def list_trips(
    vehicle_id: int | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    q = (
        select(Trip)
        .where(Trip.vehicle_id.in_(accessible_vehicle_ids(user)))
        .order_by(Trip.datum.desc(), Trip.km_start.desc())
    )
    if vehicle_id is not None:
        q = q.where(Trip.vehicle_id == vehicle_id)
    return db.execute(q).scalars().all()


@router.post("", response_model=TripOut, status_code=201)
def create_trip(payload: TripCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    vehicle = get_accessible_vehicle(db, payload.vehicle_id, user)
    if vehicle.kaufkilometerstand is not None and payload.km_start < vehicle.kaufkilometerstand:
        raise HTTPException(
            400,
            f"km-Stand am Start ({payload.km_start} km) liegt unter dem "
            f"Kilometerstand beim Kauf ({vehicle.kaufkilometerstand} km).",
        )
    trip = Trip(**payload.model_dump(), erfasst_von=user.uid)
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


@router.delete("/{trip_id}", status_code=204)
def delete_trip(trip_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(404, "Fahrt nicht gefunden")
    get_accessible_vehicle(db, trip.vehicle_id, user)
    db.delete(trip)
    db.commit()
