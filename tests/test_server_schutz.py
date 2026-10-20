"""Fremde Webseiten duerfen keine Auftraege ausloesen (Schluessel und Guthaben der Schule)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app import server  # noqa: E402


def test_post_ohne_eigenes_fenster_wird_abgelehnt():
    fremd = TestClient(server.app)
    assert fremd.post("/api/einstellungen", json={"datenschutz_gelesen": True}).status_code == 403


def test_post_von_fremder_herkunft_wird_abgelehnt():
    c = TestClient(server.app)
    c.get("/")
    r = c.post("/api/einstellungen", json={}, headers={"Origin": "https://boese.example"})
    assert r.status_code == 403


def test_eigenes_fenster_darf_speichern():
    c = TestClient(server.app)
    c.get("/")
    assert c.post("/api/einstellungen", json={}).status_code == 200


def test_fehlende_haken_bedeuten_ja():
    # Fehlt das Feld (z. B. bei aelteren Fenstern), gilt der Standard „ja“ – nicht „nein“
    assert server.ja(None) is True
    assert server.ja("true") is True and server.ja("on") is True
    assert server.ja("false") is False and server.ja("") is False
