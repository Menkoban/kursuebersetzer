"""Probe-Einspielung in ein echtes Moodle: Lässt sich die fertige Sicherung hochladen?

Nutzt den Skill moodle-testinstanz (portables Moodle 4.5 mit mod_hvp und format_tiles,
ohne Docker). Eingerichtet wird es einmalig per Knopf; die Bausteine kommen aus den
offiziellen Quellen (windows.php.net, archive.mariadb.org, packaging.moodle.org).

Vertrag von run_restore.py: Exit 0 = eingespielt, 2 = Moodle lehnt den Kurs ab,
3 = Labor nicht erreichbar (dann ist das kein Fehler des Kurses).
"""
import json
import os
import subprocess
import threading

from . import ablauf


def skriptordner():
    for p in (os.environ.get("TESTINSTANZ_ORDNER"),
              os.path.join(ablauf.APP, "..", "moodle-testinstanz"),
              os.path.expanduser("~/.claude/skills/moodle-testinstanz")):
        if p and os.path.isfile(os.path.join(p, "scripts", "run_restore.py")):
            return os.path.abspath(os.path.join(p, "scripts"))
    return None


def laborordner(umgebung=None, vorhanden=None, neu=None):
    """Ein schon eingerichtetes Labor weiterverwenden, sonst eines im Datenordner der App."""
    umgebung = os.environ if umgebung is None else umgebung
    if umgebung.get("MOODLE_LAB_HOME"):
        return umgebung["MOODLE_LAB_HOME"]
    vorhanden = vorhanden or os.path.expanduser("~/.claude/moodle-lab")
    if os.path.isdir(os.path.join(vorhanden, "moodle")):
        return vorhanden
    return neu or os.path.join(ablauf.DATEN, "moodle-lab")


def _umgebung():
    return dict(os.environ, MOODLE_LAB_HOME=laborordner(), PYTHONIOENCODING="utf-8")


def _skript(name):
    ordner = skriptordner()
    return ablauf.python_befehl(os.path.join(ordner, name)) if ordner else None


def bereit():
    befehl = _skript("run_restore.py")
    if not befehl:
        return False
    try:
        return subprocess.run(befehl + ["--health"], capture_output=True, env=_umgebung(),
                              timeout=120).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def auswerten(rc, ausgabe):
    """-> (zustand, kurzinfo, protokoll) fuer den Schritt in der Oberflaeche."""
    try:
        d = json.loads(ausgabe.strip().splitlines()[-1]) if ausgabe.strip() else {}
    except (ValueError, IndexError):
        d = {}
    tail = d.get("log_tail") or ausgabe[-3000:]
    if rc == 3 or d.get("status") == "lab_lost":
        return "uebersprungen", "Moodle-Labor nicht erreichbar", tail
    if rc == 0 and d.get("status", "ok") == "ok":
        version = (d.get("moodle_version") or "").split(" ")[0]
        if d.get("mod_hvp") is False:
            return "warnung", "eingespielt, aber ohne H5P-Plugin – Rundgang ungeprüft", tail
        return "fertig", "Moodle %s spielt den Kurs ein" % version, tail
    if rc == 2 or d.get("status") == "restore_failed":
        return "fehler", "Moodle lehnt die Sicherung ab – siehe Protokoll", tail
    return "uebersprungen", "Probe nicht möglich (Problem im Moodle-Labor, nicht im Kurs)", tail


def pruefen(mbz):
    befehl = _skript("run_restore.py")
    if not befehl:
        return "uebersprungen", "Moodle-Probe nicht eingebaut", ""
    try:
        r = subprocess.run(befehl + [mbz, "--json"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=_umgebung(), timeout=3600)
    except subprocess.TimeoutExpired:
        return "fehler", "Probe-Einspielung dauerte über eine Stunde", ""
    return auswerten(r.returncode, r.stdout + ("\n" + r.stderr if r.returncode not in (0, 2) else ""))


def _kaputte_downloads_entfernen(ordner):
    """Ein abgebrochener Download bliebe sonst als „Cache“ liegen und liesse jeden neuen Versuch scheitern."""
    import zipfile
    if not os.path.isdir(ordner):
        return
    for f in os.listdir(ordner):
        p = os.path.join(ordner, f)
        if f.lower().endswith(".zip") and not zipfile.is_zipfile(p):
            os.remove(p)


def herunterfahren():
    """Datenbank des Labors beim Programmende sauber stoppen (sonst bleibt Port 3307 belegt)."""
    befehl = _skript("run_restore.py")
    if befehl:
        try:
            subprocess.run(befehl + ["--shutdown"], capture_output=True, env=_umgebung(), timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            pass


class Einrichtung:
    """Einmaliges Einrichten im Hintergrund, mit mitlesbarem Protokoll."""

    def __init__(self):
        self.laeuft = False
        self.log = []
        self.ergebnis = ""

    def starten(self):
        if self.laeuft:
            return
        befehl = _skript("setup_lab.py")
        if not befehl:
            self.ergebnis = "Moodle-Probe ist in dieser Fassung nicht eingebaut."
            return
        self.laeuft, self.log, self.ergebnis = True, [], ""
        _kaputte_downloads_entfernen(os.path.join(laborordner(), "_dl"))
        befehl = befehl + ["--force"]

        def lauf():
            try:
                p = subprocess.Popen(befehl, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", env=_umgebung())
                for zeile in p.stdout:
                    self.log.append(zeile.rstrip())
                    del self.log[:-400]
                p.wait()
                self.ergebnis = "fertig" if p.returncode == 0 and bereit() else \
                    "Einrichten ist fehlgeschlagen (siehe Protokoll)."
            except OSError as e:
                self.ergebnis = "Einrichten ist fehlgeschlagen: %s" % e
            finally:
                self.laeuft = False
        threading.Thread(target=lauf, daemon=True).start()
