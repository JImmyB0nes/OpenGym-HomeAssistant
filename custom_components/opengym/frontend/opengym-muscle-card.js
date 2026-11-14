/**
 * openGym Muscle Card — Muskelbalance live im Dashboard.
 *
 * Liest die Attribute von sensor.opengym_muscle_balance und zeichnet die echte
 * openGym-Körperkarte. Modi wie in der App: Sätze · Erholung · Kraft · Geplant.
 * Dazu: Wochen-Pfeile, Muskel-Detail-Panel (WebSocket), 12-Wochen-Heatmap,
 * 1RM-Sparklines und ein Versions-Check gegen das Backend.
 *
 * Konfiguration (alles optional außer der automatisch erkannten Entität):
 *   type: custom:opengym-muscle-card
 *   entity: sensor.opengym_muscle_balance
 *   body: male | female        # Körpermodell (Default male)
 *   mode: sets | recovery | strength | planned
 *   show_list: true            # Muskelliste unter der Karte
 *   show_week: true            # Wochenzeile mit Pfeil-Navigation
 *   show_heatmap: true         # 12-Wochen-Trainings-Heatmap
 *   show_detail: true          # Detail-Panel beim Klick auf einen Muskel
 *   show_plan_week: true       # Wochenplan-Leiste im Geplant-Modus
 *   accent: "#a3e635"          # Akzentfarbe (Default: HA-Akzent)
 */

const TAG = "opengym-muscle-card";
const CARD_VERSION = "0.8.2";

const SLUGS = [
  "trapezius", "deltoids", "chest", "upper-back", "serratus",
  "biceps", "triceps", "forearm",
  "abs", "obliques", "lower-back",
  "gluteal", "quadriceps", "hamstring", "adductors", "hip-flexors",
  "calves", "tibialis",
];

// Muskelnamen nach Sprache — der openGym-Originalstand ist deutsch,
// Englisch greift als Fallback.
const NAMES = {
  de: {
    trapezius: "Trapez", deltoids: "Schultern", chest: "Brust", "upper-back": "Oberer Rücken",
    serratus: "Serratus", biceps: "Bizeps", triceps: "Triceps", forearm: "Unterarme",
    abs: "Core", obliques: "Seiten", "lower-back": "Unterer Rücken", gluteal: "Gesäß",
    quadriceps: "Beinstrecker", hamstring: "Kniebeugen", adductors: "Adduktoren",
    "hip-flexors": "Hüftbeuger", calves: "Waden", tibialis: "Schienbein",
  },
  en: {
    trapezius: "Trapezius", deltoids: "Shoulders", chest: "Chest", "upper-back": "Upper Back",
    serratus: "Serratus", biceps: "Biceps", triceps: "Triceps", forearm: "Forearms",
    abs: "Core", obliques: "Obliques", "lower-back": "Lower Back", gluteal: "Glutes",
    quadriceps: "Quadriceps", hamstring: "Hamstrings", adductors: "Adductors",
    "hip-flexors": "Hip Flexors", calves: "Calves", tibialis: "Tibialis",
  },
};

