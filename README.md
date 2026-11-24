# Home Assistant: sequenzieller Zigbee-OTA-Scheduler

[![CI](https://github.com/t-flow-sash/ha-zigbee-ota-scheduler-blueprint/actions/workflows/ci.yml/badge.svg)](https://github.com/t-flow-sash/ha-zigbee-ota-scheduler-blueprint/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Ein Home-Assistant-Automation-Blueprint, der verfügbare Zigbee-Firmwareupdates in einem täglichen Zeitfenster **streng nacheinander** installiert. Jede Instanz verwaltet eine frei benannte logische Geräteklasse und eine explizit sortierte Liste von `update`-Entitäten.

[![Blueprint in Home Assistant importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ft-flow-sash%2Fha-zigbee-ota-scheduler-blueprint%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fzigbee_ota_scheduler%2Fsequential_ota_by_class.yaml)

Direkter Import-Link:

```text
https://github.com/t-flow-sash/ha-zigbee-ota-scheduler-blueprint/blob/main/blueprints/automation/zigbee_ota_scheduler/sequential_ota_by_class.yaml
```

## Eigenschaften

- täglicher Start zu einer konfigurierbaren Uhrzeit
- normales oder über Mitternacht laufendes Zeitfenster
- explizite, geordnete Liste von `update`-Entitäten
- nur Zustand `on` wird installiert; `off`, `unknown`, `unavailable` und nicht vorhandene Entitäten werden übersprungen
- genau ein `update.install`-Aufruf pro Iteration
- Abschluss-Wait und konfigurierbarer Timeout
- fail-closed: Timeout oder Servicefehler beendet den Restlauf, damit kein möglicherweise paralleles OTA beginnt
- optionale Pause zwischen erfolgreich abgeschlossenen Updates
- `mode: single` verhindert überlappende Läufe derselben Blueprint-Instanz
- ein bereits laufendes Update wird beim Erreichen der Endzeit nicht abgebrochen; die Zeit wird erst vor dem nächsten Gerät erneut geprüft

## Installation

### Über den Import-Button

Den Button oben öffnen, Blueprint importieren und anschließend eine Automation daraus erstellen.

### Manuell

1. Datei herunterladen:

   ```text
   blueprints/automation/zigbee_ota_scheduler/sequential_ota_by_class.yaml
   ```

2. Unter demselben relativen Pfad in das Home-Assistant-Konfigurationsverzeichnis kopieren.
3. In Home Assistant **Einstellungen → Automatisierungen & Szenen → Blueprints** öffnen und die Blueprint-Liste neu laden.
4. Für jede logische Geräteklasse eine eigene Automation erstellen.

## Konfiguration

| Eingabe | Bedeutung |
|---|---|
| Geräteklasse / Bezeichnung | Freier logischer Gruppenname, z. B. `Zigbee-Lampen` |
| Update-Entitäten | Geordnete Liste der zugehörigen `update.*`-Entitäten |
| Startzeit | Täglicher Trigger und inklusive Fenstergrenze |
| Endzeit | Exklusive Fenstergrenze |
| Abschluss-Timeout | Maximale Wartezeit auf den bestätigten Zustand `off`, nachdem `update.install` zurückgekehrt ist |
| Pause | Wartezeit nach erfolgreichem Abschluss vor dem nächsten Listeneintrag |

### Beispiel

Erstelle eine Blueprint-Automation mit:

- **Geräteklasse:** `Zigbee-Lampen`
- **Update-Entitäten:**
  1. `update.flur_lampe_firmware`
  2. `update.wohnzimmer_lampe_firmware`
  3. `update.schlafzimmer_lampe_firmware`
- **Start:** `23:30:00`
- **Ende:** `05:00:00`
- **Timeout:** `01:00:00`
- **Pause:** `00:00:30`

Das Zeitfenster läuft in diesem Beispiel korrekt über Mitternacht. Um 05:00 Uhr wird kein neues Update mehr gestartet. Ein kurz davor begonnenes Update darf sauber enden.

## Architektur und Semantik

Home Assistant stellt für Zigbee-Geräte **keine integrationsübergreifend einheitliche, automatisch discoverbare Geräteklasse im Sinne dieses Schedulers** bereit. Deshalb ist „Geräteklasse“ hier bewusst eine logische Gruppierung: Eine Blueprint-Instanz pro Gruppe, deren `update`-Entitäten explizit ausgewählt werden.

Der Blueprint ist integrationsagnostisch und ruft ausschließlich den offiziellen Home-Assistant-Vertrag `update.install` auf. Damit kann er mit ZHA, Zigbee2MQTT oder anderen Integrationen funktionieren, **wenn** diese eine kompatible und installierbare Home-Assistant-`update`-Entität bereitstellen. Es werden keine herstellerspezifischen Fähigkeiten zugesichert.

Die Liste läuft über `repeat.for_each`; dessen Sequenz ist seriell. Vor jeder neuen Installation prüft eine Home-Assistant-Zeitbedingung das Fenster. Die Zeitbedingung unterstützt laut HA-Dokumentation auch Fenster über Mitternacht und ist am Ende exklusiv. Nur der exakte Update-Zustand `on` betritt den Installationszweig. Nach `update.install` wartet der Blueprint auf `off`. Ein Timeout ist fail-closed und verhindert den Start des nächsten Geräts.

## Grenzen

- `mode: single` gilt pro erzeugter Automation. Mehrere Blueprint-Instanzen können parallel laufen. Verwende daher disjunkte Entity-Listen und überlappungsfreie Zeitfenster, wenn auch klassenübergreifend keine parallelen OTAs gewünscht sind.
- Ein Home-Assistant-Neustart oder Automation-Reload beendet einen aktiven Automationslauf; Scriptläufe sind nicht persistent. Der nächste reguläre Versuch erfolgt zur nächsten Startzeit. Das verhindert einen blinden doppelten Wiederanlauf, bietet aber keine Checkpoint-Wiederaufnahme.
- Der Timeout beginnt erst, nachdem der `update.install`-Aufruf zurückgekehrt ist. Home Assistant kann einen integrationsintern blockierenden Installationsaufruf nicht generisch hart abbrechen.
- Einige Integrationen aktualisieren den Zustand nach der Installation verzögert. Dann wartet der Blueprint bis `off` oder beendet den Batch nach dem Timeout.
- `start_time` und `end_time` sollten verschieden sein. Für ein bewusst ganztägiges Fenster ist dieser Blueprint nicht gedacht.
- Der Blueprint prüft nicht automatisch, ob eine Entität tatsächlich Zigbee gehört; die Auswahl liegt beim Benutzer.

## Sicherheit und Batterie

- Netzversorgte Zigbee-Router und der Coordinator sollten während des Fensters stabil erreichbar bleiben.
- Batteriegeräte können für OTA lange wach bleiben und erheblich Energie verbrauchen. Batterie vorher ausreichend laden bzw. wechseln und Herstellerhinweise beachten.
- Keine Geräte ausschalten, zurücksetzen oder aus dem Zigbee-Netz entfernen, solange ein Update läuft.
- Mit wenigen, unkritischen Geräten beginnen und Hersteller-/Integrationshinweise zu Firmware-Risiken prüfen.
- Timeout nicht aggressiv kurz wählen: Ein OTA kann je nach Gerät und Mesh deutlich länger dauern.

## Entwicklung und Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
```

Die Tests parsen das YAML inklusive `!input` und prüfen statisch unter anderem Sequenz, Zeitfenster-Gate, `mode: single`, `update.install`, exaktes Target, Abschluss-Wait und fail-closed Timeout. GitHub Actions führt dieselben Prüfungen aus und lädt zusätzlich eine reale Beispielautomation über `hass --script check_config` in Home Assistant.

## Referenzen

- [Home Assistant: `update.install`](https://www.home-assistant.io/actions/update.install/)
- [Home Assistant: Update-Integration und Zustände](https://www.home-assistant.io/integrations/update/)
- [Home Assistant Developer: Update entity](https://developers.home-assistant.io/docs/core/entity/update/)
- [Home Assistant: Time condition](https://www.home-assistant.io/conditions/time/)
- [Home Assistant: Automation modes](https://www.home-assistant.io/docs/automation/modes/)
- [Home Assistant: Blueprint schema](https://www.home-assistant.io/docs/blueprint/schema/)

## Lizenz

MIT, siehe [LICENSE](LICENSE).
