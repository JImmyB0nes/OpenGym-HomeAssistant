/**
 * openGym Muscle Card — Muskelbalance live im Dashboard.
 *
 * Liest die Attribute von sensor.opengym_muscle_balance (Sets diese Woche,
 * Zielbereiche, zuletzt trainiert, bestes 1RM) und zeichnet die echte
 * openGym-Körperkarte. Drei Modi wie in der App: Sätze · Erholung · Kraft.
 *
 * Konfiguration (alles optional außer der automatisch erkannten Entität):
 *   type: custom:opengym-muscle-card
 *   entity: sensor.opengym_muscle_balance
 *   body: male | female        # Körpermodell (Default male)
 *   mode: sets | recovery | strength
 *   show_list: true            # Muskelliste unter der Karte
 *   show_week: true            # Wochenzeile einblenden
 *   accent: "#a3e635"          # Akzentfarbe (Default: HA-Akzent)
 */

const TAG = "opengym-muscle-card";
const CARD_VERSION = "0.7.0";

const SLUGS = [
  "trapezius", "deltoids", "chest", "upper-back", "serratus",
  "biceps", "triceps", "forearm",
  "abs", "obliques", "lower-back",
  "gluteal", "quadriceps", "hamstring", "adductors", "hip-flexors",
  "calves", "tibialis",
];

const NAMES = {
  trapezius: "Trapez", deltoids: "Schultern", chest: "Brust", "upper-back": "Oberer Rücken",
  serratus: "Serratus", biceps: "Bizeps", triceps: "Triceps", forearm: "Unterarme",
  abs: "Core", obliques: "Seiten", "lower-back": "Unterer Rücken", gluteal: "Gesäß",
  quadriceps: "Beinstrecker", hamstring: "Kniebeugen", adductors: "Adduktoren",
  "hip-flexors": "Hüftbeuger", calves: "Waden", tibialis: "Schienbein",
};

const MODES = [
  ["sets", "Sätze"],
  ["recovery", "Erholung"],
  ["strength", "Kraft"],
];

let GEO = null; // shared geometry cache across all cards

function fmt(n) {
  if (n == null) return "–";
  const r = Math.round(n * 10) / 10;
  return Number.isInteger(r) ? String(r) : String(r).replace(".", ",");
}

function daysBetween(iso, now) {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d)) return null;
  return Math.floor((now - d) / 86400000);
}

