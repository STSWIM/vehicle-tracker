"""
Export-Endpunkte (Issue #14): CSV mit allen Eintraegen des Zeitraums und
PDF-Bericht fuer Steuerberater bzw. Fahrzeugverkauf. Jeder mit Zugriff auf
das Fahrzeug darf exportieren. Aufbau der Dateien siehe app/export.py.
"""
from __future__ import annotations

import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.access import CurrentUser, get_accessible_vehicle, get_current_user
from app.db import get_db
from app.export import build_csv, build_pdf, collect, export_filename
from app.routers.stats import compute_vehicle_stats

router = APIRouter(prefix="/api/vehicles", tags=["export"])


def _attachment(filename: str) -> dict[str, str]:
    return {
        "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}",
        "Cache-Control": "no-store",
    }


@router.get("/{vehicle_id}/export.csv")
def export_csv(
    vehicle_id: int,
    von: datetime.date | None = None,
    bis: datetime.date | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    vehicle = get_accessible_vehicle(db, vehicle_id, user)
    content = build_csv(collect(vehicle, von, bis))
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers=_attachment(export_filename(vehicle, von, bis, "csv")),
    )


@router.get("/{vehicle_id}/export.pdf")
def export_pdf(
    vehicle_id: int,
    von: datetime.date | None = None,
    bis: datetime.date | None = None,
    mit_anschaffung: bool = True,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    vehicle = get_accessible_vehicle(db, vehicle_id, user)
    stats = compute_vehicle_stats(vehicle, von, bis, mit_anschaffung)
    content = build_pdf(collect(vehicle, von, bis), stats)
    return Response(
        content,
        media_type="application/pdf",
        headers=_attachment(export_filename(vehicle, von, bis, "pdf")),
    )
