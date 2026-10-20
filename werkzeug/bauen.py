"""Baut die Windows-Anwendung Kursuebersetzer.exe und legt Verknuepfungen an.

Ergebnis:  %LOCALAPPDATA%\\Programs\\Kursuebersetzer\\Kursuebersetzer.exe
           Verknuepfung "Kursübersetzer" auf dem Desktop und im Startmenue

Eingebaut werden: die App, der Skill moodle-kurs-uebersetzen (scripts/), verkleinern.py,
ffmpeg/ffprobe und alle Python-Pakete. Das Spracherkennungsmodell laedt die Anwendung
beim ersten Gebrauch selbst nach (bzw. nutzt das schon vorhandene).

Braucht einmalig:  pip install -r requirements.txt pyinstaller pywebview pillow
Aufruf:            python werkzeug/bauen.py
"""
import os
import shutil
import subprocess
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HIER)
WERKZEUG = os.path.dirname(APP)                      # 01_Werkzeug
SKILL = next((p for p in (os.path.join(WERKZEUG, "moodle-kurs-uebersetzen"),
                          os.path.expanduser("~/.claude/skills/moodle-kurs-uebersetzen"))
              if os.path.isfile(os.path.join(p, "scripts", "analyse.py"))),
             os.path.join(WERKZEUG, "moodle-kurs-uebersetzen"))
# verkleinern.py: die Fassung aus dem Projekt geht vor, sonst die Kopie in diesem Repo
KLEIN = next(p for p in (os.path.join(WERKZEUG, "verkleinern", "verkleinern.py"),
                         os.path.join(HIER, "verkleinern", "verkleinern.py")) if os.path.isfile(p))
TESTINSTANZ = next((p for p in (os.path.join(WERKZEUG, "moodle-testinstanz"),
                                os.path.expanduser("~/.claude/skills/moodle-testinstanz"))
                    if os.path.isfile(os.path.join(p, "scripts", "run_restore.py"))), None)
ZIEL = os.path.join(os.environ["LOCALAPPDATA"], "Programs")
NAME = "Kursuebersetzer"
ANZEIGE = "Kursübersetzer"

# Was die Skill-Skripte importieren, die App selbst aber nicht – sonst fehlt es in der .exe
FUER_SKRIPTE = ["argparse", "tarfile", "hashlib", "html", "unicodedata", "xml.etree.ElementTree",
                "io", "glob", "tempfile", "time", "re", "json", "shutil", "subprocess"]
SAMMELN = ["faster_whisper", "ctranslate2", "onnxruntime", "tokenizers", "edge_tts", "webview",
           "uvicorn", "anthropic"]


def symbol(pfad):
    from PIL import Image, ImageDraw, ImageFont
    gross = 256
    bild = Image.new("RGBA", (gross, gross), (0, 0, 0, 0))
    d = ImageDraw.Draw(bild)
    d.rounded_rectangle((8, 8, gross - 8, gross - 8), radius=56, fill=(15, 92, 85, 255))
    try:
        schrift = ImageFont.truetype("seguisb.ttf", 128)
    except OSError:
        schrift = ImageFont.truetype("arialbd.ttf", 128)
    d.text((gross / 2, gross / 2 + 4), "Aa", font=schrift, fill=(255, 209, 102, 255), anchor="mm")
    bild.save(pfad, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])


def ffmpeg_dateien():
    gefunden = []
    for name in ("ffmpeg", "ffprobe"):
        p = shutil.which(name)
        if not p:
            sys.exit("%s nicht gefunden – bitte installieren: winget install Gyan.FFmpeg" % name)
        gefunden.append(p)
    return gefunden