// UI-Texte (Modi, Labels) — ebenfalls zweisprachig.
const UI = {
  de: {
    modes: { sets: "Sätze", recovery: "Erholung", strength: "Kraft", planned: "Geplant" },
    title: "Muskelbalance", less: "Weniger", more: "Mehr", fresh: "Frisch",
    stale: "Lang her", never: "nie", today: "heute", day1: "1 Tag", days: "Tage",
    weekOf: "Woche vom", setsUnit: "Sätze", rest: "Ruhetag", planWeek: "Diese Woche",
    detail: { week: "Sätze diese Woche", last: "Zuletzt trainiert", fatigue: "Müdigkeit",
      best: "Bestes 1RM", trend: "1RM-Verlauf (12 Wochen)", exercises: "Übungen (Wochen-Sätze)",
      close: "Schließen", daysAgo: "Tage her" },
    heatmap: "Letzte 12 Wochen", versionWarn: "Falsche Karten-Version im Browser — Cache leeren.",
    noData: "Keine openGym-Daten —", retry: "Erneut laden", geoFail: "Körpergeometrie nicht geladen",
  },
  en: {
    modes: { sets: "Sets", recovery: "Recovery", strength: "Strength", planned: "Planned" },
    title: "Muscle balance", less: "Less", more: "More", fresh: "Fresh",
    stale: "Long ago", never: "never", today: "today", day1: "1 day", days: "days",
    weekOf: "Week of", setsUnit: "sets", rest: "Rest day", planWeek: "This week",
    detail: { week: "Sets this week", last: "Last trained", fatigue: "Fatigue",
      best: "Best 1RM", trend: "1RM trend (12 weeks)", exercises: "Exercises (weekly sets)",
      close: "Close", daysAgo: "days ago" },
    heatmap: "Last 12 weeks", versionWarn: "Stale card version in browser — clear cache.",
    noData: "No openGym data —", retry: "Reload", geoFail: "Body geometry failed to load",
  },
};

