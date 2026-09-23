FROM python:3.11-slim

# Systemabhaengigkeiten fuer PaddleOCR (CPU) und Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-core.txt requirements-ocr.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# HaRP-Unterstuetzung (frpc-Client + start.sh-Wrapper), siehe
# https://github.com/nextcloud/HaRP - kompatibel mit dem aelteren
# Docker-Socket-Proxy-Deployment: nc_py_api.ex_app.run_app() (main.py)
# erkennt HP_SHARED_KEY automatisch und bindet dann an den von start.sh
# erwarteten Unix-Socket statt an APP_HOST/APP_PORT.
RUN set -ex; \
    ARCH=$(uname -m); \
    if [ "$ARCH" = "aarch64" ]; then \
      FRP_URL="https://raw.githubusercontent.com/nextcloud/HaRP/main/exapps_dev/frp_0.61.1_linux_arm64.tar.gz"; \
    else \
      FRP_URL="https://raw.githubusercontent.com/nextcloud/HaRP/main/exapps_dev/frp_0.61.1_linux_amd64.tar.gz"; \
    fi; \
    curl -fL "$FRP_URL" -o /tmp/frp.tar.gz; \
    tar -C /tmp -xzf /tmp/frp.tar.gz; \
    mv /tmp/frp_0.61.1_linux_*/frpc /usr/local/bin/frpc; \
    chmod +x /usr/local/bin/frpc; \
    rm -rf /tmp/frp_0.61.1_linux_* /tmp/frp.tar.gz; \
    curl -fL https://raw.githubusercontent.com/nextcloud/HaRP/main/exapps_dev/start.sh -o /start.sh; \
    chmod +x /start.sh

COPY . .

# AppAPI setzt APP_HOST/APP_PORT zur Laufzeit; 0.0.0.0:23000 ist der
# ueblich verwendete Default-Port fuer ExApps in den offiziellen Beispielen.
ENV APP_HOST=0.0.0.0
ENV APP_PORT=23000
EXPOSE 23000

# Persistenter Datenordner, den AppAPI unter /nc_app_vehicle_tracker_data mountet
VOLUME ["/nc_app_vehicle_tracker_data"]

ENTRYPOINT ["/start.sh"]
CMD ["python", "main.py"]
