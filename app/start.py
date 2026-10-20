"""Startprogramm der Windows-Anwendung Kursuebersetzer.exe.

Doppelklick: startet den Dienst im Hintergrund und oeffnet ein eigenes Programmfenster.
Fenster zu = Programm beendet.

Dieselbe .exe spielt auch "Python" fuer die Skill-Skripte: ablauf.py ruft
`Kursuebersetzer.exe -I -X utf8 analyse.py …` auf, so wie sonst `python analyse.py …`.
So braucht der Rechner kein installiertes Python.
"""
import os
import runpy
import socket
import subprocess
import sys
import threading
import time
import urllib.request

PORT = 8765
TITEL = "Kursübersetzer"
_FLAGGEN_MIT_WERT = {"-X", "-W"}


def basis():
    """Wo die mitgelieferten Dateien liegen: im Paket (_MEIPASS) oder im Projektordner."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def skriptaufruf(argumente):
    """[-I -X utf8] skript.py arg … -> (skript.py, [arg …]); sonst None."""
    i = 0
    while i < len(argumente) and argumente[i].startswith("-"):
        i += 2 if argumente[i] in _FLAGGEN_MIT_WERT else 1
    if i < len(argumente) and argumente[i].lower().endswith(".py"):
        return argumente[i], argumente[i + 1:]
    return None


def umgebung_einrichten(wurzel, umgebung):
    """Mitgelieferten Skill, verkleinern.py und ffmpeg bekannt machen (gehen vor Installiertem)."""
    skill = os.path.join(wurzel, "werkzeug", "moodle-kurs-uebersetzen")
    if os.path.isfile(os.path.join(skill, "scripts", "analyse.py")):
        umgebung["SKILL_ORDNER"] = skill
    klein = os.path.join(wurzel, "werkzeug", "verkleinern", "verkleinern.py")
    if os.path.isfile(klein):
        umgebung["VERKLEINERN"] = klein
    labor = os.path.join(wurzel, "werkzeug", "moodle-testinstanz")
    if os.path.isfile(os.path.join(labor, "scripts", "run_restore.py")):
        umgebung["TESTINSTANZ_ORDNER"] = labor
    ffmpeg = os.path.join(wurzel, "ffmpeg")
    if os.path.isdir(ffmpeg):
        umgebung["PATH"] = ffmpeg + os.pathsep + umgebung.get("PATH", "")
    umgebung.setdefault("PYTHONIOENCODING", "utf-8")


def keine_konsolenfenster():
    """Ohne das blitzt bei jedem ffmpeg-Aufruf kurz ein schwarzes Fenster auf."""
    if os.name != "nt":
        return
    ohne_fenster = 0x08000000  # CREATE_NO_WINDOW
    original = subprocess.Popen.__init__

    def init(self, *a, **kw):
        kw["creationflags"] = kw.get("creationflags", 0) | ohne_fenster
        original(self, *a, **kw)
    subprocess.Popen.__init__ = init


def _kinder_mitbeenden():
    """Windows-Job-Objekt: schliesst das Fenster, enden auch alle Hilfsprozesse (ffmpeg, Skripte).
    Ohne das wuerden sie unsichtbar weiterlaufen und beim naechsten Start dazwischenfunken."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE

        class Grenzen(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class Zaehler(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("a", "b", "c", "d", "e", "f")]

        class Erweitert(ctypes.Structure):
            _fields_ = [("Basic", Grenzen), ("Io", Zaehler), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        job = k32.CreateJobObjectW(None, None)
        info = Erweitert()
        info.Basic.LimitFlags = 0x2000 | 0x800   # KILL_ON_JOB_CLOSE | BREAKAWAY_OK
        k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        k32.AssignProcessToJobObject(job, k32.GetCurrentProcess())
        globals()["_JOB"] = job                  # Handle offen halten, bis das Programm endet
    except Exception:
        pass


def _ausgabe_sichern():
    """Im Fenster-Programm gibt es keine Konsole; die Skripte schreiben trotzdem ins Protokoll."""
    for name, fd in (("stdout", 1), ("stderr", 2)):
        if getattr(sys, name) is None:
            try:
                setattr(sys, name, open(fd, "w", encoding="utf-8", errors="replace", closefd=False))
            except OSError:
                setattr(sys, name, open(os.devnull, "w"))
        else:
            try:
                getattr(sys, name).reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass


def skript_ausfuehren(pfad, argumente):
    _ausgabe_sichern()
    sys.argv = [pfad] + list(argumente)
    sys.path.insert(0, os.path.dirname(os.path.abspath(pfad)))
    try:
        runpy.run_path(pfad, run_name="__main__")
    except SystemExit as e:
        code = e.code
        if isinstance(code, str):
            print(code, file=sys.stderr)
            return 1
        return code or 0
    finally:
        sys.stdout.flush()
    return 0


def _laeuft_schon():
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/status" % PORT, timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def _port_frei(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _protokoll():
    import logging
    ordner = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Kursuebersetzer")
    os.makedirs(ordner, exist_ok=True)
    logging.basicConfig(filename=os.path.join(ordner, "programm.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", encoding="utf-8")


def dienst_starten(port):
    import uvicorn
    from app.server import app
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None,
                                           access_log=False))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(300):
        if server.started:
            return server
        time.sleep(0.05)
    raise RuntimeError("Der Dienst ist nicht gestartet.")


def main():
    gefunden = skriptaufruf(sys.argv[1:])
    if gefunden:
        keine_konsolenfenster()      # auch ffmpeg/php aus den Skripten ohne schwarzes Fenster
        sys.exit(skript_ausfuehren(*gefunden))

    _ausgabe_sichern()
    _protokoll()
    umgebung_einrichten(basis(), os.environ)
    keine_konsolenfenster()
    _kinder_mitbeenden()

    import webview
    webview.settings["ALLOW_DOWNLOADS"] = True
    if _laeuft_schon():                 # zweiter Doppelklick: nur ein weiteres Fenster
        server, port = None, PORT
    else:
        port = PORT if _port_frei(PORT) else 0
        if port == 0:
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
        server = dienst_starten(port)

    webview.create_window(TITEL, "http://127.0.0.1:%d/" % port, width=1340, height=920,
                          min_size=(420, 600), confirm_close=True, background_color="#F6F3EC")
    webview.start(localization={
        "global.quitConfirmation": "Kursübersetzer beenden? Ein laufender Auftrag wird abgebrochen – "
                                   "Erledigtes bleibt erhalten und wird beim nächsten Mal weiterverwendet.",
        "global.ok": "Beenden", "global.cancel": "Weiterarbeiten", "global.quit": "Beenden",
    })
    if server:
        server.should_exit = True
        try:
            from app import moodleprobe
            moodleprobe.herunterfahren()
        except Exception:
            pass
    os._exit(0)       # das Job-Objekt beendet dabei alle noch laufenden Kindprozesse


if __name__ == "__main__":
    main()
