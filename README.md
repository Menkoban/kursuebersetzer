# Kursübersetzer

Eine Windows-Anwendung, die fertige **Moodle-Kurse in andere Sprachen** bringt – ohne die
Videos neu zu drehen. Entstanden an einer berufsbildenden Schule in Niedersachsen für
Sicherheitsunterweisungen (UVV), die Lernende mit geringen Deutschkenntnissen verstehen sollen.

**Moodle-Sicherung (`.mbz`) hineinziehen → Sprache wählen → starten.** Heraus kommt eine
neue Sicherung mit übersetzten Texten, Testfragen, H5P-Rundgang-Beschriftungen und neu
vertonten Videos, die vor der Ausgabe probeweise in ein echtes Moodle eingespielt wird.

- 193 Zielsprachen (wie Google Übersetzer)
- Übersetzung mit einem Sprachmodell nach Wahl: Claude, OpenRouter (Hunderte Modelle) oder
  ein eigener OpenAI-kompatibler Dienst
- Videos: neu vertont mit Microsoft-Stimmen (Edge-Vorlesedienst oder offiziell über
  Azure Speech) oder lippensynchron über die HeyGen-API
- Fertige Videos aus einem Ordner werden automatisch zugeordnet und übernommen
- Fassung ≤ 500 MB für Schul-Moodles mit Upload-Grenze
- Probe-Einspielung in ein lokales Moodle 4.5 („geht es hoch?“)
- Jede Schule nutzt ihre **eigenen** Zugänge; Schlüssel bleiben auf dem Rechner

**⬇ Herunterladen:** [Kursuebersetzer-1.0.0-Windows.zip](https://github.com/Menkoban/kursuebersetzer/releases/latest) – entpacken, `Kursuebersetzer.exe` starten.

**Für Lehrkräfte:** siehe [ANLEITUNG.md](ANLEITUNG.md) – Herunterladen, Starten, Zugänge, erster Kurs.
**Datenschutz:** im Programm unter „Datenschutz“ (mit Vorlage für das Verzeichnis der
Verarbeitungstätigkeiten). Kein Rechtsrat.

## Aufbau

```
app/start.py       Startprogramm: Dienst + eigenes Fenster (pywebview); dieselbe .exe führt
                   auch die Skill-Skripte aus, daher ist kein installiertes Python nötig
app/server.py      Bedienoberfläche (FastAPI) und Einstellungen
app/ablauf.py      ein Auftrag von der .mbz bis zur fertigen Sicherung
app/ki.py          Anbieter für die Übersetzung (Anthropic, OpenRouter, OpenAI-kompatibel)
app/vorlesen.py    Vorlesen über edge-tts oder Azure Speech
app/heygen.py      HeyGen-API v3 (Hochladen, Übersetzen, Abholen)
app/moodleprobe.py Probe-Einspielung über moodle-testinstanz
app/sprachen*.py   Sprachliste (werkzeug/sprachen_erzeugen.py)
app/static/        Oberfläche (HTML/CSS/JS ohne Build-Schritt)
werkzeug/bauen.py  baut die .exe samt Lizenzordner
```

Die eigentliche Kursarbeit erledigen zwei eigenständige Skills, die in die .exe eingepackt
werden: [moodle-kurs-uebersetzen](https://github.com/Menkoban/moodle-kurs-uebersetzen) und
[moodle-testinstanz](https://github.com/Menkoban/moodle-testinstanz).

## Selbst bauen

```
pip install -r requirements-bauen.txt
python werkzeug/bauen.py
```

Erwartet die beiden Skills als Nachbarordner (`../moodle-kurs-uebersetzen`,
`../moodle-testinstanz` oder unter `~/.claude/skills/`) und ffmpeg im PATH. Ergebnis: `%LOCALAPPDATA%\Programs\Kursuebersetzer\Kursuebersetzer.exe`.

Zum Entwickeln ohne Bau: `start.bat` (Browser statt eigenem Fenster).

## Tests

```
python -m pytest -q -p no:randomly tests
```

## Lizenz

MIT – siehe [LICENSE](LICENSE). Mitgelieferte Fremdbestandteile (u. a. FFmpeg unter GPL v3)
und ihre Lizenzen: [DRITTANBIETER.md](DRITTANBIETER.md).
