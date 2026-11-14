/**
 * openGym Cards — Muskelbalance und Trainingswoche live im Dashboard.
 *
 * Drei Karten, ein Modul (keine externen Abhängigkeiten, CSP-sicher):
 *
 *   type: custom:opengym-muscle-card
 *   entity: sensor.opengym_muscle_balance   # Default, darf weggelassen werden
 *   title: Muskelbalance       # eigener Titel (Default: übersetzt)
 *   body: male | female        # Körpermodell (Default male)
 *   mode: sets | recovery | strength | planned
 *   show_stats: true           # Kennzahlen (Sätze, Volumen, Serie, Zuletzt, PRs, Puls, Gewicht)
 *   show_list: true            # Muskelliste unter der Karte
 *   list_limit: 8              # Zeilen bis „Alle anzeigen“ (0 = alle)
 *   show_week: true            # Wochenzeile mit Pfeil-Navigation
 *   show_legend: true          # Farblegende unter der Körperkarte
 *   show_heatmap: true         # 12-Wochen-Trainings-Heatmap
 *   show_detail: true          # Detail-Panel beim Klick auf einen Muskel
 *   show_plan_week: true       # Wochenplan-Leiste im Geplant-Modus
 *   accent: "#a3e635"          # Akzentfarbe (Default: HA-Primärfarbe)
 *
 *   type: custom:opengym-week-card
 *   entity: sensor.opengym_muscle_balance   # Datenlieferant (day_view)
 *   title: Trainingswoche
 *   days: 14                                # Tage ab Montag dieser Woche
 *   accent: "#a3e635"
 *
 *   type: custom:opengym-next-card
 *   entity: sensor.opengym_next_session     # Default
 *   title: Nächstes Training
 *   max_exercises: 6                        # 0 = alle
 *   show_muscles: true                      # Muskel-Chips
 *   show_rest_button: true                  # Knopf „Pausentimer starten“ (opengym.start_rest_timer)
 */

const TAG = "opengym-muscle-card";
const WEEK_TAG = "opengym-week-card";
const CARD_VERSION = "0.10.1";
const DEFAULT_ENTITY = "sensor.opengym_muscle_balance";

const SLUGS = [
  "trapezius", "deltoids", "chest", "upper-back", "serratus",
  "biceps", "triceps", "forearm",
  "abs", "obliques", "lower-back",
  "gluteal", "quadriceps", "hamstring", "adductors", "hip-flexors",
  "calves", "tibialis",
];

// Muskelnamen nach Sprache — Englisch greift als Fallback.
const NAMES = {
  de: {
    trapezius: "Trapez", deltoids: "Schultern", chest: "Brust", "upper-back": "Oberer Rücken",
    serratus: "Serratus", biceps: "Bizeps", triceps: "Trizeps", forearm: "Unterarme",
    abs: "Bauch", obliques: "Seitliche Bauchmuskeln", "lower-back": "Unterer Rücken", gluteal: "Gesäß",
    quadriceps: "Beinstrecker", hamstring: "Beinbeuger", adductors: "Adduktoren",
    "hip-flexors": "Hüftbeuger", calves: "Waden", tibialis: "Schienbein",
  },
  en: {
    trapezius: "Trapezius", deltoids: "Shoulders", chest: "Chest", "upper-back": "Upper back",
    serratus: "Serratus", biceps: "Biceps", triceps: "Triceps", forearm: "Forearms",
    abs: "Core", obliques: "Obliques", "lower-back": "Lower back", gluteal: "Glutes",
    quadriceps: "Quadriceps", hamstring: "Hamstrings", adductors: "Adductors",
    "hip-flexors": "Hip flexors", calves: "Calves", tibialis: "Tibialis",
  },
};

const UI = {
  de: {
    modes: { sets: "Sätze", recovery: "Erholung", strength: "Kraft", planned: "Geplant" },
    modesLabel: "Ansicht", title: "Muskelbalance", weekTitle: "Trainingswoche",
    less: "Weniger", more: "Mehr", fresh: "Gerade trainiert", stale: "Lange her", never: "nie",
    today: "heute", yesterday: "gestern", daysAgo: (n) => `vor ${n} Tagen`,
    weekOf: "Woche ab", thisWeek: "Diese Woche", prevWeek: "Vorherige Woche", nextWeek: "Nächste Woche",
    setsUnit: "Sätze", rest: "Ruhetag", planWeek: "Wochenplan", front: "Vorne", back: "Hinten",
    stats: { sets: "Sätze", volume: "Volumen", workouts: "Einheiten", streak: "Serie", last: "Zuletzt",
      prs: "PRs (Woche)", hr: "Ø Puls", weight: "Gewicht", goal: (d) => `${d} zum Ziel`, atGoal: "Ziel erreicht",
      days: (n) => (n === 1 ? "1 Tag" : `${n} Tage`), weeks: (n) => (n === 1 ? "1 Woche" : `${n} Wochen`) },
    next: { title: "Nächstes Training", none: "Kein Training geplant", noneHint: "Genieß den Ruhetag.",
      tomorrow: "morgen", inDays: (n) => `in ${n} Tagen`, exercises: "Übungen", sets: "Sätze", rest: "Pause",
      startRest: "Pausentimer starten", restStarted: "Pausentimer läuft", more: (n) => `+ ${n} weitere`,
      progress: "Fortschritt", restEnds: "Pause endet" },
    live: "Training läuft",
    detail: { week: "Sätze diese Woche", last: "Zuletzt trainiert", fatigue: "Ermüdung",
      best: "Bestes 1RM", trend: "1RM-Verlauf · 12 Wochen", exercises: "Übungen (Wochen-Sätze)",
      close: "Schließen", history: "Verlauf öffnen",
      state: { ready: "Erholt", recovering: "Erholt sich", fatigued: "Ermüdet" } },
    status: { below: "unter Ziel", within: "im Ziel", above: "über Ziel" },
    heatmap: "Letzte 12 Wochen", heatCell: (d, s, w) => `Woche ab ${d}: ${s} Sätze, ${w} Einheiten`,
    versionWarn: "Im Browser läuft eine alte Kartenversion — bitte Seite neu laden bzw. Cache leeren.",
    missing: "Entität nicht gefunden",
    missingHint: "Prüfe die openGym-Integration oder wähle im Karten-Editor eine andere Entität.",
    unavailable: "openGym ist gerade nicht erreichbar",
    unavailableHint: "Die Daten erscheinen wieder, sobald die Verbindung steht.",
    emptyWeek: "In dieser Woche noch keine Sätze — Zeit fürs Training!", emptyPlan: "Kein Training geplant.",
    emptyStrength: "Noch keine Kraftwerte erfasst.",
    retry: "Erneut laden", geoFail: "Körpergeometrie konnte nicht geladen werden.", loading: "Lade …",
    showAll: (n) => `Alle ${n} anzeigen`, showLess: "Weniger anzeigen",
    planned: "Geplant", done: "Erledigt", missed: "Verpasst", todayLabel: "Heute",
    weekSummary: (d, p) => `${d} von ${p} Einheiten diese Woche`, noDays: "Keine Tage im Plan.",
  },
  en: {
    modes: { sets: "Sets", recovery: "Recovery", strength: "Strength", planned: "Planned" },
    modesLabel: "View", title: "Muscle balance", weekTitle: "Training week",
    less: "Less", more: "More", fresh: "Just trained", stale: "Long ago", never: "never",
    today: "today", yesterday: "yesterday", daysAgo: (n) => `${n} days ago`,
    weekOf: "Week of", thisWeek: "This week", prevWeek: "Previous week", nextWeek: "Next week",
    setsUnit: "sets", rest: "Rest day", planWeek: "Weekly plan", front: "Front", back: "Back",
    stats: { sets: "Sets", volume: "Volume", workouts: "Workouts", streak: "Streak", last: "Last",
      prs: "PRs (week)", hr: "Avg HR", weight: "Weight", goal: (d) => `${d} to goal`, atGoal: "Goal reached",
      days: (n) => (n === 1 ? "1 day" : `${n} days`), weeks: (n) => (n === 1 ? "1 week" : `${n} weeks`) },
    next: { title: "Next workout", none: "No workout planned", noneHint: "Enjoy the rest day.",
      tomorrow: "tomorrow", inDays: (n) => `in ${n} days`, exercises: "Exercises", sets: "Sets", rest: "Rest",
      startRest: "Start rest timer", restStarted: "Rest timer running", more: (n) => `+ ${n} more`,
      progress: "Progress", restEnds: "Rest ends" },
    live: "Workout in progress",
    detail: { week: "Sets this week", last: "Last trained", fatigue: "Fatigue",
      best: "Best 1RM", trend: "1RM trend · 12 weeks", exercises: "Exercises (weekly sets)",
      close: "Close", history: "Open history",
      state: { ready: "Ready", recovering: "Recovering", fatigued: "Fatigued" } },
    status: { below: "below target", within: "on target", above: "above target" },
    heatmap: "Last 12 weeks", heatCell: (d, s, w) => `Week of ${d}: ${s} sets, ${w} workouts`,
    versionWarn: "Your browser runs a stale card version — reload the page or clear the cache.",
    missing: "Entity not found",
    missingHint: "Check the openGym integration or pick another entity in the card editor.",
    unavailable: "openGym is currently unavailable",
    unavailableHint: "Data will come back as soon as the connection is restored.",
    emptyWeek: "No sets yet this week — time to train!", emptyPlan: "No training planned.",
    emptyStrength: "No strength data yet.",
    retry: "Retry", geoFail: "Body geometry failed to load.", loading: "Loading …",
    showAll: (n) => `Show all ${n}`, showLess: "Show less",
    planned: "Planned", done: "Done", missed: "Missed", todayLabel: "Today",
    weekSummary: (d, p) => `${d} of ${p} sessions this week`, noDays: "No days in the plan.",
  },
};

const EDITOR_LABELS = {
  de: {
    entity: "Entität", title: "Titel (optional)", body: "Körpermodell", mode: "Startansicht",
    accent: "Akzentfarbe (CSS, optional)", show_stats: "Kennzahlen im Kopf", show_list: "Muskelliste",
    list_limit: "Listenzeilen bis „Alle anzeigen“ (0 = alle)", show_week: "Wochen-Navigation",
    show_legend: "Farblegende", show_heatmap: "12-Wochen-Heatmap", show_detail: "Detail-Panel bei Klick",
    show_plan_week: "Wochenplan im Geplant-Modus", days: "Anzahl Tage", display: "Anzeige",
    look: "Aussehen", male: "Männlich", female: "Weiblich",
    max_exercises: "Max. Übungen (0 = alle)", show_muscles: "Muskel-Chips", show_rest_button: "Pausentimer-Knopf",
  },
  en: {
    entity: "Entity", title: "Title (optional)", body: "Body model", mode: "Initial view",
    accent: "Accent colour (CSS, optional)", show_stats: "Header stats", show_list: "Muscle list",
    list_limit: "List rows before “Show all” (0 = all)", show_week: "Week navigation",
    show_legend: "Colour legend", show_heatmap: "12-week heatmap", show_detail: "Detail panel on tap",
    show_plan_week: "Weekly plan in planned view", days: "Number of days", display: "Display",
    look: "Appearance", male: "Male", female: "Female",
    max_exercises: "Max exercises (0 = all)", show_muscles: "Muscle chips", show_rest_button: "Rest timer button",
  },
};

