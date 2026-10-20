"""HeyGen-API v3 (offizielle Doku, Stand 20.10.2026): Hochladen, Uebersetzen, Status."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import heygen  # noqa: E402


class _A:
    def __init__(self, status, daten=None):
        self.status_code = status
        self._d = daten or {}
        self.text = str(self._d)
        self.headers = {}

    def json(self):
        return self._d


class _Sitzung:
    def __init__(self, *antworten):
        self.antworten = list(antworten)
        self.anfragen = []

    def _weiter(self, art, url, **kw):
        self.anfragen.append(dict(art=art, url=url, **kw))
        return self.antworten.pop(0)

    def get(self, url, **kw):
        return self._weiter("GET", url, **kw)

    def post(self, url, **kw):
        if "files" in kw:                      # Datei sofort lesen, solange sie offen ist
            kw["files"] = {k: (v[0], v[1].read()) for k, v in kw["files"].items()}
        return self._weiter("POST", url, **kw)

    def put(self, url, **kw):
        if hasattr(kw.get("data"), "read"):
            kw["data"] = kw["data"].read()
        return self._weiter("PUT", url, **kw)


def test_kleines_video_geht_direkt_an_v3_assets(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 1000)
    s = _Sitzung(_A(200, {"data": {"asset_id": "asset_1", "url": "https://files/x.mp4"}}))
    hg = heygen.HeyGen("k", sitzung=s)
    assert hg.hochladen(str(video)) == "asset_1"
    assert s.anfragen[0]["url"] == "https://api.heygen.com/v3/assets"
    assert s.anfragen[0]["headers"]["X-Api-Key"] == "k"


def test_grosses_video_ueber_direct_upload_in_drei_schritten(tmp_path, monkeypatch):
    monkeypatch.setattr(heygen, "KLEIN_BIS", 100)
    video = tmp_path / "gross.mp4"
    video.write_bytes(b"y" * 500)
    s = _Sitzung(_A(200, {"data": {"asset_id": "asset_9", "upload_url": "https://s3/put",
                                   "upload_headers": {"Content-Type": "video/mp4"}}}),
                 _A(200),
                 _A(200, {"data": {"asset_id": "asset_9", "status": "processing"}}))
    hg = heygen.HeyGen("k", sitzung=s)
    assert hg.hochladen(str(video)) == "asset_9"
    init, put, fertig = s.anfragen
    assert init["url"].endswith("/v3/assets/direct-uploads") and init["json"]["size_bytes"] == 500
    assert put["art"] == "PUT" and put["url"] == "https://s3/put" and put["data"] == b"y" * 500
    assert fertig["url"].endswith("/v3/assets/asset_9/complete")


def test_uebersetzungsauftrag_mit_asset_und_sprache():
    s = _Sitzung(_A(200, {"data": {"video_translation_ids": ["tr_1-fr"]}}))
    hg = heygen.HeyGen("k", sitzung=s)
    assert hg.uebersetzen("asset_1", "French", "Fritteuse_FR") == "tr_1-fr"
    body = s.anfragen[0]["json"]
    assert s.anfragen[0]["url"] == "https://api.heygen.com/v3/video-translations"
    assert body["video"] == {"type": "asset_id", "asset_id": "asset_1"}
    assert body["output_languages"] == ["French"] and body["mode"] == "speed"


def test_status_fertig_mit_adresse_und_fehler_mit_meldung():
    s = _Sitzung(_A(200, {"data": {"status": "completed", "video_url": "https://cdn/v.mp4"}}),
                 _A(200, {"data": {"status": "failed", "failure_message": "no speech found"}}),
                 _A(200, {"data": {"status": "running"}}))
    hg = heygen.HeyGen("k", sitzung=s)
    assert hg.stand("tr_1") == ("fertig", "https://cdn/v.mp4")
    assert hg.stand("tr_2") == ("fehler", "no speech found")
    assert hg.stand("tr_3") == ("wartet", None)
    assert s.anfragen[0]["url"] == "https://api.heygen.com/v3/video-translations/tr_1"


def test_falscher_schluessel_verstaendlich():
    s = _Sitzung(_A(401, {"error": {"code": "unauthorized", "message": "Invalid API key"}}))
    with pytest.raises(heygen.HeyGenFehler, match="Schlüssel"):
        heygen.HeyGen("falsch", sitzung=s).guthaben()


def _sprachliste(*namen):
    return _Sitzung(_A(200, {"data": {"languages": list(namen)}}))


def test_sprache_mit_klammer_wird_nie_geraten():
    hg = heygen.HeyGen("k", sitzung=_sprachliste("Kurdish (Kurmanji)", "Kurdish (Sorani)", "French"))
    assert hg.sprache_finden("Kurdish (Sorani)") == "Kurdish (Sorani)"
    hg = heygen.HeyGen("k", sitzung=_sprachliste("Kurdish (Kurmanji)", "French"))
    with pytest.raises(heygen.HeyGenFehler):
        hg.sprache_finden("Kurdish (Sorani)")


def test_sprache_ohne_klammer_nur_bei_eindeutigem_treffer():
    hg = heygen.HeyGen("k", sitzung=_sprachliste("French (France)", "German"))
    assert hg.sprache_finden("French") == "French (France)"
    hg = heygen.HeyGen("k", sitzung=_sprachliste("French (France)", "French (Canada)"))
    with pytest.raises(heygen.HeyGenFehler, match="mehrdeutig"):
        hg.sprache_finden("French")


# ------------------------------------------------------------ Bestellbuch gegen Doppelzahlung

def test_bestellbuch_merkt_bestellung_vor_dem_auftrag_und_ueberlebt_neuen_export(tmp_path):
    buch = heygen.Bestellbuch(str(tmp_path / "buch.json"))
    assert buch.eintrag("sha1abc", "fr") is None
    buch.vor_bestellung("sha1abc", "fr", asset="asset_1", titel="Fritteuse_FR")
    # Absturz zwischen Bestellung und Antwort: ein neues Buch (anderer Arbeitsordner) sieht den Eintrag
    zweites = heygen.Bestellbuch(str(tmp_path / "buch.json"))
    assert zweites.eintrag("sha1abc", "fr")["zustand"] == "bestellt"
    zweites.auftrag_gemerkt("sha1abc", "fr", "tr_9")
    assert heygen.Bestellbuch(str(tmp_path / "buch.json")).eintrag("sha1abc", "fr")["auftrag"] == "tr_9"


def test_bestellbuch_verworfen_wird_nicht_still_neu_bestellt(tmp_path):
    buch = heygen.Bestellbuch(str(tmp_path / "buch.json"))
    buch.vor_bestellung("h", "fr", asset="a", titel="t")
    buch.auftrag_gemerkt("h", "fr", "tr_1")
    buch.verworfen("h", "fr", "Länge auffällig")
    assert buch.darf_bestellen("h", "fr") is False
    buch.gescheitert("h", "fr", "HeyGen: failed")     # von HeyGen abgelehnt -> neu bestellen erlaubt
    assert buch.darf_bestellen("h", "fr") is True


def test_verlorene_auftragsnummer_wird_ueber_den_titel_wiedergefunden():
    s = _Sitzung(_A(200, {"data": [{"id": "tr_7", "title": "Andere"}, {"id": "tr_8", "title": "Fritteuse_FR"}],
                          "next_token": None}))
    assert heygen.HeyGen("k", sitzung=s).finde_auftrag("Fritteuse_FR") == "tr_8"
    s = _Sitzung(_A(200, {"data": [], "next_token": None}))
    assert heygen.HeyGen("k", sitzung=s).finde_auftrag("Fritteuse_FR") is None
