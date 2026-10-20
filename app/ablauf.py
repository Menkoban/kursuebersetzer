"""Ein Uebersetzungsauftrag von der .mbz bis zur fertigen Sicherung.

Ruft die Skripte des Skills moodle-kurs-uebersetzen auf (analyse, vorbereiten,
videos_bauen, kurs_bauen, pruefen) und ersetzt nur die Stellen, an denen im Skill
Claude von Hand arbeitet: Uebersetzen (Sprachmodell nach Wahl), Vertonen je Video mit passender Stimme,
Videos mit HeyGen. Auftraege laufen nacheinander, nie zwei zugleich.
"""
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import traceback
import uuid
import xml.etree.ElementTree as ET

from . import heygen, sprachen, stimme, uebersetzer, zuordnung

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Arbeitsordner werden schnell mehrere GB gross: nicht in OneDrive, sondern lokal ablegen
DATEN = os.environ.get("APP_DATEN") or (
    os.path.join(os.environ["LOCALAPPDATA"], "Kursuebersetzer") if os.environ.get("LOCALAPPDATA")
    else os.path.join(APP, "daten"))
GRENZE_MB = 500


def skill_ordner():
    for p in (os.environ.get("SKILL_ORDNER"),
              os.path.join(APP, "..", "moodle-kurs-uebersetzen"),
              os.path.expanduser("~/.claude/skills/moodle-kurs-uebersetzen")):
        if p and os.path.isfile(os.path.join(p, "scripts", "analyse.py")):
            return os.path.abspath(p)
    return None


def verkleinern_skript():
    for p in (os.environ.get("VERKLEINERN"), os.path.join(APP, "..", "verkleinern", "verkleinern.py")):
        if p and os.path.isfile(p):
            return os.path.abspath(p)
    return None


SCHRITTE = [
    ("einlesen", "Kurs einlesen"),
    ("videos_suchen", "Fertige Videos suchen"),
    ("texte", "Kurstexte übersetzen"),
    ("videos", "Fehlende Videos erstellen"),
    ("bauen", "Moodle-Sicherung bauen"),
    ("pruefen", "Sicherung prüfen"),
    ("klein", "Fassung ≤ 500 MB für Moodle"),
    ("moodle", "Probe-Einspielung in Moodle"),
]


class Abbruch(Exception):
    pass


class Auftrag:
    def __init__(self, **angaben):
        self.id = uuid.uuid4().hex[:10]
        self.angaben = angaben
        self.zustand = "wartet"           # wartet | laeuft | fertig | fehler | abgebrochen
        self.schritte = {k: {"name": n, "zustand": "offen", "info": ""} for k, n in SCHRITTE}
        self.log = []
        self.zahlen = {}
        self.ergebnisse = []
        self.fehler = ""
        self.hinweise = []
        self.abbrechen = False
        self.beginn = time.time()
        self.ende = None

    # ------------------------------------------------------------ Anzeige
    def melde(self, text):
        for zeile in str(text).splitlines() or [""]:
            self.log.append(zeile)
        if len(self.log) > 4000:
            del self.log[:1000]

    def schritt(self, k, zustand, info=None):
        self.schritte[k]["zustand"] = zustand
        if info is not None:
            self.schritte[k]["info"] = info

    def als_dict(self, ab=0):
        a = self.angaben
        return {"id": self.id, "zustand": self.zustand, "fehler": self.fehler,
                "kurs": a.get("mbz_name"), "sprache": a.get("code"), "modus": a.get("modus"),
                "schritte": [dict(schluessel=k, **v) for k, v in self.schritte.items()],
                "log": self.log[ab:], "log_ab": ab, "log_bis": len(self.log),
                "zahlen": self.zahlen, "ergebnisse": self.ergebnisse, "hinweise": self.hinweise,
                "dauer_s": round((self.ende or time.time()) - self.beginn)}

    def pruefe_abbruch(self):
        if self.abbrechen:
            raise Abbruch()


# ------------------------------------------------------------ Hilfen

