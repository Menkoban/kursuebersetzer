"""Die Oberflaeche muss fehlerfrei laden – ein Syntaxfehler legt die ganze App lahm."""
import os
import shutil
import subprocess

import pytest

STATIC = os.path.join(os.path.dirname(__file__), "..", "app", "static")


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js nicht installiert")
def test_javascript_ohne_syntaxfehler():
    r = subprocess.run(["node", "--check", os.path.join(STATIC, "app.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_alle_seiten_und_dateien_vorhanden():
    for datei in ("index.html", "app.js", "app.css", "datenschutz.html"):
        assert os.path.isfile(os.path.join(STATIC, datei)), datei
