"""Pfade zwischen Windows und Container umsetzen.

Im Container ist ein Windows-Ordner (z. B. die Sicherheitsbelehrungen) unter /daten
eingehaengt. Die Lehrkraft gibt aber den Pfad ein, den sie im Explorer sieht. Diese
Abbildung setzt ihn um. Ausserhalb des Containers (Start per Doppelklick) bleibt der
Pfad, wie er ist.
"""
import os
from dataclasses import dataclass


def _vergleich(p):
    return p.replace("\\", "/").rstrip("/").lower()


@dataclass
class Abbildung:
    host: str   # Windows-Pfad der Freigabe, leer = keine Abbildung
    lokal: str  # wo die Freigabe im Container liegt

    @classmethod
    def aus_umgebung(cls):
        return cls(host=os.environ.get("DATEN_HOST", ""), lokal=os.environ.get("DATEN_LOKAL", ""))

    @property
    def aktiv(self):
        return bool(self.host and self.lokal)

    def zu_lokal(self, pfad):
        if not self.aktiv:
            return pfad
        p = pfad.strip().replace("\\", "/")
        if p.startswith(self.lokal):
            return p
        basis = _vergleich(self.host)
        if _vergleich(p) == basis:
            return self.lokal
        if _vergleich(p).startswith(basis + "/"):
            return self.lokal + p[len(basis):].rstrip("/")
        raise ValueError("Der Ordner liegt außerhalb der Freigabe %s" % self.host)

    def zu_host(self, pfad):
        if not self.aktiv or not pfad.startswith(self.lokal):
            return pfad
        return self.host.rstrip("\\/") + pfad[len(self.lokal):].replace("/", "\\")
