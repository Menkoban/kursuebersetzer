# Kursübersetzer – Anleitung für Lehrkräfte

Der Kursübersetzer bringt einen fertigen Moodle-Kurs (Sicherung als `.mbz`) in eine
andere Sprache: Texte, Testfragen, Beschriftungen im H5P-Rundgang und der gesprochene Ton
der Videos. Bild und Aufbau des Kurses bleiben gleich. Heraus kommt eine neue `.mbz`, die
man in Moodle hochlädt.

## 1. Starten

1. Die Zip-Datei von https://github.com/Menkoban/kursuebersetzer/releases/latest herunterladen.
2. Den Ordner `Kursuebersetzer` an einen festen Ort entpacken, z. B.
   `C:\Users\<Name>\AppData\Local\Programs\Kursuebersetzer`.
3. `Kursuebersetzer.exe` doppelklicken. Es öffnet sich ein eigenes Fenster.
   *Tipp:* Rechtsklick auf die .exe → „Senden an“ → „Desktop (Verknüpfung erstellen)“.

**Windows-Warnung „Der Computer wurde durch Windows geschützt“:** Das Programm ist (noch)
nicht digital signiert. Auf „Weitere Informationen“ klicken, dann „Trotzdem ausführen“.
An Schulrechnern kann die Schul-IT das Starten blockieren – dann bitte dort freigeben lassen.

Es muss nichts zusätzlich installiert werden: Python, ffmpeg und die Werkzeuge sind enthalten.
Beim ersten Vertonen lädt das Programm einmalig das Spracherkennungsmodell (~1,5 GB).

## 2. Einmalig: Zugänge eintragen (Zahnrad oben rechts)

Die Schule bringt ihre eigenen Zugänge mit. Die Schlüssel bleiben nur auf diesem Rechner.

| Wofür | Was man braucht | Kosten |
|---|---|---|
| **Texte übersetzen** (Pflicht) | Schlüssel von **Claude** (console.anthropic.com) *oder* **OpenRouter** (openrouter.ai) *oder* ein eigener Dienst mit OpenAI-Schnittstelle | Claude Haiku: etwa 1–2 Cent je Kurs |
| **Videos vertonen** (kostenlos) | nichts – „Ohne Konto (Edge)“ | kostenlos, aber nicht offiziell freigegeben |
| **Videos vertonen** (offiziell) | Schlüssel und Region von **Azure Speech** (portal.azure.com, Dienst „Speech“, Region z. B. Germany West Central) | kostenloses Monatskontingent |
| **Lippensynchrone Videos** (optional) | **HeyGen-API-Schlüssel** von platform.heygen.com/api-keys (eigene Entwicklerseite, nicht in der normalen HeyGen-Oberfläche) | eigenes API-Guthaben (ab 5 $, getrennt vom HeyGen-Abo), Preis je Videominute; Verbrauch unter app.heygen.com/developers/usage |

Mit „Probeübersetzung“ und „Hörprobe“ lässt sich jeder Zugang sofort prüfen.

**Moodle-Prüfung (empfohlen):** Im Zahnrad auf „Einrichten“ klicken. Das Programm lädt
einmalig ein kleines Moodle 4.5 aus den offiziellen Quellen (~450 MB, 10–20 Minuten).
Danach wird jede fertige Sicherung probeweise eingespielt: Man weiß vor dem Hochladen,
ob Moodle sie annimmt.

## 3. Einen Kurs übersetzen

1. Im Schul-Moodle den Kurs sichern (Kurs → Mehr → Sicherung) und die `.mbz` herunterladen.
2. Die `.mbz` ins Fenster ziehen.
3. Zielsprache wählen (193 Sprachen, wie bei Google Übersetzer).
4. Videoordner angeben, z. B. `…\Kurse\Hauswirtschaft\FR\Videos`. Liegen dort schon fertige
   Videos (benannt wie die Hotspots im Rundgang, z. B. `Fritteuse_FR.mp4`), werden sie
   übernommen; alle anderen werden erstellt und dort abgelegt.
5. Weg für fehlende Videos wählen: **Microsoft-Stimme** (kostenlos, nicht lippensynchron) oder
   **HeyGen** (lippensynchron, kostet Guthaben).
6. „Übersetzung starten“. Rechts sieht man jeden Schritt. Ein Kurs mit 10 Minuten Video
   braucht mit Microsoft-Stimme etwa 15 Minuten.

Ergebnis: Liegt der Videoordner in `…\<SPRACHE>\Videos`, landet die Sicherung in
`…\<SPRACHE>\Kurs\`. Ist sie größer als 500 MB, entsteht zusätzlich eine kleine Fassung
`…_klein.mbz` – **diese** hochladen (viele Schul-Moodles nehmen höchstens 512 MB).

## 4. In Moodle hochladen

Moodle → Kurs wiederherstellen → `.mbz` hineinziehen → „Als neuen Kurs wiederherstellen“ →
durchklicken. Danach den Kurs ansehen, bevor er sichtbar geschaltet wird.

## 5. Bitte beachten

- **Datenschutz:** Kurstexte gehen an den gewählten Übersetzungsdienst, bei HeyGen auch die
  Videos mit Gesicht und Stimme. Vor dem ersten Einsatz die Seite „Datenschutz“ im Programm
  lesen und mit der schulischen Datenschutzbeauftragten abstimmen. Dort liegt auch eine
  Vorlage für das Verzeichnis der Verarbeitungstätigkeiten.
- **Qualität:** Maschinelle Übersetzung kann Fehler enthalten. Sicherheitsrelevante Aussagen
  (Verbote, „nie/immer“, Schutzausrüstung, Testantworten) vor dem Einsatz gegenprüfen.
- **Feste Links:** Zeigt der Hinweis „Fester Link“, verweist der Rundgang noch auf den alten
  Kurs. Nach dem ersten Import die Nummer des Tests im neuen Kurs ablesen, unter „Feinheiten“
  eintragen und noch einmal bauen.

## Wo liegt was?

| | |
|---|---|
| Programm | der entpackte Ordner `Kursuebersetzer` |
| Einstellungen, Zwischenstände, Protokoll | `%LOCALAPPDATA%\Kursuebersetzer` |
| Lizenzen | Ordner `Lizenzen` neben der .exe |
| Quelltext, Fragen, Fehler melden | https://github.com/Menkoban/kursuebersetzer |
