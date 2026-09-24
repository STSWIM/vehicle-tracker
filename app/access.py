"""
Zugriffsrechte auf Fahrzeuge.

Der angemeldete Nextcloud-Nutzer kommt im ExApp-Modus aus der von AppAPI
signierten Anfrage (AppAPIAuthMiddleware legt ihn in request.scope["username"]
ab). Zugriff hat der Besitzer eines Fahrzeugs sowie jeder, fuer den es als
Nutzer oder ueber eine seiner Gruppen freigegeben ist. Freigegebene haben
volle Nutzung; Freigaben verwalten und Fahrzeug deaktivieren darf nur der
Besitzer.

Im Standalone-Dev-Modus gibt es keine Nextcloud-Nutzer - dort hat ein
fester Dev-Nutzer Zugriff auf alles.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

from fastapi import HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import ShareType, Vehicle, VehicleShare

LOGGER = logging.getLogger(__name__)

GROUP_CACHE_SECONDS = 60
_group_cache: dict[str, tuple[float, frozenset[str]]] = {}


def standalone_mode() -> bool:
    return os.environ.get("STANDALONE_MODE", "true").lower() == "true"


@dataclass(frozen=True)
class CurrentUser:
    uid: str
    groups: frozenset[str] = field(default_factory=frozenset)
    superuser: bool = False


async def load_user_groups(uid: str) -> frozenset[str]:
    """Gruppen eines Nutzers bei Nextcloud abfragen (kurz gecacht, weil jede
    API-Anfrage sie braucht). Faellt bei Fehlern auf "keine Gruppen" zurueck:
    Nutzer-Freigaben und Besitz funktionieren dann weiter."""
    cached = _group_cache.get(uid)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    try:
        from nc_py_api import AsyncNextcloudApp

        info = await AsyncNextcloudApp(user=uid).users.get_user(uid)
        groups = frozenset(info.groups)
    except Exception:  # noqa: BLE001 - Nextcloud nicht erreichbar o.ae.
        LOGGER.exception("Gruppen fuer %s konnten nicht geladen werden", uid)
        groups = frozenset()
    _group_cache[uid] = (time.monotonic() + GROUP_CACHE_SECONDS, groups)
    return groups


async def load_user(uid: str) -> CurrentUser:
    return CurrentUser(uid=uid, groups=await load_user_groups(uid))


async def get_current_user(request: Request) -> CurrentUser:
    if standalone_mode():
        return CurrentUser(uid="dev", superuser=True)
    uid = request.scope.get("username") or ""
    if not uid:
        raise HTTPException(401, "Kein angemeldeter Nextcloud-Nutzer")
    return await load_user(uid)


def _access_filter(user: CurrentUser):
    shared_with_user = select(VehicleShare.vehicle_id).where(
        VehicleShare.share_type == ShareType.USER, VehicleShare.share_with == user.uid
    )
    conditions = [Vehicle.owner == user.uid, Vehicle.id.in_(shared_with_user)]
    if user.groups:
        shared_with_group = select(VehicleShare.vehicle_id).where(
            VehicleShare.share_type == ShareType.GROUP, VehicleShare.share_with.in_(user.groups)
        )
        conditions.append(Vehicle.id.in_(shared_with_group))
    return or_(*conditions)


def claim_ownerless_vehicles(db: Session, user: CurrentUser) -> None:
    """Fahrzeuge aus der Zeit vor den Zugriffsrechten haben keinen Besitzer -
    sie gehen an den ersten Nutzer, der danach die App oeffnet."""
    if user.superuser:
        return
    ownerless = db.execute(select(Vehicle).where(Vehicle.owner.is_(None))).scalars().all()
    for vehicle in ownerless:
        vehicle.owner = user.uid
    if ownerless:
        db.commit()


def accessible_vehicles_query(user: CurrentUser):
    q = select(Vehicle)
    if not user.superuser:
        q = q.where(_access_filter(user))
    return q


def accessible_vehicle_ids(user: CurrentUser):
    """Subquery der zugaenglichen Fahrzeug-IDs, fuer Listen-Endpunkte."""
    return accessible_vehicles_query(user).with_only_columns(Vehicle.id)


def get_accessible_vehicle(db: Session, vehicle_id: int, user: CurrentUser) -> Vehicle:
    """404 statt 403 bei fehlendem Zugriff, damit fremde Fahrzeuge nicht
    einmal ihre Existenz verraten."""
    vehicle = db.execute(
        accessible_vehicles_query(user).where(Vehicle.id == vehicle_id)
    ).scalar_one_or_none()
    if vehicle is None:
        raise HTTPException(404, "Fahrzeug nicht gefunden")
    return vehicle


def require_owner(vehicle: Vehicle, user: CurrentUser) -> None:
    if not user.superuser and vehicle.owner != user.uid:
        raise HTTPException(403, "Nur der Besitzer des Fahrzeugs darf das")
