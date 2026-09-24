from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import CurrentUser, accessible_vehicle_ids, get_accessible_vehicle, get_current_user
from app.db import get_db
from app.models import OtherCost
from app.schemas import OtherCostCreate, OtherCostOut

router = APIRouter(prefix="/api/other-costs", tags=["other-costs"])


@router.get("", response_model=list[OtherCostOut])
def list_other_costs(
    vehicle_id: int | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    q = select(OtherCost).where(OtherCost.vehicle_id.in_(accessible_vehicle_ids(user))).order_by(OtherCost.datum)
    if vehicle_id is not None:
        q = q.where(OtherCost.vehicle_id == vehicle_id)
    return db.execute(q).scalars().all()


@router.post("", response_model=OtherCostOut, status_code=201)
def create_other_cost(
    payload: OtherCostCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    get_accessible_vehicle(db, payload.vehicle_id, user)
    cost = OtherCost(**payload.model_dump())
    db.add(cost)
    db.commit()
    db.refresh(cost)
    return cost


@router.delete("/{cost_id}", status_code=204)
def delete_other_cost(cost_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    cost = db.get(OtherCost, cost_id)
    if cost is None:
        raise HTTPException(404, "Eintrag nicht gefunden")
    get_accessible_vehicle(db, cost.vehicle_id, user)
    db.delete(cost)
    db.commit()