def _skript(auftrag, name, *argumente, erlaubt=(0,)):
    pfad = os.path.join(skill_ordner(), "scripts", name)
    befehl = python_befehl(pfad) + list(argumente)
    umg = dict(os.environ, PYTHONIOENCODING="utf-8")
    auftrag.melde("$ %s %s" % (name, " ".join(os.path.basename(a) if os.sep in a else a for a in argumente)))
    p = subprocess.Popen(befehl, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace", env=umg)
    for zeile in p.stdout:
        auftrag.melde("  " + zeile.rstrip())
        if auftrag.abbrechen:
            p.kill()
            raise Abbruch()
    p.wait()
    if p.returncode not in erlaubt:
        raise RuntimeError("%s ist mit Fehler %d beendet worden (siehe Protokoll)." % (name, p.returncode))
    return p.returncode


def python_befehl(skript):
    """Aufruf eines Skripts. In der .exe ist sys.executable die Anwendung selbst – sie
    erkennt den Skriptaufruf (siehe start.py), ein installiertes Python ist nicht noetig."""
    return [sys.executable, "-I", "-X", "utf8", skript]


def sprechen(text, stimme, ziel, tempo=None, dienst=None):
    """Microsoft-Stimme ueber edge-tts oder Azure Speech (siehe vorlesen.py)."""
    from . import vorlesen
    vorlesen.sprechen(text, stimme, ziel, tempo=tempo, dienst=dienst)


def _lies(p, vorgabe=None):
    if not os.path.exists(p):
        return vorgabe
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _schreib(p, obj):
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(p + ".tmp", p)


def _dauer(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", p], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _sprachname(code):
    """Fuer den Auftrag ans Modell: deutscher und englischer Name, damit nichts verwechselt wird."""
    s = sprachen.SPRACHEN[code]
    return "%s (%s)" % (s["name"], s["heygen"])


def _kursnamen(mbz):
    with tarfile.open(mbz, "r:gz") as t:
        for m in t:
            if m.name == "course/course.xml":
                root = ET.fromstring(t.extractfile(m).read())
                return (root.findtext(".//fullname") or "").strip(), (root.findtext(".//shortname") or "").strip()
    return "", ""


def _ohne_kuerzel(name):
    """'DE: Sicherheitsunterweisung' -> 'Sicherheitsunterweisung'."""
    return re.sub(r"^\s*[A-Z]{2}\s*[:\-–]\s*", "", name)


def _kurzname(kurz, code):
    gross = kurz.isupper()
    kurz = re.sub(r"(?i)[_\-\s]*de$", "", kurz) or "kurs"
    return "%s_%s" % (kurz, code.upper() if gross else code)


def _kopiere_neu(quelle, ordner, name, auftrag):
    """In den Sprachordner der Lehrkraft legen, nie etwas ueberschreiben."""
    if not ordner:
        return
    try:
        os.makedirs(ordner, exist_ok=True)
        ziel = os.path.join(ordner, name)
        if os.path.exists(ziel):
            auftrag.melde("  im Videoordner schon vorhanden, bleibt: %s" % name)
            return
        shutil.copy2(quelle, ziel + ".teil")
        os.replace(ziel + ".teil", ziel)
        auftrag.melde("  abgelegt im Videoordner: %s" % name)
    except OSError as e:
        auftrag.melde("  konnte nicht in den Videoordner legen (%s): %s" % (name, e))


# ------------------------------------------------------------ die Schritte

def _einlesen(a, arbeit):
    mbz = os.path.join(arbeit, "quelle.mbz")
    a.melde("Arbeitsordner: %s" % arbeit)
    _skript(a, "analyse.py", mbz, arbeit)
    kurs = _lies(os.path.join(arbeit, "kurs.json"))
    themen = zuordnung.hotspots_aus_mbz(mbz)
    demos = 0
    for v in kurs["videos"]:
        v["thema"] = themen.get(v["dateiname"], "")
        if not v["thema"]:
            demos += 1
            v["thema"] = "Demo" if demos == 1 else "Demo %d" % demos
    _schreib(os.path.join(arbeit, "kurs.json"), kurs)
    a.zahlen.update(videos=len(kurs["videos"]), minuten=round(sum(v["dauer"] for v in kurs["videos"]) / 60, 1),
                    aktivitaeten=len(kurs["aktivitaeten"]))
    if os.path.exists(os.path.join(arbeit, "hinweise.md")):
        with open(os.path.join(arbeit, "hinweise.md"), encoding="utf-8") as fh:
            a.hinweise += [z[2:].strip() for z in fh if z.startswith("- ")]
    return kurs


def zwischenspeicher_aufraeumen(vz, herkunft, modus, stimme, tempo):
    """Entfernt aus videos_<code>/ alles, dem nicht mehr zu trauen ist. Gibt die Behaltenen zurueck.

    - Dateien ohne Vermerk (halb geschrieben, abgebrochen, unbekannt)
    - aus dem Videoordner Uebernommenes (wird gleich frisch kopiert – oder fehlt, weil
      die Lehrkraft es dort entfernt hat)
    - Microsoft-Vertonungen, wenn jetzt HeyGen gewaehlt ist oder Stimme/Tempo anders sind
    HeyGen-Videos bleiben: sie kosten Credits und werden nur durch den Videoordner ersetzt.
    """
    behalten = []
    for f in os.listdir(vz) if os.path.isdir(vz) else []:
        h = herkunft.get(f)
        weg = (h is None or h.get("quelle") in ("ordner", "stumm")
               or (h.get("quelle") == "edge" and (modus != "edge" or h.get("stimme") != stimme
                                                  or (h.get("tempo") or "") != (tempo or ""))))
        if weg:
            os.remove(os.path.join(vz, f))
        else:
            behalten.append(f)
    for f in list(herkunft):
        if f not in behalten:
            herkunft.pop(f)
    return behalten


def _herkunft_datei(arbeit, code):
    return os.path.join(arbeit, "herkunft_%s.json" % code)


def _videos_suchen(a, arbeit, kurs, code):
    ziel = os.path.join(arbeit, "videos_%s" % code)
    os.makedirs(ziel, exist_ok=True)
    herkunft = _lies(_herkunft_datei(arbeit, code), {})
    zwischenspeicher_aufraeumen(ziel, herkunft, a.angaben["modus"], a.angaben.get("stimme", "auto"),
                                a.angaben.get("tempo", ""))
    mehrdeutig = []
    treffer = zuordnung.fertige_videos(kurs["videos"], a.angaben["videoordner"], mehrdeutig=mehrdeutig)
    for t in mehrdeutig:
        a.hinweise.append("Das Thema „%s“ kommt im Kurs mehrfach vor – passende Videos aus dem Ordner "
                          "wurden nicht zugeordnet, damit nichts vertauscht wird." % t)
    for v in kurs["videos"]:
        if v["datei"] in treffer:
            teil = os.path.join(ziel, v["datei"] + ".teil")
            shutil.copy2(treffer[v["datei"]], teil)
            os.replace(teil, os.path.join(ziel, v["datei"]))
            herkunft[v["datei"]] = {"quelle": "ordner", "datei": os.path.basename(treffer[v["datei"]])}
            a.melde("  übernommen: %-28s ← %s" % (v["thema"][:28], os.path.basename(treffer[v["datei"]])))
        elif herkunft.get(v["datei"], {}).get("quelle") in ("edge", "heygen"):
            a.melde("  schon erstellt (%s): %s" % (herkunft[v["datei"]]["quelle"], v["thema"]))
    _schreib(_herkunft_datei(arbeit, code), herkunft)
    treffer = {k: 1 for k in herkunft}
    fehlend = [v for v in kurs["videos"] if v["datei"] not in treffer]
    for v in fehlend:
        a.melde("  fehlt noch: %s" % v["thema"])
    a.zahlen.update(videos_fertig=len(treffer), videos_fehlend=len(fehlend))
    return fehlend


def _texte(a, arbeit, kurs, code):
    _skript(a, "vorbereiten.py", arbeit, code)
    datei = os.path.join(arbeit, "uebersetzung_%s.json" % code)
    vorlage = _lies(datei)
    sprache = _sprachname(code)
    offen = sum(1 for v in vorlage.values() if not v)
    a.melde("%d Kurstexte, davon %d noch zu übersetzen" % (len(vorlage), offen))
    if offen:
        fertig = uebersetzer.uebersetze_texte(vorlage, sprache, ki_konfig=a.angaben.get("ki"),
                                              melde=a.melde, zwischenspeichern=lambda d: _schreib(datei, d))
        _schreib(datei, fertig)
    a.zahlen["texte"] = len(vorlage)
    voll, kurz = _kursnamen(os.path.join(arbeit, "quelle.mbz"))
    if not a.angaben.get("kursname"):
        name = _ohne_kuerzel(voll) or "Sicherheitsunterweisung"
        uebersetzt = uebersetzer.uebersetze_texte({name: ""}, sprache, ki_konfig=a.angaben.get("ki"),
                                                  melde=lambda *_: None)[name]
        a.angaben["kursname"] = "%s: %s" % (code.upper(), uebersetzt)
    if not a.angaben.get("kurzname"):
        a.angaben["kurzname"] = _kurzname(kurz, code)
    a.melde("Kursname: %s  |  Kurzname: %s" % (a.angaben["kursname"], a.angaben["kurzname"]))


def _transkribieren(a, arbeit, videos):
    """Wie transkribieren.py, aber nur fuer die Videos, die wirklich neu vertont werden."""
    ziel = os.path.join(arbeit, "sprechtexte_de.json")
    ergebnis = _lies(ziel, {})
    offen = [v for v in videos if v["hat_ton"] and v["datei"] not in ergebnis]
    if not offen:
        return ergebnis
    a.melde("Sprechtexte erkennen (lokal, offline) – %d Video(s). Das dauert etwa doppelt so lange "
            "wie die Videos selbst." % len(offen))
    from faster_whisper import WhisperModel
    modell = WhisperModel(a.angaben.get("whisper", "medium"), device="cpu", compute_type="int8",
                          cpu_threads=os.cpu_count())
    for i, v in enumerate(offen, 1):
        a.pruefe_abbruch()
        t0 = time.time()
        teile, info = modell.transcribe(os.path.join(arbeit, "audio_de", v["ton"]), language="de",
                                        beam_size=5, vad_filter=True)
        text = " ".join(s.text.strip() for s in teile).strip()
        ergebnis[v["datei"]] = {"nr": v["nr"], "dauer": round(info.duration, 1), "text": text}
        _schreib(ziel, ergebnis)
        a.melde("  [%d/%d] %-26s %3.0fs  %s" % (i, len(offen), v["thema"][:26], time.time() - t0, text[:60]))
    return ergebnis


def _videos_edge(a, arbeit, kurs, code, fehlend):
    if not sprachen.SPRACHEN[code]["stimmen"]:
        a.hinweise.append("Für %s hat Microsoft keine Vorlesestimme. Die Texte sind übersetzt, die Videos "
                          "bleiben aber deutsch – dafür HeyGen wählen oder fertige Videos in den Videoordner legen."
                          % sprachen.SPRACHEN[code]["name"])
        return
    mit_ton = fehlend
    _transkribieren(a, arbeit, mit_ton)
    _skript(a, "vorbereiten.py", arbeit, code)
    datei = os.path.join(arbeit, "sprechtexte_%s.json" % code)
    sp = _lies(datei)
    vorlage = {sp[v["datei"]]["deutsch"]: sp[v["datei"]]["text"]
               for v in mit_ton if v["datei"] in sp and sp[v["datei"]]["deutsch"]}
    if any(not t for t in vorlage.values()):
        a.melde("Sprechtexte übersetzen …")
        fertig = uebersetzer.uebersetze_texte(vorlage, _sprachname(code), paketgroesse=8,
                                              ki_konfig=a.angaben.get("ki"), sprechtext=True,
                                              melde=a.melde)
        for k, e in sp.items():
            if not e["text"] and e["deutsch"] in fertig:
                e["text"] = fertig[e["deutsch"]]
        _schreib(datei, sp)

    vz = os.path.join(arbeit, "videos_%s" % code)
    mit_ton = [v for v in mit_ton if not os.path.exists(os.path.join(vz, v["datei"]))]
    stimmen = sprachen.SPRACHEN[code]["stimmen"]
    wahl = a.angaben.get("stimme", "auto")
    tondir = os.path.join(arbeit, "audio_%s" % code)
    os.makedirs(tondir, exist_ok=True)
    a.melde("Vertonen mit Microsoft-Stimmen (kostenlos) …")
    for v in mit_ton:
        a.pruefe_abbruch()
        e = sp.get(v["datei"])
        ziel = os.path.join(tondir, os.path.splitext(v["datei"])[0] + ".mp3")
        if not e or not e["text"]:
            a.melde("  kein Sprechtext für %s – bleibt im Original" % v["thema"])
            continue
        if os.path.exists(ziel):          # alter Ton (andere Stimme, halber Lauf): immer neu
            os.remove(ziel)
        if wahl == "auto":
            g, f0 = stimme.geschlecht(os.path.join(arbeit, "audio_de", v["ton"]))
            hinweis = "%.0f Hz" % f0 if f0 else "unklar"
        else:
            g, hinweis = wahl, "gewählt"
        text = re.sub(r"[\U0001F300-\U0001FAFF☀-➿️]", "", e["text"])
        text = re.sub(r"\s+", " ", text).strip()
        fehler = ""
        for versuch in range(3):
            try:
                sprechen(text, stimmen[g], ziel + ".teil", tempo=a.angaben.get("tempo"),
                         dienst=a.angaben.get("vorlesen"))
                if _dauer(ziel + ".teil") > 1:
                    os.replace(ziel + ".teil", ziel)
                    break
                fehler = "leere Tonaufnahme"
            except Exception as e:   # Netz, Microsoft-Dienst
                fehler = str(e) or e.__class__.__name__
            time.sleep(3 * (versuch + 1))
        ok = os.path.exists(ziel)
        if not ok and "403" in fehler:
            a.hinweise.append("Microsoft hat die Vorlesestimme abgelehnt (Fehler 403): Microsoft hat die Anmeldung "
                              "geändert, der Kursübersetzer braucht eine neue Fassung von edge-tts.")
        a.melde("  %-26s %s  %s (%s)" % (v["thema"][:26], "ok" if ok else "FEHLER " + fehler[:80],
                                        stimmen[g], hinweis))
    _skript(a, "videos_bauen.py", arbeit, code, erlaubt=(0, 1))
    herkunft = _lies(_herkunft_datei(arbeit, code), {})
    for v in mit_ton:
        if os.path.exists(os.path.join(vz, v["datei"])):
            herkunft[v["datei"]] = {"quelle": "edge", "stimme": wahl, "tempo": a.angaben.get("tempo", "")}
    _schreib(_herkunft_datei(arbeit, code), herkunft)


def _fuer_heygen(pfad, a):
    """HeyGen nimmt Videos bis 200 MB; groessere werden vorher verkleinert (Bild bleibt gleich gross)."""
    if os.path.getsize(pfad) <= heygen.GROSS_BIS - (8 << 20):
        return pfad
    klein = pfad[:-4] + "_fuer_heygen.mp4"
    if not os.path.exists(klein):
        a.melde("  verkleinere für HeyGen: %s" % os.path.basename(pfad))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", pfad, "-c:v", "libx264", "-crf", "28",
                        "-preset", "medium", "-c:a", "aac", "-b:a", "128k", "-f", "mp4", klein + ".teil"],
                       check=True)
        os.replace(klein + ".teil", klein)
    return klein


