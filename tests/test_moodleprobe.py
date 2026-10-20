"""Moodle-Probe: Antwort des Testlabors richtig deuten, Laborordner richtig finden."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import moodleprobe  # noqa: E402


def test_gelungene_einspielung():
    aus = json.dumps({"status": "ok", "restored_course_id": 42, "moodle_version": "4.5.12+",
                      "mod_hvp": True, "log_tail": ""})
    zustand, info, protokoll = moodleprobe.auswerten(0, aus)
    assert zustand == "fertig"
    assert "4.5.12" in info


def test_moodle_lehnt_den_kurs_ab():
    aus = json.dumps({"status": "restore_failed", "log_tail": "dmlwriteexception: Duplicate entry"})
    zustand, info, protokoll = moodleprobe.auswerten(2, aus)
    assert zustand == "fehler"
    assert "dmlwriteexception" in protokoll


def test_labor_nicht_erreichbar_ist_kein_kursfehler():
    zustand, info, _ = moodleprobe.auswerten(3, "")
    assert zustand == "uebersprungen"


def test_ohne_h5p_plugin_wird_gewarnt():
    aus = json.dumps({"status": "ok", "restored_course_id": 7, "moodle_version": "4.5", "mod_hvp": False})
    zustand, info, _ = moodleprobe.auswerten(0, aus)
    assert zustand == "warnung"     # Moodle ueberspringt H5P dann stillschweigend


def test_laborordner_vorhandenes_labor_geht_vor(tmp_path):
    vorhanden = tmp_path / "claude" / "moodle-lab"
    (vorhanden / "moodle").mkdir(parents=True)
    assert moodleprobe.laborordner({}, vorhanden=str(vorhanden), neu=str(tmp_path / "neu")) == str(vorhanden)
    assert moodleprobe.laborordner({}, vorhanden=str(tmp_path / "fehlt"), neu=str(tmp_path / "neu")) == \
        str(tmp_path / "neu")
    assert moodleprobe.laborordner({"MOODLE_LAB_HOME": "X"}, vorhanden=str(vorhanden), neu="Y") == "X"


def test_umgebungsproblem_ist_kein_kursfehler():
    zustand, info, _ = moodleprobe.auswerten(1, "Traceback ... TimeoutExpired")
    assert zustand == "uebersprungen"
    assert "nicht möglich" in info
