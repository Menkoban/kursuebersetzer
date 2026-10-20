"""Kursübersetzer – Weboberfläche für den Skill moodle-kurs-uebersetzen.

Start:  python -m uvicorn app.server:app --port 8765   (oder start.bat / docker compose up)
"""
import hashlib
import json
import os
import re
import shutil
import string
import subprocess
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import ablauf, heygen, ki, moodleprobe, pfade, sprachen, uebersetzer

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
EINSTELLUNGEN = os.path.join(ablauf.DATEN, "einstellungen.json")
os.makedirs(ablauf.DATEN, exist_ok=True)

app = FastAPI(title="Kursübersetzer")
_SCHLUESSEL_FENSTER = uuid.uuid4().hex


@app.middleware("http")
async def nur_eigenes_fenster(request, call_next):
    """Webseiten im Browser koennten sonst an 127.0.0.1 Auftraege schicken – mit den Schluesseln
    und dem Guthaben der Schule. Aendernde Anfragen brauchen das Fenster-Cookie (SameSite=Strict)
    und duerfen nicht von fremder Herkunft kommen."""
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        herkunft = request.headers.get("origin")
        eigene = {"http://%s" % request.headers.get("host", ""), "https://%s" % request.headers.get("host", "")}
        if request.cookies.get("kue") != _SCHLUESSEL_FENSTER or (herkunft and herkunft not in eigene):
            return JSONResponse({"detail": "Nur aus dem Kursübersetzer-Fenster erlaubt."}, status_code=403)
    antwort = await call_next(request)
    if request.method == "GET" and request.cookies.get("kue") != _SCHLUESSEL_FENSTER:
        antwort.set_cookie("kue", _SCHLUESSEL_FENSTER, httponly=True, samesite="strict")
    return antwort
schlange = ablauf.Warteschlange()
abbildung = pfade.Abbildung.aus_umgebung()


# ------------------------------------------------------------ Einstellungen (API-Schlüssel)