const MODES = ["sets", "recovery", "strength", "planned"];

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
    this._detail = null;      // muscle slug of the open detail panel
    this._detailData = null;  // resolved WS payload for _sel
    this._weekOffset = 0;     // 0 = current week, -1 = last week ...
    this._geoFail = false;
    this._versionMismatch = false;
    this._versionChecked = false;
  }

  setConfig(config) {
    if (!this._root) { this._root = this.shadowRoot; }
    this._cfg = {
      entity: "sensor.opengym_muscle_balance",
      body: "male",
      mode: "sets",
      show_list: true,
      show_week: true,
      show_heatmap: true,
      show_detail: true,
      show_plan_week: true,
      ...config,
    };
  }

  getCardSize() { return 6; }

  set hass(hass) {
    this._hass = hass;
    if (!this._cfg) this.setConfig({});
    this._checkVersion();
    this._render();
  }

  _lang() {
    const l = (this._hass && this._hass.language) || "de";
    return UI[l.split("-")[0]] ? l.split("-")[0] : "de";
  }

  _t() { return UI[this._lang()]; }
  _names() { return NAMES[this._lang()] || NAMES.de; }

  _name(slug) { return this._names()[slug] || slug; }

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

  // --- Version-Check: Karte gegen Backend ----------------------------------
  async _checkVersion() {
    if (this._versionChecked) return;
    this._versionChecked = true;
    try {
      const conn = (await this._hass.connectionPromise) || this._hass.connection;
      if (!conn || !conn.sendMessagePromise) return;
      const res = await conn.sendMessagePromise({ type: "opengym:version" });
      if (res && res.version && res.version !== CARD_VERSION) {
        this._versionMismatch = true;
        this._render();
      }
    } catch {
      // old backend or no WS support — stay silent, card still works
    }
  }

  // --- Detail-Panel: Daten per WebSocket -----------------------------------
  async _loadDetail(muscle) {
    this._detailData = null;
    try {
      const conn = (await this._hass.connectionPromise) || this._hass.connection;
      if (conn && conn.sendMessagePromise) {
        const data = await conn.sendMessagePromise({
          type: "opengym:detail",
          muscle,
        });
        if (this._sel === muscle && data) {
          this._detailData = data;
          this._render();
          return;
        }
      }
    } catch {
      // fall back to attribute-derived data below
    }
    if (this._sel === muscle) this._render();
  }

  _detailFallback(muscle, attrs) {
    const trends = attrs.trends || {};
    const last = attrs.last_trained || {};
    const sets = attrs.sets || {};
    const targets = attrs.targets || {};
    const fatigue = attrs.fatigue || {};
    const oneRM = attrs.best_1rm || {};
    const f = fatigue[muscle] || 0;
    return {
      week_sets: sets[muscle] || 0,
      target: targets[muscle] || [0, 0],
      last_trained: last[muscle] || null,
      fatigue: f,
      fatigue_state: f > 0.5 ? "fatigued" : f >= 0.25 ? "recovering" : "ready",
      best_1rm: oneRM[muscle] || null,
      trend: trends[muscle] || [],
      exercises: {},
    };
  }

  // --- Werte pro Muskel und Modus ------------------------------------------
  _values(attrs) {
    const mode = this._mode || this._cfg.mode || "sets";
    const now = new Date();
    const out = {};
    if (mode === "sets") {
      if (this._weekOffset < 0) {
        const hist = (attrs.history || [])[12 + this._weekOffset];
        const sets = hist?.muscles || {};
        for (const s of SLUGS) out[s] = sets[s] || 0;
      } else {
        const sets = attrs.sets || {};
        for (const s of SLUGS) out[s] = sets[s] || 0;
      }
    } else if (mode === "recovery") {
      const last = attrs.last_trained || {};
      for (const s of SLUGS) {
        const d = daysBetween(last[s], now);
        out[s] = d == null ? -1 : Math.max(d, 0); // -1 = never trained, 0 = today
      }
    } else if (mode === "planned") {
      const planned = attrs.planned || {};
      for (const s of SLUGS) out[s] = planned[s] || 0;
    } else {
      const rm = attrs.best_1rm || {};
      for (const s of SLUGS) out[s] = rm[s] || 0;
    }
    return { mode, values: out };
  }

  _levels(values, mode) {
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

  _weekLabel(attrs) {
    const t = this._t();
    let start = attrs.week_start;
    if (!start) return "";
    if (this._weekOffset < 0) {
      const hist = (attrs.history || [])[12 + this._weekOffset];
      if (!hist) return "";
      start = hist.week_start;
    } else if (this._weekOffset > 0) {
      return "";
    }
    const d = new Date(start + "T00:00:00");
    return t.weekOf + " " + d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  }

  async _render() {
    if (!this._root) return;
    const attrs = this._attrs();
    const t = this._t();
    if (!attrs) {
      this._root.innerHTML = `<ha-card><div class="empty">${t.noData} <code>${this._cfg.entity}</code>.</div></ha-card>`;
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

    const totalSets = mode === "sets"
      ? Math.round(Object.values(values).reduce((a, b) => a + (b || 0), 0) * 10) / 10
      : null;

    const weekLabel = this._cfg.show_week ? this._weekLabel(attrs) : "";
    const weekLabelHtml = weekLabel
      ? `<span class="week">${weekLabel}</span>
         <span class="nav">
           <button class="navbtn" data-nav="-1" title="‹">‹</button>
           <button class="navbtn" data-nav="1" title="›" ${this._weekOffset >= 0 ? "disabled" : ""}>›</button>
         </span>`
      : "";

    const mapHtml = body
      ? ["front", "back"].map((v) => this._view(body[v], levels, mode)).join("")
      : `<div class="geo-fail">${t.geoFail} <button class="retry">${t.retry}</button></div>`;

    const list = SLUGS
      .map((s) => ({ s, v: values[s] }))
      .filter((x) => x.v > 0 || (mode === "recovery" && (x.v >= 0 || targets[x.s])) || (mode === "sets" && targets[x.s]))
      .sort((a, b) => b.v - a.v)
      .map((x) => this._row(x.s, x.v, mode, targets[x.s], last[x.s], oneRM[x.s], unit))
      .join("");

    const legend = mode === "recovery"
      ? `<div class="legend rec"><span>${t.fresh}</span><i class="c r4"></i><i class="c r3"></i><i class="c r2"></i><i class="c r1"></i><i class="c r0"></i><span>${t.stale}</span></div>`
      : `<div class="legend"><span>${t.less}</span><i class="c l0"></i><i class="c l1"></i><i class="c l2"></i><i class="c l3"></i><i class="c l4"></i><span>${t.more}</span></div>`;

    const heatmapHtml = (this._cfg.show_heatmap && attrs.history)
      ? this._heatmap(attrs.history)
      : "";

    const planWeekHtml = (mode === "planned" && this._cfg.show_plan_week && attrs.planned_week)
      ? this._planWeek(attrs.planned_week)
      : "";

    const detailHtml = (this._cfg.show_detail && this._sel)
      ? this._detailPanel(this._sel, attrs)
      : "";

    const versionHtml = this._versionMismatch
      ? `<div class="warn">⚠ ${t.versionWarn}</div>`
      : "";

    const accent = this._cfg.accent ? ` style="--accent-color: ${this._cfg.accent}"` : "";
    this._root.innerHTML = `
      <style>${this._css()}</style>
      <ha-card${accent}>
        <div class="head">
          <div class="title">
            <ha-icon icon="mdi:human-handsup"></ha-icon>
            <span>${t.title}</span>
            ${totalSets ? `<span class="week">${totalSets} ${t.setsUnit}</span>` : ""}
            ${weekLabelHtml}
          </div>
          <div class="modes">
            ${MODES.map((m) => `<button class="mode ${m === mode ? "on" : ""}" data-m="${m}">${t.modes[m]}</button>`).join("")}
          </div>
        </div>
        ${versionHtml}
        <div class="bodies ${body ? "" : "nomap"}">${mapHtml}</div>
        ${legend}
        ${planWeekHtml}
        ${heatmapHtml}
        ${detailHtml}
        ${this._cfg.show_list ? `<div class="list">${list}</div>` : ""}
      </ha-card>`;

    this._root.querySelectorAll("button.mode").forEach((b) =>
      b.addEventListener("click", () => { this._mode = b.dataset.m; this._render(); })
    );
    this._root.querySelectorAll("[data-muscle]").forEach((el) =>
      el.addEventListener("click", () => {
        const slug = el.dataset.muscle;
        this._sel = this._sel === slug ? null : slug;
        if (this._sel) this._loadDetail(this._sel);
        this._render();
      })
    );
    this._root.querySelectorAll("[data-nav]").forEach((b) =>
      b.addEventListener("click", () => {
        const next = this._weekOffset + Number(b.dataset.nav);
        if (next > 0 || next < -11) return;
        this._weekOffset = next;
        this._render();
      })
    );
    const closeDetail = this._root.querySelector(".detail-close");
    if (closeDetail) closeDetail.addEventListener("click", () => { this._sel = null; this._render(); });
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
          (mode === "recovery" ? " rec" : "");
        const tag = muscle ? `data-muscle="${slug}" tabindex="0"` : "";
        return ds.map((d) => `<path class="${cls}" d="${d}" ${tag}><title>${this._name(slug)}</title></path>`).join("");
      })
      .join("");
    return `<svg viewBox="${v.vb}" class="body ${mode === "recovery" ? "rec" : ""}">${paths}</svg>`;
  }

  _row(slug, v, mode, target, lastTr, rm, unit) {
    const t = this._t();
    let bar, right;
    if (mode === "sets" || mode === "planned") {
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
      right = `<span class="val">${d == null ? t.never : d === 0 ? t.today : d === 1 ? t.day1 : d + " " + t.days}</span>`;
    } else {
      bar = "";
      right = `<span class="val">${rm ? fmt(rm) + " " + unit : "–"}</span>`;
    }
    const sel = this._sel === slug ? " sel" : "";
    return `<div class="row${sel}" data-muscle="${slug}">
      <span class="name">${this._name(slug)}</span>${bar}${right}</div>`;
  }

  // --- 12-Wochen-Heatmap ----------------------------------------------------
  _heatmap(history) {
    const t = this._t();
    const cells = history.map((w) => {
      const sets = w.sets || 0;
      const lv = sets <= 0 ? 0 : sets <= 5 ? 1 : sets <= 10 ? 2 : sets <= 18 ? 3 : 4;
      const d = new Date(w.week_start + "T00:00:00");
      const label = d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
      const title = `${label}: ${fmt(sets)} ${t.setsUnit}, ${w.workouts} ×`;
      return `<div class="hcell h${lv}" title="${title}"></div>`;
    }).join("");
    return `<div class="heatwrap"><span class="heatlabel">${t.heatmap}</span><div class="heat">${cells}</div></div>`;
  }

  // --- Wochenplan-Leiste ----------------------------------------------------
  _planWeek(plan) {
    const t = this._t();
    const days = plan.map((d) => {
      const day = new Date(d.date + "T00:00:00")
        .toLocaleDateString(undefined, { weekday: "short" });
      const body = d.name
        ? `<span class="pd-name">${d.emoji ? d.emoji + " " : ""}${d.name}</span><span class="pd-sub">${d.exercises}×</span>`
        : `<span class="pd-rest">${t.rest}</span>`;
      return `<div class="pday ${d.name ? "on" : ""}"><span class="pd-day">${day}</span>${body}</div>`;
    }).join("");
    return `<div class="planweek"><span class="pw-label">${t.planWeek}</span><div class="pdays">${days}</div></div>`;
  }

  // --- Detail-Panel ---------------------------------------------------------
  _detailPanel(muscle, attrs) {
    const t = this._t();
    const d = this._detailData && this._detailData.trend ? this._detailData : this._detailFallback(muscle, attrs);
    const unit = attrs.unit || "kg";
    const trend = (d.trend || []).filter((v) => v != null);
    const spark = trend.length > 1 ? this._sparkline(d.trend) : "";
    const fatigue = d.fatigue || 0;
    const fstate = d.fatigue_state || "ready";
    const fPct = Math.min(100, fatigue * 100);
    const ex = Object.entries(d.exercises || {});
    const exMax = ex.length ? Math.max(...ex.map(([, v]) => v)) : 1;
    const exRows = ex.map(([name, v]) =>
      `<div class="exrow"><span class="exname">${name}</span>
       <div class="bar"><div class="fill" style="width:${(v / exMax) * 100}%"></div></div>
       <span class="val">${fmt(v)}</span></div>`
    ).join("");
    const lastD = daysBetween(d.last_trained, new Date());
    const lastTxt = lastD == null ? t.never : lastD === 0 ? t.today : lastD + " " + t.detail.daysAgo;
    const [lo, hi] = d.target || [0, 0];
    return `<div class="detail">
      <div class="detail-head">
        <span class="detail-title">${this._name(muscle)}</span>
        <button class="detail-close" title="${t.detail.close}">✕</button>
      </div>
      <div class="dgrid">
        <div class="dstat"><span class="dl">${t.detail.week}</span><span class="dv"><b>${fmt(d.week_sets)}</b> / ${lo}–${hi}</span></div>
        <div class="dstat"><span class="dl">${t.detail.last}</span><span class="dv">${lastTxt}</span></div>
        <div class="dstat"><span class="dl">${t.detail.fatigue}</span>
          <span class="dv"><span class="fchip ${fstate}">${fmt(fatigue)}</span></span></div>
        <div class="dstat"><span class="dl">${t.detail.best}</span><span class="dv">${d.best_1rm ? fmt(d.best_1rm) + " " + unit : "–"}</span></div>
      </div>
      <div class="fatbar"><div class="fatfill" style="width:${fPct}%"></div></div>
      ${spark ? `<div class="trend"><span class="dl">${t.detail.trend}</span>${spark}</div>` : ""}
      ${exRows ? `<div class="exlist"><span class="dl">${t.detail.exercises}</span>${exRows}</div>` : ""}
    </div>`;
  }

  _sparkline(trend) {
    const vals = trend.map((v, i) => ({ i, v })).filter((x) => x.v != null);
    if (vals.length < 2) return "";
    const w = 220, h = 44, pad = 3;
    const vs = vals.map((x) => x.v);
    const min = Math.min(...vs), max = Math.max(...vs);
    const span = max - min || 1;
    const xs = (i) => pad + (i / (trend.length - 1)) * (w - 2 * pad);
    const ys = (v) => h - pad - ((v - min) / span) * (h - 2 * pad);
    const pts = vals.map((x) => `${xs(x.i).toFixed(1)},${ys(x.v).toFixed(1)}`).join(" ");
    const last = vals[vals.length - 1];
    const area = `M${xs(vals[0].i).toFixed(1)},${h - pad} L${pts.split(" ").join(" L")} L${xs(last.i).toFixed(1)},${h - pad} Z`;
    return `<svg viewBox="0 0 ${w} ${h}" class="spark" preserveAspectRatio="none">
      <path class="sparkarea" d="${area}"></path>
      <polyline class="sparkline" points="${pts}"></polyline>
      <circle class="sparkdot" cx="${xs(last.i).toFixed(1)}" cy="${ys(last.v).toFixed(1)}" r="2.5"></circle>
    </svg>`;
  }

  _css() {
    return `
      ha-card { padding: 14px 16px 16px; }
      .head { display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between; margin-bottom:10px; }
      .title { display:flex; align-items:center; gap:8px; font-size:1.05em; font-weight:600; flex-wrap:wrap; }
      .title ha-icon { color: var(--accent-color); }
      .week { font-weight:400; opacity:.6; font-size:.85em; margin-left:6px; }
      .nav { display:inline-flex; gap:2px; margin-left:2px; }
      .navbtn { border:none; background:transparent; color: var(--primary-text-color); opacity:.55;
                font-size:1.1em; line-height:1; padding:2px 7px; border-radius:8px; cursor:pointer; }
      .navbtn:hover:not(:disabled) { background: rgba(128,128,128,.15); }
      .navbtn:disabled { opacity:.2; cursor:default; }
      .modes { display:flex; background: var(--state-icon-unavailable-color, rgba(128,128,128,.15)); border-radius:999px; padding:3px; }
      .mode { border:none; background:transparent; color: var(--primary-text-color); opacity:.55;
              padding:6px 12px; border-radius:999px; cursor:pointer; font-size:.85em; }
      .mode.on { background: var(--card-background-color, #fff); opacity:1; box-shadow: 0 1px 4px rgba(0,0,0,.25); }
      .warn { background: color-mix(in srgb, #ff9f0a 18%, transparent); color: var(--primary-text-color);
              border-radius:8px; padding:6px 10px; font-size:.8em; margin-bottom:8px; }
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
      .heatwrap { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-top:10px; flex-wrap:wrap; }
      .heatlabel { font-size:.75em; opacity:.6; }
      .heat { display:flex; gap:3px; }
      .hcell { width:16px; height:16px; border-radius:4px; background: rgba(128,128,128,.15); }
      .hcell.h1 { background: color-mix(in srgb, var(--accent-color, #4caf50) 25%, transparent); }
      .hcell.h2 { background: color-mix(in srgb, var(--accent-color, #4caf50) 50%, transparent); }
      .hcell.h3 { background: color-mix(in srgb, var(--accent-color, #4caf50) 75%, transparent); }
      .hcell.h4 { background: var(--accent-color, #4caf50); }
      .planweek { margin-top:10px; }
      .pw-label { font-size:.75em; opacity:.6; }
      .pdays { display:flex; gap:4px; margin-top:4px; }
      .pday { flex:1; min-width:0; border-radius:8px; padding:6px 4px; text-align:center;
              background: rgba(128,128,128,.08); }
      .pday.on { background: color-mix(in srgb, var(--accent-color, #4caf50) 14%, transparent); }
      .pd-day { display:block; font-size:.7em; opacity:.6; text-transform:capitalize; }
      .pd-name { display:block; font-size:.72em; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .pd-sub { display:block; font-size:.68em; opacity:.55; }
      .pd-rest { display:block; font-size:.72em; opacity:.35; }
      .detail { margin-top:12px; border:1px solid rgba(128,128,128,.2); border-radius:12px; padding:10px 12px; }
      .detail-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
      .detail-title { font-weight:600; }
      .detail-close { border:none; background:transparent; color: var(--primary-text-color); opacity:.5; cursor:pointer; font-size:1em; }
      .dgrid { display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:8px; }
      .dstat { display:flex; flex-direction:column; gap:2px; }
      .dl { font-size:.7em; opacity:.55; }
      .dv { font-size:.9em; }
      .fchip { padding:1px 8px; border-radius:99px; font-size:.85em; }
      .fchip.ready { background: color-mix(in srgb, #30d158 25%, transparent); }
      .fchip.recovering { background: color-mix(in srgb, #ffd60a 30%, transparent); }
      .fchip.fatigued { background: color-mix(in srgb, #ff453a 30%, transparent); }
      .fatbar { height:5px; border-radius:99px; background: rgba(128,128,128,.18); margin-top:8px; overflow:hidden; }
      .fatfill { height:100%; border-radius:99px; background: linear-gradient(90deg, #30d158, #ffd60a, #ff453a); }
      .trend { margin-top:10px; }
      svg.spark { width:100%; height:44px; display:block; }
      .sparkline { fill:none; stroke: var(--accent-color, #4caf50); stroke-width:2; }
      .sparkarea { fill: color-mix(in srgb, var(--accent-color, #4caf50) 14%, transparent); }
      .sparkdot { fill: var(--accent-color, #4caf50); }
      .exlist { margin-top:10px; }
      .exrow { display:flex; align-items:center; gap:8px; padding:3px 0; }
      .exname { flex:0 0 160px; font-size:.8em; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
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
      @media (max-width: 600px) {
        svg.body { height: 220px; } .name { flex-basis: 110px; }
        .exname { flex-basis: 110px; }
        .pday { padding:4px 2px; }
      }
    `;
  }
}