const MODES = ["sets", "recovery", "strength", "planned"];
const MUSCLE_DEFAULTS = {
  entity: DEFAULT_ENTITY, body: "male", mode: "sets",
  show_stats: true, show_list: true, list_limit: 8, show_week: true, show_legend: true,
  show_heatmap: true, show_detail: true, show_plan_week: true,
};
const WEEK_DEFAULTS = { entity: DEFAULT_ENTITY, days: 14 };
const NEXT_TAG = "opengym-next-card";
const DEFAULT_NEXT_ENTITY = "sensor.opengym_next_session";
const NEXT_DEFAULTS = { entity: DEFAULT_NEXT_ENTITY, max_exercises: 6, show_muscles: true, show_rest_button: true };

// --- shared helpers ---------------------------------------------------------

let GEO = null;          // geometry cache shared by all cards
let GEO_PROMISE = null;  // in-flight fetch, so several cards fetch once
let GEO_FAILED = false;

function geoUrl() {
  try { return new URL("body-geometry.json", import.meta.url).href; }
  catch { return "/opengym/body-geometry.json"; }
}

function loadGeometry() {
  if (GEO) return Promise.resolve(GEO);
  if (!GEO_PROMISE) {
    GEO_FAILED = false;
    GEO_PROMISE = fetch(geoUrl())
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((g) => { GEO = g; return g; })
      .catch((err) => {
        GEO_FAILED = true;
        GEO_PROMISE = null;
        console.error(`${TAG}: body geometry failed`, err);
        return null;
      });
  }
  return GEO_PROMISE;
}

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
function esc(v) { return v == null ? "" : String(v).replace(/[&<>"']/g, (c) => ESC[c]); }

function rawLang(hass) { return (hass && (hass.locale?.language || hass.language)) || "de"; }

// openGym keeps an icon *key* in a routine's `emoji` field (frontend/src/lib/glyphs.js), older
// profiles an emoji. The integration sends the matching `icon`; this table is the fallback for
// attributes without one. A raw key is never printed.
const GLYPH_MDI = {
  figureStrength: "mdi:weight-lifter", arm: "mdi:arm-flex", abs: "mdi:human", legs: "mdi:walk",
  pullup: "mdi:human-handsup", dumbbell: "mdi:dumbbell", barbell: "mdi:weight-lifter",
  kettlebell: "mdi:kettlebell", plate: "mdi:circle-double", machine: "mdi:cog",
  figureRun: "mdi:run", bike: "mdi:bike", swim: "mdi:swim", boxing: "mdi:boxing-glove",
  timer: "mdi:timer-outline", stretch: "mdi:yoga", moon: "mdi:weather-night", heart: "mdi:heart-pulse",
  flame: "mdi:fire", bolt: "mdi:lightning-bolt", trophy: "mdi:trophy", medal: "mdi:medal",
  crown: "mdi:crown", flag: "mdi:flag-checkered", star: "mdi:star", target: "mdi:target", shield: "mdi:shield",
};
const GLYPH_LEGACY = {
  "💪": "arm", "🦾": "arm", "🫸": "figureStrength", "🫷": "pullup", "🏋": "dumbbell",
  "🦵": "legs", "🍑": "legs", "🔥": "flame", "⚡": "bolt", "💥": "bolt", "🧨": "bolt", "😤": "flame",
  "🏃": "figureRun", "🚴": "bike", "🏊": "swim", "🤸": "stretch", "🧘": "stretch", "🥊": "boxing",
  "🧗": "pullup", "⛰": "figureRun", "🏔": "figureRun", "🚀": "bolt", "🎯": "target", "🏆": "trophy",
  "🥇": "medal", "⭐": "star", "🌟": "star", "👑": "crown", "🛡": "shield", "⚔": "shield", "❤": "heart",
  "🦍": "kettlebell", "🐂": "barbell", "🐻": "kettlebell", "🦁": "boxing", "🐺": "figureRun",
  "🦈": "swim", "🤖": "machine",
};
function routineIcon(o) {
  if (o && typeof o.icon === "string" && o.icon.startsWith("mdi:")) return o.icon;
  const raw = o && typeof o.emoji === "string" ? o.emoji.trim() : "";
  if (!raw) return GLYPH_MDI.figureStrength;
  if (GLYPH_MDI[raw]) return GLYPH_MDI[raw];
  const base = [...raw].filter((ch) => ch !== "\ufe0f" && ch !== "\u200d")[0];
  return GLYPH_MDI[GLYPH_LEGACY[base]] || "mdi:dumbbell";
}
// An exercise's name in the dashboard user's language (the integration sends `names`).
function exName(hass, ex) {
  const n = ex && ex.names;
  if (n && typeof n === "object") return n[langOf(hass)] || n.en || ex.name || "";
  return (ex && ex.name) || "";
}
function langOf(hass) { const l = rawLang(hass).split("-")[0]; return UI[l] ? l : "en"; }

function num(hass, n, digits = 1) {
  if (n == null || n === "" || Number.isNaN(Number(n))) return "–";
  try { return new Intl.NumberFormat(rawLang(hass), { maximumFractionDigits: digits }).format(Number(n)); }
  catch { return String(Math.round(Number(n) * 10) / 10); }
}

function compact(hass, n) {
  if (n == null || n === "" || Number.isNaN(Number(n))) return "–";
  const v = Number(n);
  try {
    return new Intl.NumberFormat(rawLang(hass), v >= 1000000
      ? { notation: "compact", maximumFractionDigits: 1 } : { maximumFractionDigits: 0 }).format(v);
  } catch { return String(Math.round(v)); }
}

function parseDay(iso) {
  if (!iso) return null;
  const d = new Date(String(iso).slice(0, 10) + "T00:00:00");
  return Number.isNaN(d.getTime()) ? null : d;
}

function startOfToday() { const d = new Date(); d.setHours(0, 0, 0, 0); return d; }

function daysSince(iso) {
  const d = parseDay(iso);
  if (!d) return null;
  return Math.max(0, Math.round((startOfToday() - d) / 86400000));
}

function isoDay(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function relDays(t, n) {
  if (n == null) return t.never;
  if (n === 0) return t.today;
  if (n === 1) return t.yesterday;
  return t.daysAgo(n);
}

function shortDate(hass, iso, opts = { day: "numeric", month: "short" }) {
  const d = parseDay(iso);
  if (!d) return "";
  try { return d.toLocaleDateString(rawLang(hass), opts); } catch { return String(iso); }
}

/** Sibling openGym entity on the same device (by translation_key), else a default id. */
function sibling(hass, baseEntity, keys, fallbackIds = []) {
  const reg = hass?.entities;
  const keyList = Array.isArray(keys) ? keys : [keys];
  if (reg) {
    const device = reg[baseEntity]?.device_id;
    for (const ent of Object.values(reg)) {
      if (!keyList.includes(ent.translation_key)) continue;
      if (ent.platform && ent.platform !== "opengym") continue;
      if (device && ent.device_id && ent.device_id !== device) continue;
      if (hass.states[ent.entity_id]) return ent.entity_id;
    }
  }
  for (const id of fallbackIds) if (hass?.states?.[id]) return id;
  return null;
}

function fireMoreInfo(node, entityId) {
  if (!entityId) return;
  node.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
}

const ICON_PATH = {
  left: "M15.41 16.58 10.83 12l4.58-4.59L14 6l-6 6 6 6z",
  right: "M8.59 16.58 13.17 12 8.59 7.41 10 6l6 6-6 6z",
  close: "M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
  open: "M14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3m-2 16H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7h-2z",
};
const svgIcon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${ICON_PATH[name]}"/></svg>`;

/** Shared design tokens — every value falls back to the active HA theme. */
const BASE_CSS = `
  :host { display:block; container-type:inline-size; }
  ha-card {
    --og-accent: var(--og-accent-cfg, var(--primary-color, #03a9f4));
    --og-text: var(--primary-text-color, #212121);
    --og-muted: var(--secondary-text-color, #727272);
    --og-divider: var(--divider-color, rgba(127,127,127,.2));
    --og-surface: rgba(var(--rgb-primary-text-color, 127,127,127), .05);
    --og-surface-2: rgba(var(--rgb-primary-text-color, 127,127,127), .09);
    --og-track: rgba(var(--rgb-primary-text-color, 127,127,127), .12);
    --og-bg: var(--ha-card-background, var(--card-background-color, #fff));
    --og-radius: var(--ha-card-border-radius, 12px);
    --og-radius-sm: calc(var(--og-radius) * .66);
    --og-good: var(--success-color, #43a047);
    --og-warn: var(--warning-color, #ffa600);
    --og-bad: var(--error-color, #db4437);
    --og-mid: #fdd835;
    --og-ease: cubic-bezier(.2,.7,.3,1);
    height:100%; box-sizing:border-box; padding:16px; overflow:hidden;
    display:flex; flex-direction:column; gap:14px; color: var(--og-text);
  }
  button { font:inherit; color:inherit; }
  :focus-visible { outline: 2px solid var(--og-accent); outline-offset: 2px; }
  .head { display:flex; align-items:center; gap:12px; min-width:0; }
  .badge { flex:none; width:40px; height:40px; border-radius:50%; display:grid; place-items:center;
           color: var(--og-accent); background: color-mix(in srgb, var(--og-accent) 18%, transparent); --mdc-icon-size: 22px; }
  .titles { min-width:0; flex:1; display:flex; flex-direction:column; gap:1px; }
  .title { font-size:16px; font-weight:500; line-height:1.3; letter-spacing:.1px;
           white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .subtitle { font-size:13px; color: var(--og-muted); display:flex; align-items:center; gap:2px; min-height:24px; min-width:0; }
  .iconbtn { border:none; background:transparent; width:28px; height:28px; border-radius:50%; cursor:pointer; flex:none;
             display:inline-grid; place-items:center; color: var(--og-muted); transition: background .15s, color .15s; padding:0; }
  .iconbtn:hover:not(:disabled) { background: var(--og-surface-2); color: var(--og-text); }
  .iconbtn:disabled { opacity:.3; cursor:default; }
  .iconbtn svg { width:18px; height:18px; fill: currentColor; }
  .state { display:flex; flex-direction:column; align-items:center; text-align:center; gap:6px; padding:28px 12px; color: var(--og-muted); font-size:14px; }
  .state .badge { width:48px; height:48px; margin-bottom:4px; }
  .state.err .badge { color: var(--og-warn); background: color-mix(in srgb, var(--og-warn) 16%, transparent); }
  .state b { color: var(--og-text); font-weight:500; font-size:15px; }
  .state code { font-size:12px; background: var(--og-surface-2); padding:2px 6px; border-radius:6px; }
  .live { display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:500; padding:4px 10px; border-radius:999px;
          color: var(--og-bad); background: color-mix(in srgb, var(--og-bad) 14%, transparent); border:none; cursor:pointer; white-space:nowrap; }
  .live i { width:8px; height:8px; border-radius:50%; background: currentColor; animation: og-pulse 1.6s ease-in-out infinite; }
  @keyframes og-pulse { 50% { opacity:.35; transform: scale(.8); } }
  @keyframes og-shimmer { to { background-position: -200% 0; } }
  @keyframes og-in { from { opacity:0; transform: translateY(4px); } to { opacity:1; transform:none; } }
  .bar { position:relative; height:8px; border-radius:999px; background: var(--og-track); overflow:hidden; }
  .bar .fill { position:absolute; inset:0 auto 0 0; border-radius:999px; background: var(--og-accent); transition: width .45s var(--og-ease); }
  @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation:none !important; transition:none !important; } }
`;

/** Base: shadow DOM, change-detected rendering, focus restore, error states. */
class OpenGymBase extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._sig = null;
  }

  get _t() { return UI[langOf(this._hass)]; }

  set hass(hass) {
    this._hass = hass;
    if (!this._cfg) this.setConfig({});
    const sig = this._signature();
    if (sig === this._sig) return; // nothing relevant changed — keep the DOM (and focus) as is
    this._sig = sig;
    this._render();
  }

  get hass() { return this._hass; }

  _watched() { return [this._cfg.entity]; }

  _signature() {
    const st = this._hass?.states || {};
    // HA replaces a state object on every change, so last_updated is a cheap change marker.
    return this._watched().map((id) => {
      const s = id && st[id];
      return s ? `${id}:${s.state}:${s.last_updated}` : `${id}:-`;
    }).join("|") + `|${rawLang(this._hass)}`;
  }

  _rerender() { if (!this._hass) return; this._sig = this._signature(); this._render(); }

  /** Swap the shadow DOM, keeping the focused control focused. */
  _paint(html) {
    const key = this.shadowRoot.activeElement?.dataset?.fk;
    this.shadowRoot.innerHTML = html;
    if (key) {
      const el = this.shadowRoot.querySelector(`[data-fk="${CSS.escape(key)}"]`);
      if (el) el.focus({ preventScroll: true });
    }
  }

  _accentStyle() {
    const a = this._cfg.accent;
    return a && /^[#a-zA-Z0-9(),.%\s-]+$/.test(String(a)) ? ` style="--og-accent-cfg:${esc(a)}"` : "";
  }

  _stateCard(kind, icon) {
    const t = this._t;
    const [head, hint] = kind === "missing" ? [t.missing, t.missingHint] : [t.unavailable, t.unavailableHint];
    return `<style>${BASE_CSS}</style>
      <ha-card${this._accentStyle()}>
        <div class="state err" role="status">
          <div class="badge"><ha-icon icon="${icon}"></ha-icon></div>
          <b>${esc(head)}</b><span>${esc(hint)}</span><code>${esc(this._cfg.entity)}</code>
        </div>
      </ha-card>`;
  }

  _checkEntity() {
    const st = this._hass.states[this._cfg.entity];
    if (!st) { this._paint(this._stateCard("missing", "mdi:help-circle-outline")); return null; }
    if (st.state === "unavailable" || st.state === "unknown") {
      this._paint(this._stateCard("unavailable", "mdi:cloud-off-outline"));
      return null;
    }
    return st;
  }
}

// --- Muscle card ---------------------------------------------------------------

class OpenGymMuscleCard extends OpenGymBase {
  static getConfigElement() { return document.createElement("opengym-muscle-card-editor"); }

  static getStubConfig(hass) {
    const found = hass && Object.values(hass.entities || {})
      .find((e) => e.platform === "opengym" && e.translation_key === "muscle_balance");
    return { entity: found ? found.entity_id : DEFAULT_ENTITY };
  }

  constructor() {
    super();
    this._mode = null;
    this._sel = null;
    this._detailData = null;
    this._weekOffset = 0;
    this._expanded = false;
    this._versionMismatch = false;
    this._versionChecked = false;
    this._onKey = (ev) => {
      if (ev.key === "Escape" && this._sel) { this._sel = null; this._rerender(); }
    };
  }

  setConfig(config) {
    if (config && config.mode && !MODES.includes(config.mode)) {
      throw new Error(`opengym-muscle-card: unknown mode "${config.mode}" (${MODES.join(", ")})`);
    }
    this._cfg = { ...MUSCLE_DEFAULTS, ...(config || {}) };
    if (!this._cfg.entity) this._cfg.entity = DEFAULT_ENTITY;
    this._mode = null;
    this._rerender();
  }

  getCardSize() {
    const c = this._cfg || MUSCLE_DEFAULTS;
    let size = 7;
    if (c.show_stats !== false) size += 1;
    if (c.show_heatmap !== false) size += 1;
    if (c.show_list !== false) size += Math.min(Number(c.list_limit) || 18, 18) / 2;
    return Math.ceil(size);
  }

  // Sections view (HA 2024.11+): full width by default, at least half.
  getGridOptions() { return { columns: 12, min_columns: 6, min_rows: 6 }; }
  // Older sections view API
  getLayoutOptions() { return { grid_columns: 4, grid_min_columns: 2 }; }

  connectedCallback() { this.addEventListener("keydown", this._onKey); }
  disconnectedCallback() { this.removeEventListener("keydown", this._onKey); }

  _watched() {
    const h = this._hass, e = this._cfg.entity;
    this._ids = {
      volume: sibling(h, e, "week_volume", ["sensor.opengym_week_volume"]),
      workouts: sibling(h, e, "week_workouts", ["sensor.opengym_week_workouts"]),
      streak: sibling(h, e, "streak", ["sensor.opengym_streak"]),
      weekStreak: sibling(h, e, "week_streak", ["sensor.opengym_week_streak"]),
      last: sibling(h, e, "last_workout", ["sensor.opengym_last_workout"]),
      live: sibling(h, e, "active_workout", ["binary_sensor.opengym_active_workout"]),
      hr: sibling(h, e, "workout_heart_rate", ["sensor.opengym_workout_heart_rate"]),
      weight: sibling(h, e, "last_weighin", ["sensor.opengym_last_weigh_in"]),
      prs: sibling(h, e, "personal_records", ["sensor.opengym_personal_records"]),
    };
    return [e, ...Object.values(this._ids)];
  }

  // --- data -----------------------------------------------------------------

  async _checkVersion() {
    if (this._versionChecked || !this._hass) return;
    this._versionChecked = true;
    try {
      const conn = this._hass.connection;
      if (!conn || !conn.sendMessagePromise) return;
      const res = await conn.sendMessagePromise({ type: "opengym:version" });
      if (res && res.version && res.version !== CARD_VERSION) {
        this._versionMismatch = true;
        this._rerender();
      }
    } catch { /* old backend without WS command — stay silent */ }
  }

  async _loadDetail(muscle) {
    this._detailData = null;
    try {
      const conn = this._hass?.connection;
      if (conn && conn.sendMessagePromise) {
        // entry_id (from the sensor) keeps several openGym profiles apart
        const msg = { type: "opengym:detail", muscle };
        const entryId = this._hass.states[this._cfg.entity]?.attributes?.entry_id;
        if (entryId) msg.entry_id = entryId;
        else msg.entity_id = this._cfg.entity;
        const data = await conn.sendMessagePromise(msg);
        if (this._sel === muscle && data) { this._detailData = data; this._rerender(); }
      }
    } catch { /* attribute fallback stays visible */ }
  }

  _detailFallback(muscle, a) {
    const f = (a.fatigue || {})[muscle] || 0;
    return {
      week_sets: (a.sets || {})[muscle] || 0,
      target: (a.targets || {})[muscle] || null,
      last_trained: (a.last_trained || {})[muscle] || null,
      fatigue: f,
      fatigue_state: f > 0.5 ? "fatigued" : f >= 0.25 ? "recovering" : "ready",
      best_1rm: (a.best_1rm || {})[muscle] || null,
      trend: (a.trends || {})[muscle] || [],
      exercises: {},
    };
  }

  _histWeek(a) {
    const hist = a.history || [];
    return this._weekOffset < 0 ? hist[hist.length - 1 + this._weekOffset] || null : null;
  }

  _values(a, mode) {
    const out = {};
    if (mode === "sets") {
      const src = this._weekOffset < 0 ? (this._histWeek(a)?.muscles || {}) : (a.sets || {});
      for (const s of SLUGS) out[s] = Number(src[s]) || 0;
    } else if (mode === "recovery") {
      const last = a.last_trained || {};
      for (const s of SLUGS) { const d = daysSince(last[s]); out[s] = d == null ? -1 : d; }
    } else if (mode === "planned") {
      const p = a.planned || {};
      for (const s of SLUGS) out[s] = Number(p[s]) || 0;
    } else {
      const rm = a.best_1rm || {};
      for (const s of SLUGS) out[s] = Number(rm[s]) || 0;
    }
    return out;
  }

  _levels(values, mode) {
    const lv = {};
    const pos = Object.values(values).filter((v) => v > 0);
    const max = pos.length ? Math.max(...pos) : 0;
    for (const s of SLUGS) {
      const v = values[s];
      if (mode === "recovery") {
        lv[s] = v < 0 ? 0 : v <= 1 ? 4 : v <= 2 ? 3 : v <= 4 ? 2 : v <= 7 ? 1 : 0;
      } else if (v <= 0) {
        lv[s] = 0;
      } else {
        const f = max ? v / max : 0;
        lv[s] = f >= 0.75 ? 4 : f >= 0.5 ? 3 : f >= 0.25 ? 2 : 1;
      }
    }
    return lv;
  }

  _name(slug) { return (NAMES[langOf(this._hass)] || NAMES.en)[slug] || slug; }

  _valueText(v, mode, a) {
    const t = this._t, h = this._hass;
    if (mode === "recovery") return relDays(t, v < 0 ? null : v);
    if (mode === "strength") return v > 0 ? `${num(h, v)} ${a.unit || "kg"}` : "–";
    return `${num(h, v)} ${t.setsUnit}`;
  }

  _muscleEntity(slug) {
    const key = slug === "forearm" ? "forearms" : slug.replace(/-/g, "_");
    return sibling(this._hass, this._cfg.entity, [`muscle_${key}`]);
  }

  // --- render ---------------------------------------------------------------

  _render() {
    if (!this._hass || !this._cfg) return;
    this._checkVersion();
    const st = this._checkEntity();
    if (!st) return;
    const a = st.attributes || {};
    const t = this._t;
    const mode = this._mode || this._cfg.mode || "sets";
    const values = this._values(a, mode);
    const levels = this._levels(values, mode);
    if (!GEO && !GEO_FAILED) loadGeometry().then(() => this._rerender());
    const body = GEO ? (GEO[this._cfg.body] || GEO.male) : null;
    const c = this._cfg;

    this._paint(`
      <style>${BASE_CSS}${MUSCLE_CSS}</style>
      <ha-card${this._accentStyle()}>
        ${this._header(a, mode)}
        ${this._versionMismatch ? `<div class="warn" role="alert">${esc(t.versionWarn)}</div>` : ""}
        ${c.show_stats !== false ? this._stats(a) : ""}
        ${this._tabs(mode)}
        <div class="main">
          <div class="col-map">
            <div class="mapwrap" role="tabpanel" aria-label="${esc(t.modes[mode])}">
              ${this._map(body, levels, mode)}
              <div class="tip" role="tooltip" hidden></div>
            </div>
            ${c.show_legend !== false && body ? this._legend(mode, values, a) : ""}
          </div>
          <div class="col-side">
            ${c.show_detail !== false && this._sel ? this._detailPanel(this._sel, a) : ""}
            ${mode === "planned" && c.show_plan_week !== false && Array.isArray(a.planned_week) ? this._planWeek(a.planned_week) : ""}
            ${c.show_heatmap !== false && Array.isArray(a.history) && a.history.length ? this._heatmap(a.history, mode) : ""}
            ${c.show_list !== false ? this._list(values, mode, a) : ""}
          </div>
        </div>
      </ha-card>`);
    this._bind(values, mode, a);
  }

  _header(a, mode) {
    const t = this._t;
    const title = this._cfg.title || t.title;
    let sub = "";
    if (this._cfg.show_week !== false && mode === "sets" && a.week_start) {
      const hist = (a.history || []).length;
      const start = this._weekOffset < 0 ? this._histWeek(a)?.week_start : a.week_start;
      const label = this._weekOffset === 0 ? t.thisWeek : `${t.weekOf} ${shortDate(this._hass, start)}`;
      sub = `<button class="iconbtn" data-nav="-1" data-fk="nav-prev" aria-label="${esc(t.prevWeek)}" title="${esc(t.prevWeek)}"
               ${this._weekOffset <= -(hist - 1) ? "disabled" : ""}>${svgIcon("left")}</button>
             <span class="weeklabel" aria-live="polite">${esc(label)}</span>
             <button class="iconbtn" data-nav="1" data-fk="nav-next" aria-label="${esc(t.nextWeek)}" title="${esc(t.nextWeek)}"
               ${this._weekOffset >= 0 ? "disabled" : ""}>${svgIcon("right")}</button>`;
    } else {
      sub = `<span class="weeklabel">${esc(t.modes[mode])}${a.week_start ? ` · ${esc(t.thisWeek)}` : ""}</span>`;
    }
    const liveId = this._ids?.live;
    const live = liveId && this._hass.states[liveId]?.state === "on"
      ? `<button class="live" data-more="${esc(liveId)}" data-fk="live"><i></i>${esc(t.live)}</button>` : "";
    return `<div class="head">
        <div class="badge"><ha-icon icon="mdi:human-handsup"></ha-icon></div>
        <div class="titles"><div class="title">${esc(title)}</div><div class="subtitle">${sub}</div></div>
        ${live}
      </div>`;
  }

  _stats(a) {
    const t = this._t, h = this._hass, S = h.states, ids = this._ids || {};
    const cur = this._weekOffset < 0 ? this._histWeek(a) : null;
    const ok = (v) => v != null && v !== "" && !Number.isNaN(Number(v));
    const items = [];
    const totalSets = cur ? cur.sets : Object.values(a.sets || {}).reduce((x, y) => x + (Number(y) || 0), 0);
    items.push({ label: t.stats.sets, value: esc(num(h, totalSets)), more: this._cfg.entity });
    const vol = cur ? cur.volume : S[ids.volume]?.state;
    if (ok(vol)) items.push({ label: t.stats.volume, value: `${esc(compact(h, vol))}<small> ${esc(a.unit || "kg")}</small>`, more: cur ? null : ids.volume });
    const wk = cur ? cur.workouts : S[ids.workouts]?.state;
    if (ok(wk)) items.push({ label: t.stats.workouts, value: esc(num(h, wk, 0)), more: cur ? null : ids.workouts });
    // openGym counts its streak in weeks (lib/streak.js); days only as a fallback
    const wstreak = S[ids.weekStreak]?.state;
    const streak = S[ids.streak]?.state;
    if (ok(wstreak)) items.push({ label: t.stats.streak, value: esc(t.stats.weeks(Number(wstreak))), more: ids.weekStreak, hot: Number(wstreak) >= 4 });
    else if (ok(streak)) items.push({ label: t.stats.streak, value: esc(t.stats.days(Number(streak))), more: ids.streak, hot: Number(streak) >= 3 });
    if (!cur && ok(a.week_prs)) {
      items.push({ label: t.stats.prs, value: esc(num(h, a.week_prs, 0)), more: ids.prs, hot: Number(a.week_prs) > 0 });
    }
    if (!cur && a.last_hr && ok(a.last_hr.avg)) {
      items.push({ label: t.stats.hr, value: `${esc(num(h, a.last_hr.avg, 0))}<small> bpm</small>`, more: ids.hr });
    }
    const trend = Array.isArray(a.weight_trend) ? a.weight_trend.filter((p) => ok(p.w)) : [];
    if (!cur && trend.length) {
      const w = Number(trend[trend.length - 1].w), unit = a.unit || "kg";
      let goal = "";
      if (ok(a.goal_delta) && ok(a.goal_weight)) {
        const dl = Number(a.goal_delta);
        goal = Math.abs(dl) < 0.05
          ? `<small class="goal ok"> · ${esc(t.stats.atGoal)}</small>`
          : `<small class="goal"> · ${esc(t.stats.goal(`${num(h, Math.abs(dl))} ${unit}`))}</small>`;
      }
      items.push({ label: t.stats.weight, value: `${esc(num(h, w))}<small> ${esc(unit)}</small>${goal}`,
        extra: this._spark(trend, a.goal_weight), more: ids.weight, half: true });
    }
    const last = S[ids.last];
    if (last && last.state && !["unknown", "unavailable"].includes(last.state)) {
      const d = daysSince(last.attributes?.date);
      items.push({ label: t.stats.last, value: `${esc(last.state)}<small> · ${esc(relDays(t, d))}</small>`, more: ids.last, wide: true });
    }
    return `<div class="stats">${items.map((it, i) => {
      const inner = `<span class="sl">${esc(it.label)}</span><span class="sv">${it.value}</span>${it.extra || ""}`;
      const cls = `stat${it.wide ? " wide" : ""}${it.half ? " half" : ""}${it.hot ? " hot" : ""}`;
      return it.more
        ? `<button class="${cls}" data-more="${esc(it.more)}" data-fk="stat${i}">${inner}</button>`
        : `<div class="${cls}">${inner}</div>`;
    }).join("")}</div>`;
  }

  /** Tiny weight sparkline; a dashed line marks the goal when it is in range. */
  _spark(trend, goal) {
    if (trend.length < 2) return "";
    const W = 72, H = 20, ws = trend.map((p) => Number(p.w));
    const g = goal != null && !Number.isNaN(Number(goal)) ? Number(goal) : null;
    const lo = Math.min(...ws, g ?? Infinity), hi = Math.max(...ws, g ?? -Infinity);
    const span = hi - lo || 1;
    const y = (v) => (H - 2 - ((v - lo) / span) * (H - 4)).toFixed(1);
    const pts = ws.map((v, i) => `${((i / (ws.length - 1)) * W).toFixed(1)},${y(v)}`).join(" ");
    const goalLine = g != null ? `<line x1="0" x2="${W}" y1="${y(g)}" y2="${y(g)}" class="sg"/>` : "";
    return `<svg class="wspark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">${goalLine}<polyline points="${pts}"/></svg>`;
  }

  _tabs(mode) {
    const t = this._t;
    return `<div class="tabs" role="tablist" aria-label="${esc(t.modesLabel)}">${MODES.map((m) =>
      `<button class="tab${m === mode ? " on" : ""}" role="tab" data-m="${m}" data-fk="tab-${m}"
         aria-selected="${m === mode}" tabindex="${m === mode ? 0 : -1}">${esc(t.modes[m])}</button>`).join("")}</div>`;
  }

  _map(body, levels, mode) {
    const t = this._t;
    if (!body) {
      if (GEO_FAILED) {
        return `<div class="state err small" role="alert"><span>${esc(t.geoFail)}</span>
          <button class="btn retry" data-fk="retry">${esc(t.retry)}</button></div>`;
      }
      return `<div class="bodies loading" aria-busy="true" aria-label="${esc(t.loading)}"><div class="skel"></div><div class="skel"></div></div>`;
    }
    return `<div class="bodies">${["front", "back"].map((side) => {
      const v = body[side];
      if (!v) return "";
      const paths = Object.entries(v.p || {}).map(([slug, ds]) => {
        if (!SLUGS.includes(slug)) return ds.map((d) => `<path class="sil" d="${d}"/>`).join("");
        const cls = `m l${levels[slug] || 0}${this._sel === slug ? " sel" : ""}`;
        return `<g class="${cls}" data-muscle="${slug}" data-fk="map-${side}-${slug}">${ds.map((d) => `<path d="${d}"/>`).join("")}</g>`;
      }).join("");
      const cap = side === "front" ? t.front : t.back;
      return `<figure class="view"><svg viewBox="${v.vb}" class="body ${mode}" aria-label="${esc(cap)}">${paths}</svg>
        <figcaption>${esc(cap)}</figcaption></figure>`;
    }).join("")}</div>`;
  }

  _legend(mode, values, a) {
    const t = this._t, h = this._hass;
    if (mode === "recovery") {
      return `<div class="legend" aria-hidden="true"><span>${esc(t.fresh)}</span>${[4, 3, 2, 1, 0]
        .map((i) => `<i class="sw r${i}"></i>`).join("")}<span>${esc(t.stale)}</span></div>`;
    }
    const max = Math.max(0, ...Object.values(values));
    const unit = mode === "strength" ? (a.unit || "kg") : t.setsUnit;
    return `<div class="legend" aria-hidden="true"><span>${esc(t.less)}</span>${[0, 1, 2, 3, 4]
      .map((i) => `<i class="sw l${i}"></i>`).join("")}<span>${max > 0 ? `${esc(num(h, max))} ${esc(unit)}` : esc(t.more)}</span></div>`;
  }

  _list(values, mode, a) {
    const t = this._t;
    const targets = a.targets || {};
    let rows = SLUGS.map((s) => ({ s, v: values[s] }));
    if (mode === "recovery") {
      rows = rows.filter((x) => x.v >= 0 || targets[x.s])
        .sort((x, y) => (x.v < 0 ? 1e9 : x.v) - (y.v < 0 ? 1e9 : y.v));
    } else if (mode === "sets") {
      rows = rows.filter((x) => x.v > 0 || targets[x.s]).sort((x, y) => y.v - x.v);
    } else {
      rows = rows.filter((x) => x.v > 0).sort((x, y) => y.v - x.v);
    }
    const allZero = !rows.some((r) => r.v > 0);
    if (!rows.length || (mode !== "recovery" && allZero)) {
      const msg = mode === "planned" ? t.emptyPlan : mode === "strength" ? t.emptyStrength : t.emptyWeek;
      if (!rows.length || mode !== "sets") return `<div class="emptyrow">${esc(msg)}</div>`;
    }
    const hint = mode === "sets" && allZero ? `<div class="emptyrow">${esc(t.emptyWeek)}</div>` : "";
    const limit = Number(this._cfg.list_limit) || 0;
    const canCut = limit > 0 && rows.length > limit + 1;
    const shown = canCut && !this._expanded ? rows.slice(0, limit) : rows;
    const max = Math.max(1, ...rows.map((r) => r.v));
    const more = canCut
      ? `<button class="btn more" data-expand data-fk="expand" aria-expanded="${this._expanded}">${esc(this._expanded ? t.showLess : t.showAll(rows.length))}</button>`
      : "";
    return `${hint}<div class="list">${shown.map((r) => this._row(r.s, r.v, mode, targets[r.s], a, max)).join("")}</div>${more}`;
  }

  _row(slug, v, mode, target, a, max) {
    const t = this._t, h = this._hass;
    let bar = "", right = "", status = "";
    if (mode === "sets" || mode === "planned") {
      const [lo, hi] = target || [0, 0];
      const scale = Math.max(hi || 0, v, 1);
      const pct = Math.min(100, (v / scale) * 100);
      if (mode === "sets" && hi) status = v < lo ? "below" : v > hi ? "above" : "within";
      const zone = hi ? `<span class="zone" style="left:${(lo / scale) * 100}%;width:${((hi - lo) / scale) * 100}%"></span>` : "";
      bar = `<div class="bar ${status}">${zone}<span class="fill" style="width:${pct}%"></span></div>`;
      right = `<span class="val"><b>${esc(num(h, v))}</b>${hi ? `<em> / ${esc(lo)}–${esc(hi)}</em>` : ""}</span>`;
    } else if (mode === "recovery") {
      const d = v >= 0 ? v : null;
      const cls = d == null ? "never" : d <= 1 ? "r4" : d <= 2 ? "r3" : d <= 4 ? "r2" : d <= 7 ? "r1" : "r0";
      const pct = d == null ? 0 : Math.max(6, 100 - Math.min(94, d * 7));
      bar = `<div class="bar"><span class="fill ${cls}" style="width:${pct}%"></span></div>`;
      right = `<span class="val">${esc(relDays(t, d))}</span>`;
    } else {
      bar = `<div class="bar"><span class="fill" style="width:${(v / max) * 100}%"></span></div>`;
      right = `<span class="val"><b>${esc(num(h, v))}</b><em> ${esc(a.unit || "kg")}</em></span>`;
    }
    const label = `${this._name(slug)}: ${this._valueText(v, mode, a)}${status ? ` (${t.status[status]})` : ""}`;
    const sel = this._sel === slug;
    return `<button class="row${sel ? " sel" : ""}" data-muscle="${slug}" data-fk="row-${slug}"
        aria-label="${esc(label)}" aria-pressed="${sel}">
        <span class="dot ${status}"></span><span class="name">${esc(this._name(slug))}</span>${bar}${right}</button>`;
  }

  _heatmap(history, mode) {
    const t = this._t, h = this._hass;
    const max = Math.max(1, ...history.map((w) => w.sets || 0));
    const n = history.length;
    const cells = history.map((w, i) => {
      const sets = w.sets || 0;
      const f = sets / max;
      const lv = sets <= 0 ? ((w.workouts || 0) > 0 ? 1 : 0) : f >= 0.75 ? 4 : f >= 0.5 ? 3 : f >= 0.25 ? 2 : 1;
      const offset = i - (n - 1);
      const label = t.heatCell(shortDate(h, w.week_start), num(h, sets), w.workouts || 0);
      const cur = mode === "sets" && offset === this._weekOffset ? " cur" : "";
      return `<button class="hcell h${lv}${cur}" data-week="${offset}" data-fk="wk${offset}" title="${esc(label)}" aria-label="${esc(label)}"></button>`;
    }).join("");
    return `<div class="heat">
        <div class="heathead"><span>${esc(t.heatmap)}</span><span>${esc(shortDate(h, history[0]?.week_start))} – ${esc(t.thisWeek)}</span></div>
        <div class="hgrid">${cells}</div></div>`;
  }

  _planWeek(plan) {
    const t = this._t, h = this._hass;
    const today = isoDay(startOfToday());
    const days = plan.map((d) => {
      const isToday = d.date === today;
      const body = d.name
        ? `<span class="pd-name" title="${esc(d.name)}">${esc(d.name)}</span><span class="pd-sub">${esc(d.exercises)} ×</span>`
        : `<span class="pd-rest">${esc(t.rest)}</span>`;
      return `<div class="pday${d.name ? " on" : ""}${isToday ? " today" : ""}"${isToday ? ' aria-current="date"' : ""}>
        <span class="pd-day">${esc(shortDate(h, d.date, { weekday: "short" }))}</span>${d.name ? `<ha-icon class="pd-icon" icon="${esc(routineIcon(d))}"></ha-icon>` : ""}${body}</div>`;
    }).join("");
    return `<div class="planweek"><div class="sechead">${esc(t.planWeek)}</div><div class="pdays">${days}</div></div>`;
  }

  _detailPanel(muscle, a) {
    const t = this._t, h = this._hass;
    const d = this._detailData && this._detailData.trend ? this._detailData : this._detailFallback(muscle, a);
    const unit = a.unit || "kg";
    const fatigue = Number(d.fatigue) || 0;
    const fstate = d.fatigue_state || "ready";
    const ex = Object.entries(d.exercises || {});
    const exMax = ex.length ? Math.max(...ex.map(([, v]) => v)) : 1;
    const exRows = ex.slice(0, 6).map(([name, v]) =>
      `<div class="exrow"><span class="exname" title="${esc(name)}">${esc(name)}</span>
        <div class="bar"><span class="fill" style="width:${(v / exMax) * 100}%"></span></div><span class="val">${esc(num(h, v))}</span></div>`).join("");
    const [lo, hi] = d.target || [0, 0];
    const spark = this._sparkline(d.trend || [], unit);
    const ent = this._muscleEntity(muscle);
    return `<section class="detail" aria-label="${esc(this._name(muscle))}">
      <div class="detail-head">
        <span class="detail-title">${esc(this._name(muscle))}</span>
        <span class="chip ${esc(fstate)}">${esc(t.detail.state[fstate] || fstate)}</span>
        <span class="grow"></span>
        ${ent ? `<button class="iconbtn" data-more="${esc(ent)}" data-fk="dmore" aria-label="${esc(t.detail.history)}" title="${esc(t.detail.history)}">${svgIcon("open")}</button>` : ""}
        <button class="iconbtn detail-close" data-fk="dclose" aria-label="${esc(t.detail.close)}" title="${esc(t.detail.close)}">${svgIcon("close")}</button>
      </div>
      <div class="dgrid">
        <div class="dstat"><span class="dl">${esc(t.detail.week)}</span><span class="dv"><b>${esc(num(h, d.week_sets))}</b>${hi ? `<em> / ${esc(lo)}–${esc(hi)}</em>` : ""}</span></div>
        <div class="dstat"><span class="dl">${esc(t.detail.last)}</span><span class="dv">${esc(relDays(t, daysSince(d.last_trained)))}</span></div>
        <div class="dstat"><span class="dl">${esc(t.detail.best)}</span><span class="dv">${d.best_1rm ? `<b>${esc(num(h, d.best_1rm))}</b><em> ${esc(unit)}</em>` : "–"}</span></div>
        <div class="dstat"><span class="dl">${esc(t.detail.fatigue)} · ${esc(num(h, fatigue, 2))}</span>
          <div class="fatbar" role="meter" aria-label="${esc(t.detail.fatigue)}" aria-valuemin="0" aria-valuemax="1" aria-valuenow="${esc(fatigue)}">
            <span style="left:${Math.min(100, fatigue * 100)}%"></span></div></div>
      </div>
      ${spark ? `<div class="trend"><span class="dl">${esc(t.detail.trend)}</span>${spark}</div>` : ""}
      ${exRows ? `<div class="exlist"><span class="dl">${esc(t.detail.exercises)}</span>${exRows}</div>` : ""}
    </section>`;
  }

  _sparkline(trend, unit) {
    const vals = trend.map((v, i) => ({ i, v })).filter((x) => x.v != null);
    if (vals.length < 2) return "";
    const w = 240, h = 48, pad = 4;
    const vs = vals.map((x) => x.v);
    const min = Math.min(...vs), max = Math.max(...vs);
    const span = max - min || 1;
    const xs = (i) => pad + (i / Math.max(1, trend.length - 1)) * (w - 2 * pad);
    const ys = (v) => h - pad - ((v - min) / span) * (h - 2 * pad);
    const pts = vals.map((x) => `${xs(x.i).toFixed(1)},${ys(x.v).toFixed(1)}`);
    const last = vals[vals.length - 1];
    const area = `M${xs(vals[0].i).toFixed(1)},${h} L${pts.join(" L")} L${xs(last.i).toFixed(1)},${h} Z`;
    return `<div class="sparkwrap"><span class="sparkval">${esc(num(this._hass, last.v))} ${esc(unit)}</span>
      <svg viewBox="0 0 ${w} ${h}" class="spark" preserveAspectRatio="none" aria-hidden="true">
        <path class="sparkarea" d="${area}"/><polyline class="sparkline" points="${pts.join(" ")}"/></svg>
      <span class="sparkdot" style="left:${((xs(last.i) / w) * 100).toFixed(1)}%;top:${((ys(last.v) / h) * 100).toFixed(1)}%"></span></div>`;
  }

  _select(slug) {
    if (this._cfg.show_detail === false) {
      fireMoreInfo(this, this._muscleEntity(slug));
      return;
    }
    this._sel = this._sel === slug ? null : slug;
    this._detailData = null;
    if (this._sel) this._loadDetail(this._sel);
    this._rerender();
  }

  _bind(values, mode, a) {
    const root = this.shadowRoot;
    const tabs = [...root.querySelectorAll(".tab")];
    tabs.forEach((b, i) => {
      b.addEventListener("click", () => { this._mode = b.dataset.m; this._rerender(); });
      b.addEventListener("keydown", (ev) => {
        const dir = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
        if (!dir) return;
        ev.preventDefault();
        const next = tabs[(i + dir + tabs.length) % tabs.length].dataset.m;
        this._mode = next;
        this._rerender();
        root.querySelector(`[data-fk="tab-${next}"]`)?.focus();
      });
    });
    root.querySelectorAll("[data-more]").forEach((el) =>
      el.addEventListener("click", (ev) => { ev.stopPropagation(); fireMoreInfo(this, el.dataset.more); }));
    root.querySelectorAll("button.row").forEach((el) => el.addEventListener("click", () => this._select(el.dataset.muscle)));
    root.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => {
      const hist = (a.history || []).length;
      const next = this._weekOffset + Number(b.dataset.nav);
      if (next > 0 || next < -(hist - 1)) return;
      this._weekOffset = next;
      this._rerender();
    }));
    root.querySelectorAll("[data-week]").forEach((b) => b.addEventListener("click", () => {
      this._weekOffset = Number(b.dataset.week);
      this._mode = "sets";
      this._rerender();
    }));
    root.querySelector("[data-expand]")?.addEventListener("click", () => { this._expanded = !this._expanded; this._rerender(); });
    root.querySelector(".detail-close")?.addEventListener("click", () => { this._sel = null; this._rerender(); });
    root.querySelector(".retry")?.addEventListener("click", () => { GEO_FAILED = false; this._rerender(); });

    // Body map: hover/focus tooltip; click, Enter or Space selects a muscle.
    const wrap = root.querySelector(".mapwrap");
    const tip = root.querySelector(".tip");
    const show = (g, ev) => {
      if (!tip || !wrap) return;
      const slug = g.dataset.muscle;
      tip.innerHTML = `<b>${esc(this._name(slug))}</b><span>${esc(this._valueText(values[slug], mode, a))}</span>`;
      tip.hidden = false;
      const wr = wrap.getBoundingClientRect();
      let x, y;
      if (ev && ev.clientX != null) { x = ev.clientX; y = ev.clientY; }
      else { const b = g.getBoundingClientRect(); x = b.left + b.width / 2; y = b.top; }
      tip.style.left = `${Math.min(Math.max(x - wr.left, 70), wr.width - 70)}px`;
      tip.style.top = `${Math.max(y - wr.top - 10, 36)}px`;
    };
    const hide = () => { if (tip) tip.hidden = true; };
    root.querySelectorAll("g[data-muscle]").forEach((g) => {
      const slug = g.dataset.muscle;
      g.setAttribute("tabindex", "0");
      g.setAttribute("role", "button");
      g.setAttribute("aria-pressed", String(this._sel === slug));
      g.setAttribute("aria-label", `${this._name(slug)}: ${this._valueText(values[slug], mode, a)}`);
      g.addEventListener("pointermove", (ev) => show(g, ev));
      g.addEventListener("pointerleave", hide);
      g.addEventListener("focus", () => show(g));
      g.addEventListener("blur", hide);
      g.addEventListener("click", () => this._select(slug));
      g.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); this._select(slug); }
      });
    });
  }
}

