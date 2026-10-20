"""Welche Kursvideos liegen in der Zielsprache schon fertig vor?

Die Videos in <Bereich>/<SPR>/Videos heissen nach dem Thema des Hotspots
(Fritteuse_FR.mp4), die Videos in der Sicherung nach H5P-Muster (sources-68db....mp4).
Die Bruecke ist die Hotspot-Beschriftung im H5P-Rundgang. Vergleichsregel wie in
01_Werkzeug/kursstand/kursstand.py, damit App und Kursuebersicht dasselbe zaehlen.
"""
import html
import json
import os
import re
import tarfile
import unicodedata

_KUERZEL = "de|ar|ru|ro|tr|pa|en|ra|ae|fr|uk|es|fa|pl|it|sq|so"
_RE_KUERZEL = re.compile(rf"(?i)_+\s*(?:{_KUERZEL})(?=$|[^a-z])|\s+(?:{_KUERZEL})$")
_RE_KOPIE = re.compile(r"\(\d+\)")


def normalisiere(name):
    """Dateiname oder Thema -> Vergleichsschluessel (ohne Endung, Kuerzel, (1), Umlaute)."""
    s = name.strip()
    if s.lower().endswith(".mp4"):
        s = s[:-4]
    s = _RE_KOPIE.sub(" ", s).strip()
    s = _RE_KUERZEL.sub("", s.strip())
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if ch.isascii() and ch.isalnum())


def _sauber(label):
    t = html.unescape(label or "").replace("\xad", "")
    t = re.sub(r"<[^>]+>", "", t)
    t = "".join(ch for ch in t if ch.isalnum() or ch in " -:()&/,.")
    return re.sub(r"\s+", " ", t).strip(" :")


def hotspots_aus_mbz(mbz):
    """Videodateiname (sources-....mp4) -> Hotspot-Beschriftung."""
    zuordnung = {}
    with tarfile.open(mbz, "r:gz") as tar:
        for m in tar:
            if not re.match(r"activities/hvp_\d+/hvp\.xml$", m.name):
                continue
            xml = tar.extractfile(m).read().decode("utf-8")
            treffer = re.search(r"<json_content>(.*?)</json_content>", xml, re.S)
            if not treffer:
                continue
            daten = json.loads(html.unescape(treffer.group(1)))
            for szene in daten.get("threeImage", {}).get("scenes", []):
                for it in szene.get("interactions", []):
                    label = it.get("labelSettings", {}).get("labelText") or it.get("labelText") or ""
                    params = it.get("action", {}).get("params", {})
                    for quelle in params.get("sources", []) if isinstance(params, dict) else []:
                        datei = (quelle.get("path") or "").split("#")[0].rsplit("/", 1)[-1]
                        if datei:
                            zuordnung.setdefault(datei, _sauber(label))
    return zuordnung


def fertige_videos(videos, ordner, mehrdeutig=None):
    """Kursvideo (Feld "datei") -> Pfad des fertigen Videos im Ordner. Jedes zaehlt einmal.

    Tragen zwei Kursvideos dasselbe Thema, wird nicht geraten: die Themen landen in
    `mehrdeutig` und die Videos gelten als fehlend (ausser der Dateiname passt eindeutig).
    """
    if not ordner or not os.path.isdir(ordner):
        return {}
    anzahl = {}
    for v in videos:
        k = normalisiere(v.get("thema", "")) if v.get("thema") else ""
        anzahl[k] = anzahl.get(k, 0) + 1
    doppelt = {k for k, n in anzahl.items() if k and n > 1}
    if mehrdeutig is not None:
        mehrdeutig.extend(sorted({v["thema"] for v in videos
                                  if v.get("thema") and normalisiere(v["thema"]) in doppelt}))
    dateien = sorted((f for f in os.listdir(ordner) if f.lower().endswith(".mp4")), key=str.lower)
    nach_schluessel = {}
    for f in dateien:
        nach_schluessel.setdefault(normalisiere(f), []).append(f)
    treffer, vergeben = {}, set()
    for v in videos:
        for kandidat in (v.get("thema", ""), os.path.splitext(v["dateiname"])[0]):
            k = normalisiere(kandidat) if kandidat else ""
            if k in doppelt:
                continue
            frei = [f for f in nach_schluessel.get(k, []) if f not in vergeben] if k else []
            if frei:
                vergeben.add(frei[0])
                treffer[v["datei"]] = os.path.join(ordner, frei[0])
                break
    return treffer


def zielname(thema, code, datei):
    """Dateiname fuer ein neu erzeugtes Video im Sprachordner: <Thema>_<SPR>.mp4."""
    basis = _sauber(thema).replace(":", "").replace("/", "-") if thema else os.path.splitext(datei)[0]
    basis = re.sub(r"\s+", " ", basis).strip()
    return "%s_%s.mp4" % (basis, code.upper())