customElements.define(TAG, OpenGymMuscleCard);

/**
 * openGym Week Card — Plan und Realität nebeneinander als Wochenansicht.
 *
 * Zeigt die nächsten N Tage: geplannte Routine (aus calendar/plan) und
 * absolvierte Einheit (aus workout_history), plus Volumen-Achse.
 *
 *   type: custom:opengym-week-card
 *   entity: sensor.opengym_muscle_balance   # Datenlieferant (day_view)
 *   days: 14                                # Tage ab heute (Default 14)
 */
const WEEK_TAG = "opengym-week-card";

class OpenGymWeekCard extends HTMLElement {
  static getConfigElement() { return document.createElement("opengym-week-card-editor"); }
  static getStubConfig() { return { entity: "sensor.opengym_muscle_balance", days: 14 }; }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    this._cfg = { entity: "sensor.opengym_muscle_balance", days: 14, ...config };
  }

  getCardSize() { return 4; }

  set hass(hass) {
    this._hass = hass;
    if (!this._cfg) this.setConfig({});
    this._render();
  }

  _lang() {
    const l = (this._hass && this._hass.language) || "de";
    return l.split("-")[0] === "en" ? "en" : "de";
  }

  _render() {
    const t = this._lang() === "en"
      ? { title: "Training week", planned: "planned", done: "done", rest: "rest", today: "Today", vol: "vol" }
      : { title: "Trainingswoche", planned: "Plan", done: "gemacht", rest: "Ruhetag", today: "Heute", vol: "Volumen" };
    const st = this._hass?.states?.[this._cfg.entity];
    if (!st || st.state === "unavailable") {
      this._root.innerHTML = `<ha-card><div class="empty">Keine openGym-Daten.</div></ha-card>`;
      return;
    }
    const days = (st.attributes?.day_view || []).slice(0, Math.max(1, this._cfg.days));
    const maxVol = Math.max(1, ...days.map((d) => (d.done && d.done.volume) || 0));
    const todayIso = new Date().toISOString().slice(0, 10);
    const rows = days.map((d) => {
      const day = new Date(d.date + "T00:00:00");
      const label = day.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
      const isToday = d.date === todayIso;
      const plan = d.planned
        ? `<span class="pl">${d.emoji ? d.emoji + " " : ""}${d.planned}</span>`
        : `<span class="rest">${t.rest}</span>`;
      const done = d.done
        ? `<span class="ok">✓ ${d.done.name}</span><span class="vol">${Math.round(d.done.volume || 0)}</span>`
        : plan;
      const bar = d.done
        ? `<div class="vbar"><div class="vfill" style="width:${Math.min(100, ((d.done.volume || 0) / maxVol) * 100)}%"></div></div>`
        : "";
      return `<div class="wrow${isToday ? " today" : ""}">
        <span class="wday">${label}</span>
        <span class="wplan">${done}</span>
        ${bar}
      </div>`;
    }).join("");
    this._root.innerHTML = `
      <style>
        ha-card { padding: 14px 16px 16px; }
        .head { display:flex; align-items:center; gap:8px; font-weight:600; margin-bottom:8px; }
        .head ha-icon { color: var(--accent-color); }
        .wrow { display:flex; align-items:center; gap:10px; padding:6px 2px; border-bottom:1px solid rgba(128,128,128,.12); }
        .wrow:last-child { border-bottom:none; }
        .wrow.today { background: color-mix(in srgb, var(--accent-color, #4caf50) 12%, transparent); border-radius:8px; }
        .wday { flex: 0 0 130px; font-size:.85em; opacity:.8; }
        .wplan { flex: 1; font-size:.9em; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .wplan .pl { font-weight:600; }
        .wplan .ok { color: var(--accent-color, #4caf50); font-weight:600; }
        .wplan .rest { opacity:.4; }
        .vol { font-size:.75em; opacity:.55; margin-left:6px; }
        .vbar { flex: 0 0 90px; height:5px; border-radius:99px; background: rgba(128,128,128,.18); overflow:hidden; }
        .vfill { height:100%; background: var(--accent-color, #4caf50); border-radius:99px; }
        .empty { padding: 20px; opacity:.7; }
        @media (max-width: 600px) { .wday { flex-basis: 90px; } .vbar { display:none; } }
      </style>
      <ha-card>
        <div class="head"><ha-icon icon="mdi:calendar-week"></ha-icon><span>${t.title}</span></div>
        ${rows}
      </ha-card>`;
  }
}
customElements.define(WEEK_TAG, OpenGymWeekCard);