def _einstellungen():
    try:
        with open(EINSTELLUNGEN, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _schluessel(name, umgebung):
    return _einstellungen().get(name) or os.environ.get(umgebung, "")


def _verdeckt(s):
    return (s[:7] + "…" + s[-4:]) if len(s) > 14 else ("hinterlegt" if s else "")


def ja(wert):
    """Ja/Nein aus dem Formular. Fehlt das Feld, gilt „ja“ (FastAPI wuerde sonst „nein“ annehmen)."""
    if wert is None:
        return True
    return str(wert).strip().lower() in ("true", "1", "on", "ja", "yes")


def _ki_konfig():
    """Gewaehlter Anbieter samt Modell, Adresse und Schluessel – so, wie ki.erstelle es braucht."""
    e = _einstellungen()
    anbieter = e.get("ki_anbieter") or os.environ.get("KI_ANBIETER") or "anthropic"
    if anbieter not in ki.ANBIETER:
        anbieter = "anthropic"
    return {"anbieter": anbieter,
            "modell": (e.get("ki_modelle") or {}).get(anbieter) or os.environ.get("KI_MODELL", ""),
            "url": e.get("openai_url") or os.environ.get("OPENAI_BASE_URL", ""),
            "schluessel": _schluessel(anbieter, ki.ANBIETER[anbieter]["umgebung"])}


def _vorlese_konfig():
    e = _einstellungen()
    return {"art": e.get("vorlesen_art") or "edge",
            "region": e.get("azure_region") or os.environ.get("AZURE_SPEECH_REGION") or "germanywestcentral",
            "schluessel": _schluessel("azure", "AZURE_SPEECH_KEY")}


def _ki_fehlt():
    """Leerer Text = startklar, sonst was noch fehlt."""
    k = _ki_konfig()
    info = ki.ANBIETER[k["anbieter"]]
    if info["schluessel_noetig"] and not k["schluessel"]:
        return "Für die Übersetzung fehlt der API-Schlüssel für %s – bitte im Zahnrad oben rechts eintragen." % info["name"]
    if k["anbieter"] == "openai" and not (k["url"] and k["modell"]):
        return "Für den eigenen Dienst fehlen Adresse oder Modell (Zahnrad oben rechts)."
    return ""


@app.get("/api/einstellungen")
def einstellungen_lesen():
    e = _einstellungen()
    k = _ki_konfig()
    return {"ki": {"anbieter": k["anbieter"], "modell": k["modell"] or ki.ANBIETER[k["anbieter"]]["modell"],
                   "url": k["url"], "fehlt": _ki_fehlt(),
                   "anbieter_liste": [{"id": i, "name": a["name"], "standard_modell": a["modell"],
                                       "schluessel_noetig": a["schluessel_noetig"],
                                       "modell": (e.get("ki_modelle") or {}).get(i, ""),
                                       "schluessel": _verdeckt(_schluessel(i, a["umgebung"]))}
                                      for i, a in ki.ANBIETER.items()]},
            "heygen": _verdeckt(_schluessel("heygen", "HEYGEN_API_KEY")),
            "vorlesen": {"art": _vorlese_konfig()["art"], "region": _vorlese_konfig()["region"],
                         "schluessel": _verdeckt(_schluessel("azure", "AZURE_SPEECH_KEY"))},
            "letzter_videoordner": e.get("letzter_videoordner", ""),
            "letzte_sprache": e.get("letzte_sprache", ""),
            "letzter_modus": e.get("letzter_modus", ""),
            "zuletzt_sprachen": e.get("zuletzt_sprachen", []),
            "datenschutz_gelesen": bool(e.get("datenschutz_gelesen"))}


@app.post("/api/einstellungen")
def einstellungen_speichern(daten: dict):
    e = _einstellungen()
    if daten.get("ki_anbieter") in ki.ANBIETER:
        e["ki_anbieter"] = daten["ki_anbieter"]
    if daten.get("ki_modell") is not None:
        e.setdefault("ki_modelle", {})[e.get("ki_anbieter", "anthropic")] = str(daten["ki_modell"]).strip()
    if daten.get("openai_url") is not None:
        e["openai_url"] = str(daten["openai_url"]).strip()
    if daten.get("datenschutz_gelesen"):
        e["datenschutz_gelesen"] = True
    if daten.get("vorlesen_art") in ("edge", "azure"):
        e["vorlesen_art"] = daten["vorlesen_art"]
    if daten.get("azure_region") is not None:
        e["azure_region"] = str(daten["azure_region"]).strip()
    schluessel = dict(daten.get("schluessel") or {})
    if daten.get("heygen") is not None:
        schluessel["heygen"] = daten["heygen"]
    for k, wert in schluessel.items():
        if k not in ki.ANBIETER and k not in ("heygen", "azure") or wert is None:
            continue
        wert = str(wert).strip()
        if wert:
            e[k] = wert
        else:
            e.pop(k, None)
    with open(EINSTELLUNGEN, "w", encoding="utf-8") as fh:
        json.dump(e, fh, indent=1)
    return einstellungen_lesen()


@app.get("/api/modelle")
def modellliste():
    """Modelle des gewaehlten Anbieters fuer die Auswahlliste (OpenRouter auch ohne Schluessel)."""
    try:
        return {"modelle": ki.erstelle(_ki_konfig()).modelle()[:600]}
    except Exception as e:
        return {"modelle": [], "fehler": str(e)[:200]}


@app.post("/api/einstellungen/testen")
def schluessel_testen(daten: dict):
    welcher = daten.get("welcher")
    try:
        if welcher == "ki":
            if _ki_fehlt():
                return {"ok": False, "text": _ki_fehlt()}
            k = ki.erstelle(_ki_konfig())
            antwort = uebersetzer.uebersetze_texte({"Trage immer eine Schutzbrille.": ""}, "Englisch", ki=k,
                                                   melde=lambda *_: None)
            return {"ok": True, "text": "%s antwortet: „%s“" % (k.modell, antwort["Trage immer eine Schutzbrille."])}
        if welcher == "stimme":
            import tempfile
            from . import vorlesen
            k = _vorlese_konfig()
            ziel = os.path.join(tempfile.gettempdir(), "kursuebersetzer_probe.mp3")
            vorlesen.sprechen("Trage immer eine Schutzbrille.", "de-DE-KatjaNeural", ziel, dienst=k)
            groesse = os.path.getsize(ziel) // 1024
            os.remove(ziel)
            return {"ok": True, "text": "%s liest vor (%d KB Probe)." % (
                "Azure Speech (%s)" % k["region"] if k["art"] == "azure" else "Edge-Stimme", groesse)}
        if welcher == "heygen":
            q = heygen.HeyGen(_schluessel("heygen", "HEYGEN_API_KEY")).guthaben()
            return {"ok": True, "text": "HeyGen erreichbar. Guthaben: %s" % (q or "—")}
    except Exception as e:
        return {"ok": False, "text": str(e)[:200]}
    raise HTTPException(400, "unbekannt")


# ------------------------------------------------------------ Systemstand

def _hat(befehl):
    return shutil.which(befehl) is not None


@app.get("/api/status")
def status():
    def paket(n):
        import importlib.util
        return importlib.util.find_spec(n) is not None
    return {"skill": ablauf.skill_ordner() is not None,
            "ffmpeg": _hat("ffmpeg") and _hat("ffprobe"),
            "edge_tts": paket("edge_tts"),
            "whisper": paket("faster_whisper"),
            "verkleinern": ablauf.verkleinern_skript() is not None,
            "container": abbildung.aktiv,
            "freigabe": abbildung.host}


@app.get("/api/sprachen")
def sprachliste():
    return sprachen.fuer_oberflaeche()


# ------------------------------------------------------------ Ordnerauswahl

def _wurzeln():
    if abbildung.aktiv:
        return [abbildung.host]
    if os.name == "nt":
        return ["%s:\\" % b for b in string.ascii_uppercase if os.path.exists("%s:\\" % b)]
    return ["/"]


@app.get("/api/ordner")
def ordner(pfad: str = ""):
    if not pfad:
        start = []
        home = os.path.expanduser("~")
        for p in (os.path.join(home, "OneDrive - HSOS", "Desktop"), os.path.join(home, "Desktop")):
            if os.path.isdir(p) and not abbildung.aktiv:
                start.append({"name": os.path.basename(os.path.dirname(p)) + " › Desktop", "pfad": p})
        return {"pfad": "", "eltern": None,
                "ordner": start + [{"name": w, "pfad": w} for w in _wurzeln()], "videos": 0}
    try:
        lokal = abbildung.zu_lokal(pfad)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not os.path.isdir(lokal):
        raise HTTPException(404, "Ordner gibt es nicht")
    eintraege, videos = [], 0
    try:
        for e in sorted(os.scandir(lokal), key=lambda e: e.name.lower()):
            if e.is_dir() and not e.name.startswith((".", "$")):
                eintraege.append({"name": e.name, "pfad": os.path.join(pfad, e.name)})
            elif e.name.lower().endswith(".mp4"):
                videos += 1
    except PermissionError:
        pass
    eltern = os.path.dirname(pfad.rstrip("\\/"))
    if eltern == pfad.rstrip("\\/") or (abbildung.aktiv and len(eltern) < len(abbildung.host)):
        eltern = ""
    return {"pfad": pfad, "eltern": eltern, "ordner": eintraege, "videos": videos}


# ------------------------------------------------------------ Aufträge

def _arbeitsordner(mbz_pfad, name):
    """Gleicher Kurs -> gleicher Arbeitsordner: Transkripte und Übersetzungen werden wiederverwendet."""
    h = hashlib.sha1()
    with open(mbz_pfad, "rb") as fh:
        h.update(fh.read(8 << 20))
    h.update(str(os.path.getsize(mbz_pfad)).encode())
    stamm = re.sub(r"[^\w.-]", "_", os.path.splitext(name)[0])[:60]
    return os.path.join(ablauf.DATEN, "arbeit", "%s_%s" % (stamm, h.hexdigest()[:8]))


@app.post("/api/auftrag")
async def auftrag_anlegen(
        mbz: UploadFile = File(...), sprache: str = Form(...), videoordner: str = Form(""),
        modus: str = Form("edge"), stimme: str = Form("auto"), kursname: str = Form(""),
        quizid: str = Form(""), klein: str = Form(None), moodleprobe: str = Form(None)):
    if sprache not in sprachen.SPRACHEN:
        raise HTTPException(400, "Unbekannte Sprache")
    if modus not in ("edge", "heygen"):
        raise HTTPException(400, "Unbekannter Modus")
    if not (mbz.filename or "").lower().endswith(".mbz"):
        raise HTTPException(400, "Bitte eine Moodle-Sicherung (.mbz) wählen")
    vo_lokal = ""
    if videoordner.strip():
        try:
            vo_lokal = abbildung.zu_lokal(videoordner.strip().strip('"'))
        except ValueError as e:
            raise HTTPException(400, str(e))
        if not os.path.isdir(os.path.dirname(vo_lokal.rstrip("\\/")) or vo_lokal):
            raise HTTPException(400, "Den Videoordner (oder seinen übergeordneten Ordner) gibt es nicht.")
    if _ki_fehlt():
        raise HTTPException(400, _ki_fehlt())
    if modus == "heygen" and not _schluessel("heygen", "HEYGEN_API_KEY"):
        raise HTTPException(400, "Für HeyGen fehlt der API-Schlüssel (Zahnrad oben rechts).")

    eingang = os.path.join(ablauf.DATEN, "eingang")
    os.makedirs(eingang, exist_ok=True)
    tmp = os.path.join(eingang, "upload_%s.mbz" % uuid.uuid4().hex)
    with open(tmp, "wb") as fh:
        while stueck := await mbz.read(8 << 20):
            fh.write(stueck)
    arbeit = _arbeitsordner(tmp, mbz.filename)
    os.makedirs(arbeit, exist_ok=True)
    os.replace(tmp, os.path.join(arbeit, "quelle.mbz"))

    e = _einstellungen()
    e.update(letzter_videoordner=videoordner, letzte_sprache=sprache, letzter_modus=modus,
             zuletzt_sprachen=([sprache] + [s for s in e.get("zuletzt_sprachen", []) if s != sprache])[:6])
    with open(EINSTELLUNGEN, "w", encoding="utf-8") as fh:
        json.dump(e, fh, indent=1)

    a = schlange.neu(code=sprache, modus=modus, stimme=stimme, kursname=kursname.strip(),
                     quizid=quizid.strip(), klein=ja(klein), moodleprobe=ja(moodleprobe), videoordner=vo_lokal, arbeit=arbeit,
                     mbz_name=mbz.filename, ki=_ki_konfig(), vorlesen=_vorlese_konfig(),
                     heygen=_schluessel("heygen", "HEYGEN_API_KEY"))
    return {"id": a.id}


def _fuer_anzeige(d):
    for e in d["ergebnisse"]:
        e["anzeige"] = abbildung.zu_host(e["datei"])
    return d


@app.get("/api/auftraege")
def auftraege():
    return [_fuer_anzeige(a.als_dict(ab=len(a.log))) for a in
            sorted(schlange.auftraege.values(), key=lambda a: -a.beginn)]


@app.get("/api/auftrag/{aid}")
def auftrag(aid: str, ab: int = 0):
    a = schlange.auftraege.get(aid)
    if not a:
        raise HTTPException(404, "Auftrag unbekannt")
    return _fuer_anzeige(a.als_dict(ab=ab))


@app.post("/api/auftrag/{aid}/abbrechen")
def abbrechen(aid: str):
    a = schlange.auftraege.get(aid)
    if not a:
        raise HTTPException(404, "Auftrag unbekannt")
    a.abbrechen = True
    return {"ok": True}


@app.get("/api/auftrag/{aid}/datei/{nr}")
def herunterladen(aid: str, nr: int):
    a = schlange.auftraege.get(aid)
    if not a or nr >= len(a.ergebnisse):
        raise HTTPException(404, "Datei unbekannt")
    e = a.ergebnisse[nr]
    return FileResponse(e["datei"], filename=e["name"], media_type="application/octet-stream")


@app.post("/api/auftrag/{aid}/zeigen/{nr}")
def im_explorer_zeigen(aid: str, nr: int):
    a = schlange.auftraege.get(aid)
    if not a or nr >= len(a.ergebnisse) or abbildung.aktiv or os.name != "nt":
        return JSONResponse({"ok": False})
    subprocess.Popen(["explorer", "/select,", os.path.normpath(a.ergebnisse[nr]["datei"])])
    return {"ok": True}


# ------------------------------------------------------------ Moodle-Probe (Testlabor)

_labor = moodleprobe.Einrichtung()
_bereit_merker = {"zeit": 0.0, "wert": False}


@app.get("/api/moodlelabor")
def moodlelabor():
    import time
    if not _labor.laeuft and time.time() - _bereit_merker["zeit"] > 60:
        _bereit_merker.update(zeit=time.time(), wert=moodleprobe.bereit())
    return {"eingebaut": moodleprobe.skriptordner() is not None, "bereit": _bereit_merker["wert"],
            "laeuft": _labor.laeuft, "ergebnis": _labor.ergebnis, "log": _labor.log[-12:],
            "ordner": abbildung.zu_host(moodleprobe.laborordner())}


@app.post("/api/moodlelabor/einrichten")
def moodlelabor_einrichten():
    _bereit_merker["zeit"] = 0.0
    _labor.starten()
    return moodlelabor()


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
