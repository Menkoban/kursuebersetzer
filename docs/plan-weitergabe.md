# Plan: Kursübersetzer zum Weitergeben an Schulen

Stand 20.10.2026. Grundlage: Recherche vom selben Tag (HeyGen, Microsoft, ffmpeg, DSGVO,
Signatur) und die Entscheidungen des Autors.

## Ziel

Jemand an einer anderen Schule lädt den Kursübersetzer herunter, startet die .exe und es
funktioniert bei ihm 1:1 wie beim Autor – mit **eigenen** Zugängen (Claude/OpenRouter,
optional HeyGen-API, optional Azure Speech). Nichts muss nachinstalliert werden außer dem
optionalen Moodle-Testlabor, das die App selbst per Knopf einrichtet.

## Entscheidungen des Autors (20.10.2026)

| Punkt | Entscheidung |
|---|---|
| Herausgeber | vorerst der Autor privat an Pilotschulen; Signatur folgt, wenn Schule/Land einsteigt |
| Vorlesestimme | edge-tts bleibt Standard (kostenlos, ohne Konto); **Azure Speech** kommt als offizielle Option dazu |
| HeyGen | nur über API-Schlüssel der Schule (kein MCP) |
| Quelltext | öffentlich auf GitHub, MIT-Lizenz |

## Arbeitspakete

1. **Moodle-Probe („geht es hoch?“)** – Skill `moodle-testinstanz` (setup_lab.py, run_restore.py)
   in die .exe; Knopf „Moodle-Prüfung einrichten“ lädt PHP, MariaDB, Moodle 4.5, mod_hvp,
   format_tiles einmalig aus den offiziellen Quellen nach `%LOCALAPPDATA%\Kursuebersetzer\moodle-lab`.
   Nach jedem Bau: Probe-Einspielung, Ergebnis als eigener Schritt, Testkurs wird wieder gelöscht.
   Ohne eingerichtetes Labor: Schritt „übersprungen“, kein Fehler.
2. **Azure Speech** als zweiter Vorleseweg: Schlüssel + Region im Zahnrad (Vorschlag
   `germanywestcentral`), Aufruf über die offizielle REST-Schnittstelle, gleiche Stimmnamen.
3. **HeyGen-API** gegen die aktuelle offizielle Doku (v3 video-translations, assets) prüfen
   und angleichen; Videos über 100 MB vor dem Hochladen verkleinern; Preis nicht fest
   eintragen, sondern verlinken.
4. **Datenschutz-Hinweis** beim ersten Start und vor dem ersten Versand: welcher Dienst
   bekommt was, wo stehen die Server. Vorlage für das Verzeichnis der Verarbeitungstätigkeiten
   (VVT) als Datei für die Schulleitung.
5. **Für fremde Rechner verallgemeinern** – keine Bezüge auf den Projektordner des Autors;
   „Sprachen Ihrer Kurse“ wird „Zuletzt verwendet“; Anleitung für Lehrkräfte.
6. **Lizenzen** – Ordner `Lizenzen` in der .exe: MIT (App), GPLv3 + Bauinfo + Quellcode-Link
   (ffmpeg), LGPLv3 (edge-tts), MIT/BSD/PSF der übrigen Teile.
7. **Veröffentlichen** – GitHub-Repo (öffentlich, MIT), Release mit gepackter Anwendung und
   „Erste Schritte“ (inkl. Hinweis zur Windows-Warnung, solange unsigniert).
8. **Abnahme** – Tests, unabhängiger Prüfagent, Neubau, echter Lauf mit der .exe.

## Offene Punkte für den Autor / die Datenschutzbeauftragte

- Versand von Kursinhalten in die USA (Anthropic, HeyGen, OpenRouter) – besonders Videos mit
  Gesicht und Stimme von Lehrkräften – mit der Datenschutzbeauftragten klären.
- edge-tts: Microsoft erlaubt die Nutzung außerhalb von Edge nicht ausdrücklich
  (Servicevertrag 3.a.vi). Für eine Weitergabe durch Schule/Land Azure Speech nehmen.
- Herausgeber und Signatur (Azure Artifact Signing für Organisationen ~10 $/Monat oder
  SignPath Foundation kostenlos für Open Source).
- Verteilweg, den die Schulträger akzeptieren (MSI, Store, Freigabeliste).
