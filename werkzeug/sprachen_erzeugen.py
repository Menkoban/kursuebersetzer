"""Erzeugt app/sprachen_daten.json: alle Sprachen von Google Uebersetzer mit deutschem Namen,
Eigenname, HeyGen-Name und passenden Microsoft-Stimmen.

Quelle der Sprachliste: https://cloud.google.com/translate/docs/languages (Tabelle "NMT"),
gespeichert als google_sprachen.json [[englischer Name, Google-Code], ...].
Braucht einmalig: pip install babel edge-tts  (zur Laufzeit der App nicht noetig).

Aufruf:  python werkzeug/sprachen_erzeugen.py <google_sprachen.json>
"""
import asyncio
import json
import os
import sys

from babel import Locale, UnknownLocaleError

HIER = os.path.dirname(os.path.abspath(__file__))
ZIEL = os.path.join(HIER, "..", "app", "sprachen_daten.json")

# Google-Code -> App-Kuerzel, wo die Ordnerregel des Projekts etwas anderes sagt
# (PA ist im Projekt Paschtu, bei Google heisst pa Panjabi).
KUERZEL = {"ps": "pa", "pa": "pa-in", "pa-Arab": "pa-pk", "zh-CN": "zh", "iw": "he", "jw": "jv"}
WEGLASSEN = {"fr-FR"}  # doppelt zu "fr"
NAMEN = {
    "zh-CN": "Chinesisch (vereinfacht)", "zh-TW": "Chinesisch (traditionell)", "ps": "Paschtu",
    "pa": "Panjabi (Gurmukhi)", "pa-Arab": "Panjabi (Shahmukhi)", "ms-Arab": "Malaiisch (Jawi)",
    "mni-Mtei": "Meitei (Manipuri)", "fa": "Persisch (Farsi)", "ku": "Kurdisch (Kurmandschi)",
    "ckb": "Kurdisch (Sorani)", "hmn": "Hmong", "yue": "Kantonesisch", "fr-CA": "Französisch (Kanada)",
    "pt": "Portugiesisch", "pt-PT": "Portugiesisch (Portugal)", "pt-BR": "Portugiesisch (Brasilien)",
    "ny": "Chichewa", "iw": "Hebräisch", "ht": "Haitianisch", "rom": "Romani", "crs": "Seychellen-Kreolisch",
}
# Edge-Stimmen heissen bei manchen Sprachen anders als bei Google
STIMMSPRACHE = {"iw": "he", "jw": "jv", "no": "nb"}
# von Hand gewaehlt und erprobt – bleiben
FEST = {
    "en": ("en-GB-RyanNeural", "en-GB-SoniaNeural"), "fr": ("fr-FR-HenriNeural", "fr-FR-DeniseNeural"),
    "uk": ("uk-UA-OstapNeural", "uk-UA-PolinaNeural"), "es": ("es-ES-AlvaroNeural", "es-ES-ElviraNeural"),
    "ar": ("ar-SA-HamedNeural", "ar-SA-ZariyahNeural"), "ru": ("ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"),
    "ro": ("ro-RO-EmilNeural", "ro-RO-AlinaNeural"), "tr": ("tr-TR-AhmetNeural", "tr-TR-EmelNeural"),
    "ps": ("ps-AF-GulNawazNeural", "ps-AF-LatifaNeural"), "fa": ("fa-IR-FaridNeural", "fa-IR-DilaraNeural"),
    "pl": ("pl-PL-MarekNeural", "pl-PL-ZofiaNeural"), "it": ("it-IT-DiegoNeural", "it-IT-ElsaNeural"),
    "sq": ("sq-AL-IlirNeural", "sq-AL-AnilaNeural"), "so": ("so-SO-MuuseNeural", "so-SO-UbaxNeural"),
    "zh-CN": ("zh-CN-YunxiNeural", "zh-CN-XiaoxiaoNeural"), "yue": ("zh-HK-WanLungNeural", "zh-HK-HiuGaaiNeural"), "de": ("de-DE-ConradNeural", "de-DE-KatjaNeural"),
}


def _locale(code):
    try:
        return Locale.parse(code.replace("-", "_"))
    except (UnknownLocaleError, ValueError):
        return None


def deutscher_name(code, englisch):
    if code in NAMEN:
        return NAMEN[code]
    loc = _locale(code)
    if loc and loc.get_display_name("de"):
        return loc.get_display_name("de")
    return Locale("de").languages.get(code.split("-")[0]) or englisch


EIGEN = {"zh-CN": "简体中文", "zh-TW": "繁體中文", "iw": "עברית", "yue": "粵語"}
# Schriftvarianten: eine Microsoft-Stimme der Grundsprache liest diese Schrift nicht
OHNE_STIMME = {"ms-Arab", "pa-Arab", "mni-Mtei"}


def eigenname(code, englisch):
    if code in EIGEN:
        return EIGEN[code]
    loc = _locale(code)
    try:
        n = loc.get_display_name(loc) if loc else None
    except Exception:
        n = None
    return (n[0].upper() + n[1:]) if n else englisch


def stimmen_waehlen(code, alle):
    if code in OHNE_STIMME:
        return None
    if code in FEST:
        return {"m": FEST[code][0], "w": FEST[code][1]}
    basis = STIMMSPRACHE.get(code.split("-")[0], code.split("-")[0]).lower()
    region = code.split("-")[1].upper() if "-" in code and len(code.split("-")[1]) == 2 else ""
    passend = [v for v in alle if v["Locale"].split("-")[0].lower() == basis and "Multilingual" not in v["ShortName"]]
    if region:
        genau = [v for v in passend if v["Locale"].split("-")[1].upper() == region]
        passend = genau or passend
    else:
        heimat = [v for v in passend if v["Locale"].split("-")[1].upper() == basis.upper()]
        passend = heimat or passend
    if not passend:
        return None
    passend.sort(key=lambda v: v["Locale"])
    land = passend[0]["Locale"]                      # alle Stimmen aus einem Land
    passend = [v for v in passend if v["Locale"] == land]
    m = next((v["ShortName"] for v in passend if v["Gender"] == "Male"), None)
    w = next((v["ShortName"] for v in passend if v["Gender"] == "Female"), None)
    return {"m": m or w, "w": w or m}


def main(quelle):
    import edge_tts
    alle = asyncio.run(edge_tts.list_voices())
    liste = json.load(open(quelle, encoding="utf-8"))
    daten = {}
    for englisch, code in liste:
        if code in WEGLASSEN:
            continue
        kuerzel = KUERZEL.get(code, code).lower()
        daten[kuerzel] = {"google": code, "name": deutscher_name(code, englisch),
                          "eigen": eigenname(code, englisch), "heygen": englisch,
                          "stimmen": stimmen_waehlen(code, alle)}
    with open(ZIEL, "w", encoding="utf-8") as fh:
        json.dump(daten, fh, ensure_ascii=False, indent=1, sort_keys=True)
    mit = sum(1 for d in daten.values() if d["stimmen"])
    print("%d Sprachen, davon %d mit Microsoft-Stimme -> %s" % (len(daten), mit, os.path.normpath(ZIEL)))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
