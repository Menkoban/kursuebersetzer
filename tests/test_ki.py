"""Tests der Anbieter-Anbindung (Claude direkt, OpenRouter, eigener OpenAI-kompatibler Dienst)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import ki, uebersetzer  # noqa: E402

SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


class _Antwort:
    def __init__(self, status, daten):
        self.status_code = status
        self._daten = daten
        self.text = json.dumps(daten)

    def json(self):
        return self._daten


class _Sitzung:
    """Merkt sich jede Anfrage und spielt vorbereitete Antworten der Reihe nach ab."""

    def __init__(self, *antworten):
        self.antworten = list(antworten)
        self.anfragen = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.anfragen.append({"url": url, "json": json, "headers": headers})
        return self.antworten.pop(0)


def _chat(inhalt, grund="stop"):
    return _Antwort(200, {"choices": [{"message": {"content": inhalt}, "finish_reason": grund}]})


def test_openrouter_schickt_modell_schluessel_und_schema_und_liest_json():
    s = _Sitzung(_chat('```json\n{"a": "bonjour"}\n```'))
    k = ki.erstelle({"anbieter": "openrouter", "modell": "mistralai/mistral-small", "schluessel": "sk-or-1"},
                    sitzung=s)
    assert k.frage_json("sys", "nutzer", SCHEMA) == {"a": "bonjour"}
    anfrage = s.anfragen[0]
    assert anfrage["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert anfrage["headers"]["Authorization"] == "Bearer sk-or-1"
    assert anfrage["json"]["model"] == "mistralai/mistral-small"
    assert anfrage["json"]["response_format"]["type"] == "json_schema"
    assert anfrage["json"]["messages"][0] == {"role": "system", "content": "sys"}


def test_modell_ohne_schema_unterstuetzung_bekommt_zweiten_versuch_ohne_schema():
    s = _Sitzung(_Antwort(400, {"error": {"message": "response_format json_schema not supported"}}),
                 _chat('Hier: {"a": "hola"} fertig'))
    k = ki.erstelle({"anbieter": "openrouter", "modell": "x/y", "schluessel": "k"}, sitzung=s)
    assert k.frage_json("sys", "nutzer", SCHEMA) == {"a": "hola"}
    assert "json_schema" not in json.dumps(s.anfragen[1]["json"].get("response_format", {}))
    assert '"required"' in s.anfragen[1]["json"]["messages"][0]["content"]   # Schema steht dann im Auftrag


def test_falscher_schluessel_bricht_mit_verstaendlicher_meldung_ab():
    s = _Sitzung(_Antwort(401, {"error": {"message": "No auth credentials found"}}))
    k = ki.erstelle({"anbieter": "openrouter", "modell": "x/y", "schluessel": "falsch"}, sitzung=s)
    with pytest.raises(ki.KiFehler, match="OpenRouter"):
        k.frage_json("sys", "nutzer", SCHEMA)


def test_abgeschnittene_antwort_fuehrt_zum_kleinerteilen():
    s = _Sitzung(_chat('{"a": "nur die erste Hälfte"}', grund="length"))  # gültig, aber gekappt
    k = ki.erstelle({"anbieter": "openrouter", "modell": "x/y", "schluessel": "k"}, sitzung=s)
    with pytest.raises(ki.Antwortfehler):
        k.frage_json("sys", "nutzer", SCHEMA)


def test_eigener_dienst_nutzt_eigene_adresse_und_kommt_ohne_schluessel_aus():
    s = _Sitzung(_chat('{"a": "ok"}'))
    k = ki.erstelle({"anbieter": "openai", "modell": "llama3.1", "url": "http://localhost:11434/v1/"},
                    sitzung=s)
    assert k.frage_json("sys", "nutzer", SCHEMA) == {"a": "ok"}
    assert s.anfragen[0]["url"] == "http://localhost:11434/v1/chat/completions"
    assert "Authorization" not in s.anfragen[0]["headers"]


def test_ohne_modell_gilt_das_standardmodell_des_anbieters():
    assert ki.erstelle({"anbieter": "anthropic", "schluessel": "k"}).modell == "claude-haiku-5-5"
    with pytest.raises(ValueError):
        ki.erstelle({"anbieter": "gibtsnicht"})


class _FalscheKi:
    def __init__(self):
        self.auftraege = []

    def frage_json(self, system, nutzer, schema):
        eintraege = json.loads(nutzer.split("\n\n", 1)[1])
        self.auftraege.append(eintraege)
        return {"uebersetzungen": [{"nr": e["nr"], "text": "ES:" + e["text"]} for e in eintraege]}


def test_uebersetzen_laeuft_mit_jedem_anbieter():
    k = _FalscheKi()
    erg = uebersetzer.uebersetze_texte({"Hallo": "", "Tschüss": "Adiós"}, "Spanisch", ki=k)
    assert erg == {"Hallo": "ES:Hallo", "Tschüss": "Adiós"}
    assert k.auftraege == [[{"nr": 0, "text": "Hallo"}]]
