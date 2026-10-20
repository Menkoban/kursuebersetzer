"""Videos lippensynchron uebersetzen lassen – HeyGen-API v3 mit dem Schluessel der Schule.

Nach der offiziellen Doku (developers.heygen.com, Stand 20.10.2026):
  hochladen   POST /v3/assets (bis 32 MB) bzw. direct upload in drei Schritten (bis 200 MB)
  uebersetzen POST /v3/video-translations  {video: {type: asset_id}, output_languages, mode}
  Status      GET  /v3/video-translations/{id}  -> pending | running | completed | failed
Das API-Guthaben ist getrennt vom HeyGen-Web-Abo und wird nach Laenge des Originals berechnet.
"""
import os
import time

API = "https://api.heygen.com"
NICHT_FERTIG = "nicht rechtzeitig fertig geworden"
KLEIN_BIS = 32 * 1024 * 1024          # darueber: direct upload
GROSS_BIS = 200 * 1024 * 1024         # Obergrenze direct upload fuer Videos


class HeyGenFehler(Exception):
    pass


def _meldung(r):
    try:
        d = r.json()
    except ValueError:
        return (r.text or "")[:200]
    fehler = d.get("error") or {}
    if isinstance(fehler, dict):
        return fehler.get("message") or fehler.get("code") or d.get("message") or ""
    return str(fehler) or d.get("message") or ""


def _pruefe(r):
    if r.status_code == 401:
        raise HeyGenFehler("HeyGen nimmt den API-Schlüssel nicht an – bitte im Zahnrad prüfen.")
    if r.status_code == 402:
        raise HeyGenFehler("HeyGen: API-Guthaben aufgebraucht – bitte im HeyGen-Konto aufladen.")
    if r.status_code == 429:
        raise HeyGenFehler("HeyGen: zu viele gleichzeitige Aufträge – später erneut starten.")
    if r.status_code >= 400:
        raise HeyGenFehler("HeyGen (Fehler %d): %s" % (r.status_code, _meldung(r)))
    try:
        return r.json().get("data") or {}
    except ValueError:
        return {}


class HeyGen:
    def __init__(self, schluessel, sitzung=None):
        if not schluessel:
            raise HeyGenFehler("Kein HeyGen-API-Schlüssel hinterlegt (Zahnrad oben rechts).")
        if sitzung is None:
            import requests
            sitzung = requests
        self.s = sitzung
        self.kopf = {"X-Api-Key": schluessel, "accept": "application/json"}

    def guthaben(self):
        d = _pruefe(self.s.get(API + "/v3/users/me", headers=self.kopf, timeout=30))
        for schluessel in ("api_balance", "balance", "remaining_quota", "credits", "wallet"):
            if d.get(schluessel) not in (None, ""):
                return d[schluessel]
        return "verbunden"

    def sprache_finden(self, wunsch):
        """HeyGen nennt Sprachen z. B. 'French' oder 'French (France)'. Erst exakt, dann nach Anfang."""
        d = _pruefe(self.s.get(API + "/v3/video-translations/languages", headers=self.kopf, timeout=30))
        liste = d.get("languages") if isinstance(d, dict) else d
        liste = [x if isinstance(x, str) else (x.get("name") or "") for x in (liste or [])]
        for name in liste:
            if name.lower() == wunsch.lower():
                return name
        # Varianten (Schrift, Land) nie raten: ein falsch bestelltes Video kostet Geld
        if "(" not in wunsch:
            kandidaten = [n for n in liste if n.lower().startswith(wunsch.lower() + " (")]
            if len(kandidaten) == 1:
                return kandidaten[0]
            if len(kandidaten) > 1:
                raise HeyGenFehler("Sprache „%s“ ist bei HeyGen mehrdeutig (%s) – nicht bestellt."
                                   % (wunsch, ", ".join(kandidaten)))
        raise HeyGenFehler("HeyGen bietet die Sprache „%s“ nicht an – nicht bestellt." % wunsch)

    def hochladen(self, pfad):
        groesse = os.path.getsize(pfad)
        if groesse > GROSS_BIS:
            raise HeyGenFehler("Video größer als 200 MB – HeyGen nimmt es nicht an.")
        if groesse <= KLEIN_BIS:
            with open(pfad, "rb") as fh:
                d = _pruefe(self.s.post(API + "/v3/assets", headers=self.kopf, timeout=1800,
                                        files={"file": (os.path.basename(pfad), fh, "video/mp4")}))
            return d["asset_id"]
        init = _pruefe(self.s.post(API + "/v3/assets/direct-uploads", headers=self.kopf, timeout=60,
                                   json={"filename": os.path.basename(pfad), "content_type": "video/mp4",
                                         "size_bytes": groesse}))
        with open(pfad, "rb") as fh:
            r = self.s.put(init["upload_url"], data=fh, headers=init.get("upload_headers") or {}, timeout=3600)
        if r.status_code >= 400:
            raise HeyGenFehler("Hochladen zu HeyGen fehlgeschlagen (Fehler %d)." % r.status_code)
        _pruefe(self.s.post(API + "/v3/assets/%s/complete" % init["asset_id"], headers=self.kopf,
                            json={}, timeout=60))
        return init["asset_id"]

    def uebersetzen(self, asset_id, sprache, titel, modus="speed"):
        d = _pruefe(self.s.post(API + "/v3/video-translations", headers=self.kopf, timeout=60, json={
            "video": {"type": "asset_id", "asset_id": asset_id}, "output_languages": [sprache],
            "mode": modus, "title": titel}))
        return d["video_translation_ids"][0]

    def stand(self, auftrag):
        """-> (zustand, info) mit zustand in wartet | fertig (info = Video-Adresse) | fehler (info = Grund)."""
        d = _pruefe(self.s.get(API + "/v3/video-translations/%s" % auftrag, headers=self.kopf, timeout=60))
        s = (d.get("status") or "").lower()
        if s == "completed":
            return "fertig", d.get("video_url")
        if s == "failed":
            return "fehler", d.get("failure_message") or "unbekannter Fehler"
        return "wartet", None

    def finde_auftrag(self, titel, seiten=5):
        """Auftragsnummer zu einem Titel suchen (nach einem Absturz waehrend der Bestellung)."""
        weiter = None
        for _ in range(seiten):
            parameter = "?limit=100" + ("&token=%s" % weiter if weiter else "")
            r = self.s.get(API + "/v3/video-translations" + parameter, headers=self.kopf, timeout=60)
            _pruefe(r)
            koerper = r.json()
            for eintrag in koerper.get("data") or []:
                if eintrag.get("title") == titel:
                    return eintrag.get("id")
            weiter = koerper.get("next_token")
            if not weiter:
                return None
        return None

    def abholen(self, url, ziel):
        """Laedt vollstaendig herunter oder gar nicht (Laenge gegen Content-Length geprueft)."""
        try:
            r = self.s.get(url, stream=True, timeout=600)
            if r.status_code != 200:
                return False
            soll = int(r.headers.get("Content-Length") or 0)
            ist = 0
            with open(ziel, "wb") as fh:
                for stueck in r.iter_content(1 << 20):
                    fh.write(stueck)
                    ist += len(stueck)
            return ist > 0 and (not soll or ist == soll)
        except Exception:  # Netzabbruch mitten im Download
            return False


