"""Startbild-Vorgabe und Videobau für Abläufe.

Welche Bilder entstehen, steht in `ablauf.py`. Hier bleibt nur, was davon
unabhängig ist: der Vorgabetext für ein selbst erzeugtes Startbild und das
Zusammensetzen der fertigen Bilder zu einem Video.
"""

import shutil
import subprocess

# Was hinter der Person steht. Ein Auto war als Vorgabe zu eng -- die Kulisse
# taucht spaeter in den Abwandlungen wieder auf ("die Kulisse wird gelb"),
# deshalb steht zu jedem Eintrag auch der blosse Bezeichner dafuer.
KULISSEN = {
    "auto":         ("Auto", "a parked car", "the car"),
    "raumschiff":   ("Raumschiff", "a small parked spaceship with a lowered ramp",
                     "the spaceship"),
    "fans":         ("Fangemeinde", "a small crowd of cheering fans",
                     "the crowd"),
    "motorrad":     ("Motorrad", "a parked motorcycle", "the motorcycle"),
    "pferd":        ("Pferd", "a horse standing calmly", "the horse"),
    "bagger":       ("Bagger", "a parked excavator", "the excavator"),
    "imbiss":       ("Imbisswagen", "a food truck with its hatch open",
                     "the food truck"),
    "hubschrauber": ("Hubschrauber", "a helicopter on a landing pad",
                     "the helicopter"),
    "buecher":      ("Bücherwand", "a tall wall of bookshelves",
                     "the bookshelves"),
    "surfbretter":  ("Surfbretter", "a rack of colourful surfboards",
                     "the surfboards"),
}


def kulisse_waehlen(name: str = "", seed: int = 0) -> str:
    """Schluessel der Kulisse. Ohne Angabe eine aus dem Seed abgeleitete --
    dadurch wechselt sie von Lauf zu Lauf, bleibt aber reproduzierbar."""
    if name in KULISSEN:
        return name
    return sorted(KULISSEN)[seed % len(KULISSEN)]


def basis_prompt(kulisse: str = "auto") -> str:
    was = KULISSEN.get(kulisse, KULISSEN["auto"])[1]
    return (
        "a full body photograph of one person standing on a paved driveway, neutral "
        "relaxed pose, arms at their sides, looking at the camera, "
        f"{was} behind them, plain overcast daylight, everything in sharp focus"
    )


# Rueckwaertskompatibel: die Vorgabe bleibt das Auto.
BASIS_PROMPT = basis_prompt("auto")


def available() -> dict:
    """Ohne ffmpeg entstehen nur die Einzelbilder."""
    pfad = shutil.which("ffmpeg")
    return {"available": True, "video": bool(pfad),
            "reason": "" if pfad else "ffmpeg fehlt – es entstehen nur die Einzelbilder"}


# --- Video ---------------------------------------------------------------
def baue_video(bilder: list[str], ziel: str, gesamtdauer: float = 20.0,
               blende: float = 0.35) -> str:
    """Setzt die Bilder ohne Schnitt und ohne Beschriftung zusammen.

    Die Standzeit ergibt sich aus der Wunschlaenge: bei N Bildern mit
    Ueberblendung T gilt Laenge = N*D - (N-1)*T.
    """
    anzahl = len(bilder)
    stand = (gesamtdauer + (anzahl - 1) * blende) / anzahl
    eingaben = []
    for bild in bilder:
        eingaben += ["-loop", "1", "-t", f"{stand:.4f}", "-i", bild]

    kette = [
        f"[{i}:v]scale=1280:720:force_original_aspect_ratio=decrease,"
        f"pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x14161a,setsar=1,format=yuv420p[v{i}]"
        for i in range(anzahl)
    ]
    vorher = "v0"
    for i in range(1, anzahl):
        versatz = round(i * (stand - blende), 4)
        marke = f"x{i}"
        kette.append(f"[{vorher}][v{i}]xfade=transition=fade:"
                     f"duration={blende}:offset={versatz}[{marke}]")
        vorher = marke

    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *eingaben,
         "-filter_complex", ";".join(kette), "-map", f"[{vorher}]",
         "-r", "25", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20", ziel],
        check=True)
    return ziel