const MUSCLE_CSS = `
  .weeklabel { min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding:0 2px; }
  .warn { font-size:13px; padding:8px 12px; border-radius: var(--og-radius-sm);
          background: color-mix(in srgb, var(--og-warn) 16%, transparent); border-left: 3px solid var(--og-warn); }
  .stats { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:8px; }
  .stat { display:flex; flex-direction:column; align-items:flex-start; gap:2px; min-width:0; padding:8px 10px;
          border-radius: var(--og-radius-sm); background: var(--og-surface); border:none; text-align:left; transition: background .15s; }
  button.stat { cursor:pointer; }
  button.stat:hover { background: var(--og-surface-2); }
  .stat.wide { grid-column: 1 / -1; flex-direction:row; align-items:baseline; gap:8px; }
  .sl { font-size:12px; color: var(--og-muted); white-space:nowrap; }
  .sv { font-size:16px; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:100%; }
  .sv small { font-size:12px; font-weight:400; color: var(--og-muted); }
  .stat.hot .sv { color: var(--og-warn); }
  .stat.half { grid-column: auto / span 2; }
  .stat.half { position:relative; }
  .sv .goal { color: var(--og-accent); }
  .sv .goal.ok { color: var(--og-good); }
  svg.wspark { position:absolute; top:9px; right:10px; overflow:visible; width:72px; height:20px; }
  .wspark polyline { fill:none; stroke: var(--og-accent); stroke-width:1.8; stroke-linejoin:round; stroke-linecap:round; }
  .wspark .sg { stroke: var(--og-good); stroke-width:1; stroke-dasharray:3 3; opacity:.8; }
  .tabs { display:flex; gap:2px; padding:3px; border-radius:999px; background: var(--og-surface-2); }
  .tab { flex:1; border:none; background:transparent; padding:6px 8px; border-radius:999px; cursor:pointer; font-size:13px; font-weight:500;
         color: var(--og-muted); white-space:nowrap; transition: background .2s var(--og-ease), color .2s, box-shadow .2s; }
  .tab:hover { color: var(--og-text); }
  .tab.on { background: var(--og-bg); color: var(--og-accent); box-shadow: 0 1px 3px rgba(0,0,0,.2); }
  .main { display:flex; flex-direction:column; gap:14px; min-width:0; }
  .col-map, .col-side { display:flex; flex-direction:column; gap:14px; min-width:0; }
  .col-side:empty { display:none; }
  .mapwrap { position:relative; }
  .bodies { display:flex; justify-content:center; gap: clamp(8px, 6cqi, 40px); }
  .view { margin:0; display:flex; flex-direction:column; align-items:center; gap:4px; flex: 0 1 44%; min-width:0; }
  .view figcaption { font-size:11px; color: var(--og-muted); letter-spacing:.6px; text-transform:uppercase; }
  svg.body { width:100%; height:auto; max-height: clamp(200px, 60cqi, 340px); display:block; overflow:visible; }
  svg .sil { fill: var(--og-muted); opacity:.16; }
  svg g.m { cursor:pointer; outline:none; }
  svg g.m path { fill: var(--og-muted); fill-opacity:.24; stroke: var(--og-text); stroke-opacity:0; stroke-width:0;
                 transition: fill .3s var(--og-ease), fill-opacity .3s, stroke-opacity .15s; }
  svg g.m:hover path, svg g.m:focus-visible path { stroke-width:4; stroke-opacity:.6; }
  svg g.m.sel path { stroke-width:6; stroke-opacity:1; }
  svg:not(.recovery) g.l1 path { fill: var(--og-accent); fill-opacity:.3; }
  svg:not(.recovery) g.l2 path { fill: var(--og-accent); fill-opacity:.52; }
  svg:not(.recovery) g.l3 path { fill: var(--og-accent); fill-opacity:.76; }
  svg:not(.recovery) g.l4 path { fill: var(--og-accent); fill-opacity:1; }
  svg.recovery g.l1 path { fill: var(--og-good); fill-opacity:.6; }
  svg.recovery g.l2 path { fill: var(--og-mid); fill-opacity:.95; }
  svg.recovery g.l3 path { fill: var(--og-warn); fill-opacity:1; }
  svg.recovery g.l4 path { fill: var(--og-bad); fill-opacity:1; }
  .loading { align-items:center; }
  .loading .skel { flex: 0 1 34%; aspect-ratio: 727 / 1280; max-height:320px; border-radius: var(--og-radius);
    background: linear-gradient(90deg, var(--og-surface) 0%, var(--og-surface-2) 50%, var(--og-surface) 100%);
    background-size:200% 100%; animation: og-shimmer 1.4s linear infinite; }
  .tip { position:absolute; transform: translate(-50%, -100%); pointer-events:none; z-index:2; white-space:nowrap;
         display:flex; flex-direction:column; gap:1px; padding:6px 10px; border-radius:8px; font-size:12px;
         background: var(--og-text); color: var(--og-bg); box-shadow: 0 4px 12px rgba(0,0,0,.25); }
  .tip[hidden] { display:none; }
  .tip b { font-weight:500; }
  .legend { display:flex; align-items:center; justify-content:center; gap:4px; font-size:12px; color: var(--og-muted); margin-top:-6px; }
  .legend span { padding: 0 4px; }
  .sw { width:18px; height:10px; border-radius:3px; display:inline-block; background: rgba(var(--rgb-primary-text-color, 127,127,127), .14); }
  .sw.l1 { background: color-mix(in srgb, var(--og-accent) 30%, transparent); }
  .sw.l2 { background: color-mix(in srgb, var(--og-accent) 52%, transparent); }
  .sw.l3 { background: color-mix(in srgb, var(--og-accent) 76%, transparent); }
  .sw.l4 { background: var(--og-accent); }
  .sw.r1 { background: color-mix(in srgb, var(--og-good) 60%, transparent); } .sw.r2 { background: var(--og-mid); }
  .sw.r3 { background: var(--og-warn); } .sw.r4 { background: var(--og-bad); }
  .sechead, .heathead { font-size:12px; color: var(--og-muted); margin-bottom:6px; }
  .sechead, .heathead span:first-child { font-weight:500; color: var(--og-text); }
  .heathead { display:flex; justify-content:space-between; gap:8px; }
  .hgrid { display:grid; grid-template-columns: repeat(12, minmax(0,1fr)); gap:4px; }
  .hcell { height:22px; width:100%; border:none; padding:0; border-radius:6px; cursor:pointer; background: var(--og-track);
           transition: transform .15s var(--og-ease), box-shadow .15s; }
  .hcell:hover { transform: scale(1.1); }
  .hcell.h1 { background: color-mix(in srgb, var(--og-accent) 30%, transparent); }
  .hcell.h2 { background: color-mix(in srgb, var(--og-accent) 52%, transparent); }
  .hcell.h3 { background: color-mix(in srgb, var(--og-accent) 76%, transparent); }
  .hcell.h4 { background: var(--og-accent); }
  .hcell.cur { box-shadow: 0 0 0 2px var(--og-bg), 0 0 0 4px var(--og-text); }
  .pdays { display:grid; grid-template-columns: repeat(7, minmax(0,1fr)); gap:4px; }
  .pday { min-width:0; border-radius: var(--og-radius-sm); padding:8px 4px; text-align:center; background: var(--og-surface);
          display:flex; flex-direction:column; gap:2px; }
  .pday.on { background: color-mix(in srgb, var(--og-accent) 16%, transparent); }
  .pday.today { box-shadow: inset 0 0 0 2px var(--og-accent); }
  .pd-day { font-size:11px; color: var(--og-muted); text-transform:capitalize; }
  .pd-name { font-size:12px; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .pd-sub { font-size:11px; color: var(--og-muted); }
  .pd-rest { font-size:12px; color: var(--og-muted); }
  .pd-icon { --mdc-icon-size:16px; width:16px; height:16px; margin:0 auto; color: var(--og-accent); }
  .detail { border-radius: var(--og-radius); padding:12px 14px; background: var(--og-surface); display:flex; flex-direction:column; gap:12px;
            animation: og-in .25s var(--og-ease); }
  .detail-head { display:flex; align-items:center; gap:8px; }
  .detail-title { font-weight:500; font-size:15px; }
  .grow { flex:1; }
  .chip { font-size:11px; font-weight:500; padding:2px 8px; border-radius:999px; white-space:nowrap; }
  .chip.ready { color: var(--og-good); background: color-mix(in srgb, var(--og-good) 16%, transparent); }
  .chip.recovering { color: var(--og-warn); background: color-mix(in srgb, var(--og-warn) 16%, transparent); }
  .chip.fatigued { color: var(--og-bad); background: color-mix(in srgb, var(--og-bad) 16%, transparent); }
  .dgrid { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:10px; }
  .dstat { display:flex; flex-direction:column; gap:3px; min-width:0; }
  .dl { font-size:12px; color: var(--og-muted); }
  .dv { font-size:15px; }
  .dv b, .val b { font-weight:500; }
  .dv em, .val em { font-style:normal; color: var(--og-muted); font-size:.9em; }
  .fatbar { height:8px; border-radius:999px; margin-top:5px; position:relative;
            background: linear-gradient(90deg, var(--og-good), var(--og-mid) 45%, var(--og-warn) 70%, var(--og-bad)); }
  .fatbar span { position:absolute; top:50%; width:12px; height:12px; border-radius:50%; transform: translate(-50%, -50%);
                 background: var(--og-bg); box-shadow: 0 0 0 2px var(--og-text); }
  .sparkwrap { position:relative; margin-top:6px; }
  svg.spark { width:100%; height:48px; display:block; overflow:visible; }
  .sparkline { fill:none; stroke: var(--og-accent); stroke-width:2; vector-effect: non-scaling-stroke; stroke-linejoin:round; stroke-linecap:round; }
  .sparkarea { fill: color-mix(in srgb, var(--og-accent) 14%, transparent); }
  .sparkdot { position:absolute; width:8px; height:8px; border-radius:50%; background: var(--og-accent); transform: translate(-50%, -50%);
              box-shadow: 0 0 0 2px var(--og-bg); }
  .trend { position:relative; }
  .sparkval { position:absolute; right:0; top:-20px; font-size:12px; font-weight:500; }
  .exlist { display:flex; flex-direction:column; gap:6px; }
  .exrow { display:grid; grid-template-columns: minmax(0, 40%) 1fr auto; align-items:center; gap:10px; font-size:13px; }
  .exname { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .list { display:flex; flex-direction:column; margin-top:-4px; }
  .row { display:grid; grid-template-columns: 8px minmax(0, 34%) 1fr auto; align-items:center; gap:10px; width:100%; padding:9px 6px;
         border:none; background:transparent; text-align:left; cursor:pointer; border-radius: var(--og-radius-sm); transition: background .15s; font-size:14px; }
  .row + .row { box-shadow: 0 -1px 0 var(--og-divider); }
  .row:hover { background: var(--og-surface); }
  .row.sel { background: color-mix(in srgb, var(--og-accent) 12%, transparent); box-shadow:none; }
  .row.sel + .row { box-shadow:none; }
  .dot { width:8px; height:8px; border-radius:50%; background: var(--og-track); }
  .dot.below { background: var(--og-warn); } .dot.within { background: var(--og-good); } .dot.above { background: var(--og-accent); }
  .name { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .val { white-space:nowrap; font-size:13px; text-align:right; min-width:64px; }
  .val b { font-size:14px; }
  .bar .zone { position:absolute; top:0; bottom:0; background: rgba(var(--rgb-primary-text-color, 127,127,127), .16); }
  .bar .fill { z-index:1; }
  .bar.below .fill { background: var(--og-warn); }
  .bar.within .fill { background: var(--og-good); }
  .bar .fill.r4 { background: var(--og-bad); } .bar .fill.r3 { background: var(--og-warn); } .bar .fill.r2 { background: var(--og-mid); }
  .bar .fill.r1 { background: var(--og-good); } .bar .fill.r0 { background: color-mix(in srgb, var(--og-good) 60%, transparent); }
  .btn { align-self:center; border:none; cursor:pointer; padding:6px 14px; border-radius:999px; font-size:13px; font-weight:500;
         color: var(--og-accent); background: color-mix(in srgb, var(--og-accent) 12%, transparent); transition: background .15s; }
  .btn:hover { background: color-mix(in srgb, var(--og-accent) 20%, transparent); }
  .more { margin-top:-6px; }
  .emptyrow { text-align:center; font-size:13px; color: var(--og-muted); padding:10px; border-radius: var(--og-radius-sm); background: var(--og-surface); }
  .state.small { padding:16px; }
  @container (max-width: 420px) {
    ha-card { padding:12px; gap:12px; }
    .stats { grid-template-columns: repeat(2, minmax(0,1fr)); }
    .dgrid { grid-template-columns: repeat(2, minmax(0,1fr)); }
    .tab { font-size:12px; padding:6px 4px; }
    .row { grid-template-columns: 8px minmax(0, 40%) 1fr auto; gap:8px; }
    .pd-sub { display:none; }
    .heathead span:last-child { display:none; }
    .hcell { height:18px; border-radius:4px; }
  }
  @container (min-width: 760px) {
    .main { display:grid; grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); gap:20px; align-items:start; }
    .col-map { position:sticky; top:0; }
  }
  @container (min-width: 640px) {
    .stats { grid-template-columns: repeat(6, minmax(0,1fr)); }
    .stat.wide { grid-column: auto / span 2; flex-direction:column; align-items:flex-start; gap:2px; }
  }
`;

