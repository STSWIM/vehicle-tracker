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
  const fmtNum = (v, digits = 0) =>
    v === null || v === undefined
      ? '–'
      : Number(v).toLocaleString('de-DE', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const fmtEur = (v) => (v === null || v === undefined ? '–' : `${fmtNum(v, 2)} €`);
  const fmtDate = (iso) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString('de-DE') : '–');

  const STYLE = `
    #vehicle-tracker-root {
      font-family: var(--font-face, system-ui, sans-serif);
      color: var(--color-main-text, #222);
      background: var(--color-main-background, #fff);
      border-radius: var(--border-radius-large, 10px);
      margin: 0.75rem;
      padding: 0.75rem 1.25rem 1.25rem;
    }
    #vehicle-tracker-root header { padding: 0.5rem 0; display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
    #vehicle-tracker-root h3 { margin: 1.25rem 0 0.25rem; font-size: 1rem; }
    #vehicle-tracker-root .vt-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(320px, 40%); gap: 1.5rem; align-items: start; }
    #vehicle-tracker-root .vt-side { position: sticky; top: 0.75rem; }
    #vehicle-tracker-root #vt-map { height: 70vh; min-height: 320px; border-radius: 8px; }
    @media (max-width: 1000px) {
      #vehicle-tracker-root .vt-layout { grid-template-columns: minmax(0, 1fr); }
      #vehicle-tracker-root .vt-side { position: static; }
      #vehicle-tracker-root #vt-map { height: 320px; }
    }
    #vehicle-tracker-root table { width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-top: 0.75rem; }
    #vehicle-tracker-root th, #vehicle-tracker-root td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--color-border, #eee); }
    #vehicle-tracker-root td.num, #vehicle-tracker-root th.num { text-align: right; }
    #vehicle-tracker-root .auswertung-controls { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; padding: 0.5rem 0; }
    #vehicle-tracker-root .auswertung-controls label { display: flex; gap: 0.35rem; align-items: center; }
    #vehicle-tracker-root .auswertung-controls input[type="date"] { min-width: 11em; }
    #vehicle-tracker-root #vt-stats { padding: 0.5rem 0; display: flex; gap: 0.75rem; flex-wrap: wrap; }
    #vehicle-tracker-root .stat { background: var(--color-background-dark, #f5f5f5); border-radius: 8px; padding: 0.5rem 0.9rem; min-width: 8.5rem; }
    #vehicle-tracker-root .stat b { display: block; font-size: 1.1rem; }
    #vehicle-tracker-root .stat.muted { opacity: 0.55; }
    #vehicle-tracker-root .kategorien { font-size: 0.85rem; opacity: 0.8; }
    /* Tankluecken-Hinweise (Issue #12) */
    #vehicle-tracker-root .vt-hinweise { font-size: 0.85rem; color: var(--color-warning, #9a6700); padding: 0.35rem 0 0; }
    #vehicle-tracker-root .vt-hinweise div + div { margin-top: 0.2rem; }
    #vehicle-tracker-root .hint { padding: 0.75rem 0; opacity: 0.8; }
    #vehicle-tracker-root details.manual-entry { margin: 0 0 0.75rem; border: 1px solid var(--color-border, #ddd); border-radius: 8px; }
    #vehicle-tracker-root details.manual-entry summary { padding: 0.5rem 0.9rem; cursor: pointer; font-weight: 600; }
    #vehicle-tracker-root details.manual-entry .section-body { padding: 0 0.9rem 0.9rem; }
    #vehicle-tracker-root details.manual-entry form { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: flex-end; }
    #vehicle-tracker-root details.manual-entry label { display: flex; flex-direction: column; font-size: 0.8rem; gap: 0.2rem; }
    #vehicle-tracker-root details.manual-entry input[type="date"] { min-width: 11em; }
    #vehicle-tracker-root .form-status { flex-basis: 100%; font-size: 0.85rem; }
    #vehicle-tracker-root .form-hint { flex-basis: 100%; font-size: 0.8rem; opacity: 0.7; }
    #vehicle-tracker-root input.vt-computed { font-style: italic; }
    #vehicle-tracker-root .form-status.error { color: var(--color-error, #b3261e); }
    #vehicle-tracker-root .form-status.warning { color: var(--color-warning, #9a6700); }
    #vehicle-tracker-root .form-status.success { color: var(--color-success, #1a7f37); }
    #vehicle-tracker-root button.link { background: none; border: none; padding: 0 0.3rem; cursor: pointer; min-height: 0; }

    #vt-vehicle-dialog {
      border: none; border-radius: var(--border-radius-large, 10px); padding: 1.25rem 1.5rem;
      width: min(760px, calc(100vw - 2rem)); max-height: calc(100vh - 2rem);
      background: var(--color-main-background, #fff); color: var(--color-main-text, #222);
      font-family: var(--font-face, system-ui, sans-serif);
    }
    /* Nextclouds eigenes CSS ueberschreibt die Browser-Vorgaben fuer <dialog>:
       ohne diese Regeln steht der geschlossene Dialog sichtbar unten links auf
       der Seite und der geoeffnete klebt am Rand statt mittig. */
    #vt-vehicle-dialog:not([open]) { display: none !important; }
    #vt-vehicle-dialog[open] {
      display: block; position: fixed; inset: 0; margin: auto;
      height: fit-content; overflow: auto; z-index: 10000; box-sizing: border-box;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }
    #vt-vehicle-dialog::backdrop { background: rgba(0, 0, 0, 0.45); }
    #vt-vehicle-dialog h2 { margin: 0 0 1rem; font-size: 1.15rem; }
    #vt-vehicle-dialog h4 { margin: 1.25rem 0 0.5rem; font-size: 0.95rem; }
    #vt-vehicle-dialog .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.6rem 0.9rem; }
    #vt-vehicle-dialog label { display: flex; flex-direction: column; font-size: 0.8rem; gap: 0.2rem; }
    #vt-vehicle-dialog label.check { flex-direction: row; align-items: center; gap: 0.4rem; font-size: 0.9rem; }
    #vt-vehicle-dialog input[type="date"] { min-width: 11em; }
    #vt-vehicle-dialog .actions { display: flex; gap: 0.6rem; justify-content: flex-end; margin-top: 1.25rem; }
    #vt-vehicle-dialog .form-status { font-size: 0.85rem; margin-top: 0.5rem; }
    #vt-vehicle-dialog .form-status.error { color: var(--color-error, #b3261e); }
    #vt-vehicle-dialog .muted { font-size: 0.85rem; opacity: 0.75; }
    #vt-vehicle-dialog .chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.4rem 0; }
    #vt-vehicle-dialog .chip { background: var(--color-background-dark, #eee); border-radius: 999px; padding: 0.2rem 0.4rem 0.2rem 0.7rem; display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.85rem; }
    #vt-vehicle-dialog .chip button { background: none; border: none; min-height: 0; padding: 0 0.3rem; cursor: pointer; }
    #vt-vehicle-dialog .suggestions { display: flex; flex-direction: column; border: 1px solid var(--color-border, #ddd); border-radius: 8px; margin-top: 0.3rem; max-width: 420px; }
    #vt-vehicle-dialog .suggestions:empty { display: none; }
    #vt-vehicle-dialog .suggestions button { text-align: left; background: none; border: none; border-radius: 0; padding: 0.45rem 0.7rem; cursor: pointer; }
    #vt-vehicle-dialog .suggestions button:hover { background: var(--color-background-hover, #f2f2f2); }
  `;

  const MARKUP = `
    <div id="vehicle-tracker-root">
      <header>
        <label for="vt-vehicle-select">Fahrzeug:</label>
        <select id="vt-vehicle-select"></select>
        <button type="button" id="vt-new-vehicle">Anlegen</button>
        <button type="button" id="vt-edit-vehicle" hidden>Bearbeiten</button>
      </header>

      <div class="vt-layout">
      <div class="vt-main">
      <h3>Kostenauswertung</h3>
      <div class="auswertung-controls">
        <label><input type="radio" name="vt-zeitraum" value="gesamt" checked> Gesamter Zeitraum</label>
        <label><input type="radio" name="vt-zeitraum" value="auswahl"> Zeitraum:</label>
        <input type="date" id="vt-von" disabled> –
        <input type="date" id="vt-bis" disabled>
        <label><input type="checkbox" id="vt-mit-anschaffung" checked> Anschaffungskosten einbeziehen</label>
      </div>
      <div id="vt-stats"></div>
      <div class="kategorien" id="vt-kategorien"></div>
      <div class="vt-hinweise" id="vt-hinweise" hidden></div>

      <h3>Erfassen</h3>
      <details class="manual-entry">
        <summary>Tankbeleg</summary>
        <div class="section-body">
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
            <label>Belegfoto <input type="file" id="vt-fuel-beleg-foto" accept="image/jpeg,image/png,image/webp,image/heic"></label>
            <label>Tachofoto <input type="file" id="vt-fuel-tacho-foto" accept="image/jpeg,image/png,image/webp,image/heic"></label>
            <button type="submit">Speichern</button>
            <div class="form-hint">Zwei von Menge, Preis/l und Gesamtpreis eingeben – der dritte Wert wird berechnet (kursiv).</div>
            <div class="form-status" id="vt-fuel-entry-status"></div>
          </form>
        </div>
      </details>

      <details class="manual-entry">
        <summary>Sonstige Kosten</summary>
        <div class="section-body">
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
                <option value="Einmalig">Einmalig (zählt zur Anschaffung)</option>
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
        </div>
      </details>

      <details class="manual-entry">
        <summary>Wartungslogbuch</summary>
        <div class="section-body">
          <form id="vt-logbook-form">
            <label>Datum <input type="date" name="datum" required></label>
            <label>km-Stand <input type="number" name="kilometerstand" min="0"></label>
            <label>Eintrag <input type="text" name="eintrag" required maxlength="300" placeholder="z.B. Ölwechsel + Filter"></label>
            <label>Notiz <input type="text" name="notiz"></label>
            <button type="submit">Eintragen</button>
            <div class="form-status" id="vt-logbook-status"></div>
          </form>
          <table id="vt-logbook">
            <thead><tr><th>Datum</th><th class="num">km</th><th>Eintrag</th><th>Notiz</th><th></th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
      </details>

      <details class="manual-entry">
        <summary>Fahrtenbuch</summary>
        <div class="section-body">
          <form id="vt-trip-form">
            <label>Datum <input type="date" name="datum" required></label>
            <label>Start <input type="text" name="start" required></label>
            <label>Ziel <input type="text" name="ziel" required></label>
            <label>km-Stand Start <input type="number" name="km_start" min="0" required></label>
            <label>km-Stand Ende <input type="number" name="km_ende" min="0" required></label>
            <label>Zweck
              <select name="zweck">
                <option value="Privat">Privat</option>
                <option value="Dienstlich">Dienstlich</option>
                <option value="Arbeitsweg">Arbeitsweg</option>
              </select>
            </label>
            <label>Notiz <input type="text" name="notiz"></label>
            <button type="submit">Eintragen</button>
            <div class="form-hint">Hinweis: Da Einträge nachträglich änderbar sind, ersetzt dieses Fahrtenbuch kein vom Finanzamt anerkanntes.</div>
            <div class="form-status" id="vt-trip-status"></div>
          </form>
          <div class="kategorien" id="vt-trip-summen"></div>
          <table id="vt-trips">
            <thead><tr><th>Datum</th><th>Start</th><th>Ziel</th><th class="num">km Start</th><th class="num">km Ende</th><th class="num">Strecke</th><th>Zweck</th><th></th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
      </details>

      <h3>Tankbuch</h3>
      <table id="vt-entries">
        <thead>
          <tr><th>Datum</th><th class="num">km</th><th>Kraftstoff</th><th class="num">Menge</th><th class="num">Preis/l</th><th class="num">Gesamt</th><th></th></tr>
        </thead>
        <tbody></tbody>
      </table>
      </div>

      <aside class="vt-side">
        <h3>Tankstellen</h3>
        <div id="vt-map"></div>
      </aside>
      </div>

      <dialog id="vt-vehicle-dialog">
        <form id="vt-vehicle-form">
          <h2 id="vt-vehicle-dialog-title">Fahrzeug anlegen</h2>
          <div class="grid">
            <label>Kennzeichen <input type="text" name="kennzeichen" required></label>
            <label>Hersteller <input type="text" name="hersteller" required></label>
            <label>Modell <input type="text" name="modell" required></label>
            <label>Variante <input type="text" name="variante"></label>
            <label>Tank LPG (l) <input type="number" name="tankvolumen_lpg_l" step="0.1" min="0"></label>
            <label>Tank Benzin (l) <input type="number" name="tankvolumen_benzin_l" step="0.1" min="0"></label>
            <label>Kaufdatum <input type="date" name="kaufdatum"></label>
            <label>Anschaffungspreis (€) <input type="number" name="kaufpreis" step="0.01" min="0"></label>
            <label>km-Stand bei Kauf <input type="number" name="kaufkilometerstand" min="0"></label>
            <label>Talk-Bot-Codewort <input type="text" name="bot_codewort" placeholder="z.B. previa"></label>
          </div>
          <label class="check" style="margin-top: 0.75rem;">
            <input type="checkbox" name="bei_kauf_vollgetankt">
            Bei Kauf vollgetankt (Kauf-km-Stand zählt als erste Volltankung für den Verbrauch)
          </label>

          <h4>Zugriff</h4>
          <div id="vt-share-section"></div>

          <div class="form-status" id="vt-vehicle-status"></div>
          <div class="actions">
            <button type="button" id="vt-vehicle-cancel">Abbrechen</button>
            <button type="submit" id="vt-vehicle-submit" class="primary">Anlegen</button>
          </div>
        </form>
      </dialog>
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
    const $ = (id) => document.getElementById(id);

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
      // Das Nextcloud-Layout aendert die Containergroesse noch nach der
      // Initialisierung - ohne Neuvermessung bleibt die Karte teilweise grau.
      new ResizeObserver(() => map.invalidateSize()).observe($('vt-map'));
    } catch (e) {
      document.querySelector('#vehicle-tracker-root .vt-side').remove();
      document.querySelector('#vehicle-tracker-root .vt-layout').style.gridTemplateColumns = 'minmax(0, 1fr)';
      map = null;
    }

    let me = { uid: '', standalone: false };
    let vehicles = [];
    let currentVehicleId = null;
    let editingVehicleId = null;
    let markers = [];

    function showFormStatus(el, kind, message) {
      el.textContent = message;
      el.className = `form-status ${kind}`;
    }

    function formPayload(form, extraFields) {
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
      return payload;
    }

    async function submitJson(form, url, extraFields, statusEl, method = 'POST') {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formPayload(form, extraFields)),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = Array.isArray(body.detail)
          ? body.detail.map((d) => d.msg.replace(/^Value error, /, '')).join(' / ')
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

    async function deleteEntry(url) {
      if (!window.confirm('Eintrag wirklich löschen?')) return false;
      const res = await fetch(url, { method: 'DELETE' });
      return res.ok;
    }

    function onSubmit(formId, handler) {
      $(formId).addEventListener('submit', async (ev) => {
        ev.preventDefault();
        await handler(ev.target);
      });
    }

    // --- Fahrzeug anlegen / bearbeiten ---------------------------------------

    // Freigaben-Entwurf im Dialog; gespeichert wird erst mit dem Fahrzeug.
    let shareDraft = [];
    let canManageShares = false;

    function renderShareSection(owner) {
      const section = $('vt-share-section');
      const chips = shareDraft
        .map((s, i) => `<span class="chip">${s.share_type === 'group' ? '👥' : '👤'} ${esc(s.label || s.share_with)}${
          canManageShares ? ` <button type="button" data-remove-share="${i}" title="Entfernen">×</button>` : ''
        }</span>`)
        .join('');
      const ownerText = owner ? `Besitzer: ${esc(owner)}` : '';
      if (!canManageShares) {
        section.innerHTML = `<div class="muted">${ownerText} – nur der Besitzer kann Freigaben ändern.</div>
          <div class="chips">${chips || '<span class="muted">Keine Freigaben.</span>'}</div>`;
        return;
      }
      section.innerHTML = `
        <div class="muted">${ownerText}${ownerText ? ' · ' : ''}Freigegebene Nutzer und Gruppen können alles sehen und erfassen.</div>
        <div class="chips">${chips || '<span class="muted">Noch nicht freigegeben.</span>'}</div>
        <input type="text" id="vt-share-search" placeholder="Nutzer oder Gruppe suchen …" autocomplete="off" style="max-width: 420px; width: 100%;">
        <div class="suggestions" id="vt-share-suggestions"></div>`;
    }

    // Nextclouds eigene Nutzer-/Gruppensuche (wie beim Teilen von Dateien);
    // laeuft im Browser mit der Nextcloud-Sitzung. Im Standalone-Modus gibt
    // es sie nicht - dann bleibt die manuelle Eingabe per Enter.
    const OC_ROOT = window.OC && typeof window.OC.webroot === 'string' ? window.OC.webroot : '';
    async function searchSharees(term) {
      const params = new URLSearchParams({ search: term, itemType: 'vehicle_tracker', itemId: '0', limit: '8' });
      params.append('shareTypes[]', '0');
      params.append('shareTypes[]', '1');
      try {
        const res = await fetch(`${OC_ROOT}/ocs/v2.php/core/autocomplete/get?${params}`, {
          headers: { 'OCS-APIRequest': 'true', Accept: 'application/json' },
        });
        if (!res.ok) return [];
        const data = await res.json();
        return data.ocs.data.map((d) => ({
          share_type: d.source === 'groups' ? 'group' : 'user',
          share_with: d.id,
          label: d.label && d.label !== d.id ? `${d.label} (${d.id})` : d.id,
        }));
      } catch (e) {
        return [];
      }
    }

    function addShare(share) {
      const exists = shareDraft.some((s) => s.share_type === share.share_type && s.share_with === share.share_with);
      if (!exists) shareDraft.push(share);
      renderShareSection(dialogOwner);
      $('vt-share-search').focus();
    }

    let searchTimer = null;
    let lastSuggestions = [];
    $('vt-vehicle-dialog').addEventListener('input', (ev) => {
      if (ev.target.id !== 'vt-share-search') return;
      clearTimeout(searchTimer);
      const term = ev.target.value.trim();
      searchTimer = setTimeout(async () => {
        lastSuggestions = term.length >= 2 ? await searchSharees(term) : [];
        const box = $('vt-share-suggestions');
        if (!box) return;
        box.innerHTML = lastSuggestions
          .map((s, i) => `<button type="button" data-add-share="${i}">${s.share_type === 'group' ? '👥 Gruppe' : '👤'} ${esc(s.label)}</button>`)
          .join('');
      }, 250);
    });
    $('vt-vehicle-dialog').addEventListener('keydown', (ev) => {
      if (ev.target.id !== 'vt-share-search' || ev.key !== 'Enter') return;
      ev.preventDefault(); // nicht das Fahrzeugformular absenden
      const term = ev.target.value.trim();
      if (!term) return;
      addShare(lastSuggestions[0] || { share_type: 'user', share_with: term });
    });
    $('vt-vehicle-dialog').addEventListener('click', (ev) => {
      const add = ev.target.closest('[data-add-share]');
      if (add) addShare(lastSuggestions[Number(add.dataset.addShare)]);
      const remove = ev.target.closest('[data-remove-share]');
      if (remove) {
        shareDraft.splice(Number(remove.dataset.removeShare), 1);
        renderShareSection(dialogOwner);
      }
    });

    let dialogOwner = null;

    function openVehicleDialog(vehicle) {
      const form = $('vt-vehicle-form');
      form.reset();
      editingVehicleId = vehicle ? vehicle.id : null;
      if (vehicle) {
        for (const input of form.elements) {
          if (!input.name) continue;
          if (input.type === 'checkbox') input.checked = Boolean(vehicle[input.name]);
          else input.value = vehicle[input.name] ?? '';
        }
      }
      dialogOwner = vehicle ? vehicle.owner : me.uid;
      canManageShares = me.standalone || dialogOwner === me.uid;
      shareDraft = vehicle ? vehicle.shares.map((s) => ({ ...s })) : [];
      lastSuggestions = [];
      renderShareSection(dialogOwner);
      $('vt-vehicle-dialog-title').textContent = vehicle
        ? `Fahrzeug bearbeiten: ${vehicle.hersteller} ${vehicle.modell}`
        : 'Fahrzeug anlegen';
      $('vt-vehicle-submit').textContent = vehicle ? 'Speichern' : 'Anlegen';
      $('vt-vehicle-status').textContent = '';
      $('vt-vehicle-dialog').showModal();
    }

    $('vt-new-vehicle').addEventListener('click', () => openVehicleDialog(null));
    $('vt-edit-vehicle').addEventListener('click', () =>
      openVehicleDialog(vehicles.find((v) => v.id === Number(currentVehicleId)))
    );
    $('vt-vehicle-cancel').addEventListener('click', () => $('vt-vehicle-dialog').close());

    onSubmit('vt-vehicle-form', async (form) => {
      const editing = editingVehicleId !== null;
      const saved = await submitJson(
        form,
        editing ? `${BASE}/api/vehicles/${editingVehicleId}` : `${BASE}/api/vehicles`,
        {},
        $('vt-vehicle-status'),
        editing ? 'PUT' : 'POST'
      );
      if (!saved) return;
      if (canManageShares) {
        const res = await fetch(`${BASE}/api/vehicles/${saved.id}/shares`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(shareDraft.map(({ share_type, share_with }) => ({ share_type, share_with }))),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          showFormStatus($('vt-vehicle-status'), 'error', `Fahrzeug gespeichert, Freigaben nicht: ${body.detail || res.status}`);
          editingVehicleId = saved.id;
          return;
        }
      }
      $('vt-vehicle-dialog').close();
      loadVehicles(saved.id);
    });

    // === Excel-Import (Issue #16) ============================================
    // Eigenstaendiger Block: ergaenzt den Fahrzeugdialog (nur beim Bearbeiten
    // eines vorhandenen Fahrzeugs) um den Import der bisherigen
    // Excel-Buchfuehrung. Ablauf: Datei waehlen -> Vorschau (dry_run) ->
    // "Übernehmen" (echter Import) -> Daten neu laden.
    (function setupExcelImport() {
      const importStyle = document.createElement('style');
      importStyle.textContent = `
        #vt-vehicle-dialog .vt-import-actions { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; margin-top: 0.4rem; }
        #vt-vehicle-dialog .vt-import-summary { margin: 0.5rem 0 0.3rem; }
        #vt-vehicle-dialog .vt-import-warnings { font-size: 0.85rem; color: var(--color-warning, #9a6700); margin: 0.3rem 0; padding-left: 1.2rem; }
        #vt-vehicle-dialog .vt-import-table { max-height: 280px; overflow: auto; }
        #vt-vehicle-dialog .vt-import-table table { margin-top: 0.3rem; font-size: 0.8rem; }
        #vt-vehicle-dialog .vt-import-table td.num { white-space: nowrap; }
        #vt-vehicle-dialog .vt-import-table tr.dup { opacity: 0.5; }
        #vt-vehicle-dialog details.vt-import-details summary { cursor: pointer; font-size: 0.85rem; }
        #vt-vehicle-dialog .form-status.success { color: var(--color-success, #1a7f37); }
        #vt-vehicle-dialog .form-status.warning { color: var(--color-warning, #9a6700); }
      `;
      document.head.appendChild(importStyle);

      const section = document.createElement('div');
      section.id = 'vt-import-section';
      section.hidden = true;
      section.innerHTML = `
        <h4>Import</h4>
        <div class="muted">Historische Tankungen und sonstige Kosten aus der bisherigen Excel-Buchführung (.xlsx) übernehmen.
          Bereits erfasste Einträge werden erkannt und übersprungen.</div>
        <div class="vt-import-actions">
          <button type="button" id="vt-import-pick">Aus Excel importieren</button>
          <input type="file" id="vt-import-file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden>
        </div>
        <div class="form-status" id="vt-import-status"></div>
        <div id="vt-import-preview"></div>`;
      $('vt-vehicle-status').before(section);

      let importFile = null;
      let importVehicleId = null;
      const KAUF_LABELS = { kaufpreis: 'Anschaffungspreis', kaufdatum: 'Kaufdatum', kaufkilometerstand: 'km-Stand bei Kauf' };

      function resetImport() {
        importFile = null;
        importVehicleId = editingVehicleId;
        section.hidden = editingVehicleId === null;
        $('vt-import-file').value = '';
        $('vt-import-preview').innerHTML = '';
        $('vt-import-status').textContent = '';
        $('vt-import-status').className = 'form-status';
      }
      // openVehicleDialog setzt editingVehicleId - diese Listener laufen danach.
      $('vt-new-vehicle').addEventListener('click', resetImport);
      $('vt-edit-vehicle').addEventListener('click', resetImport);

      async function sendImport(dryRun) {
        const data = new FormData();
        data.append('file', importFile);
        const res = await fetch(
          `${BASE}/api/vehicles/${importVehicleId}/import/excel?dry_run=${dryRun ? 'true' : 'false'}`,
          { method: 'POST', body: data }
        );
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join(' / ') : body.detail;
          showFormStatus($('vt-import-status'), 'error', detail || `Fehler (${res.status})`);
          return null;
        }
        return body;
      }

      function kaufText(kauf) {
        if (!kauf) return '';
        const werte = [
          kauf.kaufdatum && fmtDate(kauf.kaufdatum),
          kauf.kaufpreis !== null && fmtEur(kauf.kaufpreis),
          kauf.kaufkilometerstand !== null && `${fmtNum(kauf.kaufkilometerstand)} km`,
        ].filter(Boolean).join(', ');
        const uebernahme = kauf.uebernommen.length
          ? `wird übernommen: ${kauf.uebernommen.map((k) => KAUF_LABELS[k] || k).join(', ')}`
          : 'am Fahrzeug bereits eingetragen, bleibt unverändert';
        return `<div class="muted">Kaufdaten aus der Datei (${esc(werte)}) – ${esc(uebernahme)}.</div>`;
      }

      function rowsTable(result) {
        const rows = [
          ...result.tankungen.map((t) => ({
            datum: t.datum, dup: t.duplikat, art: `Tankung ${t.kraftstoffart}${t.nicht_voll ? ' (nicht voll)' : ''}`,
            km: fmtNum(t.kilometerstand), menge: `${fmtNum(t.fuellmenge_liter, 2)} l`, betrag: t.gesamtpreis, text: t.quelle,
          })),
          ...result.kosten.map((c) => ({
            datum: c.datum, dup: c.duplikat, art: c.kategorie, km: '', menge: '', betrag: c.betrag,
            text: [c.beschreibung, c.quelle].filter(Boolean).join(' · '),
          })),
        ].sort((a, b) => a.datum.localeCompare(b.datum));
        if (!rows.length) return '';
        return `<details class="vt-import-details"><summary>Einträge anzeigen (${rows.length})</summary>
          <div class="vt-import-table"><table>
            <thead><tr><th>Datum</th><th>Art</th><th class="num">km</th><th class="num">Menge</th><th class="num">Betrag</th><th>Status</th><th>Beschreibung / Herkunft</th></tr></thead>
            <tbody>${rows.map((r) => `<tr class="${r.dup ? 'dup' : ''}">
              <td>${fmtDate(r.datum)}</td><td>${esc(r.art)}</td><td class="num">${r.km}</td><td class="num">${r.menge}</td>
              <td class="num">${fmtEur(r.betrag)}</td><td>${r.dup ? 'Duplikat' : 'neu'}</td><td>${esc(r.text)}</td>
            </tr>`).join('')}</tbody>
          </table></div></details>`;
      }

      function renderPreview(result) {
        const duplikate = result.tankungen_duplikate + result.kosten_duplikate;
        const hatNeues = result.tankungen_neu + result.kosten_neu > 0 || (result.kauf && result.kauf.uebernommen.length);
        const warnungen = result.warnungen.length
          ? `<ul class="vt-import-warnings">${result.warnungen.map((w) => `<li>${esc(w)}</li>`).join('')}</ul>`
          : '';
        $('vt-import-preview').innerHTML = `
          <div class="vt-import-summary">
            <b>${result.tankungen_neu}</b> neue Tankungen · <b>${result.kosten_neu}</b> neue Kosten ·
            ${duplikate} ${duplikate === 1 ? "Duplikat" : "Duplikate"} übersprungen
          </div>
          ${kaufText(result.kauf)}
          ${warnungen}
          ${rowsTable(result)}
          <div class="vt-import-actions">
            ${hatNeues ? '<button type="button" id="vt-import-apply" class="primary">Übernehmen</button>' : '<span class="muted">Nichts Neues zu übernehmen.</span>'}
          </div>`;
      }

      $('vt-import-pick').addEventListener('click', () => $('vt-import-file').click());

      $('vt-import-file').addEventListener('change', async (ev) => {
        importFile = ev.target.files[0] || null;
        $('vt-import-preview').innerHTML = '';
        if (!importFile || importVehicleId === null) return;
        showFormStatus($('vt-import-status'), '', `„${importFile.name}“ wird gelesen … (große Arbeitsmappen brauchen einige Sekunden)`);
        $('vt-import-pick').disabled = true;
        try {
          const result = await sendImport(true);
          if (!result) return;
          $('vt-import-status').textContent = '';
          renderPreview(result);
        } finally {
          $('vt-import-pick').disabled = false;
        }
      });

      $('vt-import-preview').addEventListener('click', async (ev) => {
        const button = ev.target.closest('#vt-import-apply');
        if (!button || !importFile) return;
        button.disabled = true;
        showFormStatus($('vt-import-status'), '', 'Import läuft …');
        const result = await sendImport(false);
        if (!result) {
          button.disabled = false;
          return;
        }
        $('vt-import-preview').innerHTML = '';
        showFormStatus(
          $('vt-import-status'), 'success',
          `✅ Importiert: ${result.tankungen_neu} Tankungen, ${result.kosten_neu} Kosten` +
            (result.kauf && result.kauf.uebernommen.length ? ', Kaufdaten ergänzt.' : '.')
        );
        // Uebernommene Kaufdaten auch im offenen Formular eintragen, damit ein
        // anschliessendes "Speichern" sie nicht wieder leert.
        const form = $('vt-vehicle-form');
        if (result.kauf) {
          result.kauf.uebernommen.forEach((key) => { form.elements[key].value = result.kauf[key] ?? ''; });
        }
        importFile = null;
        $('vt-import-file').value = '';
        loadVehicles(importVehicleId);
      });
    })();
    // === Ende Excel-Import ====================================================

    // --- Tankbeleg mit Mitrechnen --------------------------------------------

    // Aus zwei der drei Werte Menge/Preis/Gesamt wird der dritte berechnet.
    // Berechnet wird immer das Feld, das der Nutzer nicht unter den zuletzt
    // zwei selbst bearbeiteten Feldern hat - so laesst sich jedes Feld
    // wieder ueberschreiben.
    function setupFuelAutoCalc(form) {
      const fields = ['fuellmenge_liter', 'preis_pro_liter', 'gesamtpreis'];
      const decimals = { fuellmenge_liter: 2, preis_pro_liter: 3, gesamtpreis: 2 };
      let touched = []; // selbst bearbeitete Felder, zuletzt bearbeitetes am Ende
      const num = (name) => parseFloat(form.elements[name].value);

      function compute(target) {
        const menge = num('fuellmenge_liter');
        const preis = num('preis_pro_liter');
        const gesamt = num('gesamtpreis');
        let result = NaN;
        if (target === 'gesamtpreis') result = menge * preis;
        else if (target === 'preis_pro_liter' && menge > 0) result = gesamt / menge;
        else if (target === 'fuellmenge_liter' && preis > 0) result = gesamt / preis;
        const input = form.elements[target];
        if (Number.isFinite(result)) {
          input.value = result.toFixed(decimals[target]);
          input.classList.add('vt-computed');
        }
      }

      fields.forEach((name) => {
        form.elements[name].addEventListener('input', () => {
          form.elements[name].classList.remove('vt-computed');
          touched = touched.filter((f) => f !== name);
          if (form.elements[name].value !== '') touched.push(name);
          const sources = touched.slice(-2);
          if (sources.length === 2) compute(fields.find((f) => !sources.includes(f)));
        });
      });
      form.addEventListener('reset', () => {
        touched = [];
        fields.forEach((f) => form.elements[f].classList.remove('vt-computed'));
      });
    }
    setupFuelAutoCalc($('vt-fuel-entry-form'));

    function vehicleSubmit(formId, path, statusId, afterSave) {
      onSubmit(formId, async (form) => {
        if (!currentVehicleId) return;
        const saved = await submitJson(
          form, `${BASE}${path}`, { vehicle_id: Number(currentVehicleId) }, $(statusId)
        );
        if (saved) {
          if (afterSave) await afterSave(saved, $(statusId));
          form.reset();
          loadVehicle(currentVehicleId);
        }
      });
    }
    vehicleSubmit('vt-fuel-entry-form', '/api/fuel-entries', 'vt-fuel-entry-status', uploadFuelPhotos);
    vehicleSubmit('vt-other-cost-form', '/api/other-costs', 'vt-other-cost-status');
    vehicleSubmit('vt-logbook-form', '/api/logbook', 'vt-logbook-status');
    vehicleSubmit('vt-trip-form', '/api/trips', 'vt-trip-status');

    // --- Auswertung ----------------------------------------------------------

    document.querySelectorAll('input[name="vt-zeitraum"]').forEach((radio) => {
      radio.addEventListener('change', () => {
        const auswahl = radio.value === 'auswahl' && radio.checked;
        $('vt-von').disabled = !auswahl;
        $('vt-bis').disabled = !auswahl;
        loadStats();
      });
    });
    ['vt-von', 'vt-bis', 'vt-mit-anschaffung'].forEach((id) => $(id).addEventListener('change', loadStats));

    // Zaehler gegen ueberholte Antworten: mehrere Aenderungen kurz
    // hintereinander (Zeitraum-Umschalter, von, bis) starten parallele
    // Anfragen, und eine langsamere aeltere darf die neueste nicht ueberschreiben.
    let statsRequestId = 0;

    async function loadStats() {
      if (!currentVehicleId) return;
      const requestId = ++statsRequestId;
      const params = new URLSearchParams();
      if (document.querySelector('input[name="vt-zeitraum"]:checked').value === 'auswahl') {
        if ($('vt-von').value) params.set('von', $('vt-von').value);
        if ($('vt-bis').value) params.set('bis', $('vt-bis').value);
      }
      params.set('mit_anschaffung', $('vt-mit-anschaffung').checked ? 'true' : 'false');
      const s = await fetch(`${BASE}/api/vehicles/${currentVehicleId}/stats?${params}`).then((r) => r.json());
      if (requestId === statsRequestId) renderStats(s);
    }

    function verbrauchCards(verbrauchJeArt) {
      const eintraege = Object.entries(verbrauchJeArt || {});
      if (!eintraege.length) {
        return [
          `<div class="stat" title="Braucht zwei Volltankungen desselben Kraftstoffs – oder am Fahrzeug „Bei Kauf vollgetankt" plus eine Volltankung.">` +
            `<b>–</b>Ø Verbrauch/100 km</div>`,
        ];
      }
      return eintraege.map(
        ([art, wert]) => `<div class="stat"><b>${fmtNum(wert, 2)} l</b>Ø ${esc(art)}/100 km</div>`
      );
    }

    function renderStats(s) {
      const card = (value, label, muted = false) =>
        `<div class="stat${muted ? ' muted' : ''}"><b>${value}</b>${label}</div>`;
      $('vt-stats').innerHTML = [
        card(fmtEur(s.gesamtkosten), 'Gesamtkosten'),
        card(fmtEur(s.gesamt_kraftstoffkosten), 'Kraftstoff'),
        card(fmtEur(s.gesamt_sonstige_kosten), 'Laufende Kosten'),
        card(fmtEur(s.anschaffungskosten), s.mit_anschaffung ? 'Anschaffung' : 'Anschaffung (nicht einbezogen)', !s.mit_anschaffung),
        card(`${fmtNum(s.gefahrene_km)} km`, 'Gefahren'),
        card(s.kosten_pro_km === null ? '–' : `${fmtNum(s.kosten_pro_km, 3)} €`, 'Kosten/km'),
        card(fmtEur(s.kosten_pro_monat), 'Kosten/Monat'),
        ...verbrauchCards(s.verbrauch_nach_kraftstoff),
      ].join('');
      const kategorien = Object.entries(s.kosten_nach_kategorie)
        .map(([name, betrag]) => `${esc(name)}: ${fmtEur(betrag)}`)
        .join(' · ');
      const zeitraum = s.zeitraum_von ? `Zeitraum ${fmtDate(s.zeitraum_von)} – ${fmtDate(s.zeitraum_bis)}` : '';
      $('vt-kategorien').innerHTML = [zeitraum, kategorien && `Laufende Kosten: ${kategorien}`].filter(Boolean).join('<br>');
      renderHinweise(s.hinweise);
    }

    // --- Tankluecken-Hinweise (Issue #12) ------------------------------------
    // Dauerhafter Hinweis unter den Kennzahlen, solange der letzte bekannte
    // km-Stand weiter von der letzten Tankung entfernt ist als plausibel.
    function renderHinweise(hinweise) {
      const el = $('vt-hinweise');
      const liste = hinweise || [];
      el.innerHTML = liste.map((h) => `<div>⚠️ ${esc(h)}</div>`).join('');
      el.hidden = !liste.length;
    }
    // --- Ende Tankluecken-Hinweise -------------------------------------------
    // === Export: CSV / PDF-Bericht (Issue #14) ==============================
    // Eigenstaendiger Block: haengt zwei Buttons an die Auswertungs-Leiste und
    // nutzt deren Zeitraum und "Anschaffungskosten einbeziehen". Download per
    // fetch + Blob statt eines Links, damit die Anfrage genauso durch den
    // AppAPI-Proxy geht wie alle anderen API-Aufrufe (Nextcloud-Session,
    // von Nextcloud automatisch ergaenzter requesttoken).
    (function setupExport() {
      const controls = document.querySelector('#vehicle-tracker-root .auswertung-controls');
      if (!controls) return;
      const exportStyle = document.createElement('style');
      exportStyle.textContent = `
        #vehicle-tracker-root .vt-export { display: inline-flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; margin-left: auto; }
        #vehicle-tracker-root .vt-export-status { font-size: 0.85rem; color: var(--color-error, #b3261e); }
      `;
      document.head.appendChild(exportStyle);
      const wrap = document.createElement('span');
      wrap.className = 'vt-export';
      wrap.innerHTML =
        '<button type="button" data-export="csv" title="Alle Einträge des gewählten Zeitraums als CSV (für Excel)">CSV exportieren</button>' +
        '<button type="button" data-export="pdf" title="Bericht mit Kennzahlen, Kosten, Wartungshistorie und Fahrten">PDF-Bericht</button>' +
        '<span class="vt-export-status" role="status"></span>';
      controls.appendChild(wrap);
      const status = wrap.querySelector('.vt-export-status');

      function exportParams(format) {
        const params = new URLSearchParams();
        if (document.querySelector('input[name="vt-zeitraum"]:checked').value === 'auswahl') {
          if ($('vt-von').value) params.set('von', $('vt-von').value);
          if ($('vt-bis').value) params.set('bis', $('vt-bis').value);
        }
        if (format === 'pdf') params.set('mit_anschaffung', $('vt-mit-anschaffung').checked ? 'true' : 'false');
        return params;
      }

      function filenameFrom(res, fallback) {
        const header = res.headers.get('Content-Disposition') || '';
        const utf8 = header.match(/filename\*=UTF-8''([^;]+)/i);
        if (utf8) {
          try { return decodeURIComponent(utf8[1]); } catch (e) { /* weiter mit filename= */ }
        }
        const plain = header.match(/filename="?([^";]+)"?/i);
        return plain ? plain[1] : fallback;
      }

      async function download(format, button) {
        if (!currentVehicleId) return;
        status.textContent = '';
        button.disabled = true;
        try {
          const res = await fetch(`${BASE}/api/vehicles/${currentVehicleId}/export.${format}?${exportParams(format)}`);
          if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            status.textContent = `Export fehlgeschlagen: ${body.detail || res.status}`;
            return;
          }
          const url = URL.createObjectURL(await res.blob());
          const a = document.createElement('a');
          a.href = url;
          a.download = filenameFrom(res, `fahrzeug-export.${format}`);
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 10000);
        } catch (e) {
          status.textContent = 'Export fehlgeschlagen (keine Verbindung).';
        } finally {
          button.disabled = false;
        }
      }

      wrap.querySelectorAll('button[data-export]').forEach((button) => {
        button.addEventListener('click', () => download(button.dataset.export, button));
      });
    })();
    // === Ende Export ==========================================================
    // --- Belegfotos & "erfasst von" (Issues #3/#6) ---------------------------
    // Fotos liegen in den Nextcloud-Dateien des Fahrzeugbesitzers
    // (Fahrzeuge/<Kennzeichen>/Belege) und werden ueber die API ausgeliefert,
    // damit auch freigegebene Nutzer sie oeffnen koennen.

    const PHOTO_MAX_BYTES = 15 * 1024 * 1024;
    const photoStyle = document.createElement('style');
    photoStyle.textContent = `
      #vehicle-tracker-root .vt-by { display: block; font-size: 0.75rem; opacity: 0.6; }
      #vehicle-tracker-root a.vt-photo { text-decoration: none; font-size: 0.8rem; margin-right: 0.4rem; white-space: nowrap; }
      #vehicle-tracker-root details.manual-entry input[type="file"] { max-width: 16em; }
    `;
    document.head.appendChild(photoStyle);

    function erfasstVon(entry) {
      return entry.erfasst_von ? `<span class="vt-by">erfasst von ${esc(entry.erfasst_von)}</span>` : '';
    }

    function fuelPhotoLinks(entry) {
      const link = (art, label) =>
        `<a class="vt-photo" href="${BASE}/api/fuel-entries/${entry.id}/foto?art=${art}" target="_blank" rel="noopener" title="${label} öffnen">📷 ${label}</a>`;
      return [
        entry.beleg_foto_pfad ? link('beleg', 'Beleg') : '',
        entry.tacho_foto_pfad ? link('tacho', 'Tacho') : '',
      ].join('');
    }

    // Nach dem Speichern eines Tankbelegs die gewaehlten Fotos hochladen.
    async function uploadFuelPhotos(saved, statusEl) {
      const fehler = [];
      for (const [art, inputId, label] of [['beleg', 'vt-fuel-beleg-foto', 'Belegfoto'], ['tacho', 'vt-fuel-tacho-foto', 'Tachofoto']]) {
        const file = $(inputId).files[0];
        if (!file) continue;
        if (file.size > PHOTO_MAX_BYTES) {
          fehler.push(`${label}: größer als 15 MB`);
          continue;
        }
        const data = new FormData();
        data.append('datei', file);
        try {
          const res = await fetch(`${BASE}/api/fuel-entries/${saved.id}/foto?art=${art}`, { method: 'POST', body: data });
          if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            fehler.push(`${label}: ${body.detail || `Fehler (${res.status})`}`);
          }
        } catch (e) {
          fehler.push(`${label}: Upload fehlgeschlagen`);
        }
      }
      if (fehler.length) showFormStatus(statusEl, 'error', `Eintrag gespeichert, Foto nicht: ${fehler.join(' / ')}`);
    }

    // --- Laden & Rendern -----------------------------------------------------

    async function loadVehicles(selectId) {
      vehicles = await fetch(`${BASE}/api/vehicles`).then((r) => r.json());
      const select = $('vt-vehicle-select');
      select.innerHTML = vehicles
        .map((v) => `<option value="${v.id}">${esc(v.hersteller)} ${esc(v.modell)} (${esc(v.kennzeichen)})</option>`)
        .join('');
      select.onchange = () => loadVehicle(select.value);
      $('vt-edit-vehicle').hidden = !vehicles.length;

      if (!vehicles.length) {
        currentVehicleId = null;
        renderHinweise([]);
        $('vt-stats').innerHTML =
          '<div class="hint">Noch kein Fahrzeug – über „Anlegen" oben eines erfassen, oder den Besitzer eines Fahrzeugs um eine Freigabe bitten.</div>';
        return;
      }
      const target = vehicles.some((v) => v.id === selectId) ? selectId : vehicles[0].id;
      select.value = String(target);
      loadVehicle(target);
    }

    async function loadVehicle(vehicleId) {
      currentVehicleId = vehicleId;
      const [entries, logbook, trips] = await Promise.all([
        fetch(`${BASE}/api/fuel-entries?vehicle_id=${vehicleId}`).then((r) => r.json()),
        fetch(`${BASE}/api/logbook?vehicle_id=${vehicleId}`).then((r) => r.json()),
        fetch(`${BASE}/api/trips?vehicle_id=${vehicleId}`).then((r) => r.json()),
      ]);
      loadStats();
      loadReminders(vehicleId);
      renderFuelEntries(entries);
      renderMarkers(entries);
      renderLogbook(logbook);
      renderTrips(trips);
    }

    function renderFuelEntries(entries) {
      document.querySelector('#vt-entries tbody').innerHTML = entries
        .map(
          (e) => `<tr>
            <td>${fmtDate(e.datum)}</td><td class="num">${fmtNum(e.kilometerstand)}</td><td>${esc(e.kraftstoffart)}</td>
            <td class="num">${fmtNum(e.fuellmenge_liter, 2)} l</td><td class="num">${fmtNum(e.preis_pro_liter, 3)} €</td>
            <td class="num">${fmtEur(e.gesamtpreis)}</td>
            <td>${fuelPhotoLinks(e)}${erfasstVon(e)}</td>
          </tr>`
        )
        .join('');
    }

    function deleteButton(path, id) {
      return `<button type="button" class="link" data-delete="${path}/${id}" title="Löschen">🗑</button>`;
    }

    content.addEventListener('click', async (ev) => {
      const target = ev.target.closest('[data-delete]');
      if (!target) return;
      if (await deleteEntry(`${BASE}${target.dataset.delete}`)) loadVehicle(currentVehicleId);
    });

    function renderLogbook(entries) {
      document.querySelector('#vt-logbook tbody').innerHTML = entries
        .map(
          (e) => `<tr>
            <td>${fmtDate(e.datum)}</td><td class="num">${e.kilometerstand === null ? '' : fmtNum(e.kilometerstand)}</td>
            <td>${esc(e.eintrag)}${erfasstVon(e)}</td><td>${esc(e.notiz)}</td><td>${deleteButton('/api/logbook', e.id)}</td>
          </tr>`
        )
        .join('');
    }

    function renderTrips(trips) {
      document.querySelector('#vt-trips tbody').innerHTML = trips
        .map(
          (t) => `<tr>
            <td>${fmtDate(t.datum)}</td><td>${esc(t.start)}</td><td>${esc(t.ziel)}</td>
            <td class="num">${fmtNum(t.km_start)}</td><td class="num">${fmtNum(t.km_ende)}</td>
            <td class="num">${fmtNum(t.km_ende - t.km_start)} km</td><td>${esc(t.zweck)}${erfasstVon(t)}</td>
            <td>${deleteButton('/api/trips', t.id)}</td>
          </tr>`
        )
        .join('');

      const summen = {};
      trips.forEach((t) => { summen[t.zweck] = (summen[t.zweck] || 0) + (t.km_ende - t.km_start); });
      $('vt-trip-summen').textContent = Object.keys(summen).length
        ? 'Summe: ' + Object.entries(summen).map(([zweck, km]) => `${zweck} ${fmtNum(km)} km`).join(' · ')
        : '';

      // Naechste Fahrt startet ueblicherweise beim letzten Ende-km-Stand.
      const kmStart = $('vt-trip-form').elements.km_start;
      if (!kmStart.value && trips.length) kmStart.value = Math.max(...trips.map((t) => t.km_ende));
    }

    function renderMarkers(entries) {
      if (!map) return;
      markers.forEach((m) => map.removeLayer(m));
      markers = [];
      const withLocation = entries.filter((e) => e.lat && e.lon);
      withLocation.forEach((e) => {
        const marker = L.marker([e.lat, e.lon])
          .addTo(map)
          .bindPopup(`${esc(e.tankstelle_name ?? 'Tankstelle')}<br>${fmtDate(e.datum)} – ${fmtNum(e.preis_pro_liter, 3)} €/l`);
        markers.push(marker);
      });
      if (withLocation.length) {
        map.fitBounds(withLocation.map((e) => [e.lat, e.lon]), { padding: [30, 30], maxZoom: 13 });
      }
    }

    // === Erinnerungen (GitHub-Issue #4) ======================================
    // Eigenstaendiger Block: Abschnitt, Formular und Hinweis-Badge im Kopf
    // werden hier per DOM eingefuegt; von aussen nur loadReminders(vehicleId)
    // aus loadVehicle(). Status (faellig/bald) berechnet das Backend
    // (/api/reminders/status), gleiche Regeln wie die Nextcloud-Benachrichtigung.

    const REMINDER_TYPES = ['TÜV/HU', 'Versicherung fällig', 'Steuer fällig', 'Service/Inspektion', 'Reifenwechsel', 'Sonstiges'];

    const reminderStyle = document.createElement('style');
    reminderStyle.textContent = `
      #vehicle-tracker-root tr.vt-rem-faellig td { background: color-mix(in srgb, var(--color-error, #b3261e) 12%, transparent); }
      #vehicle-tracker-root tr.vt-rem-bald td { background: color-mix(in srgb, var(--color-warning, #9a6700) 12%, transparent); }
      #vehicle-tracker-root .vt-rem-state.faellig { color: var(--color-error, #b3261e); font-weight: 600; }
      #vehicle-tracker-root .vt-rem-state.bald { color: var(--color-warning, #9a6700); font-weight: 600; }
      #vehicle-tracker-root .vt-reminder-badge { margin-left: auto; border-radius: 999px; padding: 0.2rem 0.8rem; cursor: pointer; font-size: 0.85rem;
        border: 1px solid var(--color-warning, #9a6700); background: color-mix(in srgb, var(--color-warning, #9a6700) 12%, transparent); color: inherit; }
      #vehicle-tracker-root .vt-reminder-badge.faellig { border-color: var(--color-error, #b3261e); background: color-mix(in srgb, var(--color-error, #b3261e) 12%, transparent); }
      #vehicle-tracker-root #vt-reminder-count { font-weight: normal; font-size: 0.85rem; opacity: 0.8; }
      #vehicle-tracker-root td.vt-rem-actions { white-space: nowrap; }
    `;
    document.head.appendChild(reminderStyle);

    const reminderSection = document.createElement('details');
    reminderSection.className = 'manual-entry';
    reminderSection.id = 'vt-reminder-section';
    reminderSection.innerHTML = `
      <summary>Erinnerungen <span id="vt-reminder-count"></span></summary>
      <div class="section-body">
        <form id="vt-reminder-form">
          <label>Art
            <select name="typ" required>${REMINDER_TYPES.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join('')}</select>
          </label>
          <label>Beschreibung <input type="text" name="beschreibung" maxlength="300" placeholder="z.B. HU + AU"></label>
          <label>Fällig am <input type="date" name="faellig_am"></label>
          <label>Fällig bei km <input type="number" name="faellig_km" min="0"></label>
          <label>Wiederholen alle … Monate <input type="number" name="intervall_monate" min="1"></label>
          <label>Wiederholen alle … km <input type="number" name="intervall_km" min="1"></label>
          <button type="submit" id="vt-reminder-submit">Speichern</button>
          <button type="button" id="vt-reminder-cancel" hidden>Abbrechen</button>
          <div class="form-hint">Fälligkeit nach Datum und/oder km-Stand. Mit Intervall wird nach „erledigt" automatisch die nächste Fälligkeit gesetzt. Der Besitzer erhält eine Nextcloud-Benachrichtigung 14 Tage bzw. 500 km vorher und bei Fälligkeit.</div>
          <div class="form-status" id="vt-reminder-status"></div>
        </form>
        <table id="vt-reminders">
          <thead><tr><th>Art</th><th>Beschreibung</th><th>Fällig am</th><th class="num">Fällig bei</th><th>Intervall</th><th>Status</th><th></th></tr></thead>
          <tbody></tbody>
        </table>
      </div>`;
    {
      const tankbuchHeading = $('vt-entries') && $('vt-entries').previousElementSibling;
      if (tankbuchHeading && tankbuchHeading.tagName === 'H3') {
        tankbuchHeading.parentNode.insertBefore(reminderSection, tankbuchHeading);
      } else {
        document.querySelector('#vehicle-tracker-root .vt-main').appendChild(reminderSection);
      }
    }

    const reminderBadge = document.createElement('button');
    reminderBadge.type = 'button';
    reminderBadge.className = 'vt-reminder-badge';
    reminderBadge.hidden = true;
    document.querySelector('#vehicle-tracker-root header').appendChild(reminderBadge);

    let reminders = [];
    let editingReminderId = null;
    let remindersRequestId = 0;

    function reminderIntervall(r) {
      const teile = [];
      if (r.intervall_monate) teile.push(`${fmtNum(r.intervall_monate)} Mon.`);
      if (r.intervall_km) teile.push(`${fmtNum(r.intervall_km)} km`);
      return teile.join(' / ');
    }

    function reminderState(r) {
      if (r.status === 'faellig') {
        if (r.rest_tage !== null && r.rest_tage < 0) return `überfällig (${fmtNum(-r.rest_tage)} Tage)`;
        if (r.rest_tage === 0) return 'heute fällig';
        return r.rest_km ? `fällig (${fmtNum(-r.rest_km)} km drüber)` : 'km-Stand erreicht';
      }
      if (r.status === 'bald') {
        const teile = [];
        if (r.rest_tage !== null && r.rest_tage > 0 && r.rest_tage <= 14) teile.push(`in ${fmtNum(r.rest_tage)} Tagen`);
        if (r.rest_km !== null && r.rest_km > 0 && r.rest_km <= 500) teile.push(`noch ${fmtNum(r.rest_km)} km`);
        return teile.join(' / ') || 'bald fällig';
      }
      return 'offen';
    }

    function vehicleLabel(vehicleId) {
      const v = vehicles.find((x) => x.id === vehicleId);
      return v ? v.kennzeichen : `#${vehicleId}`;
    }

    async function loadReminders(vehicleId) {
      const requestId = ++remindersRequestId;
      let all = [];
      try {
        const res = await fetch(`${BASE}/api/reminders/status`);
        all = res.ok ? await res.json() : [];
      } catch (e) {
        all = [];
      }
      if (requestId !== remindersRequestId) return;
      reminders = all;
      renderReminders(all.filter((r) => r.vehicle_id === Number(vehicleId)));
      renderReminderBadge(all);
    }

    function renderReminders(list) {
      document.querySelector('#vt-reminders tbody').innerHTML = list.length
        ? list
          .map(
            (r) => `<tr class="${r.status ? `vt-rem-${r.status}` : ''}">
              <td>${esc(r.typ)}</td><td>${esc(r.beschreibung)}</td>
              <td>${r.faellig_am ? fmtDate(r.faellig_am) : ''}</td>
              <td class="num">${r.faellig_km === null ? '' : `${fmtNum(r.faellig_km)} km`}</td>
              <td>${esc(reminderIntervall(r))}</td>
              <td><span class="vt-rem-state ${r.status || ''}">${esc(reminderState(r))}</span></td>
              <td class="vt-rem-actions">
                <button type="button" data-reminder-done="${r.id}" title="Als erledigt markieren">✓ erledigt</button>
                <button type="button" class="link" data-reminder-edit="${r.id}" title="Bearbeiten">✏️</button>
                ${deleteButton('/api/reminders', r.id)}
              </td>
            </tr>`
          )
          .join('')
        : '<tr><td colspan="7" class="hint">Keine offenen Erinnerungen.</td></tr>';
      const due = list.filter((r) => r.status).length;
      $('vt-reminder-count').textContent = list.length ? `(${list.length} offen${due ? `, ${due} fällig/bald` : ''})` : '';
    }

    function renderReminderBadge(all) {
      const due = all.filter((r) => r.status);
      reminderBadge.hidden = !due.length;
      if (!due.length) return;
      const overdue = due.some((r) => r.status === 'faellig');
      reminderBadge.classList.toggle('faellig', overdue);
      reminderBadge.textContent = `⏰ ${due.length} ${due.length === 1 ? 'Erinnerung' : 'Erinnerungen'} ${overdue ? 'fällig' : 'bald fällig'}`;
      reminderBadge.title = due
        .map((r) => `${vehicleLabel(r.vehicle_id)}: ${r.typ}${r.beschreibung ? ` – ${r.beschreibung}` : ''} (${reminderState(r)})`)
        .join('\n');
    }

    reminderBadge.addEventListener('click', () => {
      const first = reminders.find((r) => r.status === 'faellig') || reminders.find((r) => r.status);
      if (first && first.vehicle_id !== Number(currentVehicleId)) {
        $('vt-vehicle-select').value = String(first.vehicle_id);
        loadVehicle(first.vehicle_id);
      }
      reminderSection.open = true;
      reminderSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });

    function resetReminderForm() {
      editingReminderId = null;
      $('vt-reminder-form').reset();
      $('vt-reminder-submit').textContent = 'Speichern';
      $('vt-reminder-cancel').hidden = true;
    }

    $('vt-reminder-cancel').addEventListener('click', () => {
      resetReminderForm();
      $('vt-reminder-status').textContent = '';
    });

    onSubmit('vt-reminder-form', async (form) => {
      if (!currentVehicleId) return;
      const editing = editingReminderId !== null;
      const saved = await submitJson(
        form,
        editing ? `${BASE}/api/reminders/${editingReminderId}` : `${BASE}/api/reminders`,
        { vehicle_id: Number(currentVehicleId) },
        $('vt-reminder-status'),
        editing ? 'PUT' : 'POST'
      );
      if (saved) {
        resetReminderForm();
        loadReminders(currentVehicleId);
      }
    });

    content.addEventListener('click', async (ev) => {
      const edit = ev.target.closest('[data-reminder-edit]');
      if (edit) {
        const r = reminders.find((x) => x.id === Number(edit.dataset.reminderEdit));
        if (!r) return;
        const form = $('vt-reminder-form');
        ['typ', 'beschreibung', 'faellig_am', 'faellig_km', 'intervall_monate', 'intervall_km'].forEach((name) => {
          form.elements[name].value = r[name] ?? '';
        });
        editingReminderId = r.id;
        $('vt-reminder-submit').textContent = 'Änderung speichern';
        $('vt-reminder-cancel').hidden = false;
        $('vt-reminder-status').textContent = '';
        form.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        return;
      }

      const done = ev.target.closest('[data-reminder-done]');
      if (!done) return;
      const r = reminders.find((x) => x.id === Number(done.dataset.reminderDone));
      if (!r) return;
      const params = new URLSearchParams();
      if (r.intervall_km || r.faellig_km !== null) {
        const answer = window.prompt(
          r.intervall_km
            ? 'Kilometerstand bei Erledigung (für die nächste Fälligkeit):'
            : 'Kilometerstand bei Erledigung (optional):',
          r.aktueller_km ?? ''
        );
        if (answer === null) return;
        if (answer.trim() !== '') {
          const km = parseInt(answer.replace(/\./g, ''), 10);
          if (!Number.isFinite(km) || km < 0) {
            showFormStatus($('vt-reminder-status'), 'error', 'Ungültiger Kilometerstand.');
            return;
          }
          params.set('km', String(km));
        }
      } else if (!window.confirm(`„${r.typ}" als erledigt markieren?`)) {
        return;
      }
      const res = await fetch(`${BASE}/api/reminders/${r.id}/erledigt?${params}`, { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        showFormStatus($('vt-reminder-status'), 'error', body.detail || `Fehler (${res.status})`);
        return;
      }
      showFormStatus($('vt-reminder-status'), 'success', r.intervall_monate || r.intervall_km
        ? '✅ Erledigt – nächste Fälligkeit gesetzt.'
        : '✅ Erledigt.');
      loadReminders(currentVehicleId);
    });

    // === Ende Erinnerungen ===================================================

    try {
      me = await fetch(`${BASE}/api/me`).then((r) => r.json());
    } catch (e) {
      // ohne Nutzerinfo bleiben Freigaben im Dialog nur lesbar
    }
    loadVehicles();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
