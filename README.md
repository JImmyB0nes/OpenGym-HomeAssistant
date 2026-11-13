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

## Installation

### HACS *(empfohlen)*

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
| `sensor.opengym_muscle_balance` | Wochen-Sets je Muskel, Zielbereiche, zuletzt trainiert, bestes 1RM — als Attribute für die Muskel-Karte |

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

Seit **v0.7.0** liefert die Integration eine fertige **Lovelace-Karte** gleich mit — kein HACS-Einzeleintrag, keine manuelle Resource. Installiert die Integration, und `custom:opengym-muscle-card` erscheint automatisch im Karten-Dialog.

Sie zeichnet **openGyms echte Körperkarte** (dieselbe Geometrie wie die App) und schummelt die Wochen-Realität drüber:

| Modus | Was die Karte zeigt |
|---|---|
| **Sätze** | Effektive Sätze pro Muskel gegen den Zielbereich (10–20 & Co., wie in der App) |
| **Erholung** | Frisch bis brachliegend — rot heißt „eben trainiert“, grün „seit Wochen nicht“ |
| **Kraft** | Bestes geschätztes 1RM je Muskel (Epley) |

```yaml
type: custom:opengym-muscle-card
entity: sensor.opengym_muscle_balance   # Default, darf weggelassen werden
body: male          # male | female
mode: sets          # sets | recovery | strength
show_list: true     # Muskelliste mit Zielbalken
show_week: true     # Wochenzeile „Woche vom …“
accent: "#a3e635"   # eigene Akzentfarbe (Default: HA-Akzent)
```

Datenquelle ist der neue `sensor.opengym_muscle_balance` — Wochen-Sets, Zielbereiche, zuletzt trainiert und 1RM stecken als Attribute drin und lassen sich damit auch in eigenen Karten, Templates oder Automationen verwenden.

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
- Poll-Intervall (Standard 15 Min.) einstellbar über die **Optionen** der Integration.

## Lizenz

Diese Integration: **MIT**. openGym selbst steht unter **AGPL-3.0** — und das gezeigte Logo ist das offizielle openGym-Icon von [DuarteSantos8/openGym](https://github.com/DuarteSantos8/openGym).
