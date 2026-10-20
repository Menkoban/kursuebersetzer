"""Sprechtexte vorlesen lassen – zwei Wege mit denselben Microsoft-Stimmen.

- edge:  Vorlese-Dienst des Edge-Browsers ueber die Bibliothek edge-tts. Kostenlos, ohne
         Konto – aber von Microsoft nicht offiziell fuer andere Programme freigegeben und
         gelegentlich gesperrt (zuletzt Fehler 403 im Oktober 2026).
- azure: Azure AI Speech mit eigenem Schluessel der Schule. Offiziell, Rechenzentrum in
         der EU waehlbar (z. B. germanywestcentral), kostenloses Kontingent je Monat.
"""
import os
from xml.sax.saxutils import escape


class VorleseFehler(Exception):
    pass


def edge_sprechen(text, stimme, ziel, tempo=None):
    import asyncio
    import edge_tts
    asyncio.run(edge_tts.Communicate(text, stimme, rate=tempo or "+0%").save(ziel))


def azure_sprechen(text, stimme, ziel, schluessel, region, tempo=None, sitzung=None):
    if sitzung is None:
        import requests
        sitzung = requests
    sprache = "-".join(stimme.split("-")[:2])
    ssml = ("<speak version='1.0' xml:lang='%s'><voice name='%s'><prosody rate='%s'>%s</prosody>"
            "</voice></speak>" % (sprache, stimme, tempo or "+0%", escape(text)))
    try:
        r = sitzung.post("https://%s.tts.speech.microsoft.com/cognitiveservices/v1" % region.strip(),
                         data=ssml.encode("utf-8"), timeout=120, headers={
                             "Ocp-Apim-Subscription-Key": schluessel,
                             "Content-Type": "application/ssml+xml",
                             "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                             "User-Agent": "Kursuebersetzer"})
    except Exception as e:  # Netzfehler jeder Art
        raise VorleseFehler("Keine Verbindung zu Azure Speech (%s)." % e.__class__.__name__)
    if r.status_code in (401, 403):
        raise VorleseFehler("Azure Speech nimmt den Schlüssel nicht an – Schlüssel und Region im Zahnrad prüfen.")
    if r.status_code == 429:
        raise VorleseFehler("Azure Speech: Kontingent erschöpft oder zu viele Anfragen – später erneut starten.")
    if r.status_code == 400:
        raise VorleseFehler("Azure Speech kennt die Stimme %s nicht oder der Text ist ungültig." % stimme)
    if r.status_code != 200 or not r.content:
        raise VorleseFehler("Azure Speech antwortet mit Fehler %d." % r.status_code)
    with open(ziel, "wb") as fh:
        fh.write(r.content)


def sprechen(text, stimme, ziel, tempo=None, dienst=None):
    dienst = dienst or {}
    if dienst.get("art") == "azure":
        if not (dienst.get("schluessel") and dienst.get("region")):
            raise VorleseFehler("Für Azure Speech fehlen Schlüssel oder Region (Zahnrad).")
        azure_sprechen(text, stimme, ziel, dienst["schluessel"], dienst["region"], tempo=tempo)
    else:
        edge_sprechen(text, stimme, ziel, tempo=tempo)
    if not os.path.exists(ziel):
        raise VorleseFehler("Keine Tonaufnahme entstanden.")