class Bestellbuch:
    """Merkt sich jede HeyGen-Bestellung je Originalvideo (Pruefsumme) und Sprache –
    ueber alle Arbeitsordner hinweg. Eingetragen wird VOR der Bestellung, damit ein Absturz
    oder ein neuer Moodle-Export nie zu einer zweiten, bezahlten Bestellung fuehrt.

    zustand: bestellt (Antwort steht aus) | auftrag (Nummer bekannt) | fertig | verworfen | gescheitert
    """

    def __init__(self, pfad):
        import json
        self.pfad = pfad
        try:
            with open(pfad, encoding="utf-8") as fh:
                self.daten = json.load(fh)
        except (OSError, ValueError):
            self.daten = {}

    def _speichern(self):
        import json
        os.makedirs(os.path.dirname(self.pfad) or ".", exist_ok=True)
        with open(self.pfad + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(self.daten, fh, ensure_ascii=False, indent=1)
        os.replace(self.pfad + ".tmp", self.pfad)

    @staticmethod
    def _k(video, code):
        return "%s_%s" % (video, code)

    def eintrag(self, video, code):
        return self.daten.get(self._k(video, code))

    def _setze(self, video, code, **felder):
        e = self.daten.setdefault(self._k(video, code), {})
        e.update(felder, zeit=time.strftime("%Y-%m-%d %H:%M"))
        self._speichern()

    def vor_bestellung(self, video, code, asset, titel):
        self._setze(video, code, zustand="bestellt", asset=asset, titel=titel, auftrag=None)

    def auftrag_gemerkt(self, video, code, auftrag):
        self._setze(video, code, zustand="auftrag", auftrag=auftrag)

    def fertig(self, video, code, datei):
        self._setze(video, code, zustand="fertig", datei=datei)

    def verworfen(self, video, code, grund):
        self._setze(video, code, zustand="verworfen", grund=grund)

    def gescheitert(self, video, code, grund):
        self._setze(video, code, zustand="gescheitert", grund=grund)

    def darf_bestellen(self, video, code):
        e = self.eintrag(video, code)
        return e is None or e.get("zustand") == "gescheitert"


def warte_auf_alle(hg, auftraege, abholen, melde, abbruch=lambda: False, hoechstens_s=4 * 3600):
    """auftraege: {schluessel: auftrags_id}. abholen(schluessel, url) -> True | False | None (verworfen)."""
    offen = dict(auftraege)
    fehler = {}
    beginn = time.time()
    while offen and time.time() - beginn < hoechstens_s and not abbruch():
        for k, aid in list(offen.items()):
            try:
                zustand, info = hg.stand(aid)
            except Exception as e:  # HeyGenFehler, Netz
                melde("  Statusabfrage %s: %s" % (k, e))
                continue
            if zustand == "fertig" and info:
                ergebnis = abholen(k, info)
                if ergebnis is None:
                    fehler[k] = "Länge auffällig, verworfen"
                    del offen[k]
                elif ergebnis:
                    del offen[k]
                    melde("  fertig: %s" % k)
            elif zustand == "fehler":
                fehler[k] = info
                del offen[k]
                melde("  FEHLER bei %s: %s" % (k, info))
        if offen:
            melde("  warte auf HeyGen: noch %d Video(s) …" % len(offen))
            for _ in range(30):
                if abbruch():
                    break
                time.sleep(1)
    for k in offen:
        fehler[k] = NICHT_FERTIG
    return fehler
