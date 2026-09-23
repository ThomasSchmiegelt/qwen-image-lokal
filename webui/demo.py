"""Vorführung: sieben Bilder, die zeigen was sich einzeln steuern lässt.

Jeder Schritt geht vom selben Basisbild aus und ändert genau eine Sache. Was
dabei stehen bleibt, ist der eigentliche Punkt der Vorführung -- deshalb steht
in jedem Schritt ausdrücklich, was unverändert bleiben muss.

Die Schritte sind als Parametersätze der normalen Schnittstelle beschrieben.
Es gibt also keinen Sonderweg durch die Erzeugung: die Vorführung benutzt
genau das, was auch die Oberfläche benutzt.
"""

import os
import shutil
import subprocess

BASIS_PROMPT = (
    "a full body photograph of one person standing on a paved driveway, neutral "
    "relaxed pose, arms at their sides, looking at the camera, a parked car behind "
    "them, plain overcast daylight, everything in sharp focus"
)
BLEIBT = "Die Person, ihr Gesicht, ihre Haltung"

HINTERGRUND_ZIEL = "das Auto im Hintergrund"


def basis(prompt: str = "") -> dict:
    """Schritt 0: das Basisbild erzeugen. Leerer Prompt heisst Vorgabe."""
    return {
        "name": "basis", "titel": "Basisbild",
        "unterzeile": "Ausgangspunkt für alles Weitere",
        "params": {"mode": "t2i", "prompt": prompt.strip() or BASIS_PROMPT,
                   "aspect": "3:2", "seed": 3100, "count": 1},
    }

# Alle Achsen aus; jeder Schritt schaltet genau eine wieder ein.
_AUS = {"mode": "varianten", "subject": "person", "prompt": "",
        "follow_reference": True, "count": 1, "sweep": "varianten",
        "paint": "-", "scene": "-", "light": "-", "device": "-",
        "angle": "-", "material": "-", "paint_target": ""}

def schritte(hintergrund_ziel: str = HINTERGRUND_ZIEL) -> list[dict]:
    """Die fünf Abwandlungen. `hintergrund_ziel` ist das, was in Schritt 4
    umgefärbt wird -- bei einem eigenen Foto ohne Auto etwa „die Wand
    im Hintergrund"."""
    ziel = hintergrund_ziel.strip() or HINTERGRUND_ZIEL
    return [
    {"name": "kleidung", "titel": "Nur die Kleidungsfarbe",
     "unterzeile": "Perspektive, Hintergrund und Auto bleiben stehen",
     "params": {**_AUS, "seed": 3101, "paint": "rot",
                "paint_target": "die Jacke der Person",
                "keep": f"{BLEIBT}, die Perspektive und der gesamte Hintergrund samt Auto"}},

    {"name": "perspektive", "titel": "Nur die Perspektive",
     "unterzeile": "Dieselbe Person, dieselbe Kleidung, dieselbe Umgebung",
     "params": {**_AUS, "seed": 3102, "angle": "pa_profil",
                "keep": f"{BLEIBT}, ihre Kleidung, das Auto und die gesamte Umgebung"}},

    {"name": "hintergrund", "titel": "Nur der Hintergrund",
     "unterzeile": "Person, Kleidung und Blickwinkel bleiben unverändert",
     "params": {**_AUS, "seed": 3103, "scene": "ps_strand",
                "keep": f"{BLEIBT}, ihre Kleidung und die Perspektive"}},

    {"name": "autofarbe", "titel": "Nur ein Teil des Hintergrunds",
     "unterzeile": f"„{ziel}“ wird gelb — sonst ändert sich nichts",
     "params": {**_AUS, "seed": 3104, "paint": "gelb",
                "paint_target": ziel,
                "keep": f"{BLEIBT}, ihre Kleidung, die Perspektive und die "
                        "gesamte übrige Umgebung"}},

    {"name": "geist", "titel": "Nur die Darstellung",
     "unterzeile": "Als leuchtender Geist, Haltung und Ort bleiben",
     "params": {**_AUS, "seed": 3105, "scenario": "geister",
                "keep": f"{BLEIBT}, ihre Perspektive und die Umgebung"}},
    ]

# Der letzte Schritt braucht zwei Bilder und laeuft deshalb gesondert.
GRUPPE = {
    "name": "gruppe", "titel": "Als Gruppe",
    "unterzeile": "Zwei Einzelbilder werden zu einem gemeinsamen Foto",
    "params": {"mode": "gruppe", "action": "zusammen", "prompt": "",
               "image_prompts": ["", ""], "aspect": "3:2",
               "follow_reference": False, "seed": 3106, "count": 1},
}

ANZAHL = 2 + len(schritte())   # Basis + Abwandlungen + Gruppe


def available() -> dict:
    """Ohne ffmpeg gibt es Bilder, aber kein Video."""
    pfad = shutil.which("ffmpeg")
    return {"available": True, "video": bool(pfad),
            "steps": ANZAHL,
            "reason": "" if pfad else "ffmpeg fehlt – es entstehen nur die Einzelbilder"}


# --- Video ---------------------------------------------------------------
def baue_video(bilder: list[str], ziel: str,
               sekunden: float = 3.0, blende: float = 0.9) -> str:
    """Setzt die Bilder zu einem Video ohne Schnitt zusammen.

    Keine Beschriftung, keine harten Uebergaenge: jedes Bild blendet in das
    naechste. Weil alle Schritte vom selben Basisbild ausgehen und nur eine
    Sache aendern, liegen die Motive deckungsgleich uebereinander -- die
    Ueberblendung zeigt die Aenderung dann von selbst.
    """
    eingaben = []
    for bild in bilder:
        eingaben += ["-loop", "1", "-t", str(sekunden), "-i", bild]

    # Alle auf dasselbe Raster bringen, sonst verweigert xfade die Arbeit.
    kette = [
        f"[{i}:v]scale=1280:720:force_original_aspect_ratio=decrease,"
        f"pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x14161a,setsar=1,format=yuv420p[v{i}]"
        for i in range(len(bilder))
    ]
    # Jede Ueberblendung beginnt um (Standzeit - Blende) spaeter als die davor.
    vorher = "v0"
    for i in range(1, len(bilder)):
        versatz = round(i * (sekunden - blende), 3)
        marke = f"x{i}"
        kette.append(f"[{vorher}][v{i}]xfade=transition=fade:"
                     f"duration={blende}:offset={versatz}[{marke}]")
        vorher = marke

    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *eingaben,
         "-filter_complex", ";".join(kette), "-map", f"[{vorher}]",
         "-r", "24", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20", ziel],
        check=True)
    return ziel
