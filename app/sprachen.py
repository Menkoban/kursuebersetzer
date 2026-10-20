"""Zielsprachen: alle Sprachen von Google Uebersetzer (siehe werkzeug/sprachen_erzeugen.py).

Das Kuerzel ist das der Ordnerregel (FR, UK, PA ...), nicht zwingend der Google-Code:
Paschtu heisst im Projekt PA (Google: ps), Panjabi deshalb PA-IN (Google: pa).
Je Sprache: deutscher Name, Eigenname, HeyGen-Name (englisch) und – wo Microsoft eine
hat – je eine maennliche und weibliche Stimme, sonst stimmen = None.
"""
import json
import os
import unicodedata

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sprachen_daten.json"), encoding="utf-8") as _fh:
    SPRACHEN = json.load(_fh)


def sortierschluessel(name):
    """Alphabetisch wie im Woerterbuch: Ä wie A, Groß/klein egal."""
    ohne = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in ohne if not unicodedata.combining(ch)).casefold()


def fuer_oberflaeche():
    liste = [{"code": c, "name": s["name"], "eigen": s["eigen"], "stimme": bool(s["stimmen"])}
             for c, s in SPRACHEN.items()]
    return sorted(liste, key=lambda s: sortierschluessel(s["name"]))
