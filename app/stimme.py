"""Maennliche oder weibliche Stimme? Aus der Grundfrequenz des Originaltons geschaetzt.

Faustregel aus dem Skill: maennlich etwa 85-155 Hz, weiblich 165-255 Hz. Die Grenze
liegt bei 160 Hz. Der neue Ton liegt spaeter auf dem alten Bild, also soll die
Stimme zum sichtbaren Avatar passen.
"""
import subprocess

GRENZE_HZ = 160


def grundfrequenz(pfad, rate=16000, hoechstens_s=60):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", pfad, "-t", str(hoechstens_s), "-ac", "1",
                        "-ar", str(rate), "-f", "s16le", "-"], capture_output=True)
    ton = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32)
    if ton.size < rate:
        return None
    rahmen = int(0.04 * rate)
    lmin, lmax = rate // 400, rate // 70           # 70-400 Hz
    lautstaerke = np.sqrt(np.mean(ton ** 2)) or 1.0
    werte = []
    for start in range(0, ton.size - rahmen, rahmen):
        x = ton[start:start + rahmen]
        if np.sqrt(np.mean(x ** 2)) < 0.5 * lautstaerke:
            continue                                # Pause oder leise Stelle
        x = x - x.mean()
        ak = np.correlate(x, x, mode="full")[rahmen - 1:]
        if ak[0] <= 0:
            continue
        bereich = ak[lmin:lmax]
        lag = int(np.argmax(bereich)) + lmin
        if bereich.max() / ak[0] > 0.45:            # deutlich stimmhaft
            werte.append(rate / lag)
    return float(np.median(werte)) if len(werte) >= 10 else None


def geschlecht(pfad, vorgabe="w"):
    try:
        f0 = grundfrequenz(pfad)
    except Exception:
        return vorgabe, None
    if f0 is None:
        return vorgabe, None
    return ("m" if f0 < GRENZE_HZ else "w"), f0