def lizenzen(ordner):
    """Lizenztexte neben die .exe – Pflicht bei der Weitergabe (u. a. GPL v3 von FFmpeg)."""
    ziel = os.path.join(ordner, "Lizenzen")
    os.makedirs(ziel, exist_ok=True)
    shutil.copy(os.path.join(APP, "LICENSE"), os.path.join(ziel, "Kursuebersetzer-LICENSE.txt"))
    shutil.copy(os.path.join(APP, "DRITTANBIETER.md"), os.path.join(ziel, "DRITTANBIETER.md"))
    for name, quelle in (("moodle-kurs-uebersetzen", SKILL), ("moodle-testinstanz", TESTINSTANZ)):
        if os.path.isfile(os.path.join(quelle, "LICENSE")):
            shutil.copy(os.path.join(quelle, "LICENSE"), os.path.join(ziel, name + "-LICENSE.txt"))
    ffmpeg_basis = os.path.dirname(os.path.dirname(shutil.which("ffmpeg")))
    for datei, neu in (("LICENSE", "ffmpeg-LICENSE-GPLv3.txt"), ("README.txt", "ffmpeg-README.txt")):
        if os.path.isfile(os.path.join(ffmpeg_basis, datei)):
            shutil.copy(os.path.join(ffmpeg_basis, datei), os.path.join(ziel, neu))
    import glob
    import edge_tts
    for p in glob.glob(os.path.join(os.path.dirname(edge_tts.__file__), "..", "edge_tts-*.dist-info", "licenses", "*")):
        shutil.copy(p, os.path.join(ziel, "edge-tts-" + os.path.basename(p) + ".txt"))
    shutil.copy(os.path.join(APP, "ANLEITUNG.md"), os.path.join(ordner, "ANLEITUNG.md"))


def verknuepfung(lnk, exe, ordner):
    befehl = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');$s.TargetPath='%s';"
              "$s.WorkingDirectory='%s';$s.IconLocation='%s,0';$s.Description='Moodle-Kurse übersetzen';$s.Save()"
              % (lnk, exe, ordner, exe))
    subprocess.run(["powershell", "-NoProfile", "-Command", befehl], check=True)


def main():
    if not os.path.isfile(os.path.join(SKILL, "scripts", "analyse.py")):
        sys.exit("Skill nicht gefunden: %s" % SKILL)
    if not TESTINSTANZ:
        sys.exit("Skill moodle-testinstanz nicht gefunden (fuer die Moodle-Pruefung).")
    bau = os.path.join(os.environ.get("TEMP", HIER), "kursuebersetzer_bau")
    ico = os.path.join(bau, "symbol.ico")
    os.makedirs(bau, exist_ok=True)
    symbol(ico)

    sep = os.pathsep
    befehl = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
              "--name", NAME, "--icon", ico, "--distpath", ZIEL, "--workpath", os.path.join(bau, "work"),
              "--specpath", bau, "--paths", APP,
              "--add-data", os.path.join(APP, "app", "static") + sep + "app/static",
              "--add-data", os.path.join(APP, "app", "sprachen_daten.json") + sep + "app",
              "--add-data", os.path.join(SKILL, "scripts") + sep + "werkzeug/moodle-kurs-uebersetzen/scripts",
              "--add-data", KLEIN + sep + "werkzeug/verkleinern",
              "--add-data", os.path.join(TESTINSTANZ, "scripts") + sep + "werkzeug/moodle-testinstanz/scripts",
              "--collect-submodules", "app", "--copy-metadata", "anthropic"]
    for p in ffmpeg_dateien():
        befehl += ["--add-binary", p + sep + "ffmpeg"]
    for m in FUER_SKRIPTE:
        befehl += ["--hidden-import", m]
    for m in SAMMELN:
        befehl += ["--collect-all", m]
    befehl.append(os.path.join(APP, "app", "start.py"))
    subprocess.run(befehl, check=True, cwd=APP)

    exe = os.path.join(ZIEL, NAME, NAME + ".exe")
    ordner = os.path.dirname(exe)
    lizenzen(ordner)
    desktop = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                             capture_output=True, text=True).stdout.strip()
    programme = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Programs')"],
                               capture_output=True, text=True).stdout.strip()
    for wo in (desktop, programme):
        if wo:
            verknuepfung(os.path.join(wo, ANZEIGE + ".lnk"), exe, ordner)
    groesse = sum(os.path.getsize(os.path.join(w, f)) for w, _, fs in os.walk(ordner) for f in fs)
    print("\nFertig: %s (%.0f MB)\nVerknüpfungen: Desktop und Startmenü" % (exe, groesse / 1e6))


if __name__ == "__main__":
    main()
