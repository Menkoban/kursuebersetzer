"""Tests der App-Bausteine, die ohne Netz und ohne echte Sicherung laufen."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import pfade, sprachen, uebersetzer, zuordnung  # noqa: E402


# ------------------------------------------------------------ Zuordnung Videos

def test_normalisiere_entfernt_kuerzel_umlaute_und_kopiezaehler():
    assert zuordnung.normalisiere("Bügeleisen_FR (1).mp4") == "buegeleisen"
    assert zuordnung.normalisiere("Start: Maschinenraum") == "startmaschinenraum"


def test_fertiges_video_wird_ueber_hotspot_namen_gefunden(tmp_path):
    (tmp_path / "Fritteuse_FR.mp4").write_bytes(b"x")
    (tmp_path / "Wasserkocher_FR.mp4").write_bytes(b"x")
    videos = [{"datei": "01_sources-a.mp4", "dateiname": "sources-a.mp4", "thema": "Fritteuse"},
              {"datei": "02_sources-b.mp4", "dateiname": "sources-b.mp4", "thema": "Mikrowelle"}]
    treffer = zuordnung.fertige_videos(videos, str(tmp_path))
    assert treffer == {"01_sources-a.mp4": str(tmp_path / "Fritteuse_FR.mp4")}


def test_fertiges_video_auch_ueber_originalen_dateinamen(tmp_path):
    (tmp_path / "sources-b.mp4").write_bytes(b"x")
    videos = [{"datei": "02_sources-b.mp4", "dateiname": "sources-b.mp4", "thema": ""}]
    assert zuordnung.fertige_videos(videos, str(tmp_path)) == {
        "02_sources-b.mp4": str(tmp_path / "sources-b.mp4")}


def test_ein_fertiges_video_wird_nicht_zwei_kursvideos_zugeordnet(tmp_path):
    (tmp_path / "Demo_FR.mp4").write_bytes(b"x")
    videos = [{"datei": "01_a.mp4", "dateiname": "a.mp4", "thema": "Demo"},
              {"datei": "02_b.mp4", "dateiname": "Demo.mp4", "thema": "Demo 2"}]
    assert zuordnung.fertige_videos(videos, str(tmp_path)) == {"01_a.mp4": str(tmp_path / "Demo_FR.mp4")}


def test_zielname_fuer_neue_videos_folgt_der_ordnerregel():
    assert zuordnung.zielname("Start: Maschinenraum", "fr", "01_x.mp4") == "Start Maschinenraum_FR.mp4"
    assert zuordnung.zielname("", "uk", "07_sources-ab.mp4") == "07_sources-ab_UK.mp4"


# ------------------------------------------------------------ Pfade (Container)

def test_windowspfad_wird_im_container_auf_daten_umgesetzt():
    abb = pfade.Abbildung(host=r"C:\Users\User\Sicherheitsbelehrungen", lokal="/daten")
    assert abb.zu_lokal(r"C:\Users\User\Sicherheitsbelehrungen\10_Hauswirtschaft\FR\Videos") \
        == "/daten/10_Hauswirtschaft/FR/Videos"
    assert abb.zu_lokal("c:/users/user/sicherheitsbelehrungen/AR") == "/daten/AR"


def test_ohne_abbildung_bleibt_der_pfad_wie_er_ist():
    abb = pfade.Abbildung(host="", lokal="")
    assert abb.zu_lokal(r"D:\Kurse\Videos") == r"D:\Kurse\Videos"


def test_pfad_ausserhalb_der_freigabe_wird_im_container_abgelehnt():
    abb = pfade.Abbildung(host=r"C:\Kurse", lokal="/daten")
    with pytest.raises(ValueError):
        abb.zu_lokal(r"D:\Anderswo\Videos")


# ------------------------------------------------------------ Sprachen und Stimmen

def test_stimmen_wenn_vorhanden_aus_derselben_sprache():
    for code, s in sprachen.SPRACHEN.items():
        assert s["heygen"], code
        if s["stimmen"]:
            assert s["stimmen"]["m"][:2] == s["stimmen"]["w"][:2], code


def test_paschtu_nutzt_den_projektcode_pa_aber_die_stimme_ps():
    assert sprachen.SPRACHEN["pa"]["name"] == "Paschtu"
    assert sprachen.SPRACHEN["pa"]["stimmen"]["m"] == "ps-AF-GulNawazNeural"


def test_alle_sprachen_von_google_uebersetzer_sind_waehlbar():
    # Stand der Google-Liste am 19.10.2026: 194 Eintraege, ohne die doppelte Variante fr-FR
    assert len(sprachen.SPRACHEN) >= 190
    namen = {s["name"] for s in sprachen.SPRACHEN.values()}
    for erwartet in ("Chinesisch (vereinfacht)", "Tigrinya", "Panjabi", "Kurdisch", "Somali", "Kantonesisch"):
        assert any(n.startswith(erwartet) for n in namen), erwartet


def test_dropdown_ist_alphabetisch_nach_deutschem_namen():
    liste = [s["name"] for s in sprachen.fuer_oberflaeche()]
    assert liste == sorted(liste, key=sprachen.sortierschluessel)
    assert liste.index("Ukrainisch") < liste.index("Ungarisch")


def test_kuerzel_eindeutig_und_als_dateiname_brauchbar():
    import re
    for code in sprachen.SPRACHEN:
        assert re.fullmatch(r"[a-z]{2,3}(-[a-z]{2,4})?", code), code


def test_chinesisch_hat_microsoft_stimme_abchasisch_nicht():
    assert sprachen.SPRACHEN["zh"]["stimmen"]["w"].startswith("zh-CN-")
    assert sprachen.SPRACHEN["ab"]["stimmen"] is None


# ------------------------------------------------------------ Uebersetzung mit Haiku

class _FalscherClient:
    """Antwortet wie die API: JSON mit nummerierten Uebersetzungen."""

    def __init__(self):
        self.aufrufe = 0
        self.messages = self

    def create(self, **kw):
        self.aufrufe += 1
        auftrag = json.loads(kw["messages"][0]["content"].split("\n\n", 1)[1])
        antwort = {"uebersetzungen": [{"nr": t["nr"], "text": "FR:" + t["text"]} for t in auftrag]}

        class Block:
            type = "text"
            text = json.dumps(antwort)

        class Antwort:
            content = [Block()]
            stop_reason = "end_turn"
        return Antwort()


def test_uebersetzen_fuellt_nur_leere_felder_und_teilt_in_pakete():
    vorlage = {"Hallo": "", "Schon da": "Déjà là", "<p>Achtung</p>": ""}
    client = _FalscherClient()
    ergebnis = uebersetzer.uebersetze_texte(vorlage, "Französisch", client=client, paketgroesse=1)
    assert ergebnis == {"Hallo": "FR:Hallo", "Schon da": "Déjà là", "<p>Achtung</p>": "FR:<p>Achtung</p>"}
    assert client.aufrufe == 2


# ------------------------------------------------------------ Videoordner der Lehrkraft

def test_neues_video_ueberschreibt_nie_ein_vorhandenes(tmp_path):
    from app import ablauf
    neu = tmp_path / "neu.mp4"
    neu.write_bytes(b"NEU")
    ordner = tmp_path / "FR" / "Videos"
    ordner.mkdir(parents=True)
    (ordner / "Fritteuse_FR.mp4").write_bytes(b"ALT")
    a = ablauf.Auftrag(code="fr")
    ablauf._kopiere_neu(str(neu), str(ordner), "Fritteuse_FR.mp4", a)
    ablauf._kopiere_neu(str(neu), str(ordner), "Mikrowelle_FR.mp4", a)
    assert (ordner / "Fritteuse_FR.mp4").read_bytes() == b"ALT"
    assert (ordner / "Mikrowelle_FR.mp4").read_bytes() == b"NEU"
    assert sorted(p.name for p in ordner.iterdir()) == ["Fritteuse_FR.mp4", "Mikrowelle_FR.mp4"]


def test_doppeltes_thema_wird_nicht_geraten_sondern_gemeldet(tmp_path):
    (tmp_path / "Fritteuse_FR.mp4").write_bytes(b"x")
    (tmp_path / "Fritteuse_FR (1).mp4").write_bytes(b"x")
    videos = [{"datei": "01_a.mp4", "dateiname": "a.mp4", "thema": "Fritteuse"},
              {"datei": "02_b.mp4", "dateiname": "b.mp4", "thema": "Fritteuse"}]
    mehrdeutig = []
    assert zuordnung.fertige_videos(videos, str(tmp_path), mehrdeutig=mehrdeutig) == {}
    assert mehrdeutig == ["Fritteuse"]


# ------------------------------------------------------------ Zwischenspeicher videos_<code>

def _vz(tmp_path, dateien):
    vz = tmp_path / "videos_fr"
    vz.mkdir()
    for d in dateien:
        (vz / d).write_bytes(b"v")
    return vz


def test_aufraeumen_entfernt_unbekannte_und_vom_nutzer_entfernte_videos(tmp_path):
    from app import ablauf
    vz = _vz(tmp_path, ["01.mp4", "02.mp4", "03.mp4", "04.mp4"])
    herkunft = {"01.mp4": {"quelle": "ordner"},              # Nutzer hat es inzwischen geloescht
                "02.mp4": {"quelle": "edge", "stimme": "auto", "tempo": ""},
                "03.mp4": {"quelle": "heygen"}}             # 04.mp4: halbe Datei ohne Vermerk
    geblieben = ablauf.zwischenspeicher_aufraeumen(str(vz), herkunft, modus="edge", stimme="auto", tempo="")
    assert sorted(p.name for p in vz.iterdir()) == ["02.mp4", "03.mp4"]
    assert sorted(geblieben) == ["02.mp4", "03.mp4"]


def test_aufraeumen_baut_neu_wenn_stimme_oder_weg_gewechselt(tmp_path):
    from app import ablauf
    vz = _vz(tmp_path, ["02.mp4", "05.mp4"])
    herkunft = {"02.mp4": {"quelle": "edge", "stimme": "auto", "tempo": ""},
                "05.mp4": {"quelle": "edge", "stimme": "w", "tempo": ""}}
    ablauf.zwischenspeicher_aufraeumen(str(vz), herkunft, modus="edge", stimme="m", tempo="")
    assert list(vz.iterdir()) == []
    (tmp_path / "zwei").mkdir()
    vz2 = _vz(tmp_path / "zwei", ["06.mp4"])
    ablauf.zwischenspeicher_aufraeumen(str(vz2), {"06.mp4": {"quelle": "edge", "stimme": "m", "tempo": ""}},
                                       modus="heygen", stimme="auto", tempo="")
    assert list(vz2.iterdir()) == []


def test_kurzname_folgt_der_schreibweise_des_originals():
    from app import ablauf
    assert ablauf._kurzname("SB_ML_DE", "zh") == "SB_ML_ZH"
    assert ablauf._kurzname("sb_gk_de", "fr") == "sb_gk_fr"
    assert ablauf._kurzname("ht_sb_de", "zh-tw") == "ht_sb_zh-tw"
