"""Baut zu einer fertigen Kurssicherung eine zweite, kleinere Fassung (Upload-Grenze Moodle 512 MB).

Die Original-.mbz bleibt unverändert. Die Videos aus <arbeitsordner>/videos_<code>/ werden
nach videos_<code>_klein/ neu kodiert (H.264, gleiche Auflösung, CRF 26, Ton unverändert),
dann baut kurs_bauen.py daraus <Kurs>/sicherung-<kurz>_klein.mbz. Liegt das Ergebnis über
--grenze MB, wird mit CRF 28, dann 30 wiederholt.

Aufruf: python -I -X utf8 verkleinern.py <arbeitsordner> <code> <original.mbz> --kursname "..." --kurzname "..."
"""
import argparse, os, shutil, subprocess, sys

sys.stdout.reconfigure(encoding="utf-8")
SKRIPTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "moodle-kurs-uebersetzen", "scripts")

ap = argparse.ArgumentParser()
ap.add_argument("ordner"); ap.add_argument("code"); ap.add_argument("original")
ap.add_argument("--kursname", required=True); ap.add_argument("--kurzname", required=True)
ap.add_argument("--grenze", type=int, default=500)
a = ap.parse_args()

quelle = os.path.join(a.ordner, f"videos_{a.code}")
kcode = f"{a.code}_klein"
ziel_v = os.path.join(a.ordner, f"videos_{kcode}")
# kurs_bauen.py liest uebersetzung_<code>.json: Kopie unter dem _klein-Code, immer frisch
shutil.copyfile(os.path.join(a.ordner, f"uebersetzung_{a.code}.json"),
                os.path.join(a.ordner, f"uebersetzung_{kcode}.json"))
ziel_mbz = a.original[:-4] + "_klein.mbz"

for crf in (26, 28, 30):
    os.makedirs(ziel_v, exist_ok=True)
    for f in sorted(os.listdir(quelle)):
        z = os.path.join(ziel_v, f)
        if os.path.exists(z) and os.path.getsize(z) > 0 and crf == 26:
            continue
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(quelle, f), "-c:v", "libx264",
                        "-preset", "medium", "-crf", str(crf), "-c:a", "copy", "-movflags", "+faststart", z],
                       check=True)
    subprocess.run([sys.executable, "-I", "-X", "utf8", os.path.join(SKRIPTE, "kurs_bauen.py"), a.ordner, kcode,
                    ziel_mbz, "--kursname", a.kursname, "--kurzname", a.kurzname], check=True,
                   stdout=subprocess.DEVNULL)
    mb = os.path.getsize(ziel_mbz) / 1e6
    print(f"{os.path.basename(ziel_mbz)}: {mb:.0f} MB (CRF {crf})")
    if mb <= a.grenze:
        break
    shutil.rmtree(ziel_v)
else:
    sys.exit(f"ACHTUNG: auch mit CRF 30 noch {mb:.0f} MB")