customElements.define(TAG, OpenGymMuscleCard);

// --- Week card -----------------------------------------------------------------

class OpenGymWeekCard extends OpenGymBase {
  static getConfigElement() { return document.createElement("opengym-week-card-editor"); }
  static getStubConfig(hass) { return { ...OpenGymMuscleCard.getStubConfig(hass), days: 7 }; }

  setConfig(config) {
    this._cfg = { ...WEEK_DEFAULTS, ...(config || {}) };
    if (!this._cfg.entity) this._cfg.entity = DEFAULT_ENTITY;
    this._rerender();
  }

  _days() { return Math.min(14, Math.max(1, Number(this._cfg?.days) || 14)); }
  getCardSize() { return 2 + Math.ceil(this._days() / 1.5); }
  getGridOptions() { return { columns: 6, min_columns: 4, min_rows: 3 }; }
  getLayoutOptions() { return { grid_columns: 2, grid_min_columns: 2 }; }

  _render() {
    if (!this._hass || !this._cfg) return;
    const t = this._t, h = this._hass;
    const st = this._checkEntity();
    if (!st) return;
    const a = st.attributes || {};
    const days = (Array.isArray(a.day_view) ? a.day_view : []).slice(0, this._days());
    const today = isoDay(startOfToday());
    const maxVol = Math.max(1, ...days.map((d) => Number(d.done?.volume) || 0));
    const week = days.slice(0, 7);
    const planned = week.filter((d) => d.planned || d.done).length;
    const done = week.filter((d) => d.done).length;
    const pct = planned ? Math.min(100, (done / planned) * 100) : 0;
    const unit = a.unit || "kg";
    const summary = t.weekSummary(done, planned);

    const rows = days.map((d) => {
      const isToday = d.date === today;
      const past = d.date < today;
      const status = d.done ? "done" : d.planned ? (past ? "missed" : isToday ? "today" : "planned") : "rest";
      const title = d.done ? d.done.name : d.planned || t.rest;
      const icon = d.planned || d.done ? `<ha-icon class="wicon" icon="${esc(routineIcon(d))}"></ha-icon>` : "";
      const chip = { done: t.done, missed: t.missed, today: t.todayLabel, planned: t.planned, rest: "" }[status];
      const meta = d.done
        ? `<span class="wmeta"><span class="vbar" aria-hidden="true"><span style="width:${Math.min(100, ((Number(d.done.volume) || 0) / maxVol) * 100)}%"></span></span>
           <span class="vol">${esc(compact(h, d.done.volume))} ${esc(unit)}${d.done.sets ? ` · ${esc(d.done.sets)} ${esc(t.setsUnit)}` : ""}</span></span>`
        : "";
      return `<li class="wrow ${status}${isToday ? " is-today" : ""}"${isToday ? ' aria-current="date"' : ""}>
          <span class="wday"><b>${esc(shortDate(h, d.date, { weekday: "short" }))}</b><small>${esc(shortDate(h, d.date))}</small></span>
          <span class="wmain"><span class="wtitle">${icon}${esc(title)}</span>${meta}</span>
          ${chip ? `<span class="wchip ${status}">${esc(chip)}</span>` : ""}
        </li>`;
    }).join("");

    this._paint(`
      <style>${BASE_CSS}${WEEK_CSS}</style>
      <ha-card${this._accentStyle()}>
        <div class="head">
          <div class="badge"><ha-icon icon="mdi:calendar-week"></ha-icon></div>
          <div class="titles"><div class="title">${esc(this._cfg.title || t.weekTitle)}</div>
            <div class="subtitle">${esc(planned ? summary : t.thisWeek)}</div></div>
          ${planned ? `<div class="ring" role="img" aria-label="${esc(summary)}" style="--p:${pct.toFixed(0)}"><span>${done}/${planned}</span></div>` : ""}
        </div>
        ${days.length ? `<ol class="wlist">${rows}</ol>` : `<div class="state"><span>${esc(t.noDays)}</span></div>`}
      </ha-card>`);
  }
}

