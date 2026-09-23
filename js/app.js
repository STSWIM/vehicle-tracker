/*
 * Top-Menu-Einbettung fuer die ExApp (Nextcloud AppAPI "embedded"-Ansicht,
 * siehe app_api/templates/embedded.php: liefert nur ein leeres
 * <div id="content">, in das dieses Skript die Oberflaeche rendert).
 *
 * Anders als frontend/static/index.html (eigene, unabhaengige Seite unter
 * /exapps/vehicle_tracker/ui/) laeuft dieses Skript im Kontext der
 * Nextcloud-Seite selbst - relative fetch()-Aufrufe wuerden daher gegen
 * die Nextcloud-Domain statt gegen unsere ExApp gehen. Deshalb immer mit
 * API_BASE (absoluter ExApp-Pfad) arbeiten.
 */
(function () {
  const API_BASE = '/exapps/vehicle_tracker';

  const STYLE = `
    #vehicle-tracker-root { font-family: system-ui, sans-serif; }
    #vehicle-tracker-root header { padding: 0.75rem 0; }
    #vehicle-tracker-root #map { height: 320px; margin-top: 0.75rem; }
    #vehicle-tracker-root table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    #vehicle-tracker-root th, #vehicle-tracker-root td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #eee; }
    #vehicle-tracker-root #stats { padding: 0.75rem 0; display: flex; gap: 1.5rem; flex-wrap: wrap; }
    #vehicle-tracker-root .stat { background: #f5f5f5; border-radius: 8px; padding: 0.5rem 0.9rem; }
    #vehicle-tracker-root .stat b { display: block; font-size: 1.1rem; }
    #vehicle-tracker-root details.manual-entry { margin: 0 0 0.75rem; border: 1px solid #ddd; border-radius: 8px; }
    #vehicle-tracker-root details.manual-entry summary { padding: 0.5rem 0.9rem; cursor: pointer; font-weight: 600; }
    #vehicle-tracker-root details.manual-entry form { display: flex; flex-wrap: wrap; gap: 0.6rem; padding: 0 0.9rem 0.9rem; align-items: flex-end; }
    #vehicle-tracker-root details.manual-entry label { display: flex; flex-direction: column; font-size: 0.8rem; gap: 0.2rem; }
    #vehicle-tracker-root details.manual-entry input, #vehicle-tracker-root details.manual-entry select { padding: 0.3rem; }
    #vehicle-tracker-root details.manual-entry button { padding: 0.4rem 0.9rem; }
    #vehicle-tracker-root .form-status { flex-basis: 100%; font-size: 0.85rem; }
    #vehicle-tracker-root .form-status.error { color: #b3261e; }
    #vehicle-tracker-root .form-status.warning { color: #9a6700; }
    #vehicle-tracker-root .form-status.success { color: #1a7f37; }
  `;

  const MARKUP = `
    <div id="vehicle-tracker-root">
      <header>
        <label for="vt-vehicle-select">Fahrzeug: </label>
        <select id="vt-vehicle-select"></select>
      </header>

      <div id="stats"></div>

      <details class="manual-entry">
        <summary>Tankbeleg manuell erfassen</summary>
        <form id="vt-fuel-entry-form">
          <label>Datum <input type="date" name="datum" required></label>
          <label>Kilometerstand <input type="number" name="kilometerstand" min="0" required></label>
          <label>Kraftstoff
            <select name="kraftstoffart" required>
              <option value="LPG">LPG</option>
              <option value="Benzin">Benzin</option>
              <option value="Diesel">Diesel</option>
              <option value="Strom">Strom</option>
            </select>
          </label>
          <label>Menge (l) <input type="number" name="fuellmenge_liter" step="0.01" min="0" required></label>
          <label>Preis/l (€) <input type="number" name="preis_pro_liter" step="0.001" min="0" required></label>
          <label>Gesamtpreis (€) <input type="number" name="gesamtpreis" step="0.01" min="0" required></label>
          <label>Tankstelle <input type="text" name="tankstelle_name"></label>
          <label><input type="checkbox" name="nicht_voll"> nicht volltgetankt</label>
          <button type="submit">Speichern</button>
          <div class="form-status" id="vt-fuel-entry-status"></div>
        </form>
      </details>

      <details class="manual-entry">
        <summary>Sonstige Kosten manuell erfassen</summary>
        <form id="vt-other-cost-form">
          <label>Datum <input type="date" name="datum" required></label>
          <label>Kategorie
            <select name="kategorie" required>
              <option value="Versicherung">Versicherung</option>
              <option value="Steuer">Steuer</option>
              <option value="Finanzierung">Finanzierung</option>
              <option value="Reifen/Teile">Reifen/Teile</option>
              <option value="Service/TÜV">Service/TÜV</option>
              <option value="Waschen">Waschen</option>
              <option value="Einmalig">Einmalig</option>
              <option value="Einnahme">Einnahme</option>
              <option value="Sonstiges">Sonstiges</option>
            </select>
          </label>
          <label>Betrag (€) <input type="number" name="betrag" step="0.01" required></label>
          <label>Beschreibung <input type="text" name="beschreibung"></label>
          <label><input type="checkbox" name="jaehrlich_wiederkehrend"> jährlich wiederkehrend</label>
          <button type="submit">Speichern</button>
          <div class="form-status" id="vt-other-cost-status"></div>
        </form>
      </details>

      <div id="map"></div>
      <table id="vt-entries">
        <thead>
          <tr><th>Datum</th><th>km</th><th>Kraftstoff</th><th>Menge</th><th>Preis/l</th><th>Gesamt</th></tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  `;

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  function loadStylesheet(href) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    document.head.appendChild(link);
  }

  async function init() {
    const content = document.getElementById('content');
    if (!content) return;

    const styleTag = document.createElement('style');
    styleTag.textContent = STYLE;
    document.head.appendChild(styleTag);

    content.innerHTML = MARKUP;

    if (!window.L) {
      loadStylesheet('https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css');
      await loadScript('https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js');
    }

    const map = L.map('map').setView([51.1657, 10.4515], 6); // Deutschland-Mitte als Default
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap-Mitwirkende',
    }).addTo(map);

    let markers = [];
    let currentVehicleId = null;

    function showFormStatus(el, kind, message) {
      el.textContent = message;
      el.className = `form-status ${kind}`;
    }

    async function submitJson(form, url, extraFields, statusEl) {
      const data = Object.fromEntries(new FormData(form).entries());
      const payload = { ...extraFields };
      for (const [key, value] of Object.entries(data)) {
        const input = form.elements[key];
        if (input.type === 'checkbox') {
          payload[key] = input.checked;
        } else if (input.type === 'number') {
          payload[key] = value === '' ? null : Number(value);
        } else {
          payload[key] = value === '' ? null : value;
        }
      }
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        showFormStatus(statusEl, 'error', body.detail || `Fehler (${res.status})`);
        return null;
      }
      if (body.warnungen && body.warnungen.length) {
        showFormStatus(statusEl, 'warning', '⚠️ ' + body.warnungen.join(' / '));
      } else {
        showFormStatus(statusEl, 'success', '✅ Gespeichert.');
      }
      return body;
    }

    document.getElementById('vt-fuel-entry-form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      if (!currentVehicleId) return;
      const form = ev.target;
      const statusEl = document.getElementById('vt-fuel-entry-status');
      const saved = await submitJson(
        form,
        `${API_BASE}/api/fuel-entries`,
        { vehicle_id: Number(currentVehicleId) },
        statusEl
      );
      if (saved) {
        form.reset();
        loadVehicle(currentVehicleId);
      }
    });

    document.getElementById('vt-other-cost-form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      if (!currentVehicleId) return;
      const form = ev.target;
      const statusEl = document.getElementById('vt-other-cost-status');
      const saved = await submitJson(
        form,
        `${API_BASE}/api/other-costs`,
        { vehicle_id: Number(currentVehicleId) },
        statusEl
      );
      if (saved) {
        form.reset();
        loadVehicle(currentVehicleId);
      }
    });

    async function loadVehicles() {
      const res = await fetch(`${API_BASE}/api/vehicles`);
      const vehicles = await res.json();
      const select = document.getElementById('vt-vehicle-select');
      select.innerHTML = vehicles
        .map((v) => `<option value="${v.id}">${v.hersteller} ${v.modell} (${v.kennzeichen})</option>`)
        .join('');
      if (vehicles.length) loadVehicle(vehicles[0].id);
      select.onchange = () => loadVehicle(select.value);
    }

    async function loadVehicle(vehicleId) {
      currentVehicleId = vehicleId;
      const [entries, statsRes] = await Promise.all([
        fetch(`${API_BASE}/api/fuel-entries?vehicle_id=${vehicleId}`).then((r) => r.json()),
        fetch(`${API_BASE}/api/vehicles/${vehicleId}/stats`).then((r) => r.json()),
      ]);
      renderStats(statsRes);
      renderTable(entries);
      renderMarkers(entries);
    }

    function renderStats(s) {
      const el = document.getElementById('stats');
      const fmt = (v, unit) => (v === null || v === undefined ? '–' : `${v}${unit}`);
      el.innerHTML = `
        <div class="stat"><b>${fmt(s.ø_verbrauch_l_100km, ' l/100km')}</b>Ø Verbrauch</div>
        <div class="stat"><b>${fmt(s.kosten_pro_km, ' €/km')}</b>Kosten/km</div>
        <div class="stat"><b>${fmt(s.kosten_pro_monat, ' €/Monat')}</b>Kosten/Monat</div>
        <div class="stat"><b>${fmt(s.gesamtkosten, ' €')}</b>Gesamtkosten</div>
      `;
    }

    function renderTable(entries) {
      const tbody = document.querySelector('#vt-entries tbody');
      tbody.innerHTML = entries
        .map(
          (e) => `<tr>
            <td>${e.datum}</td><td>${e.kilometerstand}</td><td>${e.kraftstoffart}</td>
            <td>${e.fuellmenge_liter} l</td><td>${e.preis_pro_liter} €</td><td>${e.gesamtpreis} €</td>
          </tr>`
        )
        .join('');
    }

    function renderMarkers(entries) {
      markers.forEach((m) => map.removeLayer(m));
      markers = [];
      const withLocation = entries.filter((e) => e.lat && e.lon);
      withLocation.forEach((e) => {
        const marker = L.marker([e.lat, e.lon])
          .addTo(map)
          .bindPopup(`${e.tankstelle_name ?? 'Tankstelle'}<br>${e.datum} – ${e.preis_pro_liter} €/l`);
        markers.push(marker);
      });
      if (withLocation.length) {
        map.fitBounds(withLocation.map((e) => [e.lat, e.lon]), { padding: [30, 30] });
      }
    }

    loadVehicles();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
