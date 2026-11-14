<div align="center">

<img src="brand/logo.png" alt="openGym Logo" width="180" />

# openGym für Home Assistant

**Trainingsdaten live im Smart Home.**

[![GitHub Release](https://img.shields.io/github/v/tag/JImmyB0nes/OpenGym-HomeAssistant?label=Release&color=a3e635)](https://github.com/JImmyB0nes/OpenGym-HomeAssistant/releases)
[![License](https://img.shields.io/badge/Lizenz-MIT-gray)](LICENSE)
[![openGym](https://img.shields.io/badge/openGym-DuarteSantos8%2FopenGym-163?logo=homeassistant&logoColor=white)](https://github.com/DuarteSantos8/openGym)

</div>

Diese Integration verbindet eine [**openGym**](https://github.com/DuarteSantos8/openGym)-Instanz mit Home Assistant — dein Workout, dein Streak und deine Fortschritte lösen dann Automationen aus, statt in der App zu liegen.

Sie funktioniert zweigleisig:

| | |
|---|---|
| ⚡ **Echtzeit** | openGym sendet signierte Webhooks bei *Workout beendet*, *neuem Rekord* und *Wiegen* |
| 🔄 **Im Hintergrund** | Pollen der openGym-API liefert Plan, Muskelabdeckung, Bestgewichte und Streaks |

## Features

- 🏋️ **15 Stamm-Sensoren** — letztes Workout, Wochen-Volumen, Streak, nächste Einheit, geschätztes 1RM u.v.m.
- 🧬 **Muskel-Karte im Dashboard** — gebündelte Lovelace-Card mit echter openGym-Körperkarte, Wochen-Sets gegen Zielbereiche, Erholung und Kraft
- ✅ **"Heute / diese Woche trainiert"** — die meistgenutzten Trigger für Automationen
- 📆 **Workout-Verlauf** — abgeschlossene Workouts als Kalender-Events für die native Calendar-Card
- 💪 **28 Muskel-Sensoren** — Idle-Tage und Erholungsstatus für 14 Muskelgruppen, aus openGyms echter Muskelkarte (246 Übungen)
- 🟢 **Live-Training** — `binary_sensor.opengym_active_workout` zeigt, ob gerade wirklich gehoben wird
- 📅 **Kalender** — der Wochentagsplan als Entität, die jeder Karten- und Kalender-Card versteht
- 🔔 **Device-Trigger & -Actions** — Automationen ohne YAML: *„Wenn das openGym-Gerät ein Workout abschließt …“*
- ⚖️ **Zwei-Wege** — `log_weighin` schreibt die Waage zurück in openGym, `trigger_test_event` testet die Leitung
- 🪄 **Auto-Webhook** — beim Koppeln richtet die Integration die Webhook-Verbindung in openGym gleich selbst ein
- 🔐 **Abgesichert** — HMAC-SHA256-Signaturprüfung, Pairing-Code statt Passwort, automatische Reauth bei abgelegtem Token
- 🩺 **Diagnostik & Reparaturen** — Fehler landen als klickbarer Reparatur-Hinweis im HA-UI, Konfig-Dump für Issue-Reports
- ⬆️ **Update-Anzeige** — `update.opengym_*` zeigt, ob die Instanz hinter dem offiziellen Release steht
- ⚡ **Schnellprüfung** *(0.10)* — alle 30 s nur die Revision (`/api/data/rev`, ein paar Bytes); das ganze Dokument wird nur bei Änderungen geladen
- ⏱️ **Pausentimer** *(0.10)* — `opengym.start_rest_timer` schickt deinen Geräten den Pausen-Push, Live-Fortschritt als Sensor
- 🧑‍🏫 **Coach** *(0.10)* — Review anstoßen, Status als Sensor, Vorschläge per Button annehmen/ablehnen
- 🗓️ **Plan bearbeiten** *(0.10)* — Ruhetag setzen, Training verschieben, Tagesnotiz (krank/unterwegs …) mit konfliktsicherem Schreiben
- ⌚ **Uhr** *(0.10)* — Herzfrequenz und HF-Zone von der gekoppelten Uhr
- 📈 **Langzeitstatistik** *(0.10)* — Wochen-Sätze je Muskel als Statistik-Sensoren für Verlaufsgraphen

## Installation

### Voraussetzungen

- **Home Assistant ≥ 2024.7** — die Integration nutzt APIs, die früher nicht
  verfügbar sind (`ConfigFlowResult` seit 2024.4, `ConfigEntry`-Generics seit
  2024.6, `StaticPathConfig` für die Dashboard-Karte seit 2024.7). Ältere
  Installationen erkennen die Integration nicht oder melden beim Hinzufügen
  *„Invalid handler specified“*.

### HACS *(empfohlen)*

[![HACS openGym][hacs-shield]](https://my.home-assistant.io/redirect/hacs_repository/?owner=JImmyB0nes&repository=OpenGym-HomeAssistant&category=integration)

1. HACS → **⋮ → Custom Repositories** → Repository `JImmyB0nes/OpenGym-HomeAssistant`, Kategorie *Integration*
2. Im Reiter **Integrationen** → *openGym* → **Download**
3. Home Assistant neu starten

### Manuell

```bash
git clone https://github.com/JImmyB0nes/OpenGym-HomeAssistant
cp -r OpenGym-HomeAssistant/custom_components/opengym <config>/custom_components/
```

## Einrichten

### 1. openGym vorbereiten

Webhooks gibt es nur auf der selbst gehosteten Instanz. In der `.env`:

```ini
INTEGRATIONS=webhook
INTEGRATIONS_ALLOW_LAN=1   # nur, wenn HA im selben LAN liegt
```

Danach den `api`-Container neu starten.

### 2. In Home Assistant hinzufügen

**Einstellungen → Geräte & Dienste → Integration hinzufügen → openGym** — URL der Instanz eintragen.

### 3. Koppeln

In openGym unter *Einstellungen → Integrationen → „Die App koppeln“* einen Code erstellen (5 Min. gültig) und im Dialog eingeben.

**„Webhook automatisch einrichten“** anklicken — dann legt die Integration die Webhook-Verbindung in openGym selbst an und übernimmt das Signing Secret automatisch. Dazu muss Home Assistant für den openGym-Server erreichbar sein (LAN genügt, wenn `INTEGRATIONS_ALLOW_LAN=1` gesetzt ist).

Ohne Haken: Die Integrationsseite zeigt die **Webhook-URL** (`/api/webhook/…`) — diese manuell in openGym unter *Einstellungen → Integrationen → Webhooks* eintragen.

## Was die Integration anlegt

### Sensoren

| Entität | Anzeigen |
|---|---|
| `sensor.opengym_last_workout` | letztes Workout (Datum, Volumen, Sätze als Attribute) |
| `sensor.opengym_last_record` | Rekorde des letzten Workouts |
| `sensor.opengym_last_weighin` | Gewicht — echter Wiegesensor, für Energie-Dashboard & Co. |
| `sensor.opengym_week_volume` | Volumen dieser Woche (kg) |
| `sensor.opengym_week_workouts` | Einheiten dieser Woche |
| `sensor.opengym_streak` | Trainingstage in Folge |
| `sensor.opengym_days_since_workout` | Tage ohne Training — für Erinnerungen |
| `sensor.opengym_next_session` | `Push · 2026-11-16` oder `Rest` |
| `sensor.opengym_total_lifting` | jemals gehobenes Volumen |
| `sensor.opengym_goal_weight` | Zielgewicht mit `delta` und `at_or_below_goal` |
| `sensor.opengym_personal_records` | Anzahl Bestgewichte, alle je Übung als Attribut |
| `sensor.opengym_workout_heart_rate` | Ø Puls des letzten Workouts (wenn HF-Sätze vorhanden) |
| `sensor.opengym_best_one_rm` | bestes geschätztes 1RM (Epley), alle Übungen als Attribut |
| `sensor.opengym_custom_exercises` | Anzahl eigener Übungen (Liste als Attribut) |
| `sensor.opengym_muscle_balance` | Wochen-Sets je Muskel, Zielbereiche, zuletzt trainiert, bestes 1RM, PRs der Woche, Gewichtsverlauf, Ø Puls — als Attribute für die Karten |
| `sensor.opengym_live_workout_progress` | *(0.10)* Fortschritt des laufenden Trainings in % (Übung x/y, Sätze x/y als Attribute; braucht Admin-Rechte) |
| `sensor.opengym_rest_timer` | *(0.10)* Ende des aus HA gestarteten Pausentimers (Zeitstempel) |
| `sensor.opengym_<muskel>_weekly_sets` | *(0.10)* effektive Sätze dieser Woche je Muskel — mit `state_class: measurement`, also Langzeitstatistik |
| `sensor.opengym_coach` | *(0.10, nur mit Coach)* `idle` · `queued` · `running` · `proposal`, Vorschlag und Änderungen als Attribute |
| `sensor.opengym_paired_watches` | *(0.10, nur mit Uhr-Funktion)* gekoppelte Uhren, zuletzt gesehen |
| `sensor.opengym_watch_heart_rate` | *(0.10)* neueste Herzfrequenz von der Uhr (bpm) |
| `sensor.opengym_heart_rate_zone` | *(0.10)* HF-Zone 1–5 (50/60/70/80/90 % der Max-HF aus den Optionen) |

Außerdem *(0.10)*:

- `binary_sensor.opengym_today_done` — `on`, sobald heute ein Workout oder eine Tagesnotiz existiert (openGyms `nudge-check`)
- `binary_sensor.opengym_workout_reminder_due` — `on`, solange openGyms Erinnerungsregel heute noch erinnern würde
- `button.opengym_accept_coach_proposal` / `button.opengym_reject_coach_proposal` — nur, wenn die Instanz den Coach anbietet

### Muskeln & Erholung

Aus openGyms Muskelkarte für 246 Übungen, abgedeckt 14 Gruppen (`chest`, `deltoids`, `hamstring`, `abs`, …):

- `sensor.opengym_muscle_<gruppe>` — Tage seit der letzten Einheit (`999` = noch nie)
- `binary_sensor.opengym_muscle_<gruppe>_recovering` — `on`, solange die Gruppe (< 2 Tage) noch erholt
- `binary_sensor.opengym_rest_day` — `on`, wenn heute keine Einheit geplant ist
- `binary_sensor.opengym_worked_out_today` / `_this_week` — Trainiert-Trigger für Automationen
- `binary_sensor.opengym_active_workout` — `on`, solange live gehoben wird (mit Attributen: Name, Übung, Sätze). Benötigt Admin-Rechte auf der openGym-Instanz — ohne sie bleibt der Sensor unavailable.
- `calendar.opengym_training_plan` — Wochenplan inkl. Tages-Overrides
- `calendar.opengym_workout_history` — abgeschlossene Workouts als Kalender
- `update.opengym_open_gym_instanz` — zeigt an, wenn die Instanz hinter dem offiziellen Release steht

### Automationen ohne YAML

Das Gerät **openGym** bietet im Automation-Editor:

| | |
|---|---|
| **Auslöser** | Workout abgeschlossen · Neuer persönlicher Rekord · Wiegewägung erfasst |
| **Aktion** | Wiegewägung protokollieren |

### Services

```yaml
action: opengym.log_weighin
data:
  weight: 80.4        # kg oder lb, je nach unit
  unit: kg
  date: "2026-11-13"  # optional, Standard: heute

action: opengym.trigger_test_event
data:
  event_type: workout.finished
```

Neu in **0.10**:

```yaml
# Pausentimer: openGym schickt deinen Geräten den Push, der nach Ablauf klingelt
action: opengym.start_rest_timer
data:
  seconds: 90          # optional, Standard: deine Pausenzeit aus openGym (sonst 90)
action: opengym.cancel_rest_timer

# Plan bearbeiten (schreibt mit baseRev; bei 409 wird die Änderung auf den neuen Stand
# erneut angewendet, bis zu 4 Versuche)
action: opengym.set_rest_day
data:
  date: "2026-11-18"   # optional, Standard: heute; clear: true nimmt die Tagesänderung zurück
action: opengym.move_day
data:
  from_date: "2026-11-18"
  to_date: "2026-11-19"
action: opengym.add_day_note
data:
  tag: sick            # sick | travel | rest | injured — nur heute oder früher
  text: "Grippe"

# Coach-Review (Antwort kommt als Vorschlag → sensor.opengym_coach + Buttons)
action: opengym.coach_review
data:
  note: "Knie zwickt, weniger Kniebeugen"
  lang: de
```

Mehrere openGym-Profile? Jeder Service nimmt optional `entry_id`.

### Antwort-Services (read-only, für Vorlagen und Skripte)

```yaml
# Workout-Verlauf mit Summary — ideal für Wochenberichte
action: opengym.get_workout_history
data:
  days: 7
response_variable: history
# -> history.summary: { total_workouts, total_volume, workout_days, avg_duration_min, unit }

# Routinen mit Übungen — z.B. für Dashboard-Auswahl
action: opengym.get_routines
response_variable: routines
```

### Events

Für alle, die es genau wissen wollen:

| openGym-Ereignis | HA-Ereignis |
|---|---|
| `workout.finished` | `opengym_workout_finished` |
| `workout.pr` | `opengym_personal_record` |
| `weighin.logged` | `opengym_weighin_logged` |

## Dashboard: die Muskel-Karte direkt in Home Assistant

Seit **v0.7.0** liefert die Integration fertige **Lovelace-Karten** gleich mit — kein HACS-Einzeleintrag, keine manuelle Resource. Installiert die Integration, und `custom:opengym-muscle-card` erscheint automatisch im Karten-Dialog.

Sie zeichnet **openGyms echte Körperkarte** (dieselbe Geometrie wie die App) und schummelt die Wochen-Realität drüber:

| Modus | Was die Karte zeigt |
|---|---|
| **Sätze** | Effektive Sätze pro Muskel gegen den Zielbereich (10–20 & Co., wie in der App) |
| **Erholung** | Frisch bis brachliegend — rot heißt „eben trainiert“, grün „seit Wochen nicht“ |
| **Kraft** | Bestes geschätztes 1RM je Muskel (Epley) |
| **Geplant** | Welche Muskeln die nächste geplante Einheit treffen würde — plus Wochenplan-Leiste |

![openGym Muscle Card – hell](docs/screenshots/card/after-light.png)

**Neues Design:** HA-Theme-Farben (hell & dunkel), Kennzahlen im Kopf (Sätze, Volumen, Einheiten, Serie, letztes Workout — Klick öffnet den Verlauf), Tooltips auf der Körperkarte, Tastaturbedienung, „Training läuft“-Badge, Lade-/Fehlerzustände, responsives Layout bis hin zu zwei Spalten auf breiten Dashboards und ein visueller Editor.

Seit **v0.8.0** kann die Karte mehr als die App an dieser Stelle:

- **Wochen-Pfeile** — mit ‹ › die Körperkarte für vergangene Wochen aufrufen
- **Muskel-Detail** — Klick auf einen Muskel öffnet ein Panel mit Wochen-Sätzen, Müdigkeit, 1RM-Sparkline und den Übungen, die den Muskel treffen
- **12-Wochen-Heatmap** — Trainierte Wochen als GitHub-artiges Grid
- **Müdigkeits-Modell** — echter Halbwertszeit-Verfall je Muskelgruppe (24/30/48 h, openGym-Originalmodell) statt „vor N Tagen“
- **Zweisprachig** — Muskelnamen und UI folgen der HA-Sprache (de/en)
- **Versions-Check** — meldet stale Browser-Caches nach Updates selbst

```yaml
type: custom:opengym-muscle-card
entity: sensor.opengym_muscle_balance   # Default, darf weggelassen werden
body: male          # male | female
mode: sets          # sets | recovery | strength | planned
show_list: true     # Muskelliste mit Zielbalken
show_week: true     # Wochenzeile mit Pfeil-Navigation
show_heatmap: true  # 12-Wochen-Heatmap
show_detail: true   # Detail-Panel bei Muskel-Klick
show_plan_week: true # Wochenplan-Leiste im Geplant-Modus
show_stats: true    # Kennzahlen im Kopf
show_legend: true   # Farblegende
list_limit: 8       # Zeilen bis „Alle anzeigen“ (0 = alle)
title: Muskelbalance # eigener Titel
accent: "#a3e635"   # eigene Akzentfarbe (Default: HA-Primärfarbe)
```

Seit **v0.10.0** zeigt die Kennzahlen-Leiste zusätzlich **PRs dieser Woche**, den **Ø Puls** des letzten Workouts und das **Gewicht** mit Mini-Verlauf und Abstand zum Zielgewicht. Mit mehreren openGym-Profilen fragt die Karte die Muskel-Details beim richtigen Eintrag ab (`entry_id`).

![openGym Muscle Card 0.10 – hell](docs/screenshots/card/v010-muscle-light.png)

Dazu die **Wochen-Karte** — Plan und Realität nebeneinander:

```yaml
type: custom:opengym-week-card
entity: sensor.opengym_muscle_balance
days: 14            # Tage ab Montag dieser Woche (1–14)
title: Trainingswoche
accent: "#a3e635"
```

Neu in **v0.10.0**: die **Nächstes-Training-Karte** — Routine, Übungen mit Sätzen × Wiederholungen und Gewicht, Live-Fortschritt während des Trainings und ein Knopf für den Pausentimer:

```yaml
type: custom:opengym-next-card
entity: sensor.opengym_next_session   # Default
max_exercises: 6        # 0 = alle
show_muscles: true      # Muskel-Chips
show_rest_button: true  # „Pausentimer starten“ (opengym.start_rest_timer)
```

![openGym Next Workout Card – dunkel](docs/screenshots/card/v010-next-dark-live.png)

Datenquelle ist `sensor.opengym_muscle_balance` — Wochen-Sets, Zielbereiche, zuletzt trainiert, 1RM, Müdigkeit, Trends, Plan und Historie stecken als Attribute drin und lassen sich damit auch in eigenen Karten, Templates oder Automationen verwenden.

## Beispiele

**Licht anspringen, wenn das Training fertig ist:**

```yaml
automation:
  - alias: "Workout geschafft"
    triggers:
      - trigger: device
        device_id: !device_id opengym   # oder: Trigger-Gerät im Editor wählen
        domain: opengym
        type: workout_finished
    actions:
      - action: light.turn_on
        target: { entity_id: light.wohnzimmer }
        data:
          brightness: 200
```

**Erinnerung, wenn zu lange nichts lief:**

```yaml
automation:
  - alias: "Ab ins Gym"
    triggers:
      - trigger: state
        entity_id: sensor.opengym_days_since_workout
        above: 4
    actions:
      - action: notify.mobile_app
        data:
          message: "Seit 5 Tagen kein Training. Nächste Einheit: {{ states('sensor.opengym_next_session') }}"
```

**Waage automatisch zurückschreiben:**

```yaml
automation:
  - alias: "Morgendliche Waage"
    triggers:
      - trigger: state
        entity_id: sensor.smart_scale_weight
    actions:
      - action: opengym.log_weighin
        data:
          weight: "{{ trigger.to_state.state | float }}"
```

## Sicherheit

- Die **Webhook-URL ist das Geheimnis** — sie ist einmalig, lang und nicht erratbar.
- Mit hinterlegtem **Signing Secret** prüft die Integration jeden Aufruf: `X-OpenGym-Signature` als HMAC-SHA256 über `t=<zeit>.<body>`, Zeitfenster 5 Minuten, Timing-safe verglichen. Unpassende Sendungen werden verworfen.
- **Keine Passwörter:** der Zugriff läuft über einen Pairing-Code, der Token wird automatisch erneuert.

## Hinweise

- openGym liefert nur **HTTPS** aus — oder `http://` ins LAN, wenn `INTEGRATIONS_ALLOW_LAN=1` gesetzt ist.
- openGym liefert „mindestens einmal“ — Duplikate lassen sich über `event_id` erkennen.
- Über die **Optionen** der Integration einstellbar: Poll-Intervall (Standard 15 Min.), Schnellprüfung (Standard 30 s, `0` = aus) und maximale Herzfrequenz für die HF-Zonen (Standard 190).
- **Coach, Uhr und Integrationen sind optional.** Bietet die Instanz sie nicht an (503 `off` bzw. 404), legt die Integration die zugehörigen Entitäten gar nicht an — ohne Fehler im Log. Wird ein Feature später auf der Instanz eingeschaltet, die Integration einmal neu laden.
- **Coach-Vorschläge annehmen:** openGym zeichnet mit `pending/resolve` nur die Entscheidung auf, anwenden muss der Client. Home Assistant übernimmt einfache Werte selbst (Sätze, Wiederholungen, Wdh.-Bereich, Sekunden, Steigerung, Progression, Aufwärmen, Routinenname) — inklusive Undo-Schnappschuss für die App. Vorschläge mit Strukturänderungen (Übung tauschen/hinzufügen, Wochenplan, neuer Plan) bitte in der App annehmen; dann ist der Annehmen-Button nicht verfügbar. Ablehnen geht immer.
- **Pausentimer:** openGym hält Timer nur im Speicher und gibt sie nicht heraus — `sensor.opengym_rest_timer` kennt deshalb nur Timer, die aus Home Assistant gestartet wurden.
- **Live-Training** (`active_workout`, `live_workout_progress`) braucht Admin-Rechte auf der Instanz (openGym teilt Presence nur über `/api/admin/users`).
- **Uhr-Puls:** Lesbar sind nur die Uhr-Ereignisse, die noch in openGyms Warteschlange liegen (bis die App sie abholt); die Uhr-Snapshot-Box ist mit dem App-Token nicht lesbar. Der Puls-Sensor zeigt daher den zuletzt gesehenen Wert.
- **Zustellprobleme:** Scheitern Webhook-Zustellungen dauerhaft, erscheint unter *Einstellungen → Reparaturen* ein Hinweis; „Beheben“ reiht die fehlgeschlagenen Zustellungen in openGym erneut ein. Das Zustell-Log steht in den Diagnosedaten.

## Lizenz

Diese Integration: **MIT**. openGym selbst steht unter **AGPL-3.0** — und das gezeigte Logo ist das offizielle openGym-Icon von [DuarteSantos8/openGym](https://github.com/DuarteSantos8/openGym).

[hacs-shield]: https://img.shields.io/badge/HACS-openGym-orange?logo=homeassistant