const WEEK_CSS = `
  .ring { --size:44px; width:var(--size); height:var(--size); border-radius:50%; flex:none; display:grid; place-items:center;
          background: conic-gradient(var(--og-accent) calc(var(--p) * 1%), var(--og-track) 0); }
  .ring span { width: calc(var(--size) - 8px); height: calc(var(--size) - 8px); border-radius:50%; display:grid; place-items:center;
               background: var(--og-bg); font-size:12px; font-weight:500; }
  .wlist { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:2px; }
  .wrow { display:grid; grid-template-columns: 52px minmax(0,1fr) auto; align-items:center; gap:10px; padding:8px; border-radius: var(--og-radius-sm); }
  .wrow + .wrow:not(.is-today) { box-shadow: 0 -1px 0 var(--og-divider); }
  .wrow.is-today { background: color-mix(in srgb, var(--og-accent) 12%, transparent); }
  .wrow.is-today + .wrow { box-shadow:none; }
  .wrow.rest .wtitle { color: var(--og-muted); }
  .wtitle { display:flex; align-items:center; gap:6px; }
  .wicon { --mdc-icon-size:16px; width:16px; height:16px; color: var(--og-accent); flex:none; }
  .wday { display:flex; flex-direction:column; line-height:1.25; }
  .wday b { font-size:13px; font-weight:500; text-transform:capitalize; }
  .wday small { font-size:11px; color: var(--og-muted); }
  .wmain { min-width:0; display:flex; flex-direction:column; gap:4px; }
  .wtitle { font-size:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .wrow.done .wtitle, .wrow.planned .wtitle, .wrow.today .wtitle { font-weight:500; }
  .wrow.missed .wtitle { color: var(--og-muted); text-decoration: line-through; }
  .wmeta { display:flex; align-items:center; gap:8px; min-width:0; }
  .vbar { flex: 0 1 120px; height:4px; border-radius:999px; background: var(--og-track); overflow:hidden; }
  .vbar span { display:block; height:100%; border-radius:999px; background: var(--og-accent); transition: width .45s var(--og-ease); }
  .vol { font-size:12px; color: var(--og-muted); white-space:nowrap; }
  .wchip { font-size:11px; font-weight:500; padding:3px 8px; border-radius:999px; white-space:nowrap; }
  .wchip.done { color: var(--og-good); background: color-mix(in srgb, var(--og-good) 16%, transparent); }
  .wchip.missed { color: var(--og-muted); background: var(--og-surface-2); }
  .wchip.today { color: var(--og-accent); background: color-mix(in srgb, var(--og-accent) 18%, transparent); }
  .wchip.planned { color: var(--og-muted); background: var(--og-surface); }
  @container (max-width: 300px) {
    .vbar { display:none; }
    .wrow { grid-template-columns: 44px minmax(0,1fr) auto; gap:6px; }
  }
`;

