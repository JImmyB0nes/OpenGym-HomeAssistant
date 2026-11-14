<div align="center">

<img src="https://raw.githubusercontent.com/JImmyB0nes/OpenGym-HomeAssistant/main/brand/logo.png" alt="openGym Logo" width="140" />

# openGym für Home Assistant

**Dein Training im Smart Home – Workouts, Rekorde, Muskelbalance und Trainingsplan aus deiner selbst gehosteten [openGym](https://github.com/DuarteSantos8/openGym)-Instanz.**

[![Release](https://img.shields.io/github/v/release/JImmyB0nes/OpenGym-HomeAssistant?label=Release&color=a3e635)](https://github.com/JImmyB0nes/OpenGym-HomeAssistant/releases/latest)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-%E2%89%A5%202024.11-18bcf2?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-41bdf5?logo=homeassistantcommunitystore&logoColor=white)](https://hacs.xyz/)
[![CI](https://img.shields.io/github/actions/workflow/status/JImmyB0nes/OpenGym-HomeAssistant/ci.yml?branch=main&label=CI)](https://github.com/JImmyB0nes/OpenGym-HomeAssistant/actions/workflows/ci.yml)
[![Lizenz](https://img.shields.io/github/license/JImmyB0nes/OpenGym-HomeAssistant?label=Lizenz)](LICENSE)

[![In HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JImmyB0nes&repository=OpenGym-HomeAssistant&category=integration)
[![Integration hinzufügen](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=opengym)

<a href="#-installation--einrichtung">Installation</a> ·
<a href="#-dashboard-karten">Karten</a> ·
<a href="#-entitäten--services">Entitäten</a> ·
<a href="#-fehlerbehebung">Fehlerbehebung</a> ·
<a href="#-faq">FAQ</a>

</div>

<table>
  <tr>
    <td width="40%" align="center"><img src="https://raw.githubusercontent.com/JImmyB0nes/OpenGym-HomeAssistant/main/docs/screenshots/card/v0101-dark-all.png" alt="Alle drei Karten im dunklen Theme" /><br/><sub>Muskel-, Wochen- und Nächstes-Training-Karte (dunkel)</sub></td>
    <td width="60%" align="center"><img src="https://raw.githubusercontent.com/JImmyB0nes/OpenGym-HomeAssistant/main/docs/screenshots/card/v010-muscle-light.png" alt="Muskel-Karte im hellen Theme" /><br/><sub>Muskelbalance mit Kennzahlen (hell)</sub><br/><br/><img src="https://raw.githubusercontent.com/JImmyB0nes/OpenGym-HomeAssistant/main/docs/screenshots/card/v010-next-dark-live.png" alt="Nächstes Training mit Live-Fortschritt" /><br/><sub>Nächstes Training mit Live-Fortschritt</sub></td>
  </tr>
</table>

## ✨ Was du bekommst

| | |
|---|---|
| ⚡ **Echtzeit** | Signierte Webhooks bei *Training beendet*, *neuem Rekord* und *Wiegen* – als HA-Ereignisse und Geräte-Auslöser |
| 🔄 **Immer aktuell** | Polling der openGym-API (Standard 15 Min.) plus Schnellprüfung der Revision alle 30 s |
| 🧬 **Dashboard-Karten** | Muskelbalance mit openGyms Körperkarte, Trainingswoche, nächstes Training – mitgeliefert, ohne extra Ressource |
| 🏋️ **Sensoren** | Letztes Workout, Volumen, Wochen-Serie, nächste Einheit, Rekorde, 1RM, Gewicht & Ziel, Müdigkeit, Wochen-Sätze je Muskel |
| 💪 **Muskeln** | Ruhetage und Erholung für 14 Muskelgruppen aus openGyms Übungskatalog (über 5.600 Übungen, Namen auf Deutsch/Englisch) |
| 🗓️ **Plan** | Trainingsplan und Verlauf als Kalender; Ruhetag setzen, Training verschieben, Tagesnotiz – konfliktsicher zurückgeschrieben |
| ⏱️ **Im Training** | Pausentimer-Push an deine Geräte, Live-Fortschritt *(Admin)*, Herzfrequenz & Zone von der Uhr |
| 🧑‍🏫 **Coach** | Review anstoßen, Status als Sensor, Vorschläge per Button annehmen/ablehnen *(wenn die Instanz den Coach anbietet)* |
| 🔐 **Sicher & wartbar** | Kopplungscode statt Passwort, HMAC-Signaturprüfung, Reauth, Reparatur-Hinweise, Diagnosedaten, Update-Entität |

## 🚀 Installation & Einrichtung

> **Kurzfassung:** `INTEGRATIONS=webhook` (+ `INTEGRATIONS_ALLOW_LAN=1`, wenn HA im Heimnetz läuft) in openGyms `.env` → `docker compose up -d` → Integration per HACS installieren → neu starten → *openGym* hinzufügen → Kopplungscode aus **Einstellungen → Konto → „Mobile App koppeln“** eingeben.

Die Einrichtung dauert etwa zehn Minuten und hat vier Teile: openGym vorbereiten, die Adressen klären, die Integration installieren und koppeln, die Karten einbinden. Die Beispiele verwenden durchgehend diese Werte, ersetze sie durch deine eigenen:

| Was | Beispiel |
|---|---|
| openGym im Heimnetz | `http://192.168.123.14:8080` |
| openGym öffentlich (Reverse Proxy/Tunnel) | `https://gym.example.de` |
| Home Assistant im Heimnetz | `http://192.168.123.20:8123` |
| Home Assistant öffentlich (optional) | `https://ha.example.de` |

### 1. Voraussetzungen

- Eine **selbst gehostete openGym-Instanz** ([DuarteSantos8/openGym](https://github.com/DuarteSantos8/openGym), Docker Compose). Die reine Handy-App ohne Server reicht nicht, denn Home Assistant braucht die API des Servers.
- Ein **openGym-Konto** auf dieser Instanz, mit dem du dich im Browser anmelden kannst (Passkey oder Passwort). Für Live-Fortschritt und „Training läuft“ muss es ein **Admin**-Konto sein, denn openGym teilt Live-Präsenz nur mit Admins.
- **Home Assistant 2024.11 oder neuer.**
- **[HACS](https://hacs.xyz/)** (empfohlen) oder Zugriff auf den Ordner `config/custom_components`.

### 2. openGym vorbereiten (Server)

Ohne diesen Schritt funktioniert die Integration auch, allerdings nur per **Polling** (Standard alle 15 Minuten, dazu eine schnelle Revisionsprüfung alle 30 s). Mit Webhooks meldet openGym abgeschlossene Workouts, Rekorde und Wiegungen **sofort**.

**2.1 Webhooks einschalten.** Integrationen sind in openGym standardmäßig aus. Ohne Einstellung blendet openGym die Webhook-Karte für alle außer Admins aus und legt keine Webhooks an. Trage in die `.env` neben der `docker-compose.yml` ein:

```ini
INTEGRATIONS=webhook
```

**2.2 Webhooks ins Heimnetz erlauben (`INTEGRATIONS_ALLOW_LAN`).** openGym behandelt eine Webhook-URL wie einen Push-Endpunkt: nur `https://` und nie eine private Adresse. Die Adresse wird beim Verbindungsaufbau geprüft, also auch dann, wenn ein Hostname auf eine private IP auflöst. Läuft Home Assistant unter `http://192.168.123.20:8123`, verwirft openGym jede Zustellung, bis du das freigibst:

```ini
INTEGRATIONS_ALLOW_LAN=1
```

<details>
<summary>Was genau freigegeben wird – und was gesperrt bleibt</summary>

Was der Schalter freigibt (`api/net-guard.js`):

- die Heimnetz-Bereiche `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `100.64.0.0/10` (Tailscale & Co.) und IPv6 `fc00::/7`
- **unverschlüsseltes `http://`, aber nur zu diesen Adressen**

Was gesperrt bleibt, egal was eingestellt ist:

- Loopback (`127.0.0.1`, also der openGym-Server selbst)
- Link-Local (`169.254.x.x`)
- Multicast und reservierte Bereiche
- `http://` zu einer Internet-Adresse

Gültige Werte sind `1`, `true`, `yes` oder `on`. Beachte: Danach kann jeder angemeldete Nutzer deiner Instanz den Server Anfragen in dein Heimnetz schicken lassen. Schalte es also nur auf einer Instanz ein, deren Nutzern du vertraust.

</details>

<details>
<summary>Weitere Variablen: <code>ALLOWED_PRIVATE_IPS</code>, <code>ORIGIN</code>/<code>RP_ID</code>, <code>WEB_PORT</code></summary>

| Variable | Wofür |
|---|---|
| `ALLOWED_PRIVATE_IPS` | Einzelne private Adressen, Bereiche (`a-b`) oder CIDR-Blöcke, die zusätzlich erlaubt sind, z. B. `192.168.123.20` oder `10.0.0.0/8`. Gilt für Push und Webhooks. Das ist der Weg, wenn du *nur* Home Assistant freigeben willst; mit `INTEGRATIONS_ALLOW_LAN=1` ist das ganze Heimnetz offen. |
| `ORIGIN` / `RP_ID` | Die Adresse, unter der du openGym im Browser öffnest (Passkeys). Home Assistant meldet sich mit einem Bearer-Token an und ist davon nicht betroffen. Den Kopplungscode musst du aber im Browser unter dieser Adresse erzeugen. |
| `WEB_PORT` | Host-Port des `web`-Containers (Standard `8080`), also der Port in der LAN-URL. |

</details>

**Wohin damit?** Die `docker-compose.yml` von openGym lädt die `.env` mit `env_file: .env` in den `api`-Container. Die `.env` ist deshalb der einfachste Weg:

```ini
# .env (neben docker-compose.yml)
INTEGRATIONS=webhook
INTEGRATIONS_ALLOW_LAN=1
```

<details>
<summary>Alternativ: direkt in der <code>docker-compose.yml</code></summary>

Alternativ direkt am `api`-Dienst in der `docker-compose.yml`:

```yaml
services:
  api:
    environment:
      - INTEGRATIONS=webhook
      - INTEGRATIONS_ALLOW_LAN=1
```

</details>

**Übernehmen.** Ein einfacher `docker compose restart` liest geänderte Umgebungsvariablen **nicht** neu ein. Der Container muss neu erstellt werden:

```bash
docker compose up -d
```

Compose erkennt die geänderte Konfiguration und erstellt den `api`-Container neu. Wenn er sich nicht neu erstellt: `docker compose up -d --force-recreate api`.

**Prüfen, ob es wirkt:**

```bash
docker compose exec api printenv INTEGRATIONS INTEGRATIONS_ALLOW_LAN
# erwartet:
# webhook
# 1
```

In der openGym-Web-App erscheint unter **Einstellungen → Integrationen** jetzt die Karte **Webhooks** mit **Verbinden**. Ein Tippfehler in `INTEGRATIONS` steht als Warnung im Log (`docker compose logs api`).

### 3. Welche openGym-URL Home Assistant benutzt

Diese URL trägst du später im Einrichtungsdialog ein. Home Assistant liest darüber den Datenstand und schreibt Planänderungen zurück.

| | LAN-URL `http://192.168.123.14:8080` | Öffentliche URL `https://gym.example.de` |
|---|---|---|
| **Vorteile** | kein Proxy nötig, schnell, funktioniert ohne Internet | verschlüsselt, funktioniert auch, wenn HA woanders steht |
| **Nachteile** | unverschlüsselt im LAN; feste IP bzw. DHCP-Reservierung nötig | hängt an Proxy/Tunnel und DNS; Cloudflare Access o. Ä. davor blockiert HA |
| **Wann** | HA und openGym im selben Netz (Normalfall) | HA außerhalb oder openGym nur per Proxy erreichbar |

Hinweise:

- Gemeint ist der **`web`-Container** (Port `WEB_PORT`, Standard `8080`), nicht der `api`-Port `3000`. Der API-Port ist in der Standard-Compose-Datei nicht veröffentlicht.
- Ohne abschließenden `/`. Bei einer Installation unter einem Unterpfad (`BASE_PATH=/gym`) gehört der Pfad dazu: `https://example.de/gym`.
- Schnelltest von einem Rechner im LAN: `curl http://192.168.123.14:8080/api/config` muss JSON mit `invite_only` liefern. Eine HTML-Seite heißt: falscher Port oder ein Proxy-Login dazwischen.

### 4. Die URL, unter der openGym Home Assistant erreicht

Webhooks gehen in die **andere Richtung**: Der `api`-Container von openGym schickt einen `POST` an `https://<HA>/api/webhook/<id>`. Die Integration baut diese URL aus den Netzwerk-Einstellungen von Home Assistant, unter **Einstellungen → System → Netzwerk → Home-Assistant-URL**. Das Feld ist nur im **erweiterten Modus** sichtbar, den du im Benutzerprofil einschaltest.

- **Internet**, z. B. `https://ha.example.de`: wird **bevorzugt**, sobald es gesetzt ist. Öffentliches HTTPS, dafür ist kein `INTEGRATIONS_ALLOW_LAN` nötig.
- **Lokales Netzwerk**, z. B. `http://192.168.123.20:8123`: wird genommen, wenn keine Internet-URL gesetzt ist. Dafür braucht openGym `INTEGRATIONS_ALLOW_LAN=1` (oder die IP in `ALLOWED_PRIVATE_IPS`).

Die gewählte URL muss **aus dem openGym-Container heraus** erreichbar sein, nicht nur von deinem Rechner aus:

<details>
<summary>Checkliste: erreichbar aus dem Container?</summary>

- Nimm die **IP-Adresse**. `homeassistant.local` (mDNS) löst im Docker-Container meist nicht auf.
- Nimm nicht `127.0.0.1` oder `localhost`, auch wenn beides auf demselben Host läuft. Loopback ist immer gesperrt. Nimm die LAN-IP des Hosts.
- Probe aus dem Container: `docker compose exec api wget -qO- http://192.168.123.20:8123/api/` muss mit `401 Unauthorized` antworten – das heißt: erreichbar. Fehlt `wget` im Image, nimm `node -e "fetch('http://192.168.123.20:8123/api/').then(r=>console.log(r.status))"`.

</details>

Welche URL die Integration verwendet, zeigt der Einrichtungsdialog in Schritt 6 an.

### 5. Integration installieren

**Per HACS (empfohlen)**

[![In HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JImmyB0nes&repository=OpenGym-HomeAssistant&category=integration)

1. HACS → **⋮ → Benutzerdefinierte Repositories** → `https://github.com/JImmyB0nes/OpenGym-HomeAssistant`, Typ **Integration** → **Hinzufügen**
2. *openGym* suchen → **Herunterladen**
3. **Home Assistant neu starten** (Einstellungen → System → ⏻ → Home Assistant neu starten)

<details>
<summary>Manuell (ohne HACS)</summary>

```bash
git clone https://github.com/JImmyB0nes/OpenGym-HomeAssistant
cp -r OpenGym-HomeAssistant/custom_components/opengym <config>/custom_components/
```
Danach ebenfalls neu starten.

</details>

### 6. Integration einrichten und koppeln

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → openGym** – oder direkt:
   [![Integration hinzufügen](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=opengym)
2. **URL** aus Schritt 3 eintragen, z. B. `http://192.168.123.14:8080`. Die Integration prüft sofort `GET /api/config`.
3. **Kopplungscode erzeugen.** Öffne die openGym-Web-App im Browser, angemeldet mit dem Konto, das HA sehen soll:
   **Einstellungen → Konto → „Mobile App koppeln“** → mit Passkey oder Passwort bestätigen („Bestätige zuerst, dass du es bist.“) → openGym zeigt einen 8-stelligen Code.
   - Der Code gilt **5 Minuten** und nur einmal. Ein neuer Code ersetzt den alten.
   - Erzeuge ihn im **Browser**. In der Handy-App klappt das nur, wenn das Konto ein Passwort hat.
4. Den Code im Dialog eintragen. Optional einen Namen vergeben, das ist sinnvoll bei mehreren Profilen.
5. **Webhook** wählen:
   - **„Webhook automatisch einrichten“** (Standard): Die Integration legt in openGym selbst die Webhook-Verbindung „Home Assistant“ mit den Events `workout.finished`, `workout.pr` und `weighin.logged` an und übernimmt das Signing Secret. Voraussetzung sind Schritt 2 und Schritt 4. Klappt es nicht, steht im HA-Log *„could not create the webhook connection automatically“*. Die Integration läuft trotzdem und pollt weiter.
   - **Manuell** (Haken aus): Der Dialog zeigt die Webhook-URL (`…/api/webhook/<id>`). Trage sie in openGym unter **Einstellungen → Integrationen → Webhooks → Verbinden** ein, wähle die drei Ereignisse *Training beendet*, *Neuer persönlicher Rekord* und *Wiegen erfasst* und kopiere das Signing Secret, das **nur einmal** angezeigt wird, ins Feld *Secret*. Ohne Secret werden Zustellungen nicht signaturgeprüft.
6. Kontrolle: In HA unter **Entwicklerwerkzeuge → Ereignisse** das Ereignis `opengym_workout_finished` abonnieren. Dann in openGym unter **Einstellungen → Integrationen → Webhooks** die Verbindung öffnen und **Test-Ereignis senden** antippen, oder in HA die Aktion `opengym.trigger_test_event` ausführen. Es muss ein Ereignis mit `"test": true` erscheinen. Das Blatt der Verbindung in openGym zeigt auch die letzte Zustellung und den letzten Fehler.

### 7. Karten einbinden

Die Integration bringt drei Karten mit (`custom:opengym-muscle-card`, `custom:opengym-week-card`, `custom:opengym-next-card`). Es ist kein eigener HACS-Eintrag nötig.

- **Dashboards im UI-Modus (Standard):** Die Ressource `/opengym/opengym-muscle-card.js?v=<Version>` wird beim Start automatisch registriert und bei Updates angepasst. Danach Dashboard → **Bearbeiten → Karte hinzufügen** → nach *openGym* suchen.
- **Dashboards im YAML-Modus:** Hier kann die Integration nichts eintragen. Füge die Ressource selbst hinzu:

  ```yaml
  # configuration.yaml
  lovelace:
    mode: yaml
    resources:
      - url: /opengym/opengym-muscle-card.js?v=0.10.1
        type: module
  ```

  Alternativ in der UI unter **Einstellungen → Dashboards → ⋮ → Ressourcen → Ressource hinzufügen**, mit URL `/opengym/opengym-muscle-card.js` und Typ *JavaScript-Modul*. Dieser Menüpunkt erscheint nur im erweiterten Modus.
- **Nach einem Update:** Die Karte meldet selbst, wenn der Browser noch die alte Version im Cache hat. Dann die Seite hart neu laden (Strg+F5). In der Companion-App den Frontend-Cache zurücksetzen: **Einstellungen → Companion App → Fehlerbehebung** (Android) bzw. **Debugging** (iOS) **→ Frontend-Cache zurücksetzen**.

## 🧬 Dashboard-Karten

Drei Karten kommen mit der Integration. Sie folgen dem HA-Theme (hell/dunkel) und der HA-Sprache (de/en) und haben einen visuellen Editor.

### Muskelbalance – `custom:opengym-muscle-card`

openGyms echte Körperkarte, darüber deine Woche. Mit ‹ › blätterst du durch vergangene Wochen. Ein Klick auf einen Muskel öffnet Details (Wochen-Sätze, Müdigkeit, 1RM-Verlauf, Übungen). Dazu kommen eine 12-Wochen-Heatmap und Kennzahlen (Sätze, Volumen, Einheiten, Wochen-Serie, PRs, Ø Puls, Gewicht).

| Modus | Was die Karte zeigt |
|---|---|
| **Sätze** | Effektive Sätze pro Muskel gegen den Zielbereich (10–20 & Co., wie in der App) |
| **Erholung** | Frisch bis brachliegend — rot heißt „eben trainiert“, grün „seit Wochen nicht“ |
| **Kraft** | Bestes geschätztes 1RM je Muskel (Epley) |
| **Geplant** | Welche Muskeln die nächste geplante Einheit treffen würde — plus Wochenplan-Leiste |

<details>
<summary>Konfiguration</summary>

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

</details>

### Trainingswoche – `custom:opengym-week-card`

Plan und Realität nebeneinander: geplante Routine mit Icon, erledigte Einheiten mit Volumen und Sätzen.

<details>
<summary>Konfiguration</summary>

```yaml
type: custom:opengym-week-card
entity: sensor.opengym_muscle_balance
days: 14            # Tage ab Montag dieser Woche (1–14)
title: Trainingswoche
accent: "#a3e635"
```

</details>

### Nächstes Training – `custom:opengym-next-card`

Routine mit Icon, Übungen mit Sätzen × Wiederholungen und Gewicht, Muskel-Chips, Live-Fortschritt während des Trainings und ein Knopf für den Pausentimer.

<details>
<summary>Konfiguration</summary>

```yaml
type: custom:opengym-next-card
entity: sensor.opengym_next_session   # Default
max_exercises: 6        # 0 = alle
show_muscles: true      # Muskel-Chips
show_rest_button: true  # „Pausentimer starten“ (opengym.start_rest_timer)
```

</details>

Datenquelle ist `sensor.opengym_muscle_balance` bzw. `sensor.opengym_next_session`. Alle Werte stecken als Attribute darin und lassen sich auch in eigenen Karten, Templates oder Automationen verwenden.

## 📋 Entitäten & Services

Entitäts-IDs entstehen aus den englischen Namen und dem Gerätenamen *openGym*. Hast du das Gerät umbenannt, ändert sich das Präfix.

<details>
<summary><b>Sensoren</b></summary>

| Entität | Anzeigen |
|---|---|
| `sensor.opengym_last_workout` | letztes Workout (Datum, Volumen, Sätze als Attribute) |
| `sensor.opengym_last_personal_record` | Rekorde des letzten Workouts |
| `sensor.opengym_last_weigh_in` | Gewicht — echter Wiegesensor, für Energie-Dashboard & Co. |
| `sensor.opengym_volume_this_week` | Volumen dieser Woche (kg) |
| `sensor.opengym_workouts_this_week` | Einheiten dieser Woche |
| `sensor.opengym_workout_streak` | Trainingstage in Folge |
| `sensor.opengym_week_streak` | *(0.10.1)* Wochen-Serie wie in openGym: Wochen in Folge mit Training, inkl. Freeze (alle 4 Wochen einer, max. 2); die laufende Woche bricht die Serie nicht |
| `sensor.opengym_days_since_last_workout` | Tage ohne Training — für Erinnerungen |
| `sensor.opengym_next_session` | `Push · 2026-11-16` oder `Rest` |
| `sensor.opengym_total_lifted` | jemals gehobenes Volumen |
| `sensor.opengym_goal_weight` | Zielgewicht mit `delta` und `at_or_below_goal` |
| `sensor.opengym_personal_records` | Anzahl Bestgewichte, alle je Übung als Attribut |
| `sensor.opengym_workout_heart_rate` | Ø Puls des letzten Workouts (wenn HF-Sätze vorhanden) |
| `sensor.opengym_estimated_1rm` | bestes geschätztes 1RM (Epley), alle Übungen als Attribut |
| `sensor.opengym_custom_exercises` | Anzahl eigener Übungen (Liste als Attribut) |
| `sensor.opengym_muscle_fatigue` | Müdigkeit je Muskel (Halbwertszeit-Modell) als Attribute |
| `sensor.opengym_weekly_training_history` | 12-Wochen-Verlauf (Sätze, Einheiten, Volumen) für die Heatmap |
| `sensor.opengym_muscle_balance` | Wochen-Sets je Muskel, Zielbereiche, zuletzt trainiert, bestes 1RM, PRs der Woche, Gewichtsverlauf, Ø Puls — als Attribute für die Karten |
| `sensor.opengym_live_workout_progress` | *(0.10)* Fortschritt des laufenden Trainings in % (Übung x/y, Sätze x/y als Attribute; braucht Admin-Rechte) |
| `sensor.opengym_rest_timer` | *(0.10)* Pausentimer aus HA: `idle` (Bereit) / `running` (Läuft), Ende als Attribut `ends_at`, Restzeit `remaining` |
| `sensor.opengym_<muskel>_weekly_sets` | *(0.10)* effektive Sätze dieser Woche je Muskel — mit `state_class: measurement`, also Langzeitstatistik |
| `sensor.opengym_coach` | *(0.10, nur mit Coach)* `idle` · `queued` · `running` · `proposal`, Vorschlag und Änderungen als Attribute |
| `sensor.opengym_paired_watches` | *(0.10, nur mit Uhr-Funktion)* gekoppelte Uhren, zuletzt gesehen |
| `sensor.opengym_watch_heart_rate` | *(0.10)* neueste Herzfrequenz von der Uhr (bpm). Uhr-Sensoren gibt es erst, sobald eine Uhr gekoppelt ist; sie erscheinen dann ohne Neustart. |
| `sensor.opengym_heart_rate_zone` | *(0.10)* HF-Zone 1–5 (50/60/70/80/90 % der Max-HF aus den Optionen) |

Außerdem *(0.10)*:

- `binary_sensor.opengym_today_done` — `on`, sobald heute ein Workout oder eine Tagesnotiz existiert (openGyms `nudge-check`)
- `binary_sensor.opengym_workout_reminder_due` — `on`, solange openGyms Erinnerungsregel heute noch erinnern würde
- `button.opengym_accept_coach_proposal` / `button.opengym_reject_coach_proposal` — nur, wenn die Instanz den Coach anbietet

</details>

<details>
<summary><b>Muskeln, Kalender & Binärsensoren</b></summary>

Aus openGyms Übungskatalog (alle Bibliotheksübungen, dieselben Gewichte wie die App: Hauptmuskel 1,0, Hilfsmuskeln 0,4; eigene Übungen über ihre Muskeln bzw. Körperpartie), abgedeckt 14 Gruppen (`chest`, `deltoids`, `hamstring`, `abs`, …):

- `sensor.opengym_<gruppe>_idle` (z. B. `sensor.opengym_chest_idle`) — Tage seit der letzten Einheit (`999` = noch nie)
- `binary_sensor.opengym_<gruppe>_recovering` — `on`, solange die Gruppe (< 2 Tage) noch erholt
- `binary_sensor.opengym_rest_day` — `on`, wenn heute keine Einheit geplant ist
- `binary_sensor.opengym_heute_trainiert` / `binary_sensor.opengym_diese_woche_trainiert` — Trainiert-Trigger für Automationen
- `binary_sensor.opengym_active_workout` — `on`, solange live gehoben wird (mit Attributen: Name, Übung, Sätze). Benötigt Admin-Rechte auf der openGym-Instanz. Ohne sie wird der Sensor seit 0.10.1 gar nicht erst angelegt.
- `calendar.opengym_training_plan` — Wochenplan inkl. Tages-Overrides
- `calendar.opengym_workout_history` — abgeschlossene Workouts als Kalender
- `update.opengym_opengym_instanz` — zeigt an, wenn die Instanz hinter dem offiziellen Release steht

</details>

<details>
<summary><b>Geräte-Auslöser & Aktionen (ohne YAML)</b></summary>

Das Gerät **openGym** bietet im Automation-Editor:

| | |
|---|---|
| **Auslöser** | Workout abgeschlossen · Neuer persönlicher Rekord · Wiegewägung erfasst |
| **Aktion** | Wiegewägung protokollieren |

</details>

<details>
<summary><b>Services</b></summary>

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

</details>

<details>
<summary><b>Ereignisse</b></summary>

Für alle, die es genau wissen wollen:

| openGym-Ereignis | HA-Ereignis |
|---|---|
| `workout.finished` | `opengym_workout_finished` |
| `workout.pr` | `opengym_personal_record` |
| `weighin.logged` | `opengym_weighin_logged` |

</details>

<details>
<summary><b>Beispiel-Automationen</b></summary>

**Licht an, wenn das Training fertig ist:**

```yaml
automation:
  - alias: "Workout geschafft"
    triggers:
      - trigger: event
        event_type: opengym_workout_finished
    actions:
      - action: light.turn_on
        target:
          entity_id: light.wohnzimmer
        data:
          brightness: 200
```

**Erinnerung, wenn zu lange nichts lief:**

```yaml
automation:
  - alias: "Ab ins Gym"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.opengym_days_since_last_workout
        above: 4
    actions:
      - action: notify.notify
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

</details>

## 🩺 Fehlerbehebung

| Problem | Ursache | Lösung |
|---|---|---|
| **`cannot_connect`** („nicht erreichbar“) beim Einrichten | falsche URL oder Port (`3000` statt `8080`), Proxy-Login oder HTML-Seite statt API, HTTPS-Zertifikat ungültig, Firewall | `curl <URL>/api/config` vom HA-Host aus muss JSON liefern; LAN-URL des `web`-Containers nehmen; Cloudflare Access o. Ä. für `/api/*` ausnehmen |
| **`invalid_code`** („Code falsch oder abgelaufen“) | Code älter als 5 Minuten, schon benutzt, durch einen neueren ersetzt, oder für eine andere Instanz erzeugt | neuen Code unter *Einstellungen → Konto → Mobile App koppeln* erzeugen und sofort eintragen; dieselbe Instanz wie in der URL verwenden |
| **Webhooks kommen nicht an** (Daten erst nach dem Poll) | `INTEGRATIONS=webhook` fehlt; HA-URL privat ohne `INTEGRATIONS_ALLOW_LAN=1`; `.local`-Name oder `127.0.0.1` als HA-URL; Container nach `.env`-Änderung nicht neu erstellt | Schritt 2 und 4 prüfen; `docker compose up -d`; `docker compose exec api printenv INTEGRATIONS_ALLOW_LAN`; in openGym das Blatt der Webhook-Verbindung öffnen und den letzten Fehler lesen (`refusing to connect` heißt: Adresse gesperrt) |
| Webhook-Fehler `ECONNREFUSED` oder Timeout | HA-Port von der Firewall gesperrt, oder openGym in einem Docker-Netz ohne Route ins LAN | Port `8123` für den openGym-Host freigeben; Probe aus dem Container (Schritt 4); bei `network_mode`/eigenen Netzen die Route prüfen |
| HA meldet eine **Reparatur** „Webhook-Zustellungen fehlgeschlagen“ | openGym konnte mehrfach nicht zustellen | Ursache wie oben beheben, dann die Reparatur bestätigen. Die fehlgeschlagenen Zustellungen werden neu eingereiht. |
| **Karten fehlen** im Karten-Dialog | HA nach der Installation nicht neu gestartet; Dashboard im YAML-Modus; Browser-Cache | neu starten; Ressource manuell eintragen (Schritt 7); Strg+F5 bzw. Frontend-Cache der App leeren |
| Karte zeigt „Konfigurationsfehler“ / *Custom element doesn't exist* | Ressource fehlt oder alter Cache | wie oben; unter *Ressourcen* muss `/opengym/opengym-muscle-card.js?v=…` stehen |
| **Entitäten „Nicht verfügbar“** | openGym nicht erreichbar, nach mehreren Fehlschlägen erscheint zusätzlich eine Reparatur; Sitzung abgelaufen, dann startet HA eine erneute Authentifizierung | URL und Erreichbarkeit prüfen; bei *Erneut authentifizieren* einen neuen Kopplungscode eingeben. Seit 0.10.1 werden Uhr-Sensoren erst angelegt, wenn eine Uhr gekoppelt ist, und Live-Sensoren nur mit Admin-Konto. Alte Einträge entfernt die Integration selbst. |
| Live-Fortschritt / „Training läuft“ fehlt | Konto ist kein Admin | openGym gibt Live-Präsenz nur an Admins heraus; mit einem Admin-Konto koppeln |

## ❓ FAQ

<details>
<summary><b>Brauche ich Webhooks?</b></summary>

Nein. Ohne Webhooks pollt die Integration (Standard alle 15 Minuten, dazu die Schnellprüfung alle 30 s). Webhooks machen *Training beendet*, *Rekord* und *Wiegen* sofort sichtbar und lösen Automationen ohne Verzögerung aus.
</details>

<details>
<summary><b>Warum fehlen Live-Fortschritt und „Training läuft“?</b></summary>

openGym teilt Live-Präsenz nur mit Admin-Konten (`/api/admin/users`). Ohne Admin-Rechte legt die Integration diese Entitäten gar nicht an.
</details>

<details>
<summary><b>Warum sehe ich keine Uhr- oder Coach-Entitäten?</b></summary>

Uhr-Sensoren entstehen erst, wenn eine Uhr gekoppelt ist, dann ohne Neustart. Coach-Entitäten gibt es nur, wenn die Instanz den Coach anbietet. Wird der Coach später eingeschaltet, die Integration einmal neu laden.
</details>

<details>
<summary><b>Kann ich Coach-Vorschläge in HA annehmen?</b></summary>

Einfache Werte (Sätze, Wiederholungen, Wdh.-Bereich, Sekunden, Steigerung, Progression, Aufwärmen, Routinenname) übernimmt Home Assistant selbst, inklusive Undo-Schnappschuss für die App. Vorschläge mit Strukturänderungen (Übung tauschen, Wochenplan, neuer Plan) musst du in der App annehmen; der Annehmen-Button sagt dir das dann. Ablehnen geht immer.
</details>

<details>
<summary><b>Warum kennt der Pausentimer nur Timer aus HA?</b></summary>

openGym hält Timer nur im Speicher und gibt sie nicht heraus. `sensor.opengym_rest_timer` zeigt deshalb Timer, die mit `opengym.start_rest_timer` gestartet wurden: `idle` oder `running`, mit Endzeit in `ends_at`.
</details>

<details>
<summary><b>Mehrere openGym-Profile?</b></summary>

Die Integration mehrfach hinzufügen, je Profil ein Kopplungscode. Jeder Service nimmt optional `entry_id`, und die Karten fragen beim richtigen Eintrag nach.
</details>

<details>
<summary><b>Was lässt sich einstellen?</b></summary>

Über die **Optionen** der Integration: Poll-Intervall (Standard 15 Min.), Schnellprüfung (Standard 30 s, `0` = aus) und maximale Herzfrequenz für die HF-Zonen (Standard 190).
</details>

<details>
<summary><b>Wie sicher ist das?</b></summary>

- Die **Webhook-URL ist das Geheimnis** — sie ist einmalig, lang und nicht erratbar.
- Mit hinterlegtem **Signing Secret** prüft die Integration jeden Aufruf: `X-OpenGym-Signature` als HMAC-SHA256 über `t=<zeit>.<body>`, Zeitfenster 5 Minuten, Timing-safe verglichen. Unpassende Sendungen werden verworfen.
- **Keine Passwörter:** der Zugriff läuft über einen Pairing-Code, der Token wird automatisch erneuert.
- openGym liefert nur an **HTTPS** aus, oder per `http://` ins LAN, wenn `INTEGRATIONS_ALLOW_LAN=1` gesetzt ist. Zustellungen kommen „mindestens einmal“; Duplikate erkennst du an `event_id`.
</details>

## 🙏 Credits & Lizenz

- **[openGym](https://github.com/DuarteSantos8/openGym)** von DuarteSantos8 (AGPL-3.0). Logo, Körperkarten-Geometrie und Übungskatalog stammen aus dem openGym-Projekt; Details und Lizenzen in [NOTICE.md](NOTICE.md).
- Körperkarte basiert auf [MuscleMap](https://github.com/melihcolpan/MuscleMap) (MIT).
- Diese Integration: **[MIT](LICENSE)**. Kein offizielles openGym- oder Home-Assistant-Projekt.
