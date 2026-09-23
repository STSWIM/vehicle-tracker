#!/usr/bin/env bash
# Registriert die ExApp waehrend der Entwicklung ueber "manual_install"
# (die App laeuft dabei lokal per `python main.py`, NICHT im Docker-Deploy-
# Modus). Muss auf dem Server ausgefuehrt werden, auf dem Nextcloud selbst
# laeuft (occ-Befehle).
#
# Referenz: https://docs.nextcloud.com/server/stable/developer_manual/exapp_development/tech_details/Deployment.html
# Vor der Nutzung pruefen, ob sich Befehle/Parameter in einer neueren
# AppAPI-Version geaendert haben.

set -euo pipefail

NC_PATH="${NC_PATH:-/var/www/nextcloud}"   # ggf. anpassen
APP_HOST="${APP_HOST:-localhost}"
APP_PORT="${APP_PORT:-23000}"

echo "1) manual-install Deploy-Daemon registrieren (einmalig)"
php "$NC_PATH/occ" app_api:daemon:register \
  manual_install "Manual Install" manual-install http

echo "2) ExApp beim Daemon registrieren"
php "$NC_PATH/occ" app_api:app:register \
  vehicle_tracker manual_install \
  --info-xml "$(dirname "$0")/../appinfo/info.xml" \
  --force-scopes

echo "Fertig. Die App laeuft lokal unter http://${APP_HOST}:${APP_PORT}"
echo "und sollte jetzt in Nextcloud unter 'Verwaltung > Apps' als aktiviert erscheinen."
