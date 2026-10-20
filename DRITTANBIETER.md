# Mitgelieferte Fremdbestandteile

Der Kursübersetzer selbst steht unter der MIT-Lizenz (siehe `LICENSE`). Die fertige
Windows-Anwendung enthält außerdem folgende Bestandteile anderer Urheber. Ihre
Lizenztexte liegen im Ordner `Lizenzen` neben der `Kursuebersetzer.exe`.

| Bestandteil | Zweck | Lizenz | Quelle |
|---|---|---|---|
| FFmpeg 8.1.2 (Build von gyan.dev, „full“) | Videos und Ton bearbeiten | **GPL v3** | Quellcode: https://github.com/FFmpeg/FFmpeg/commit/38b88335f9 · Build-Konfiguration: `Lizenzen/ffmpeg-README.txt` · https://www.gyan.dev/ffmpeg/builds/ |
| moodle-kurs-uebersetzen | Kurs einlesen, Sicherung bauen, prüfen | MIT | https://github.com/Menkoban/moodle-kurs-uebersetzen |
| moodle-testinstanz | Probe-Einspielung in Moodle | MIT | https://github.com/Menkoban/moodle-testinstanz |
| edge-tts | Vorlesen über den Edge-Vorlesedienst | LGPL v3 | https://github.com/rany2/edge-tts |
| faster-whisper, CTranslate2 | Spracherkennung (lokal) | MIT | https://github.com/SYSTRAN/faster-whisper |
| Whisper-Modell „medium“ (wird beim ersten Gebrauch geladen) | Spracherkennung | MIT | https://huggingface.co/Systran/faster-whisper-medium |
| ONNX Runtime | Sprachpausen erkennen | MIT | https://github.com/microsoft/onnxruntime |
| pywebview | Programmfenster | BSD-3-Clause | https://github.com/r0x0r/pywebview |
| FastAPI, Starlette, Uvicorn | Bedienoberfläche | MIT / BSD-3-Clause | https://github.com/fastapi/fastapi |
| Anthropic Python SDK | Anbindung Claude | MIT | https://github.com/anthropics/anthropic-sdk-python |
| requests, httpx | Internetverbindungen | Apache-2.0 / BSD-3-Clause | https://github.com/psf/requests |
| Python 3.12 | Laufzeit | PSF-Lizenz | https://www.python.org |

**Nicht mitgeliefert, sondern beim Einrichten der Moodle-Prüfung aus den offiziellen
Quellen geladen:** PHP 8.2 (PHP-Lizenz), MariaDB 10.11 (GPL v2), Moodle 4.5 (GPL v3),
mod_hvp (GPL v3), format_tiles (GPL v3).

**Dienste, für die jede Schule eigene Zugänge braucht** (nicht Teil der Anwendung):
Anthropic (Claude) bzw. OpenRouter, optional Azure AI Speech, optional HeyGen. Es gelten
deren Nutzungsbedingungen. Der Edge-Vorlesedienst ist von Microsoft nicht offiziell für
andere Programme freigegeben; für den Einsatz durch Schule oder Land Azure Speech nutzen.