def _bestellbuch():
    return heygen.Bestellbuch(os.path.join(DATEN, "heygen-bestellbuch.json"))


def _heygen_ergebnis(video, code):
    """Fertige HeyGen-Videos je Originalvideo und Sprache – ueberleben neue Moodle-Exporte."""
    return os.path.join(DATEN, "heygen-ergebnisse", "%s_%s.mp4" % (video, code))


def _videos_heygen(a, arbeit, kurs, code, fehlend):
    hg = heygen.HeyGen(a.angaben.get("heygen"))
    buch = _bestellbuch()
    vziel = os.path.join(arbeit, "videos_%s" % code)
    fehlend = [v for v in fehlend if not os.path.exists(os.path.join(vziel, v["datei"]))]
    nach_datei = {v["datei"]: v for v in fehlend}

    def uebernehmen(v, quelle, auftrag):
        shutil.copy2(quelle, os.path.join(vziel, v["datei"]))
        herkunft = _lies(_herkunft_datei(arbeit, code), {})
        herkunft[v["datei"]] = {"quelle": "heygen", "auftrag": auftrag}
        _schreib(_herkunft_datei(arbeit, code), herkunft)

    # 1. Was schon bestellt oder fertig ist, nie ein zweites Mal bezahlen
    offen, zu_bestellen = {}, []
    for v in fehlend:
        e = buch.eintrag(v["hash"], code) or {}
        z = e.get("zustand")
        if z == "fertig" and os.path.exists(_heygen_ergebnis(v["hash"], code)):
            uebernehmen(v, _heygen_ergebnis(v["hash"], code), e.get("auftrag"))
            a.melde("  schon von HeyGen geliefert: %s" % v["thema"])
        elif z in ("auftrag", "fertig") and e.get("auftrag"):
            offen[v["datei"]] = e["auftrag"]
        elif z == "bestellt":
            gefunden = hg.finde_auftrag(e.get("titel", ""))
            if gefunden:
                buch.auftrag_gemerkt(v["hash"], code, gefunden)
                offen[v["datei"]] = gefunden
                a.melde("  Bestellung wiedergefunden: %s" % v["thema"])
            else:
                a.hinweise.append("HeyGen: Für „%s“ ist unklar, ob die Bestellung angekommen ist – nicht "
                                  "erneut bestellt. Bitte im HeyGen-Konto nachsehen." % v["thema"])
        elif z == "verworfen":
            a.hinweise.append("HeyGen: Das Video „%s“ kam in auffälliger Länge zurück und wurde verworfen – "
                              "nicht automatisch neu bestellt. Bitte im HeyGen-Konto prüfen." % v["thema"])
        else:
            zu_bestellen.append(v)

    if zu_bestellen:
        sprache = hg.sprache_finden(sprachen.SPRACHEN[code]["heygen"])
        a.melde("HeyGen-Zielsprache: %s" % sprache)
        try:
            a.melde("HeyGen-Guthaben: %s" % hg.guthaben())
        except heygen.HeyGenFehler:
            pass
    for v in zu_bestellen:
        a.pruefe_abbruch()
        titel = "%s_%s_%s" % (v["thema"], code.upper(), v["hash"][:8])
        a.melde("  hochladen: %s (%.0f s)" % (v["thema"], v["dauer"]))
        asset = hg.hochladen(_fuer_heygen(os.path.join(arbeit, "videos", v["datei"]), a))
        buch.vor_bestellung(v["hash"], code, asset=asset, titel=titel)     # VOR der bezahlten Bestellung
        auftrag = hg.uebersetzen(asset, sprache, titel)
        buch.auftrag_gemerkt(v["hash"], code, auftrag)
        offen[v["datei"]] = auftrag

    def abholen(datei, url):
        v = nach_datei[datei]
        tmp = os.path.join(arbeit, "heygen_%s.teil" % datei)
        if not hg.abholen(url, tmp):
            if os.path.exists(tmp):
                os.remove(tmp)
            return False
        dq, dn = v["dauer"], _dauer(tmp)
        if dn <= 0 or (dq and not 0.7 <= dn / dq <= 1.6):
            a.melde("  AUFFÄLLIG: %s – Länge %.0f s statt etwa %.0f s, nicht übernommen" % (v["thema"], dn, dq))
            os.remove(tmp)
            buch.verworfen(v["hash"], code, "Länge %.0f s statt %.0f s" % (dn, dq))
            return None
        ergebnis = _heygen_ergebnis(v["hash"], code)
        os.makedirs(os.path.dirname(ergebnis), exist_ok=True)
        os.replace(tmp, ergebnis)
        buch.fertig(v["hash"], code, ergebnis)
        uebernehmen(v, ergebnis, offen[datei])
        return True

    fehler = heygen.warte_auf_alle(hg, offen, abholen, a.melde, abbruch=lambda: a.abbrechen)
    a.pruefe_abbruch()
    gescheitert = [k for k, grund in fehler.items() if grund not in (heygen.NICHT_FERTIG, "Länge auffällig, verworfen")]
    for k in gescheitert:                    # von HeyGen abgelehnt: beim naechsten Lauf neu bestellen
        buch.gescheitert(nach_datei[k]["hash"], code, fehler[k])
    if fehler:
        a.hinweise.append("HeyGen: %d Video(s) nicht fertig (%d von HeyGen abgelehnt, %d noch in Arbeit). Später "
                          "einfach neu starten: laufende werden nur abgeholt, nichts wird doppelt bezahlt."
                          % (len(fehler), len(gescheitert), len(fehler) - len(gescheitert)))