class OpenGymMuscleCard extends HTMLElement {
  static getConfigElement() { return document.createElement("opengym-muscle-card-editor"); }
  static getStubConfig() { return { entity: "sensor.opengym_muscle_balance" }; }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._mode = null;
    this._sel = null;
    this._geoFail = false;
  }

  setConfig(config) {
    if (!this._root) { this._root = this.shadowRoot; }
    this._cfg = {
      entity: "sensor.opengym_muscle_balance",
      body: "male",
      mode: "sets",
      show_list: true,
      show_week: true,
      ...config,
    };
  }

  getCardSize() { return 5; }

  set hass(hass) {
    this._hass = hass;
    if (!this._cfg) this.setConfig({});
    this._render();
  }

  _geoUrl() {
    try { return new URL("body-geometry.json", import.meta.url).href; }
    catch { return "/opengym/body-geometry.json"; }
  }

  async _ensureGeo() {
    if (GEO || this._geoFail) return;
    try {
      const r = await fetch(this._geoUrl());
      if (!r.ok) throw new Error(r.status);
      GEO = await r.json();
    } catch (err) {
      this._geoFail = true;
      console.error(`${TAG}: body geometry failed`, err);
    }
  }

  _attrs() {
    const st = this._hass?.states?.[this._cfg.entity];
    if (!st || st.state === "unavailable") return null;
    return st.attributes || {};
  }

  _values(attrs) {
    const mode = this._mode || this._cfg.mode || "sets";
    const now = new Date();
    const out = {};
    if (mode === "sets") {
      const sets = attrs.sets || {};
      for (const s of SLUGS) out[s] = sets[s] || 0;
    } else if (mode === "recovery") {
      const last = attrs.last_trained || {};
      for (const s of SLUGS) {
        const d = daysBetween(last[s], now);
        out[s] = d == null ? -1 : Math.max(d, 0); // -1 = never trained, 0 = today
      }
    } else {
      const rm = attrs.best_1rm || {};
      for (const s of SLUGS) out[s] = rm[s] || 0;
    }
    return { mode, values: out };
  }

  _levels(values, mode) {
    // 5 heat steps; recovery uses a red->green semantic instead of balance.
    const lv = {};
    const pos = Object.values(values).filter((v) => v > 0);
    const max = pos.length ? Math.max(...pos) : 0;
    for (const s of SLUGS) {
      const v = values[s];
      if (mode === "recovery") {
        if (v < 0) { lv[s] = 0; continue; }
        lv[s] = v <= 1 ? 4 : v <= 2 ? 3 : v <= 4 ? 2 : v <= 7 ? 1 : 0;
      } else {
        if (v <= 0) { lv[s] = 0; continue; }
        const f = max ? v / max : 0;
        lv[s] = f >= 0.75 ? 4 : f >= 0.5 ? 3 : f >= 0.25 ? 2 : 1;
      }
    }
    return lv;
  }

  async _render() {
    if (!this._root) return;
    const attrs = this._attrs();
    if (!attrs) {
      this._root.innerHTML = `<ha-card><div class="empty">Keine openGym-Daten — <code>${this._cfg.entity}</code> nicht verfügbar.</div></ha-card>`;
      return;
    }
    await this._ensureGeo();
    const { mode, values } = this._values(attrs);
    const levels = this._levels(values, mode);
    const targets = attrs.targets || {};
    const last = attrs.last_trained || {};
    const oneRM = attrs.best_1rm || {};
    const unit = attrs.unit || "kg";

    const body = GEO?.[this._cfg.body] || GEO?.male;
    const weekStart = attrs.week_start ? new Date(attrs.week_start + "T00:00:00") : null;
    const weekLabel = weekStart
      ? "Woche vom " + weekStart.toLocaleDateString(undefined, { day: "numeric", month: "short" })
      : "";

    const totalSets = mode === "sets"
      ? Math.round(Object.values(values).reduce((a, b) => a + (b || 0), 0) * 10) / 10
      : null;

    const mapHtml = body
      ? ["front", "back"].map((v) => this._view(body[v], levels, mode)).join("")
      : `<div class="geo-fail">Körpergeometrie nicht geladen <button class="retry">Erneut laden</button></div>`;

    const list = SLUGS
      .map((s) => ({ s, v: values[s] }))
      .filter((x) => x.v > 0 || (mode === "recovery" && (x.v >= 0 || targets[x.s])) || (mode === "sets" && targets[x.s]))
      .sort((a, b) => b.v - a.v)
      .map((x) => this._row(x.s, x.v, mode, targets[x.s], last[x.s], oneRM[x.s], unit))
      .join("");

    const legend = mode === "recovery"
      ? `<div class="legend rec"><span>Frisch</span><i class="c r4"></i><i class="c r3"></i><i class="c r2"></i><i class="c r1"></i><i class="c r0"></i><span>Lang her</span></div>`
      : `<div class="legend"><span>Weniger</span><i class="c l0"></i><i class="c l1"></i><i class="c l2"></i><i class="c l3"></i><i class="c l4"></i><span>Mehr</span></div>`;

    const accent = this._cfg.accent ? ` style="--accent-color: ${this._cfg.accent}"` : "";
    this._root.innerHTML = `
      <style>${this._css()}</style>
      <ha-card${accent}>
        <div class="head">
          <div class="title">
            <ha-icon icon="mdi:human-handsup"></ha-icon>
            <span>Muskelbalance</span>
            ${totalSets ? `<span class="week">${fmt(totalSets)} Sätze</span>` : ""}
            ${this._cfg.show_week && weekLabel ? `<span class="week">${weekLabel}</span>` : ""}
          </div>
          <div class="modes">
            ${MODES.map(([m, l]) => `<button class="mode ${m === mode ? "on" : ""}" data-m="${m}">${l}</button>`).join("")}
          </div>
        </div>
        <div class="bodies ${body ? "" : "nomap"}">${mapHtml}</div>
        ${legend}
        ${this._cfg.show_list ? `<div class="list">${list}</div>` : ""}
      </ha-card>`;

    this._root.querySelectorAll("button.mode").forEach((b) =>
      b.addEventListener("click", () => { this._mode = b.dataset.m; this._render(); })
    );
    this._root.querySelectorAll("[data-muscle]").forEach((el) =>
      el.addEventListener("click", () => { this._sel = this._sel === el.dataset.muscle ? null : el.dataset.muscle; this._render(); })
    );
    const retry = this._root.querySelector(".retry");
    if (retry) retry.addEventListener("click", () => { this._geoFail = false; this._render(); });
  }

  _view(v, levels, mode) {
    if (!v) return "";
    const paths = Object.entries(v.p || {})
      .map(([slug, ds]) => {
        const muscle = SLUGS.includes(slug);
        const cls = (muscle ? "m l" + (levels[slug] || 0) : "sil") +
          (this._sel === slug ? " sel" : "") +
          (mode === "recovery" && muscle ? " rec" : "");
        const tag = muscle ? `data-muscle="${slug}" tabindex="0"` : "";
        return ds.map((d) => `<path class="${cls}" d="${d}" ${tag}><title>${NAMES[slug] || slug}</title></path>`).join("");
      })
      .join("");
    return `<svg viewBox="${v.vb}" class="body ${mode === "recovery" ? "rec" : ""}">${paths}</svg>`;
  }

  _row(slug, v, mode, target, lastTr, rm, unit) {
    let bar, right;
    if (mode === "sets") {
      const [lo, hi] = target || [0, 20];
      const scaleMax = Math.max(hi, v, 1);
      const pct = Math.min(100, (v / scaleMax) * 100);
      const loPct = (lo / scaleMax) * 100;
      const hiPct = (hi / scaleMax) * 100;
      bar = `<div class="bar"><div class="fill" style="width:${pct}%"></div>
             <div class="zone" style="left:${loPct}%;width:${hiPct - loPct}%"></div></div>`;
      right = `<span class="val"><b>${fmt(v)}</b> <em>/ ${lo}–${hi}</em></span>`;
    } else if (mode === "recovery") {
      const d = v >= 0 ? v : null;
      const pct = d == null ? 0 : Math.min(100, (d / 10) * 100);
      const cls = d == null ? "never" : d <= 2 ? "fresh" : d <= 5 ? "ok" : "stale";
      bar = `<div class="bar"><div class="fill ${cls}" style="width:${pct || 4}%"></div></div>`;
      right = `<span class="val">${d == null ? "nie" : d === 0 ? "heute" : d === 1 ? "1 Tag" : d + " Tage"}</span>`;
    } else {
      bar = "";
      right = `<span class="val">${rm ? fmt(rm) + " " + unit : "–"}</span>`;
    }
    const sel = this._sel === slug ? " sel" : "";
    return `<div class="row${sel}" data-muscle="${slug}">
      <span class="name">${NAMES[slug] || slug}</span>${bar}${right}</div>`;
  }

  _css() {
    return `
      ha-card { padding: 14px 16px 16px; }
      .head { display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between; margin-bottom:10px; }
      .title { display:flex; align-items:center; gap:8px; font-size:1.05em; font-weight:600; }
      .title ha-icon { color: var(--accent-color); }
      .week { font-weight:400; opacity:.6; font-size:.85em; margin-left:6px; }
      .modes { display:flex; background: var(--state-icon-unavailable-color, rgba(128,128,128,.15)); border-radius:999px; padding:3px; }
      .mode { border:none; background:transparent; color: var(--primary-text-color); opacity:.55;
              padding:6px 14px; border-radius:999px; cursor:pointer; font-size:.85em; }
      .mode.on { background: var(--card-background-color, #fff); opacity:1; box-shadow: 0 1px 4px rgba(0,0,0,.25); }
      .bodies { display:flex; justify-content:center; gap:14px; }
      .bodies.nomap { display:block; }
      svg.body { height: 300px; width:auto; }
      svg .sil { fill: var(--disabled-text-color, #555); opacity:.25; }
      svg .m { fill: var(--disabled-text-color, #555); opacity:.25; cursor:pointer; transition: fill .2s; }
      svg:not(.rec) .m.l1 { fill: color-mix(in srgb, var(--accent-color, #4caf50) 32%, transparent); opacity:1; }
      svg:not(.rec) .m.l2 { fill: color-mix(in srgb, var(--accent-color, #4caf50) 56%, transparent); opacity:1; }
      svg:not(.rec) .m.l3 { fill: color-mix(in srgb, var(--accent-color, #4caf50) 78%, transparent); opacity:1; }
      svg:not(.rec) .m.l4 { fill: var(--accent-color, #4caf50); opacity:1; }
      svg.rec .m.l1 { fill: color-mix(in srgb, #ffd60a 35%, transparent); opacity:1; }
      svg.rec .m.l2 { fill: #ffd60a; opacity:1; }
      svg.rec .m.l3 { fill: #ff9f0a; opacity:1; }
      svg.rec .m.l4 { fill: #ff453a; opacity:1; }
      svg .m.sel { stroke: var(--primary-text-color); stroke-width: 3; }
      .legend { display:flex; justify-content:flex-end; align-items:center; gap:4px; font-size:.75em; opacity:.7; margin-top:6px; }
      .legend .c { width:14px; height:14px; border-radius:3px; display:inline-block; }
      .c.l0 { background: var(--disabled-text-color, #555); opacity:.25; }
      .c.l1 { background: color-mix(in srgb, var(--accent-color, #4caf50) 32%, transparent); }
      .c.l2 { background: color-mix(in srgb, var(--accent-color, #4caf50) 56%, transparent); }
      .c.l3 { background: color-mix(in srgb, var(--accent-color, #4caf50) 78%, transparent); }
      .c.l4 { background: var(--accent-color, #4caf50); }
      .legend.rec .c.r1 { background: color-mix(in srgb, #ffd60a 35%, transparent); }
      .legend.rec .c.r2 { background: #ffd60a; }
      .legend.rec .c.r3 { background: #ff9f0a; }
      .legend.rec .c.r4 { background: #ff453a; }
      .legend.rec .c.r0 { background: var(--disabled-text-color, #555); opacity:.25; }
      .list { margin-top:10px; }
      .row { display:flex; align-items:center; gap:10px; padding:7px 2px; cursor:pointer; border-bottom:1px solid rgba(128,128,128,.12); }
      .row:last-child { border-bottom:none; }
      .row.sel { background: color-mix(in srgb, var(--accent-color, #4caf50) 10%, transparent); }
      .name { flex: 0 0 150px; font-size:.9em; }
      .val { flex: 0 0 auto; font-size:.9em; white-space:nowrap; }
      .val b { font-weight:600; } .val em { font-style:normal; opacity:.55; }
      .bar { position:relative; flex:1; height:7px; border-radius:99px; background: rgba(128,128,128,.18); overflow:hidden; }
      .bar .fill { position:absolute; inset:0 auto 0 0; border-radius:99px; background: var(--accent-color, #4caf50); }
      .bar .fill.fresh { background:#ff453a; } .bar .fill.ok { background:#ffd60a; }
      .bar .fill.stale { background: var(--accent-color, #4caf50); } .bar .fill.never { background: rgba(128,128,128,.4); }
      .bar .zone { position:absolute; top:0; bottom:0; background: rgba(128,128,128,.30); }
      .empty { padding: 20px; opacity:.7; }
      .geo-fail { text-align:center; padding:10px; opacity:.7; }
      .retry { margin-left:8px; }
      @media (max-width: 600px) { svg.body { height: 220px; } .name { flex-basis: 110px; } }
    `;
  }
}