customElements.define(WEEK_TAG, OpenGymWeekCard);

// --- Next-workout card ----------------------------------------------------------

class OpenGymNextCard extends OpenGymBase {
  static getConfigElement() { return document.createElement("opengym-next-card-editor"); }

  static getStubConfig(hass) {
    const found = hass && Object.values(hass.entities || {})
      .find((e) => e.platform === "opengym" && e.translation_key === "next_session");
    return { entity: found ? found.entity_id : DEFAULT_NEXT_ENTITY };
  }

  setConfig(config) {
    this._cfg = { ...NEXT_DEFAULTS, ...(config || {}) };
    if (!this._cfg.entity) this._cfg.entity = DEFAULT_NEXT_ENTITY;
    this._rerender();
  }

  getCardSize() { return 3 + Math.min(Number(this._cfg?.max_exercises) || 6, 10); }
  getGridOptions() { return { columns: 6, min_columns: 4, min_rows: 3 }; }
  getLayoutOptions() { return { grid_columns: 2, grid_min_columns: 2 }; }

  _watched() {
    const h = this._hass, e = this._cfg.entity;
    this._ids = {
      progress: sibling(h, e, "live_progress", ["sensor.opengym_live_workout_progress"]),
      rest: sibling(h, e, "rest_timer", ["sensor.opengym_rest_timer"]),
    };
    return [e, ...Object.values(this._ids)];
  }

