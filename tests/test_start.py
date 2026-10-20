"""Startprogramm der Windows-Anwendung: Skriptaufrufe erkennen, Werkzeuge finden, Stimme erzeugen."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import ablauf, start  # noqa: E402


def test_skriptaufruf_wird_erkannt_wie_bei_python():
    # So ruft ablauf.py die Skill-Skripte auf, und so ruft verkleinern.py kurs_bauen.py auf
    assert start.skriptaufruf(["-I", "-X", "utf8", r"C:\w\analyse.py", "kurs.mbz", "arbeit"]) == \
        (r"C:\w\analyse.py", ["kurs.mbz", "arbeit"])
    assert start.skriptaufruf([r"C:\w\pruefen.py", "a.mbz"]) == (r"C:\w\pruefen.py", ["a.mbz"])


def test_normaler_start_ist_kein_skriptaufruf():
    assert start.skriptaufruf([]) is None
    assert start.skriptaufruf(["--irgendwas"]) is None


def test_mitgelieferte_werkzeuge_haben_vorrang(tmp_path):
    (tmp_path / "werkzeug" / "moodle-kurs-uebersetzen" / "scripts").mkdir(parents=True)
    (tmp_path / "werkzeug" / "moodle-kurs-uebersetzen" / "scripts" / "analyse.py").write_text("")
    (tmp_path / "werkzeug" / "verkleinern").mkdir()
    (tmp_path / "werkzeug" / "verkleinern" / "verkleinern.py").write_text("")
    (tmp_path / "werkzeug" / "moodle-testinstanz" / "scripts").mkdir(parents=True)
    (tmp_path / "werkzeug" / "moodle-testinstanz" / "scripts" / "run_restore.py").write_text("")
    (tmp_path / "ffmpeg").mkdir()
    umgebung = {"PATH": r"C:\Windows"}
    start.umgebung_einrichten(str(tmp_path), umgebung)
    assert umgebung["SKILL_ORDNER"] == str(tmp_path / "werkzeug" / "moodle-kurs-uebersetzen")
    assert umgebung["VERKLEINERN"] == str(tmp_path / "werkzeug" / "verkleinern" / "verkleinern.py")
    assert umgebung["PATH"].split(os.pathsep)[0] == str(tmp_path / "ffmpeg")
    assert umgebung["TESTINSTANZ_ORDNER"] == str(tmp_path / "werkzeug" / "moodle-testinstanz")


def test_python_befehl_im_paket_ist_die_anwendung_selbst(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Programme\Kursuebersetzer.exe")
    assert ablauf.python_befehl("x.py") == [r"C:\Programme\Kursuebersetzer.exe", "-I", "-X", "utf8", "x.py"]


def test_vertonen_braucht_kein_edge_tts_programm(monkeypatch, tmp_path):
    aufgerufen = {}

    class FalscheStimme:
        def __init__(self, text, voice, rate="+0%"):
            aufgerufen.update(text=text, voice=voice, rate=rate)

        async def save(self, pfad):
            open(pfad, "wb").write(b"mp3")

    import edge_tts
    monkeypatch.setattr(edge_tts, "Communicate", FalscheStimme)
    ziel = tmp_path / "t.mp3"
    ablauf.sprechen("Hallo", "zh-CN-YunxiNeural", str(ziel), tempo="-5%")
    assert ziel.read_bytes() == b"mp3"
    assert aufgerufen == {"text": "Hallo", "voice": "zh-CN-YunxiNeural", "rate": "-5%"}
