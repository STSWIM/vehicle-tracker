"""
Einstiegspunkt der ExApp.

Zwei Betriebsmodi ueber die Umgebungsvariable STANDALONE_MODE:

- STANDALONE_MODE=true (Default fuer die lokale Entwicklung, siehe
  docker-compose.yml): startet nur die FastAPI-App mit allen Routern,
  OHNE AppAPI-Lifecycle. Damit lassen sich API, OCR-Pipeline und Statistik-
  Berechnung sofort testen, ganz ohne eine echte Nextcloud-Instanz.

- STANDALONE_MODE=false: echter ExApp-Modus ueber nc_py_api, so wie
  AppAPI es erwartet (Heartbeat, /enabled-Endpunkt, Auth-Middleware).
  WICHTIG: den Import-Pfad und die genaue API von nc_py_api vor dem realen
  Deployment gegen die aktuelle Doku pruefen –
  https://cloud-py-api.github.io/nc_py_api/NextcloudApp.html
  Diese Datei wurde ohne Zugriff auf eine laufende Nextcloud-Instanz
  erstellt und ist als Ausgangspunkt, nicht als getesteter Endzustand,
  gedacht.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app.db import init_db  # noqa: E402
from app.routers import fuel_entries, logbook, me, other_costs, reminders, stats, trips, vehicles  # noqa: E402
from app.talk_bot.webhook import router as talk_bot_router  # noqa: E402

STANDALONE_MODE = os.environ.get("STANDALONE_MODE", "true").lower() == "true"


def _mount_routers(app: FastAPI) -> None:
    app.include_router(vehicles.router)
    app.include_router(fuel_entries.router)
    app.include_router(other_costs.router)
    app.include_router(reminders.router)
    app.include_router(stats.router)
    app.include_router(logbook.router)
    app.include_router(trips.router)
    app.include_router(me.router)
    app.include_router(talk_bot_router)
    app.mount("/ui", StaticFiles(directory="frontend/static", html=True), name="ui")


if STANDALONE_MODE:

    @asynccontextmanager
    async def _standalone_lifespan(_app: FastAPI):
        init_db()
        yield

    app = FastAPI(title="Fahrzeug Buchführung (Standalone-Dev-Modus)", lifespan=_standalone_lifespan)
    _mount_routers(app)
    # Im ExApp-Modus mountet nc_py_api.set_handlers js/ und img/ automatisch.
    app.mount("/js", StaticFiles(directory="js"), name="js")
    app.mount("/img", StaticFiles(directory="img"), name="img")

    if __name__ == "__main__":
        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("APP_PORT", 23000)))

else:
    # Echter AppAPI-ExApp-Modus.
    from nc_py_api import AsyncNextcloudApp
    from nc_py_api.ex_app import AppAPIAuthMiddleware, LogLvl, run_app, set_handlers

    from app.talk_bot.bot import handle_enabled as handle_talk_bot_enabled  # noqa: E402

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        from app.reminder_notifications import start_notification_task

        set_handlers(fastapi_app, enabled_handler)
        init_db()
        # Taeglicher Job fuer Erinnerungs-Benachrichtigungen; prueft selbst,
        # ob die App gerade aktiviert ist.
        reminder_task = start_notification_task()
        yield
        if reminder_task:
            reminder_task.cancel()

    app = FastAPI(title="Fahrzeug Buchführung", lifespan=lifespan)
    app.add_middleware(AppAPIAuthMiddleware)
    _mount_routers(app)

    async def enabled_handler(enabled: bool, nc: AsyncNextcloudApp) -> str:
        await handle_talk_bot_enabled(enabled, nc)
        if enabled:
            await nc.ui.top_menu.register("ui", "Fahrzeug Buchführung", icon="img/icon.svg")
            # Ohne ".js": AppAPIs ExAppUiMiddleware haengt die Endung beim Einsetzen selbst an.
            await nc.ui.resources.set_script("top_menu", "ui", "js/app")
            await nc.log(LogLvl.INFO, "vehicle_tracker aktiviert.")
        else:
            await nc.ui.resources.delete_script("top_menu", "ui", "js/app")
            await nc.ui.top_menu.unregister("ui")
        return ""

    if __name__ == "__main__":
        run_app("main:app", log_level="info")
