@echo off
rem Kursuebersetzer ohne Container starten: Doppelklick genuegt.
chcp 65001 >nul
cd /d "%~dp0"
python -c "import fastapi, uvicorn, multipart, anthropic" 2>nul || (
  echo Einmalig: benoetigte Pakete werden installiert ...
  python -m pip install -q -r requirements.txt
)
rem Microsoft aendert ab und zu die Anmeldung der Vorlesestimmen; nur die neueste
rem edge-tts-Fassung kommt dann durch. Darum bei jedem Start kurz nachziehen.
python -m pip install -q --upgrade edge-tts >nul 2>&1
echo.
echo   Kursuebersetzer laeuft:  http://localhost:8765
echo   Zum Beenden dieses Fenster schliessen.
echo.
start "" http://localhost:8765
python -m uvicorn app.server:app --host 127.0.0.1 --port 8765
