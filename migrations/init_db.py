"""Einmaliges DB-Setup + Beispiel-Fahrzeug zum Ausprobieren.

Aufruf: python -m migrations.init_db
"""
from app.db import SessionLocal, init_db
from app.models import Vehicle


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        if not db.query(Vehicle).filter_by(kennzeichen="RT-WI 14").first():
            db.add(
                Vehicle(
                    kennzeichen="RT-WI 14",
                    hersteller="Toyota",
                    modell="Previa",
                    variante="mit Prins Gasumbau",
                    tankvolumen_lpg_l=54,
                    tankvolumen_benzin_l=75,
                    bot_codewort="previa",
                )
            )
            db.commit()
            print("Beispiel-Fahrzeug 'Previa' angelegt (Codewort: previa).")
        else:
            print("Beispiel-Fahrzeug existiert bereits.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
