# Home Assistant: sequenzieller Zigbee-OTA-Scheduler

[![CI](https://github.com/t-flow-sash/ha-zigbee-ota-scheduler-blueprint/actions/workflows/ci.yml/badge.svg)](https://github.com/t-flow-sash/ha-zigbee-ota-scheduler-blueprint/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Mit diesem Blueprint verwaltet **eine Blueprint-Instanz** beliebig viele priorisierte Zigbee-Geräteklassen und installiert verfügbare Firmwareupdates global streng nacheinander. Die `update.*`-Entitäten werden bei jedem Lauf live aus Home Assistant abgeleitet; eine manuelle Update-Entity-Liste gibt es nicht mehr.

[![Blueprint in Home Assistant importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ft-flow-sash%2Fha-zigbee-ota-scheduler-blueprint%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fzigbee_ota_scheduler%2Fsequential_ota_by_class.yaml)

Direkter Import-Link:

```text
https://github.com/t-flow-sash/ha-zigbee-ota-scheduler-blueprint/blob/main/blueprints/automation/zigbee_ota_scheduler/sequential_ota_by_class.yaml
```

## Voraussetzungen

- **Home Assistant 2025.8.0 oder neuer.** Der Blueprint verwendet den offiziellen `object`-Selector mit `multiple: true` und `fields` sowie Registry-Templatefunktionen.
- ZHA oder Zigbee2MQTT muss pro Gerät eine installierbare Home-Assistant-`update`-Entität bereitstellen.

## Live-Discovery und „Primär-Domain“

Home Assistant Devices besitzen in der Device Registry **keine kanonische Primary-Domain**. „Primär-Domain“ bedeutet in diesem Blueprint deshalb bewusst: **die erste passende konfigurierte Domain**. Die Reihenfolge der Klassen ist die deterministische Prioritätsregel.

Bei jedem Minutentick und beim Home-Assistant-Start:

1. Der Blueprint durchläuft live `states.update`.
2. `device_id(update_entity)` muss eine Device-ID liefern.
3. `device_attr(device_id, 'identifiers')` muss das Gerät als Zigbee ausweisen:
   - ZHA: Identifier-Namespace `zha`;
   - Zigbee2MQTT: Namespace `mqtt` und der Identifier-Wert enthält case-insensitive `zigbee2mqtt`.
4. Aus `device_entities(device_id)` werden die Domains aller Geschwister-Entitäten abgeleitet.
5. Das Update gehört ausschließlich zur ersten konfigurierten Domain, die unter diesen Domains vorkommt. Dadurch wird kein Update doppelt eingeplant.

Typische Reihenfolgen sind `climate vor sensor`, `light vor sensor` oder `binary_sensor vor sensor`. Ein Gerät mit `climate.*`, `sensor.*` und `update.*` landet also in der früher konfigurierten Klasse. Umbenannte und neu hinzugefügte Geräte werden ohne Blueprint-Edit beim nächsten Tick erfasst. Innerhalb einer Klasse werden Kandidaten deterministisch nach Entity-ID sortiert.

Bewusste Grenzen: Geräte ohne Device-ID, ohne passende Registry-Identifier, Nicht-Zigbee-Updates und Kandidaten ohne Treffer in einer konfigurierten Domain werden übersprungen. Beim MQTT-Pfad werden ausschließlich Identifier mit `mqtt` **und** `zigbee2mqtt` akzeptiert; generische MQTT-Fremdgeräte werden nicht aufgenommen. Deaktivierte Registry-Entities ohne Zustand erscheinen nicht in `states.update`.

## Eigenschaften

- beliebig viele Domain-Klassen über den offiziellen `object`-Selector mit `multiple: true` und `fields`
- benutzerfreundliche Domain-Auswahl mit gängigen physischen Domains und `custom_value: true` für künftige Home-Assistant-Domains
- eigene Update- und optionale Stummzeitfenster je Klasse, einschließlich Mitternachtsüberlauf
- minütliche Prüfung plus Prüfung beim Home-Assistant-Start; dadurch maximal etwa eine Minute Startlatenz
- Installation nur bei exakt `on`; `off`, `unknown`, `unavailable` und fehlende Entitäten starten kein OTA
- optionales All-trackers-home-Gate: Sind Tracker konfiguriert, müssen **ALLE** exakt `home` sein
- `update.install` und direkt anschließend Warten auf den bestätigten Zustand `off`
- globaler Abschluss-Timeout; Timeout oder Servicefehler beendet den Lauf fail-closed
- `mode: single`, keine Pause und kein Delay; innerhalb einer Instanz läuft höchstens ein OTA
- vor jedem Update werden Zeitfenster, Stummzeit, Tracker und Zustand `on` erneut geprüft

## Installation

Import-Button öffnen, Blueprint importieren und anschließend genau eine Automation daraus erstellen. Alternativ die Datei `blueprints/automation/zigbee_ota_scheduler/sequential_ota_by_class.yaml` unter demselben relativen Pfad im Home-Assistant-Konfigurationsverzeichnis speichern.

## Konfiguration

### Globale Eingaben

| Eingabe | Bedeutung |
|---|---|
| Geräteklassen | Geordnete Liste priorisierter Domain-/Fenster-Konfigurationen |
| Anwesenheitstracker | Optionale `device_tracker.*`; leer deaktiviert das Gate |
| Abschluss-Timeout | Maximale Wartezeit auf `off` nach `update.install` |

### Felder je Klasse

| Feld | Bedeutung |
|---|---|
| Klassenname | Frei gewählter Anzeigename |
| Primär-Domain | Geschwister-Entity-Domain, z. B. `light`, `climate`, `switch`, `cover` oder ein Custom-Wert |
| Updatefenster Start/Ende | Inklusive Start- und exklusive Endgrenze für neue OTA-Starts |
| Stummzeit aktiv | Aktiviert das Ausschlussfenster |
| Stummzeit Start/Ende | Inklusive Start- und exklusive Endgrenze, in der kein neues OTA startet |

### Zeitfenster-Semantik

- `Start < Ende`: normales Fenster am selben Tag.
- `Start > Ende`: Fenster über Mitternacht.
- `start == end`: Das Updatefenster gilt ganztägig. Ein aktiviertes Stummzeitfenster mit gleichen Grenzen gilt ebenfalls ganztägig und blockiert alle neuen Starts.
- Endgrenzen sind exklusiv. Ein laufendes OTA wird nicht abgebrochen; vor dem nächsten Gerät gelten alle Gates erneut.

### Tracker-Semantik

Eine leere Tracker-Liste deaktiviert das Gate. Sonst müssen **ALLE** ausgewählten Tracker unmittelbar vor jedem neuen OTA exakt `home` sein. `not_home`, `unknown`, `unavailable` und fehlende Entitäten verhindern fail-closed einen neuen Start.

## Beispiel: priorisierte Domains in einer Instanz

```yaml
use_blueprint:
  path: zigbee_ota_scheduler/sequential_ota_by_class.yaml
  input:
    device_classes:
      - name: Heizgeräte
        domain: climate
        update_start: "23:30:00"
        update_end: "05:00:00"
        quiet_enabled: true
        quiet_start: "00:30:00"
        quiet_end: "01:30:00"
      - name: Lampen
        domain: light
        update_start: "23:30:00"
        update_end: "05:00:00"
        quiet_enabled: false
      - name: Übrige Sensoren
        domain: sensor
        update_start: "06:00:00"
        update_end: "08:00:00"
        quiet_enabled: false
    presence_trackers:
      - device_tracker.alex_phone
    install_timeout:
      hours: 1
```

## Architektur und Laufzeitgrenzen

Ein äußerer serieller `repeat` verarbeitet Klassen in Konfigurationsreihenfolge. Klassenobjekt und 1-basierter Prioritätsindex werden vor dem inneren `repeat` gesichert. Das Discovery-Template iteriert live über `states.update`, prüft Registry-Identifier und ermittelt über `device_entities` den ersten passenden Klassenindex. Der innere serielle `repeat` verarbeitet nur die dieser Klasse gehörenden Updates.

- `mode: single` serialisiert nur diese eine erzeugte Automation. Keine zweite Instanz mit denselben Geräten anlegen, wenn globale Serialisierung gewünscht ist.
- Minutenticks während eines laufenden OTA werden verworfen; spätestens der nächste Tick prüft erneut.
- Home-Assistant-Neustart oder Automation-Reload beendet aktive Läufe und Waits; es gibt keine persistente Wiederaufnahme.
- Der Timeout beginnt, nachdem `update.install` zurückgekehrt ist. Ein integrationsintern blockierender Serviceaufruf lässt sich generisch nicht hart abbrechen.

## Breaking Migration: manuelle Listen → Domain-Klassen

Diese Version ist nicht eingabekompatibel mit Automationen, die je Klasse `update_entities` gespeichert haben. Bestehende Automationen müssen in der UI neu konfiguriert werden:

1. Vorhandene manuelle `update_entities`-Listen entfernen; sie werden nicht mehr unterstützt.
2. Für jedes bisherige Fenster stattdessen eine `domain` auswählen.
3. Die Klassen so sortieren, dass spezifische Domains vor generischen liegen, z. B. `climate`, `light`, `binary_sensor` jeweils vor `sensor`.
4. Zeiten, optionale Stummzeit, Tracker und Timeout übernehmen.
5. Nach einem Testlauf alte redundante Blueprint-Automationen deaktivieren oder entfernen.

## Sicherheit und Batterie

- Coordinator und netzversorgte Zigbee-Router während des Fensters stabil erreichbar halten.
- Batteriegeräte können bei OTA lange wach bleiben; vorher ausreichend laden beziehungsweise Batterie wechseln.
- Geräte während eines Updates nicht ausschalten, zurücksetzen oder entfernen.
- Mit wenigen unkritischen Geräten beginnen und Integrations-/Herstellerhinweise prüfen.

## Entwicklung und Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
```

Die Tests prüfen Selector- und Discovery-Verträge, eine pure Python Referenzklassifikation samt Identifier-Matrix, First-Match-Priorität/Deduplizierung, Skip-Fälle, Zeit-/Quiet-/Tracker-/State-Gates, direkten fail-closed Wait, Timeout, `mode: single` und das Fehlen von Delays. GitHub Actions führt zusätzlich `hass --script check_config` mit Home Assistant 2025.8.0 und der aktuellen Version aus.

## Referenzen

- [Home Assistant: Templating – Devices](https://www.home-assistant.io/docs/configuration/templating/#devices)
- [Home Assistant: Blueprint selectors](https://www.home-assistant.io/docs/blueprint/selectors/)
- [Home Assistant: `update.install`](https://www.home-assistant.io/actions/update.install/)
- [Home Assistant: Automation modes](https://www.home-assistant.io/docs/automation/modes/)

## Lizenz

MIT, siehe [LICENSE](LICENSE).
