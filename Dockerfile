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

COPY . .

# AppAPI setzt APP_HOST/APP_PORT zur Laufzeit; 0.0.0.0:23000 ist der
# ueblich verwendete Default-Port fuer ExApps in den offiziellen Beispielen.
ENV APP_HOST=0.0.0.0
ENV APP_PORT=23000
EXPOSE 23000

# Persistenter Datenordner, den AppAPI unter /nc_app_vehicle_tracker_data mountet
VOLUME ["/nc_app_vehicle_tracker_data"]

CMD ["python", "main.py"]
