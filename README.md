# Home Assistant: sequenzieller Zigbee-OTA-Scheduler

[![CI](https://github.com/t-flow-sash/ha-zigbee-ota-scheduler-blueprint/actions/workflows/ci.yml/badge.svg)](https://github.com/t-flow-sash/ha-zigbee-ota-scheduler-blueprint/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Mit diesem Blueprint verwaltet eine Blueprint-Instanz beliebig viele logische Zigbee-Geräteklassen und installiert verfügbare Firmwareupdates **global streng nacheinander**. Jede Klasse hat eine eigene geordnete Liste von `update`-Entitäten, ein Updatefenster und optional ein Stummzeitfenster. Ein optionales All-trackers-home-Gate verhindert neue Starts, wenn nicht alle ausgewählten Personen zuhause sind.

[![Blueprint in Home Assistant importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ft-flow-sash%2Fha-zigbee-ota-scheduler-blueprint%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fzigbee_ota_scheduler%2Fsequential_ota_by_class.yaml)

Direkter Import-Link:

```text
https://github.com/t-flow-sash/ha-zigbee-ota-scheduler-blueprint/blob/main/blueprints/automation/zigbee_ota_scheduler/sequential_ota_by_class.yaml
```

## Voraussetzungen

- **Home Assistant 2025.8.0 oder neuer.** `fields` und `multiple` für den offiziellen `object`-Selector kamen mit 2025.7; die hier zusätzlich benötigte sortierbare Mehrfachauswahl (`reorder`) ist ab 2025.8 verfügbar.
- Die Zigbee-Integration muss pro Gerät eine installierbare Home-Assistant-`update`-Entität bereitstellen.

## Eigenschaften

- beliebig viele Klassen in einer Automation über den offiziellen `object`-Selector mit `multiple: true` und `fields`
- eigene Update- und optionale Stummzeitfenster je Klasse, jeweils mit korrektem Mitternachtsüberlauf
- Klassenreihenfolge und Entity-Reihenfolge bilden gemeinsam die Priorität
- minütliche Prüfung plus Prüfung beim Home-Assistant-Start; dadurch maximal etwa eine Minute Startlatenz
- Installation nur bei exakt `on`; `off`, `unknown`, `unavailable` und fehlende Entitäten starten kein OTA
- optionales All-trackers-home-Gate: Sind Tracker konfiguriert, müssen **ALLE** exakt `home` sein
- `update.install` und direkt anschließend Warten auf den bestätigten Zustand `off`
- globaler Abschluss-Timeout; Timeout oder Servicefehler beendet den Lauf fail-closed
- `mode: single` verhindert innerhalb dieser einen Instanz jedes parallele OTA
- ein bereits laufendes OTA wird bei Fensterende, Stummzeitbeginn oder Abwesenheit nicht hart abgebrochen; vor dem nächsten Gerät gelten alle Gates erneut

## Installation

### Über den Import-Button

Den Button oben öffnen, Blueprint importieren und anschließend **eine** Automation daraus erstellen. Alle gewünschten Klassen werden in dieser Automation konfiguriert.

### Manuell

1. Die Datei `blueprints/automation/zigbee_ota_scheduler/sequential_ota_by_class.yaml` herunterladen.
2. Unter demselben relativen Pfad in das Home-Assistant-Konfigurationsverzeichnis kopieren.
3. In Home Assistant **Einstellungen → Automatisierungen & Szenen → Blueprints** öffnen und die Blueprint-Liste neu laden.
4. Eine Automation erstellen und dort alle Klassen in der gewünschten Priorität eintragen.

## Konfiguration

### Globale Eingaben

| Eingabe | Bedeutung |
|---|---|
| Geräteklassen | Geordnete, beliebig erweiterbare Liste der Klassenobjekte |
| Anwesenheitstracker | Optionale Liste von `device_tracker.*`; leer deaktiviert das Gate |
| Abschluss-Timeout | Maximale Wartezeit auf `off`, nachdem `update.install` zurückgekehrt ist |

### Felder je Klasse

| Feld | Bedeutung |
|---|---|
| Klassenname | Frei benannte logische Gruppe; nur Metadaten, keine automatische Erkennung |
| Update-Entitäten | Geordnete Liste der zugehörigen `update.*`-Entitäten |
| Updatefenster Start/Ende | Inklusive Start- und exklusive Endgrenze für neue OTA-Starts |
| Stummzeit aktiv | Schaltet das Ausschlussfenster für diese Klasse ein |
| Stummzeit Start/Ende | Inklusive Start- und exklusive Endgrenze, in der kein neues OTA startet |

### Zeitfenster-Semantik

- `Start < Ende`: normales Fenster am selben Tag, zum Beispiel `01:00` bis `05:00`.
- `Start > Ende`: Fenster über Mitternacht, zum Beispiel `23:30` bis `05:00`.
- `start == end`: Das Updatefenster gilt ganztägig. Ein **aktiviertes** Stummzeitfenster mit gleichen Grenzen gilt ebenfalls ganztägig und blockiert damit alle neuen Starts. Ist die Stummzeit deaktiviert, werden ihre Zeiten ignoriert.
- Alle Endgrenzen sind exklusiv. Ein schon laufendes OTA darf sauber fertig werden.

### Tracker-Semantik

Eine leere Tracker-Liste deaktiviert das Gate. Sobald mindestens ein Tracker gewählt ist, müssen **ALLE** ausgewählten Entitäten unmittelbar vor jedem neuen OTA exakt den Zustand `home` haben. `not_home`, `unknown`, `unavailable` und eine fehlende Entität sind fail-closed und verhindern einen neuen Start. Nach Abschluss des laufenden OTA werden Fenster, Stummzeit und Tracker vor dem nächsten Gerät erneut ausgewertet.

## Beispiel: zwei Klassen in einer Instanz

```yaml
use_blueprint:
  path: zigbee_ota_scheduler/sequential_ota_by_class.yaml
  input:
    device_classes:
      - name: Zigbee-Lampen
        update_entities:
          - update.flur_lampe_firmware
          - update.wohnzimmer_lampe_firmware
        update_start: "23:30:00"
        update_end: "05:00:00"
        quiet_enabled: true
        quiet_start: "00:30:00"
        quiet_end: "01:30:00"
      - name: Batteriesensoren
        update_entities:
          - update.keller_sensor_firmware
          - update.garage_sensor_firmware
        update_start: "06:00:00"
        update_end: "08:00:00"
        quiet_enabled: false
        quiet_start: "00:00:00"
        quiet_end: "00:00:00"
    presence_trackers:
      - device_tracker.alex_phone
      - device_tracker.sam_phone
    install_timeout:
      hours: 1
```

Sind mehrere Klassen gleichzeitig erlaubt, wird zuerst die frühere Klasse vollständig in ihrer Entity-Reihenfolge geprüft. Danach folgt die nächste Klasse. Entitäten ohne verfügbares Update werden übersprungen.

## Architektur und Grenzen

Der Blueprint kopiert `device_classes` und die Tracker-Eingabe zunächst in Automation-Variablen. Ein äußerer serieller `repeat` verarbeitet Klassen; vor dem inneren `repeat` werden die Klassenfelder gesichert, damit dessen eigenes `repeat.item` die äußeren Werte nicht überschreibt. Ein innerer serieller `repeat` prüft unmittelbar vor jeder Installation Updatefenster, Stummzeit, alle Tracker und den exakten Zustand `on`.

Der Blueprint nutzt ausschließlich den Home-Assistant-Vertrag `update.install`. Er ist damit für ZHA, Zigbee2MQTT und andere Integrationen geeignet, **sofern** diese eine kompatible Update-Entität liefern. Daraus folgen keine Hersteller- oder Kompatibilitätszusagen.

- `mode: single` serialisiert nur die eine erzeugte Automation. Erstelle nicht zusätzlich eine zweite Instanz mit denselben Geräten, wenn globale Serialisierung gewünscht ist.
- Minutenticks während eines laufenden OTA werden durch `mode: single` verworfen. Nach dem Abschluss prüft spätestens der nächste Minutentick erneut.
- Home-Assistant-Neustart oder Automation-Reload beendet aktive Automationsläufe und Waits; es gibt keine persistente Checkpoint-Wiederaufnahme.
- Der Timeout beginnt erst, nachdem `update.install` zurückgekehrt ist. Ein integrationsintern blockierender Serviceaufruf lässt sich generisch nicht hart abbrechen.
- Der Blueprint prüft nicht, ob eine Entität tatsächlich zu Zigbee gehört; die Auswahl liegt beim Benutzer.

## Migration von der bisherigen Version

Die bisherigen Eingaben `device_class_name`, `update_entities`, `start_time`, `end_time` und `inter_device_delay` existieren nicht mehr. Bestehende erzeugte Automationen müssen in der UI neu konfiguriert werden:

1. Eine einzige Automation aus dem aktualisierten Blueprint verwenden.
2. Jede bisherige Instanz als Klassenobjekt in **Geräteklassen** übertragen.
3. Bisherige Start-/Endzeiten in `update_start`/`update_end` übernehmen.
4. Optional Stummzeit und Anwesenheitstracker konfigurieren.
5. Alte, nun redundante Blueprint-Automationen erst nach erfolgreicher Prüfung deaktivieren oder entfernen.

## Sicherheit und Batterie

- Coordinator und netzversorgte Zigbee-Router während des Fensters stabil erreichbar halten.
- Batteriegeräte können bei OTA lange wach bleiben und viel Energie verbrauchen; vorher ausreichend laden beziehungsweise Batterie wechseln.
- Geräte während eines Updates nicht ausschalten, zurücksetzen oder aus dem Netz entfernen.
- Mit wenigen unkritischen Geräten beginnen und Integrations-/Herstellerhinweise prüfen.
- Den Abschluss-Timeout nicht aggressiv kurz wählen.

## Entwicklung und Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
```

Die statischen Tests prüfen unter anderem Object-Selector-Felder, mehrere Klassen, beide Trigger, verschachtelte Serialisierung, All-home-Gate, normale/ganztägige/Mitternachtsfenster, Stummzeit, exakten `on`-Start, direkten Abschluss-Wait, Timeout und `mode: single`. GitHub Actions instanziiert außerdem zwei Klassen mit Stummzeit und Tracker und führt `hass --script check_config` aus.

## Referenzen

- [Home Assistant: Blueprint selectors](https://www.home-assistant.io/docs/blueprint/selectors/)
- [Home Assistant Core 2025.7: Object selector fields/multiple](https://github.com/home-assistant/core/pull/147215)
- [Home Assistant: `update.install`](https://www.home-assistant.io/actions/update.install/)
- [Home Assistant: Update-Integration](https://www.home-assistant.io/integrations/update/)
- [Home Assistant: Automation modes](https://www.home-assistant.io/docs/automation/modes/)

## Lizenz

MIT, siehe [LICENSE](LICENSE).