def _videos(a, arbeit, kurs, code, fehlend):
    vz = os.path.join(arbeit, "videos_%s" % code)
    herkunft = _lies(_herkunft_datei(arbeit, code), {})
    for v in [v for v in fehlend if not v["hat_ton"]]:   # stumme Videos: nichts zu vertonen
        shutil.copy2(os.path.join(arbeit, "videos", v["datei"]), os.path.join(vz, v["datei"]))
        herkunft[v["datei"]] = {"quelle": "stumm"}
    _schreib(_herkunft_datei(arbeit, code), herkunft)
    fehlend = [v for v in fehlend if v["hat_ton"]]
    if fehlend:
        if a.angaben["modus"] == "heygen":
            _videos_heygen(a, arbeit, kurs, code, fehlend)
        else:
            _videos_edge(a, arbeit, kurs, code, fehlend)
    herkunft = _lies(_herkunft_datei(arbeit, code), {})
    themen = [zuordnung.normalisiere(v["thema"]) for v in kurs["videos"]]
    neu = 0
    for v in fehlend:
        p = os.path.join(vz, v["datei"])
        if os.path.exists(p) and herkunft.get(v["datei"], {}).get("quelle") in ("edge", "heygen"):
            neu += 1
            name = zuordnung.zielname(v["thema"], code, v["datei"])
            if themen.count(zuordnung.normalisiere(v["thema"])) > 1:   # doppeltes Thema: eindeutig machen
                name = "%s %02d_%s.mp4" % (name[:-4].rsplit("_", 1)[0], v["nr"], code.upper())
            _kopiere_neu(p, a.angaben["videoordner"], name, a)
    a.zahlen["videos_neu"] = neu
    deutsch = [v["thema"] for v in kurs["videos"]
               if v["hat_ton"] and not os.path.exists(os.path.join(vz, v["datei"]))]
    a.zahlen["videos_deutsch"] = len(deutsch)
    if deutsch:
        a.hinweise.append("%d Video(s) bleiben vorerst DEUTSCH im Kurs: %s"
                          % (len(deutsch), ", ".join(deutsch[:8]) + (" …" if len(deutsch) > 8 else "")))
        return "warnung", "%d neu, %d bleiben deutsch" % (neu, len(deutsch))
    return "fertig", ("%d neu erstellt" % neu) if neu else "alle schon vorhanden"