customElements.define(TAG, OpenGymMuscleCard);

// Editor: minimal — entity, body, mode, toggles.
const EDITOR_SCHEMA = [
  { name: "entity", required: true, selector: { entity: { integration: "opengym", domain: "sensor" } } },
  { name: "body", selector: { select: { options: ["male", "female"], mode: "dropdown" } } },
  { name: "mode", selector: { select: { options: ["sets", "recovery", "strength"], mode: "dropdown" } } },
  { name: "show_list", selector: { boolean: {} } },
  { name: "show_week", selector: { boolean: {} } },
  { name: "accent", selector: { text: {} } },
];

class OpenGymMuscleCardEditor extends HTMLElement {
  connectedCallback() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      const form = document.createElement("ha-form");
      form.schema = EDITOR_SCHEMA;
      form.addEventListener("value-changed", (ev) => {
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: ev.detail.value },
            bubbles: true,
            composed: true,
          })
        );
      });
      this.shadowRoot.appendChild(form);
    }
    this._form = this.shadowRoot.querySelector("ha-form");
    if (this._cfg) this._form.data = this._cfg;
  }

  setConfig(config) {
    this._cfg = { body: "male", mode: "sets", show_list: true, show_week: true, ...config };
    if (this._form) this._form.data = this._cfg;
  }
}
customElements.define("opengym-muscle-card-editor", OpenGymMuscleCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: TAG,
  name: "openGym Muscle Card",
  preview: false,
  description: "Muskelbalance, Erholung und Kraft als echte openGym-Körperkarte im Dashboard.",
});
