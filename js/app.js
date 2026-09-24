/*
 * Oberflaeche der Fahrzeug-Buchfuehrung. Rendert in ein vorhandenes
 * <div id="content"> - das liefert sowohl die AppAPI-"embedded"-Ansicht
 * (Top-Menue, app_api/templates/embedded.php) als auch frontend/static/index.html.
 *
 * Der API-Pfad wird aus der URL dieses Skripts abgeleitet, weil es je nach
 * Einbindung unter verschiedenen Praefixen liegt:
 *   /index.php/apps/app_api/proxy/vehicle_tracker/js/app.js  (Top-Menue)
 *   /exapps/vehicle_tracker/js/app.js                        (/ui/ ueber HaRP)
 *   /js/app.js                                               (Standalone-Dev-Modus)
 */
(function () {
  function findScriptUrl() {
    if (document.currentScript && document.currentScript.src) {
      return document.currentScript.src;
    }
    // Nextcloud laedt Skripte teils als ES-Module, dort ist currentScript null.
    const match = Array.from(document.scripts)
      .map((s) => s.src)
      .find((src) => /\/js\/app\.js(\?|$)/.test(src));
    return match || window.location.href;
  }

  const BASE = new URL('..', findScriptUrl()).pathname.replace(/\/$/, '');

  const esc = (value) =>
    String(value ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));

  const STYLE = `
    #vehicle-tracker-root {
      font-family: var(--font-face, system-ui, sans-serif);
      color: var(--color-main-text, #222);
      background: var(--color-main-background, #fff);
      border-radius: var(--border-radius-large, 10px);
      margin: 0.75rem;
      padding: 0.75rem 1.25rem 1.25rem;
    }
    #vehicle-tracker-root header { padding: 0.5rem 0; display: flex; gap: 0.5rem; align-items: center; }
    #vehicle-tracker-root #vt-map { height: 320px; margin-top: 0.75rem; border-radius: 8px; }
    #vehicle-tracker-root table { width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-top: 0.75rem; }
    #vehicle-tracker-root th, #vehicle-tracker-root td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--color-border, #eee); }
    #vehicle-tracker-root #vt-stats { padding: 0.75rem 0; display: flex; gap: 1.5rem; flex-wrap: wrap; }
    #vehicle-tracker-root .stat { background: var(--color-background-dark, #f5f5f5); border-radius: 8px; padding: 0.5rem 0.9rem; }
    #vehicle-tracker-root .stat b { display: block; font-size: 1.1rem; }
    #vehicle-tracker-root .hint { padding: 0.75rem 0; opacity: 0.8; }
    #vehicle-tracker-root details.manual-entry { margin: 0 0 0.75rem; border: 1px solid var(--color-border, #ddd); border-radius: 8px; }
    #vehicle-tracker-root details.manual-entry summary { padding: 0.5rem 0.9rem; cursor: pointer; font-weight: 600; }
    #vehicle-tracker-root details.manual-entry form { display: flex; flex-wrap: wrap; gap: 0.6rem; padding: 0 0.9rem 0.9rem; align-items: flex-end; }
    #vehicle-tracker-root details.manual-entry label { display: flex; flex-direction: column; font-size: 0.8rem; gap: 0.2rem; }
    #vehicle-tracker-root .form-status { flex-basis: 100%; font-size: 0.85rem; }
    #vehicle-tracker-root .form-status.error { color: var(--color-error, #b3261e); }
    #vehicle-tracker-root .form-status.warning { color: var(--color-warning, #9a6700); }
    #vehicle-tracker-root .form-status.success { color: var(--color-success, #1a7f37); }
  `;

  const MARKUP = `
    <div id="vehicle-tracker-root">
      <header>
        <label for="vt-vehicle-select">Fahrzeug:</label>
        <select id="vt-vehicle-select"></select>
      </header>

      <div id="vt-stats"></div>

      <details class="manual-entry" id="vt-vehicle-details">
        <summary>Fahrzeug anlegen</summary>
        <form id="vt-vehicle-form">
          <label>Kennzeichen <input type="text" name="kennzeichen" required></label>
          <label>Hersteller <input type="text" name="hersteller" required></label>
          <label>Modell <input type="text" name="modell" required></label>
          <label>Variante <input type="text" name="variante"></label>
          <label>Tank LPG (l) <input type="number" name="tankvolumen_lpg_l" step="0.1" min="0"></label>
          <label>Tank Benzin (l) <input type="number" name="tankvolumen_benzin_l" step="0.1" min="0"></label>
          <label>Kaufdatum <input type="date" name="kaufdatum"></label>
          <label>Talk-Bot-Codewort <input type="text" name="bot_codewort" placeholder="z.B. previa"></label>
          <button type="submit">Anlegen</button>
          <div class="form-status" id="vt-vehicle-status"></div>
        </form>
      </details>

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
          <label><input type="checkbox" name="nicht_voll"> nicht vollgetankt</label>
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

      <div id="vt-map"></div>
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

    // Leaflet wird mitgeliefert statt vom CDN geladen: die CSP der
    // Nextcloud-Seite erlaubt keine Stylesheets/Skripte von fremden Hosts.
    // Scheitert die Karte trotzdem, bleibt der Rest nutzbar.
    let map = null;
    try {
      if (!window.L) {
        loadStylesheet(`${BASE}/js/vendor/leaflet/leaflet.css`);
        await loadScript(`${BASE}/js/vendor/leaflet/leaflet.js`);
      }
      map = L.map('vt-map').setView([51.1657, 10.4515], 6); // Deutschland-Mitte als Default
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap-Mitwirkende',
        // Nextcloud/nginx senden "Referrer-Policy: no-referrer", die
        // OSM-Kachelserver verlangen aber einen Referer.
        referrerPolicy: 'strict-origin-when-cross-origin',
      }).addTo(map);
    } catch (e) {
      document.getElementById('vt-map').remove();
      map = null;
    }

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
        const detail = Array.isArray(body.detail)
          ? body.detail.map((d) => d.msg).join(' / ')
          : body.detail;
        showFormStatus(statusEl, 'error', detail || `Fehler (${res.status})`);
        return null;
      }
      if (body.warnungen && body.warnungen.length) {
        showFormStatus(statusEl, 'warning', '⚠️ ' + body.warnungen.join(' / '));
      } else {
        showFormStatus(statusEl, 'success', '✅ Gespeichert.');
      }
      return body;
    }

    document.getElementById('vt-vehicle-form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const form = ev.target;
      const saved = await submitJson(
        form, `${BASE}/api/vehicles`, {}, document.getElementById('vt-vehicle-status')
      );
      if (saved) {
        form.reset();
        loadVehicles(saved.id);
      }
    });

    document.getElementById('vt-fuel-entry-form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      if (!currentVehicleId) return;
      const form = ev.target;
      const saved = await submitJson(
        form,
        `${BASE}/api/fuel-entries`,
        { vehicle_id: Number(currentVehicleId) },
        document.getElementById('vt-fuel-entry-status')
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
      const saved = await submitJson(
        form,
        `${BASE}/api/other-costs`,
        { vehicle_id: Number(currentVehicleId) },
        document.getElementById('vt-other-cost-status')
      );
      if (saved) {
        form.reset();
        loadVehicle(currentVehicleId);
      }
    });

    async function loadVehicles(selectId) {
      const res = await fetch(`${BASE}/api/vehicles`);
      const vehicles = await res.json();
      const select = document.getElementById('vt-vehicle-select');
      select.innerHTML = vehicles
        .map((v) => `<option value="${v.id}">${esc(v.hersteller)} ${esc(v.modell)} (${esc(v.kennzeichen)})</option>`)
        .join('');
      select.onchange = () => loadVehicle(select.value);

      if (!vehicles.length) {
        currentVehicleId = null;
        document.getElementById('vt-stats').innerHTML =
          '<div class="hint">Noch kein Fahrzeug angelegt – bitte zuerst unter „Fahrzeug anlegen" eintragen.</div>';
        document.getElementById('vt-vehicle-details').open = true;
        renderTable([]);
        return;
      }
      const target = vehicles.some((v) => v.id === selectId) ? selectId : vehicles[0].id;
      select.value = String(target);
      loadVehicle(target);
    }

    async function loadVehicle(vehicleId) {
      currentVehicleId = vehicleId;
      const [entries, statsRes] = await Promise.all([
        fetch(`${BASE}/api/fuel-entries?vehicle_id=${vehicleId}`).then((r) => r.json()),
        fetch(`${BASE}/api/vehicles/${vehicleId}/stats`).then((r) => r.json()),
      ]);
      renderStats(statsRes);
      renderTable(entries);
      renderMarkers(entries);
    }

    function renderStats(s) {
      const fmt = (v, unit) => (v === null || v === undefined ? '–' : `${v}${unit}`);
      document.getElementById('vt-stats').innerHTML = `
        <div class="stat"><b>${fmt(s.ø_verbrauch_l_100km, ' l/100km')}</b>Ø Verbrauch</div>
        <div class="stat"><b>${fmt(s.kosten_pro_km, ' €/km')}</b>Kosten/km</div>
        <div class="stat"><b>${fmt(s.kosten_pro_monat, ' €/Monat')}</b>Kosten/Monat</div>
        <div class="stat"><b>${fmt(s.gesamtkosten, ' €')}</b>Gesamtkosten</div>
      `;
    }

    function renderTable(entries) {
      document.querySelector('#vt-entries tbody').innerHTML = entries
        .map(
          (e) => `<tr>
            <td>${esc(e.datum)}</td><td>${esc(e.kilometerstand)}</td><td>${esc(e.kraftstoffart)}</td>
            <td>${esc(e.fuellmenge_liter)} l</td><td>${esc(e.preis_pro_liter)} €</td><td>${esc(e.gesamtpreis)} €</td>
          </tr>`
        )
        .join('');
    }

    function renderMarkers(entries) {
      if (!map) return;
      markers.forEach((m) => map.removeLayer(m));
      markers = [];
      const withLocation = entries.filter((e) => e.lat && e.lon);
      withLocation.forEach((e) => {
        const marker = L.marker([e.lat, e.lon])
          .addTo(map)
          .bindPopup(`${esc(e.tankstelle_name ?? 'Tankstelle')}<br>${esc(e.datum)} – ${esc(e.preis_pro_liter)} €/l`);
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
