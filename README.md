# openGym – Home Assistant Integration

Home Assistant Custom Integration für [openGym](https://github.com/DuarteSantos8/openGym).

openGym sendet bei **abgeschlossenem Workout**, **neuem Personal Record** und **Waegen** signierte Webhooks – diese Integration nimmt sie entgegen, feuert Events auf der HA-Ereignisseite und zeigt die neuesten Ergebnisse als Sensoren.

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
   Name und optional das Signing Secret eingeben. Nach dem Anlegen zeigt die Integrationsseite die Webhook-URL (`/api/webhook/...`).

3. **In openGym:** Einstellungen → Integrationen → Webhooks → **Verbinden**, URL einfügen,
   die gewuenschten Ereignisse (Workout beendet, PR, Wiegen) anhaengen und das einmalig
   angezeigte **Signing Secret** in HA eintragen.

## Sensoren

| Sensor | Zustand |
|---|---|
| Letztes Workout | `Push (61 min)` |
| Letzter Rekord | `barbell bench press 82.5kg x5` |
| Letzte Wieegung | `80.4 kg` |

Alle Sensoren fueren das komplette Payload als Attribute (`exercises`, `totals`, `records`, …).

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
