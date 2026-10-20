"""Vorlesen: offizieller Weg ueber Azure Speech (eigener Schluessel der Schule)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import vorlesen  # noqa: E402


class _Antwort:
    def __init__(self, status, inhalt=b""):
        self.status_code = status
        self.content = inhalt
        self.text = inhalt.decode("utf-8", "ignore")


class _Sitzung:
    def __init__(self, antwort):
        self.antwort = antwort
        self.anfragen = []

    def post(self, url, data=None, headers=None, timeout=None):
        self.anfragen.append({"url": url, "data": data, "headers": headers})
        return self.antwort


def test_azure_ruft_die_region_mit_ssml_und_schluessel_auf(tmp_path):
    s = _Sitzung(_Antwort(200, b"ID3mp3daten"))
    ziel = tmp_path / "t.mp3"
    vorlesen.azure_sprechen("Trage <immer> eine Brille & Handschuhe.", "it-IT-DiegoNeural", str(ziel),
                            schluessel="abc", region="germanywestcentral", tempo="-5%", sitzung=s)
    a = s.anfragen[0]
    assert a["url"] == "https://germanywestcentral.tts.speech.microsoft.com/cognitiveservices/v1"
    assert a["headers"]["Ocp-Apim-Subscription-Key"] == "abc"
    assert "mp3" in a["headers"]["X-Microsoft-OutputFormat"]
    ssml = a["data"].decode("utf-8")
    assert "xml:lang='it-IT'" in ssml and "name='it-IT-DiegoNeural'" in ssml
    assert "&lt;immer&gt;" in ssml and "&amp;" in ssml          # Sonderzeichen sicher verpackt
    assert "rate='-5%'" in ssml
    assert ziel.read_bytes() == b"ID3mp3daten"


def test_azure_falscher_schluessel_klare_meldung(tmp_path):
    s = _Sitzung(_Antwort(401))
    with pytest.raises(vorlesen.VorleseFehler, match="Schlüssel"):
        vorlesen.azure_sprechen("Hallo", "de-DE-KatjaNeural", str(tmp_path / "x.mp3"),
                                schluessel="falsch", region="westeurope", sitzung=s)
    assert not (tmp_path / "x.mp3").exists()


def test_ohne_azure_angaben_wird_edge_genommen(monkeypatch, tmp_path):
    genutzt = []
    def falsch(name):
        def stimme(text, st, ziel, *a, **k):
            genutzt.append(name)
            open(ziel, "wb").write(b"mp3")
        return stimme
    monkeypatch.setattr(vorlesen, "edge_sprechen", falsch("edge"))
    monkeypatch.setattr(vorlesen, "azure_sprechen", falsch("azure"))
    vorlesen.sprechen("Hallo", "fr-FR-HenriNeural", str(tmp_path / "a.mp3"), dienst={"art": "edge"})
    vorlesen.sprechen("Hallo", "fr-FR-HenriNeural", str(tmp_path / "b.mp3"),
                      dienst={"art": "azure", "schluessel": "k", "region": "westeurope"})
    assert genutzt == ["edge", "azure"]
