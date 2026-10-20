"""Texte mit einem Sprachmodell uebersetzen (Anbieter frei waehlbar, siehe ki.py).

Ersetzt den Schritt, den im Skill Claude selbst erledigt: die leeren Zielfelder in
uebersetzung_<code>.json und sprechtexte_<code>.json ausfuellen. Die Texte gehen
nummeriert in Paketen hinaus, die Antwort kommt als JSON mit fester Form zurueck.
"""
import json

from . import ki as kimodul

SYSTEM = (
    "Du übersetzt einen Moodle-Kurs (Sicherheitsunterweisung an einer berufsbildenden Schule) "
    "aus dem Deutschen in diese Sprache: {sprache}. Zielgruppe sind Lernende mit geringen Sprachkenntnissen.\n"
    "- Einfache, kurze Sätze, direkte Anrede (du-Form der Zielsprache), keine Schachtelsätze.\n"
    "- Sicherheitsaussagen exakt erhalten: Verbote, nie/immer, Schutzausrüstung, Gerätenamen, "
    "Zahlen. Nichts weglassen, nichts hinzufügen.\n"
    "- HTML-Tags, Attribute, Farb-Styles, Links und Platzhalter wie $@...@$ oder {{...}} "
    "unverändert übernehmen; nur den sichtbaren Text übersetzen.\n"
    "- Eigennamen von Personen, Schulen und Marken nicht übersetzen.\n"
    "- Gib jede Nummer genau einmal zurück."
)
SYSTEM_SPRECHTEXT = (
    "\n- Die Texte sind Sprechtexte für eine Sprachausgabe: ausgeschriebene Zahlen und Einheiten, "
    "keine Emojis, keine Aufzählungszeichen."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "uebersetzungen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"nr": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["nr", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["uebersetzungen"],
    "additionalProperties": False,
}


def _pakete(eintraege, groesse, zeichen=12000):
    paket, laenge = [], 0
    for e in eintraege:
        if paket and (len(paket) >= groesse or laenge + len(e["text"]) > zeichen):
            yield paket
            paket, laenge = [], 0
        paket.append(e)
        laenge += len(e["text"])
    if paket:
        yield paket


def _frage(k, paket, sprache, sprechtext):
    system = SYSTEM.format(sprache=sprache) + (SYSTEM_SPRECHTEXT if sprechtext else "")
    nutzer = "Übersetze jeden Eintrag in diese Sprache: %s.\n\n%s" % (sprache, json.dumps(paket, ensure_ascii=False))
    antwort = k.frage_json(system, nutzer, SCHEMA)
    try:
        return {int(u["nr"]): u["text"] for u in antwort["uebersetzungen"]}
    except (KeyError, TypeError, ValueError):
        raise kimodul.Antwortfehler("Antwort hat nicht die erwartete Form.")


def uebersetze_texte(vorlage, sprache, ki=None, ki_konfig=None, client=None, paketgroesse=40,
                     sprechtext=False, melde=print, zwischenspeichern=None):
    """{deutsch: ziel} -> dieselbe Abbildung, leere Ziele ausgefuellt. Vorhandenes bleibt.

    ki: fertiger Anbieter (siehe ki.py); sonst wird er aus ki_konfig gebaut.
    """
    k = ki or kimodul.erstelle(ki_konfig or {}, client=client)
    ergebnis = dict(vorlage)
    offen = [{"nr": i, "text": k} for i, (k, v) in enumerate(vorlage.items()) if not v]
    schluessel = {e["nr"]: e["text"] for e in offen}
    pakete = list(_pakete(offen, paketgroesse))
    for i, paket in enumerate(pakete, 1):
        try:
            antworten = _frage(k, paket, sprache, sprechtext)
        except kimodul.Antwortfehler:
            if len(paket) == 1:
                raise
            antworten = {}
            for haelfte in (paket[: len(paket) // 2], paket[len(paket) // 2:]):
                antworten.update(_frage(k, haelfte, sprache, sprechtext))
        for nr, text in antworten.items():
            if nr in schluessel and text.strip():
                ergebnis[schluessel[nr]] = text
        if zwischenspeichern:
            zwischenspeichern(ergebnis)
        melde("Paket %d/%d übersetzt (%d Texte)" % (i, len(pakete), len(paket)))
    return ergebnis