def _ausgabeordner(a, arbeit):
    vo = a.angaben.get("videoordner") or ""
    if os.path.basename(vo.rstrip("\\/")).lower() == "videos":
        return os.path.join(os.path.dirname(vo.rstrip("\\/")), "Kurs")
    return os.path.join(arbeit, "ergebnis")


def _bauen(a, arbeit, code):
    ordner = _ausgabeordner(a, arbeit)
    os.makedirs(ordner, exist_ok=True)
    ziel = os.path.join(ordner, "sicherung-%s.mbz" % a.angaben["kurzname"].lower())
    stempel = time.strftime("%Y%m%d-%H%M%S")
    for alt in (ziel, ziel[:-4] + "_klein.mbz"):
        if os.path.exists(alt):
            neu = alt[:-4] + "_vorher_%s.mbz" % stempel
            os.replace(alt, neu)
            a.melde("Vorherige Sicherung umbenannt: %s" % os.path.basename(neu))
    argumente = [arbeit, code, ziel, "--kursname", a.angaben["kursname"], "--kurzname", a.angaben["kurzname"]]
    if a.angaben.get("quizid"):
        argumente += ["--quizid", str(a.angaben["quizid"])]
    _skript(a, "kurs_bauen.py", *argumente)
    return ziel


def _moodle_probe(a):
    """Die Datei, die hochgeladen werden soll, einmal echt in Moodle einspielen."""
    from . import moodleprobe
    if not a.angaben.get("moodleprobe", True):
        a.schritt("moodle", "uebersprungen", "abgeschaltet")
        return
    if not moodleprobe.bereit():
        a.schritt("moodle", "uebersprungen", "Moodle-Prüfung nicht eingerichtet (Zahnrad)")
        return
    datei = next((e for e in a.ergebnisse if e.get("empfohlen")), a.ergebnisse[-1])
    a.schritt("moodle", "laeuft")
    a.melde("$ Probe-Einspielung in Moodle: %s" % datei["name"])
    zustand, info, protokoll = moodleprobe.pruefen(datei["datei"])
    if zustand in ("fehler", "warnung"):
        a.melde(protokoll)
    if zustand == "fehler":
        a.hinweise.append("Moodle hat die Sicherung bei der Probe-Einspielung abgelehnt – bitte das Protokoll "
                          "ansehen, bevor die Datei hochgeladen wird.")
    a.schritt("moodle", zustand, info)
    a.melde("  " + info)


