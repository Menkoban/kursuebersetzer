"""Anbieter fuer die Uebersetzung: Claude direkt, OpenRouter oder ein eigener Dienst.

Alle liefern dasselbe: frage_json(system, nutzer, schema) -> dict. Der Rest der App
weiss nicht, welches Modell dahinter steckt.

- anthropic   Claude ueber die Anthropic-API (offizielles SDK, strukturierte Ausgabe)
- openrouter  hunderte Modelle ueber einen Schluessel (OpenAI-kompatible Schnittstelle)
- openai      jeder OpenAI-kompatible Dienst mit eigener Adresse: OpenAI selbst,
              Ollama oder LM Studio auf dem eigenen Rechner, Schul-Server …
"""
import json
import re
import time

ANBIETER = {
    "anthropic": {"name": "Claude (Anthropic)", "modell": "claude-haiku-5-5", "url": "",
                  "schluessel_noetig": True, "umgebung": "ANTHROPIC_API_KEY"},
    "openrouter": {"name": "OpenRouter", "modell": "anthropic/claude-haiku-5.5",
                   "url": "https://openrouter.ai/api/v1", "schluessel_noetig": True,
                   "umgebung": "OPENROUTER_API_KEY"},
    "openai": {"name": "Eigener Dienst (OpenAI-kompatibel)", "modell": "", "url": "",
               "schluessel_noetig": False, "umgebung": "OPENAI_API_KEY"},
}


class KiFehler(Exception):
    """Dauerhafter Fehler (Schluessel, Guthaben, Verbindung): Kleinerteilen hilft nicht."""


class Antwortfehler(RuntimeError):
    """Antwort unbrauchbar (abgeschnitten, kein JSON): mit kleinerem Paket erneut versuchen."""


def erstelle(konfig, sitzung=None, client=None):
    anbieter = konfig.get("anbieter") or "anthropic"
    if anbieter not in ANBIETER:
        raise ValueError("Unbekannter Anbieter: %s" % anbieter)
    modell = (konfig.get("modell") or "").strip() or ANBIETER[anbieter]["modell"]
    if not modell:
        raise KiFehler("Für „%s“ ist kein Modell eingetragen (Zahnrad oben rechts)." % ANBIETER[anbieter]["name"])
    if anbieter == "anthropic":
        return AnthropicKi(konfig.get("schluessel"), modell, client=client)
    url = (konfig.get("url") or "").strip() or ANBIETER[anbieter]["url"]
    if not url:
        raise KiFehler("Für den eigenen Dienst fehlt die Adresse, z. B. http://localhost:11434/v1")
    return OpenAIKompatibel(url, konfig.get("schluessel"), modell, ANBIETER[anbieter]["name"], sitzung=sitzung)