  _when(a) {
    const t = this._t.next, h = this._hass;
    const n = Number(a.days_until);
    const rel = n === 0 ? this._t.today : n === 1 ? t.tomorrow : n > 1 ? t.inDays(n) : "";
    const day = a.date ? shortDate(h, a.date, { weekday: "long", day: "numeric", month: "short" }) : "";
    return [rel, day].filter(Boolean).join(" · ");
  }

  _dose(ex, unit) {
    const h = this._hass;
    const sets = Number(ex.sets) || 0;
    let what;
    if (ex.mode === "cardio") return `${ex.min || "?"} min`;
    if (ex.mode === "time" || (ex.sec && !ex.reps)) what = `${ex.sec || "?"} s`;
    else if (ex.reps_min && ex.reps_max) what = `${ex.reps_min}–${ex.reps_max}`;
    else what = ex.reps != null ? String(ex.reps) : "?";
    const w = Number(ex.weight);
    return `${sets ? `${sets} × ` : ""}${what}${w > 0 ? ` · ${num(h, w)} ${unit}` : ""}`;
  }

  _render() {
    if (!this._hass || !this._cfg) return;
    const t = this._t, tn = t.next, S = this._hass.states, c = this._cfg;
    const st = this._checkEntity();
    if (!st) return;
    const a = st.attributes || {};
    const list = Array.isArray(a.exercise_list) ? a.exercise_list : [];
    const title = c.title || tn.title;
    if (!a.routine_id) {
      this._paint(`<style>${BASE_CSS}${NEXT_CSS}</style>
        <ha-card${this._accentStyle()}>
          <div class="head"><div class="badge"><ha-icon icon="mdi:sofa-outline"></ha-icon></div>
            <div class="titles"><div class="title">${esc(title)}</div><div class="subtitle">${esc(tn.none)}</div></div></div>
          <div class="state"><span>${esc(tn.noneHint)}</span></div>
        </ha-card>`);
      return;
    }
    const limit = Number(c.max_exercises) || 0;
    const shown = limit > 0 ? list.slice(0, limit) : list;
    const unit = a.unit || "kg";
    const names = NAMES[langOf(this._hass)] || NAMES.en;
    const prog = S[this._ids?.progress];
    const active = prog && prog.attributes?.active && !Number.isNaN(Number(prog.state));
    const rest = S[this._ids?.rest];
    // 0.10.1: state idle/running, end time in `ends_at` (0.10.0: the state was the timestamp)
    const restRaw = rest ? (rest.attributes?.ends_at || (/^\d{4}-/.test(rest.state) ? rest.state : null)) : null;
    const restEnds = restRaw ? new Date(restRaw) : null;
    const restLeft = restEnds ? Math.round((restEnds - Date.now()) / 1000) : 0;
    const chips = [
      `${list.length} ${tn.exercises}`,
      a.total_sets ? `${a.total_sets} ${tn.sets}` : "",
      a.rest_sec ? `${tn.rest} ${a.rest_sec} s` : "",
    ].filter(Boolean);
    this._paint(`
      <style>${BASE_CSS}${NEXT_CSS}</style>
      <ha-card${this._accentStyle()}>
        <div class="head">
          <div class="badge"><ha-icon icon="${esc(routineIcon(a))}"></ha-icon></div>
          <div class="titles"><div class="title">${esc(a.name || title)}</div><div class="subtitle">${esc(this._when(a))}</div></div>
          ${Number(a.days_until) === 0 ? `<span class="nchip today">${esc(t.todayLabel)}</span>` : ""}
        </div>
        <div class="chips">${chips.map((x) => `<span class="nchip">${esc(x)}</span>`).join("")}</div>
        ${active ? `<div class="live-row"><span class="sl">${esc(tn.progress)}</span>
            <div class="bar"><div class="fill" style="width:${Math.min(100, Number(prog.state))}%"></div></div>
            <span class="pct">${esc(prog.state)} %</span></div>` : ""}
        ${c.show_muscles !== false && Array.isArray(a.muscles) && a.muscles.length
          ? `<div class="mchips">${a.muscles.map((m) => `<span class="mchip">${esc(names[m] || m)}</span>`).join("")}</div>` : ""}
        <ol class="exlist">${shown.map((ex, i) => `
          <li><span class="idx">${i + 1}</span><span class="exn">${esc(exName(this._hass, ex) || "?")}</span>
              <span class="dose">${esc(this._dose(ex, unit))}</span></li>`).join("")}
        </ol>
        ${list.length > shown.length ? `<div class="morex">${esc(tn.more(list.length - shown.length))}</div>` : ""}
        ${c.show_rest_button !== false ? `<div class="actions">
            <button class="btn" data-rest data-fk="rest">${restLeft > 0
              ? `${esc(tn.restStarted)} · ${esc(restEnds.toLocaleTimeString(rawLang(this._hass), { hour: "2-digit", minute: "2-digit", second: "2-digit" }))}`
              : `${esc(tn.startRest)}${a.rest_sec ? ` (${esc(a.rest_sec)} s)` : ""}`}</button></div>` : ""}
      </ha-card>`);
    const btn = this.shadowRoot.querySelector("[data-rest]");
    if (btn) {
      btn.addEventListener("click", () => {
        const data = a.entry_id ? { entry_id: a.entry_id } : {};
        this._hass.callService("opengym", "start_rest_timer", data);
      });
    }
  }
}

