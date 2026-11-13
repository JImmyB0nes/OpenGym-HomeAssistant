# openGym – Home Assistant Integration

Home Assistant Custom Integration für [openGym](https://github.com/DuarteSantos8/openGym).

openGym sendet bei **abgeschlossenem Workout**, **neuem Personal Record** und **Wiegen** signierte Webhooks – die Integration nimmt sie entgegen, feuert Events auf dem HA-Ereignisbus und pollt zusätzlich den kompletten Kontostand (`/api/data`): Trainingsplan, Muskelabdeckung, Streaks und Services.

## Installation

Am einfachsten über [HACS](https://hacs.xyz/) (Custom Repository, Kategorie *Integration*).
Alternativ `custom_components/opengym/` ins HA-Konfigurationsverzeichnis kopieren und HA neu starten.

## Einrichten

1. **openGym-Server vorbereiten** (nur selbst gehostet, Webhooks brauchen einen Server):
   in der `.env` der openGym-Instanz
   ```
   INTEGRATIONS=webhook
   INTEGRATIONS_ALLOW_LAN=1   # nur noetig, wenn HA im selben LAN erreichbar ist
   ```
   danach den `api`-Container neu starten.

2. **In HA:** Einstellungen → Geräte & Dienste → Integration hinzufügen → **openGym**.
   URL der Instanz eingeben.

3. **Koppeln:** In openGym unter Einstellungen → Integrationen → *„Die App koppeln“*
   einen Code erstellen (5 Min. gültig) und im Config-Flow eintragen. Optional das
   Signing Secret aus den Webhooks mitgeben. Danach legt HA den Webhook-Pfad an — die
   URL (`/api/webhook/...`) wird auf der Integrationsseite angezeigt und muss in
   openGym unter Einstellungen → Integrationen → Webhooks als Webhook eingetragen
   werden (sonst kommen keine Push-Events an).

## Sensoren

Stamm-Sensoren (Webhooks + Polling von `/api/data`):

| Entity | Zustand |
|---|---|
| `sensor.opengym_last_workout` | Name des letzten Workouts (Attribute: Datum, Volumen, Saetze) |
| `sensor.opengym_last_record` | PRs des letzten Workouts |
| `sensor.opengym_last_weighin` | Gewicht als echter Wiegesensor (kg) |
| `sensor.opengym_week_volume` | Volumen diese Woche (kg) |
| `sensor.opengym_week_workouts` | Workouts diese Woche |
| `sensor.opengym_streak` | Trainingstage in Folge |
| `sensor.opengym_next_session` | `Push - 2026-11-16` oder `Rest` |
| `sensor.opengym_total_lifting` | Gehobenes Gesamtvolumen (kg) |
| `sensor.opengym_goal_weight` | Zielgewicht (Attribute: `delta`, `at_or_below_goal`) |
| `sensor.opengym_days_since_workout` | Tage seit der letzten Einheit |
| `sensor.opengym_personal_records` | Anzahl geführter Bestgewichte (alle je Übung als Attribut) |
| `sensor.opengym_workout_heart_rate` | Ø Puls des letzten Workouts, wenn HF-Saetze vorhanden |

Muskel-Abdeckung (14 Gruppen, aus openGyms Muskelkarte, 246 Uebungen):

* `sensor.opengym_muscle_<gruppe>` - Tage seit der letzten Einheit (999 = nie)
* `binary_sensor.opengym_muscle_<gruppe>_recovering` - `on`, solange die Gruppe noch in Erholung ist (<= 2 Tage)

Dazu:

* `binary_sensor.opengym_rest_day` - `on`, wenn heute keine Einheit geplant ist
* `calendar.opengym_training_plan` - Wochentagsplan (mit Tages-Overrides) als Kalender

## Services

```yaml
action: opengym.log_weighin
data: { weight: 80.4, unit: kg }          # Wiegen -> openGym zurueck schreiben

action: opengym.trigger_test_event
data: { event_type: workout.finished }    # openGym schickt sofort ein Test-Event
```

## Events

| Ereignistyp | HA-Event |
|---|---|
| `workout.finished` | `opengym_workout_finished` |
| `workout.pr` | `opengym_personal_record` |
| `weighin.logged` | `opengym_weighin_logged` |

Beispiel-Automation:

```yaml
automation:
  - alias: "Workout abgeschlossen – Licht"
    triggers:
      - trigger: event
        event_type: opengym_workout_finished
    actions:
      - action: light.turn_on
        target: { entity_id: light.bad }
        data:
          message: >
            {{ trigger.json.data.workout.name }} fertig,
            {{ trigger.json.data.workout.totals.volume }} kg Volume!
```

## Sicherheit

- Die Webhook-URL selbst ist das eigentliche Geheimnis – nie weitergeben.
- Wird ein Signing Secret hinterlegt, prueft die Integration den `X-OpenGym-Signature`
  Header (HMAC-SHA256, `t=<unix>,v1=<hex>`, Zeitfenster 5 min) und verwirft unpassende
  Sendungen.

## Hinweise

- Erreichbarkeit: openGym akzeptiert nur HTTPS – oder `http://`, wenn `INTEGRATIONS_ALLOW_LAN=1` gesetzt ist und HA im LAN liegt.
- openGym antwortet mit beliebigem `2xx`; die Integration liefert das standardmaessig aus.
- Duplikate koennen durch openGyms „at least once“-Zustellung auftreten – `event_id` zur Identifikation verwenden.

## Lizenz

MIT für diesen Integrationsteil; openGym selbst steht unter AGPL-3.0.