class OpenGymWeekCardEditor extends HTMLElement {
  connectedCallback() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      const form = document.createElement("ha-form");
      form.schema = [
        { name: "entity", required: true, selector: { entity: { integration: "opengym", domain: "sensor" } } },
        { name: "days", selector: { number: { min: 7, max: 30, mode: "slider" } } },
      ];
      form.addEventListener("value-changed", (ev) => {
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: ev.detail.value }, bubbles: true, composed: true }));
      });
      this.shadowRoot.appendChild(form);
    }
    this._form = this.shadowRoot.querySelector("ha-form");
    if (this._cfg) this._form.data = this._cfg;
  }
  setConfig(config) {
    this._cfg = { days: 14, ...config };
    if (this._form) this._form.data = this._cfg;
  }
}
customElements.define("opengym-week-card-editor", OpenGymWeekCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: WEEK_TAG,
  name: "openGym Week Card",
  preview: false,
  description: "Trainingswoche: geplannte Routinen und gemachte Workdays nebeneinander, mit Volumen-Achse.",
});

// Editor: minimal — entity, body, mode, toggles.
const EDITOR_SCHEMA = [
  { name: "entity", required: true, selector: { entity: { integration: "opengym", domain: "sensor" } } },
  { name: "body", selector: { select: { options: ["male", "female"], mode: "dropdown" } } },
  { name: "mode", selector: { select: { options: ["sets", "recovery", "strength", "planned"], mode: "dropdown" } } },
  { name: "show_list", selector: { boolean: {} } },
  { name: "show_week", selector: { boolean: {} } },
  { name: "show_heatmap", selector: { boolean: {} } },
  { name: "show_detail", selector: { boolean: {} } },
  { name: "show_plan_week", selector: { boolean: {} } },
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
    this._cfg = {
      body: "male", mode: "sets", show_list: true, show_week: true,
      show_heatmap: true, show_detail: true, show_plan_week: true, ...config,
    };
    if (this._form) this._form.data = this._cfg;
  }
}
customElements.define("opengym-muscle-card-editor", OpenGymMuscleCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: TAG,
  name: "openGym Muscle Card",
  preview: false,
  description: "Muskelbalance, Erholung, Kraft und Plan als echte openGym-Körperkarte — mit Wochenrückblick, Detail-Panel und 12-Wochen-Heatmap.",
});