const NEXT_CSS = `
  .chips, .mchips { display:flex; flex-wrap:wrap; gap:6px; }
  .nchip { font-size:12px; font-weight:500; padding:4px 10px; border-radius:999px; background: var(--og-surface-2); color: var(--og-text); white-space:nowrap; }
  .nchip.today { color: var(--og-accent); background: color-mix(in srgb, var(--og-accent) 18%, transparent); }
  .mchip { font-size:11px; padding:3px 8px; border-radius:999px; color: var(--og-accent);
           background: color-mix(in srgb, var(--og-accent) 12%, transparent); }
  .live-row { display:grid; grid-template-columns: auto 1fr auto; align-items:center; gap:10px; }
  .live-row .sl { font-size:12px; color: var(--og-muted); }
  .live-row .pct { font-size:12px; font-weight:500; }
  .exlist { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; }
  .exlist li { display:grid; grid-template-columns: 22px minmax(0,1fr) auto; gap:10px; align-items:center; padding:8px 2px; }
  .exlist li + li { box-shadow: 0 -1px 0 var(--og-divider); }
  .idx { width:22px; height:22px; border-radius:50%; display:grid; place-items:center; font-size:11px; font-weight:500;
         background: var(--og-surface-2); color: var(--og-muted); }
  .exn { font-size:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .dose { font-size:13px; color: var(--og-muted); white-space:nowrap; font-variant-numeric: tabular-nums; }
  .morex { font-size:12px; color: var(--og-muted); padding-left:34px; }
  .actions { display:flex; justify-content:flex-end; }
  .btn { border:none; cursor:pointer; padding:8px 14px; border-radius:999px; font-size:13px; font-weight:500;
         color: var(--og-accent); background: color-mix(in srgb, var(--og-accent) 14%, transparent); transition: background .15s; }
  .btn:hover { background: color-mix(in srgb, var(--og-accent) 22%, transparent); }
  @container (max-width: 300px) { .dose { font-size:12px; } .exlist li { gap:6px; } }
`;

customElements.define(NEXT_TAG, OpenGymNextCard);

// --- Editors -------------------------------------------------------------------

/** ha-form based editor; writes only keys the user actually set (keeps YAML tidy). */
class OpenGymEditorBase extends HTMLElement {
  setConfig(config) {
    this._config = { ...(config || {}) };
    this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  _labels() { return EDITOR_LABELS[langOf(this._hass)] || EDITOR_LABELS.en; }

  _update() {
    if (!this._config) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => this._labels()[s.name] || s.title || s.name;
      this._form.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        const defaults = this.constructor.defaults;
        const next = { ...this._config };
        for (const [k, v] of Object.entries(ev.detail.value || {})) {
          if (v === "" || v == null) delete next[k];
          else if (!(k in this._config) && defaults[k] === v) continue; // untouched default
          else next[k] = v;
        }
        this._config = next;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: next }, bubbles: true, composed: true }));
      });
      this.shadowRoot.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = this._schema();
    this._form.data = { ...this.constructor.defaults, ...this._config };
  }
}

const ENTITY_SELECTOR = { entity: { filter: { integration: "opengym", domain: "sensor" } } };

class OpenGymMuscleCardEditor extends OpenGymEditorBase {
  static get defaults() { return MUSCLE_DEFAULTS; }
  _schema() {
    const L = this._labels(), t = UI[langOf(this._hass)];
    return [
      { name: "entity", required: true, selector: ENTITY_SELECTOR },
      { name: "title", selector: { text: {} } },
      { type: "grid", name: "", schema: [
        { name: "body", selector: { select: { mode: "dropdown", options: [{ value: "male", label: L.male }, { value: "female", label: L.female }] } } },
        { name: "mode", selector: { select: { mode: "dropdown", options: MODES.map((m) => ({ value: m, label: t.modes[m] })) } } },
      ] },
      { type: "expandable", name: "", title: L.display, flatten: true, schema: [
        { type: "grid", name: "", schema: [
          { name: "show_stats", selector: { boolean: {} } },
          { name: "show_week", selector: { boolean: {} } },
          { name: "show_legend", selector: { boolean: {} } },
          { name: "show_heatmap", selector: { boolean: {} } },
          { name: "show_detail", selector: { boolean: {} } },
          { name: "show_plan_week", selector: { boolean: {} } },
          { name: "show_list", selector: { boolean: {} } },
        ] },
        { name: "list_limit", selector: { number: { min: 0, max: 18, mode: "box" } } },
      ] },
      { type: "expandable", name: "", title: L.look, flatten: true, schema: [
        { name: "accent", selector: { text: {} } },
      ] },
    ];
  }
}
customElements.define("opengym-muscle-card-editor", OpenGymMuscleCardEditor);

class OpenGymWeekCardEditor extends OpenGymEditorBase {
  static get defaults() { return WEEK_DEFAULTS; }
  _schema() {
    return [
      { name: "entity", required: true, selector: ENTITY_SELECTOR },
      { name: "title", selector: { text: {} } },
      { name: "days", selector: { number: { min: 1, max: 14, mode: "slider" } } },
      { name: "accent", selector: { text: {} } },
    ];
  }
}
customElements.define("opengym-week-card-editor", OpenGymWeekCardEditor);

class OpenGymNextCardEditor extends OpenGymEditorBase {
  static get defaults() { return NEXT_DEFAULTS; }
  _schema() {
    return [
      { name: "entity", required: true, selector: ENTITY_SELECTOR },
      { name: "title", selector: { text: {} } },
      { name: "max_exercises", selector: { number: { min: 0, max: 20, mode: "box" } } },
      { type: "grid", name: "", schema: [
        { name: "show_muscles", selector: { boolean: {} } },
        { name: "show_rest_button", selector: { boolean: {} } },
      ] },
      { name: "accent", selector: { text: {} } },
    ];
  }
}
customElements.define("opengym-next-card-editor", OpenGymNextCardEditor);

window.customCards = window.customCards || [];
for (const card of [
  {
    type: TAG,
    name: "openGym Muscle Card",
    preview: true,
    description: "Muskelbalance, Erholung, Kraft und Plan als openGym-Körperkarte — mit Wochenkennzahlen, Detail-Panel und 12-Wochen-Heatmap.",
    documentationURL: "https://github.com/JImmyB0nes/OpenGym-HomeAssistant",
  },
  {
    type: WEEK_TAG,
    name: "openGym Week Card",
    preview: true,
    description: "Trainingswoche: geplante Routinen und erledigte Workouts nebeneinander, mit Volumen und Wochenfortschritt.",
    documentationURL: "https://github.com/JImmyB0nes/OpenGym-HomeAssistant",
  },
  {
    type: NEXT_TAG,
    name: "openGym Next Workout Card",
    preview: true,
    description: "Nächstes Training: Routine, Übungen mit Sätzen/Wiederholungen/Gewicht, Live-Fortschritt und Pausentimer-Knopf.",
    documentationURL: "https://github.com/JImmyB0nes/OpenGym-HomeAssistant",
  },
]) {
  if (!window.customCards.some((c) => c.type === card.type)) window.customCards.push(card);
}

console.info(`%c openGym cards %c ${CARD_VERSION} `,
  "background:#03a9f4;color:#fff;border-radius:4px 0 0 4px;padding:2px 6px",
  "background:#424242;color:#fff;border-radius:0 4px 4px 0;padding:2px 6px");