def json_aus_text(text):
    """Holt das JSON-Objekt aus einer Antwort, auch wenn Codezaun oder Vorrede drumherum stehen."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        return json.loads(t)
    except ValueError:
        anfang, ende = t.find("{"), t.rfind("}")
        if anfang >= 0 and ende > anfang:
            try:
                return json.loads(t[anfang:ende + 1])
            except ValueError:
                pass
    raise Antwortfehler("Antwort ist kein gültiges JSON.")


# ------------------------------------------------------------ Claude direkt

class AnthropicKi:
    def __init__(self, schluessel, modell, client=None):
        self.modell = modell
        self._schluessel = schluessel
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._schluessel) if self._schluessel else anthropic.Anthropic()
        return self._client

    def frage_json(self, system, nutzer, schema):
        import anthropic
        try:
            antwort = self.client.messages.create(
                model=self.modell, max_tokens=16000, system=system,
                messages=[{"role": "user", "content": nutzer}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.AuthenticationError:
            raise KiFehler("Der Claude-API-Schlüssel wird nicht angenommen. Bitte im Zahnrad oben rechts prüfen.")
        except anthropic.PermissionDeniedError:
            raise KiFehler("Der Claude-API-Schlüssel darf das Modell %s nicht nutzen." % self.modell)
        except anthropic.NotFoundError:
            raise KiFehler("Claude kennt das Modell „%s“ nicht." % self.modell)
        except anthropic.RateLimitError:
            raise KiFehler("Claude meldet: Guthaben oder Tageslimit erschöpft. Später erneut starten – "
                           "schon Übersetztes bleibt erhalten.")
        except anthropic.APIConnectionError:
            raise KiFehler("Keine Verbindung zu Claude – ist das Internet da?")
        if antwort.stop_reason == "refusal":
            raise Antwortfehler("Das Modell hat die Übersetzung abgelehnt.")
        if antwort.stop_reason == "max_tokens":
            raise Antwortfehler("Antwort zu lang.")
        return json_aus_text(next(b.text for b in antwort.content if b.type == "text"))

    def modelle(self):
        return [{"id": m.id, "name": m.display_name} for m in self.client.models.list()]


# ------------------------------------------------------------ OpenRouter und Verwandte

class OpenAIKompatibel:
    def __init__(self, url, schluessel, modell, name, sitzung=None):
        self.url = url.rstrip("/")
        self.modell = modell
        self.name = name
        self._schluessel = schluessel
        if sitzung is None:
            import requests
            sitzung = requests
        self.sitzung = sitzung

    def _kopf(self):
        kopf = {"Content-Type": "application/json"}
        if self._schluessel:
            kopf["Authorization"] = "Bearer %s" % self._schluessel
        if "openrouter.ai" in self.url:
            kopf.update({"HTTP-Referer": "http://localhost:8765", "X-Title": "Kursuebersetzer"})
        return kopf

    def _senden(self, nachrichten, format_):
        daten = {"model": self.modell, "messages": nachrichten, "temperature": 0.2, "max_tokens": 16000}
        if format_:
            daten["response_format"] = format_
        for versuch in range(4):
            try:
                r = self.sitzung.post(self.url + "/chat/completions", json=daten, headers=self._kopf(), timeout=600)
            except Exception as e:  # Verbindungsfehler jeder Bibliothek
                raise KiFehler("Keine Verbindung zu %s (%s)." % (self.name, e.__class__.__name__))
            if r.status_code in (429, 502, 503) and versuch < 3:
                time.sleep(5 * (versuch + 1))
                continue
            return r
        return r

    def frage_json(self, system, nutzer, schema):
        mit_schema = {"type": "json_schema", "json_schema": {"name": "antwort", "strict": True, "schema": schema}}
        r = self._senden([{"role": "system", "content": system}, {"role": "user", "content": nutzer}], mit_schema)
        if r.status_code == 400:
            # Nicht jedes Modell kann eine feste Antwortform: dann steht die Form im Auftrag
            system2 = (system + "\n\nAntworte ausschließlich mit einem JSON-Objekt nach diesem Schema, "
                       "ohne Vorrede und ohne Codezaun:\n" + json.dumps(schema, ensure_ascii=False))
            r = self._senden([{"role": "system", "content": system2}, {"role": "user", "content": nutzer}], None)
        self._pruefe(r)
        wahl = (r.json().get("choices") or [{}])[0]
        if wahl.get("finish_reason") == "length":
            raise Antwortfehler("Antwort abgeschnitten.")
        return json_aus_text((wahl.get("message") or {}).get("content"))

    def _pruefe(self, r):
        if r.status_code < 400:
            return
        try:
            meldung = (r.json().get("error") or {}).get("message") or r.text[:200]
        except ValueError:
            meldung = r.text[:200]
        if r.status_code == 401:
            raise KiFehler("%s nimmt den API-Schlüssel nicht an. Bitte im Zahnrad oben rechts prüfen." % self.name)
        if r.status_code == 402:
            raise KiFehler("%s meldet: Guthaben aufgebraucht. Bitte aufladen und erneut starten – "
                           "schon Übersetztes bleibt erhalten." % self.name)
        if r.status_code == 403:
            raise KiFehler("%s verweigert das Modell %s: %s" % (self.name, self.modell, meldung))
        if r.status_code == 404:
            raise KiFehler("%s kennt das Modell „%s“ nicht." % (self.name, self.modell))
        if r.status_code == 429:
            raise KiFehler("%s meldet: zu viele Anfragen oder Tageslimit erreicht. Später erneut starten." % self.name)
        raise KiFehler("%s antwortet mit Fehler %d: %s" % (self.name, r.status_code, meldung))

    def modelle(self):
        r = self.sitzung.get(self.url + "/models", headers=self._kopf(), timeout=30)
        self._pruefe(r)
        liste = []
        for m in r.json().get("data", []):
            preis = m.get("pricing") or {}
            try:
                # OpenRouter: Preis je Token -> Dollar je Million Ausgabe-Token
                ausgabe = float(preis.get("completion", "")) * 1e6
                info = "kostenlos" if ausgabe == 0 else "%.2f $ / Mio. Wörterteile" % ausgabe
            except ValueError:
                info = ""
            liste.append({"id": m["id"], "name": m.get("name") or m["id"], "info": info})
        return sorted(liste, key=lambda m: m["id"])