# ------------------------------------------------------------ Gesamtablauf

def ausfuehren(a):
    code = a.angaben["code"]
    arbeit = a.angaben["arbeit"]
    a.zustand = "laeuft"
    aktuell = None
    try:
        if not skill_ordner():
            raise RuntimeError("Skill moodle-kurs-uebersetzen nicht gefunden.")

        aktuell = "einlesen"
        a.schritt(aktuell, "laeuft")
        kurs = _einlesen(a, arbeit)
        a.schritt(aktuell, "fertig", "%d Videos, %d Aktivitäten" % (len(kurs["videos"]), len(kurs["aktivitaeten"])))

        aktuell = "videos_suchen"
        a.schritt(aktuell, "laeuft")
        fehlend = _videos_suchen(a, arbeit, kurs, code)
        a.schritt(aktuell, "fertig", "%d gefunden, %d fehlen" % (len(kurs["videos"]) - len(fehlend), len(fehlend)))

        aktuell = "texte"
        a.schritt(aktuell, "laeuft")
        _texte(a, arbeit, kurs, code)
        a.schritt(aktuell, "fertig", "%d Texte" % a.zahlen.get("texte", 0))

        aktuell = "videos"
        a.schritt(aktuell, "laeuft")
        a.schritt(aktuell, *_videos(a, arbeit, kurs, code, fehlend))
        a.pruefe_abbruch()

        aktuell = "bauen"
        a.schritt(aktuell, "laeuft")
        ziel = _bauen(a, arbeit, code)
        mb = os.path.getsize(ziel) / 1e6
        a.ergebnisse.append({"datei": ziel, "name": os.path.basename(ziel), "mb": round(mb)})
        a.schritt(aktuell, "fertig", "%.0f MB" % mb)

        aktuell = "pruefen"
        a.schritt(aktuell, "laeuft")
        rc = _skript(a, "pruefen.py", ziel, arbeit, erlaubt=(0, 1))
        a.schritt(aktuell, "fertig" if rc == 0 else "warnung", "sauber" if rc == 0 else "Probleme – siehe Protokoll")

        aktuell = "klein"
        if mb > GRENZE_MB and a.angaben.get("klein", True) and verkleinern_skript():
            a.schritt(aktuell, "laeuft")
            # verkleinern.py nimmt vorhandene Kleinfassungen der Videos ungeprueft: immer frisch
            shutil.rmtree(os.path.join(arbeit, "videos_%s_klein" % code), ignore_errors=True)
            befehl = python_befehl(verkleinern_skript()) + [arbeit, code, ziel,
                      "--kursname", a.angaben["kursname"], "--kurzname", a.angaben["kurzname"]]
            a.melde("$ verkleinern.py (dauert einige Minuten)")
            r = subprocess.run(befehl, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               env=dict(os.environ, SKILL_ORDNER=skill_ordner()))
            a.melde(r.stdout + r.stderr)
            klein = ziel[:-4] + "_klein.mbz"
            if r.returncode == 0 and os.path.exists(klein):
                kmb = os.path.getsize(klein) / 1e6
                a.ergebnisse.append({"datei": klein, "name": os.path.basename(klein), "mb": round(kmb),
                                     "empfohlen": True})
                _skript(a, "pruefen.py", klein, arbeit, erlaubt=(0, 1))
                a.schritt(aktuell, "fertig", "%.0f MB" % kmb)
            else:
                a.schritt(aktuell, "warnung", "nicht gelungen – siehe Protokoll")
        else:
            a.schritt(aktuell, "uebersprungen", "nicht nötig" if mb <= GRENZE_MB else "abgeschaltet")

        aktuell = "moodle"
        _moodle_probe(a)
        a.zustand = "fertig"
        a.melde("\nFERTIG.")
    except Abbruch:
        a.zustand = "abgebrochen"
        if aktuell:
            a.schritt(aktuell, "fehler", "abgebrochen")
        a.melde("Abgebrochen. Bereits Erledigtes bleibt im Arbeitsordner und wird beim nächsten Mal genutzt.")
    except Exception as e:  # alles, was schiefgeht, landet lesbar in der Oberflaeche
        a.zustand = "fehler"
        a.fehler = str(e) or e.__class__.__name__
        if aktuell:
            a.schritt(aktuell, "fehler", "")
        a.melde("FEHLER: %s" % a.fehler)
        a.melde(traceback.format_exc())
    finally:
        a.ende = time.time()


class Warteschlange:
    """Ein Auftrag nach dem anderen – Videos bauen lastet den Rechner voll aus."""

    def __init__(self):
        self.auftraege = {}
        self._q = queue.Queue()
        threading.Thread(target=self._lauf, daemon=True).start()

    def _lauf(self):
        while True:
            a = self._q.get()
            if not a.abbrechen:
                ausfuehren(a)
            else:
                a.zustand = "abgebrochen"

    def neu(self, **angaben):
        a = Auftrag(**angaben)
        self.auftraege[a.id] = a
        self._q.put(a)
        return a
