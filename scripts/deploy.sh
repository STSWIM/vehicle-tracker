#!/usr/bin/env bash
# Aktualisiert die ExApp auf dem Server (im entpackten Repo ausfuehren).
#
#   scripts/deploy.sh          Schnell (Sekunden): kopiert den App-Code in den
#                              laufenden Container und startet ihn neu. Kein
#                              Build, keine Neu-Registrierung, der Talk-Bot
#                              bleibt in seinen Unterhaltungen aktiv.
#   scripts/deploy.sh --full   Image bauen, pushen, App neu registrieren. Nur
#                              noetig, wenn sich Dockerfile, requirements*.txt
#                              oder appinfo/info.xml geaendert haben - das
#                              Skript merkt das und verlangt dann --full.
#
# Der schnelle Weg aendert nur den laufenden Container; ein spaeteres --full
# baut das Image aus demselben Stand, es geht also nichts verloren.
set -euo pipefail
cd "$(dirname "$0")/.."

APP=vehicle_tracker
IMAGE=ghcr.io/stswim/vehicle-tracker:0.1.0
CONTAINER=nc_app_$APP
OCC=(sudo -u www-data php /var/www/cloud/occ)
STATE="$HOME/.vehicle-tracker-deploy"
TALK_DEBUG_PAYLOAD=${TALK_DEBUG_PAYLOAD:-false}

fingerprint=$(cat Dockerfile requirements*.txt appinfo/info.xml | sha256sum | cut -d' ' -f1)
step() { echo; echo "==> $1  ($(date +%T))"; }

if [ "${1:-}" != "--full" ]; then
    if [ -f "$STATE" ] && [ "$(cat "$STATE")" != "$fingerprint" ]; then
        echo "Dockerfile, Abhaengigkeiten oder info.xml haben sich geaendert - bitte: scripts/deploy.sh --full"
        exit 1
    fi
    if ! sudo docker inspect "$CONTAINER" >/dev/null 2>&1; then
        echo "Container $CONTAINER laeuft nicht - bitte: scripts/deploy.sh --full"
        exit 1
    fi
    step "Code in den laufenden Container kopieren"
    for pfad in app js img frontend appinfo main.py; do
        sudo docker cp "$pfad" "$CONTAINER:/app/"
    done
    step "Container neu starten"
    sudo docker restart "$CONTAINER" >/dev/null
    [ -f "$STATE" ] || echo "$fingerprint" > "$STATE"
    step "Fertig - im Browser mit Strg+F5 neu laden"
    exit 0
fi

step "Image bauen"
# --cache-from + Inline-Cache: auch wenn Dockers lokaler Zwischenspeicher weg
# ist, werden unveraenderte Schichten (v.a. die ~1,4 GB OCR-Bibliotheken) aus
# dem zuletzt gepushten Image wiederverwendet statt neu gebaut und gepackt.
sudo docker pull -q "$IMAGE" >/dev/null 2>&1 || true
sudo docker build --cache-from "$IMAGE" --build-arg BUILDKIT_INLINE_CACHE=1 -t "$IMAGE" .

step "Image hochladen (bei 'unauthorized' vorher: sudo docker login ghcr.io -u STSWIM)"
sudo docker push "$IMAGE"

step "App neu registrieren"
sudo cp appinfo/info.xml /tmp/vehicle-tracker-info.xml
"${OCC[@]}" app_api:app:unregister "$APP" || true
"${OCC[@]}" app_api:app:register "$APP" harp_local --info-xml /tmp/vehicle-tracker-info.xml \
    --env STANDALONE_MODE=false --env APP_LOCALE=de --env "TALK_DEBUG_PAYLOAD=$TALK_DEBUG_PAYLOAD" --wait-finish

echo "$fingerprint" > "$STATE"
step "Fertig - Talk-Bot wird in bekannten Unterhaltungen automatisch wieder aktiviert; im Browser Strg+F5"
