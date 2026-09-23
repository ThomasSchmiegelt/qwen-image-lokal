"""Vorführung: vierzig Bilder, die zeigen was sich steuern lässt.

Der Bogen ist bewusst dramaturgisch:

  1       Basisbild
  2 – 6   nur die Person wird getauscht, Kleidung und Umgebung bleiben
  7       zurück zum Ausgangsbild, das ab hier die Grundlage für alles ist
  8 – 12  konservativ: Kleidungsfarbe, Perspektive, Hintergrund, Autolack, Gruppe
 13 – 17  Lichtstimmungen, noch fotografisch
 18 – 23  es wird kreativer und dystopischer
 24 – 28  Malerei und Comic
 29 – 35  Cyberpunk und immer knalligeres Neon
 36 – 39  zurück ins Realistische
 40       wieder das Ausgangsbild

Alle Abwandlungen gehen vom selben Basisbild aus und laufen mit demselben
Seed. Dadurch liegen die Bilder deckungsgleich übereinander -- beim
Überblenden verändert sich sichtbar nur das, was der Schritt ändert.

Die Prompts stehen hier fertig auf Englisch. Das spart die Übersetzung und
macht die Vorführung reproduzierbar; übersetzt wird nur, was der Benutzer
selbst eingibt.
"""

import os
import shutil
import subprocess

from presets import VARIANT_TEMPLATE

HINTERGRUND_ZIEL = "das Auto im Hintergrund"

BASIS_PROMPT = (
    "a full body photograph of one person standing on a paved driveway, neutral "
    "relaxed pose, arms at their sides, looking at the camera, a parked car behind "
    "them, plain overcast daylight, everything in sharp focus"
)

# Beim Personentausch bleibt alles ausser dem Menschen.
_TAUSCH = (
    "A photograph identical to the reference image in every respect -- the same "
    "clothing, the same pose, the same framing, the same lighting and the same "
    "background including the car -- except that the person is {wer}."
)

PERSONEN = [
    ("Andere Person", "a woman in her early thirties with shoulder-length brown hair"),
    ("Andere Person", "an older man with grey hair and a short beard"),
    ("Andere Person", "a young man with glasses and curly hair"),
    ("Andere Person", "a woman with long dark hair tied back"),
    ("Andere Person", "a man with a shaved head and stubble"),
]

_ALLES = ("the person, their face, their clothing, their pose and their position "
          "in the frame, the framing and the whole background")
_PERSON = "the person, their face, their pose and their position in the frame"
# Kurzfassungen fuer die Stilschritte -- dort waere eine lange Bewahrungsliste
# kontraproduktiv.
_PERSON_KURZ = "the person, their face and their pose"
_ALLES_KURZ = "the person, their clothing and the car behind them"


# Fuer die behutsamen Schritte: die Varianten-Vorlage, die auf Beharren aus ist.
def _variante(bleibt: str, *bausteine: str) -> str:
    kopf = VARIANT_TEMPLATE.format(keep=bleibt, extra="").strip()
    return ", ".join([kopf] + [b for b in bausteine if b])


# Fuer Stilwechsel genau andersherum. Die Varianten-Vorlage wiederholt
# "identisch, nicht veraendern, nicht umfaerben" so oft, dass ein angehaengter
# Stilbaustein untergeht -- das Modell folgt der lauteren Anweisung und liefert
# das Ausgangsbild zurueck. Hier steht deshalb die Verwandlung vorn und das
# Bewahren als knappe Ausnahme dahinter.
_STIL = (
    "Redraw the entire scene from the reference image in this style: {stil}. "
    "The whole picture takes on that look -- the light, the colours, the surfaces, "
    "the background and the mood all change with it. Only one thing stays: {bleibt} "
    "must stay recognisable and in the same place in the frame."
)


def _stil(bleibt: str, baustein: str) -> str:
    return _STIL.format(stil=baustein, bleibt=bleibt)


def folge(hintergrund_ziel: str = "the car in the background") -> list[dict]:
    """Die 37 zu erzeugenden Abwandlungen, in Reihenfolge der Vorführung."""
    ziel = hintergrund_ziel.strip() or "the car in the background"
    schritte = []

    def dazu(titel, prompt, art="edit", fest=False):
        """`fest` heisst: derselbe Seed wie das Basisbild.

        Fuer behutsame Schritte ist das richtig, da haelt es die Bildaufteilung
        ruhig. Fuer Stilwechsel ist es schaedlich: ein gesperrter Seed
        zementiert auch die Neigung dieses einen Rauschmusters, nah an der
        Vorlage zu bleiben -- aus "grelles Neon" wird dann ein violetter Hauch.
        Gemessen: Abweichung 42 mit gesperrtem, 79 mit freiem Seed.
        """
        schritte.append({"titel": titel, "prompt": prompt, "art": art, "fest": fest})

    for titel, wer in PERSONEN:
        dazu(titel, _TAUSCH.format(wer=wer), fest=True)

    # Konservativ -- einzelne Stellschrauben, sonst nichts.
    dazu("Kleidungsfarbe", _variante(
        f"{_PERSON}, the perspective and the whole background including the car",
        "the person's jacket is bright red"), fest=True)
    dazu("Perspektive", _variante(
        f"{_PERSON}, their clothing, the car and the whole surroundings",
        "seen from the side in profile"), fest=True)
    dazu("Hintergrund", _variante(
        f"{_PERSON}, their clothing and the perspective", "on a sandy beach by the sea"), fest=True)
    dazu("Teil des Hintergrunds", _variante(
        f"{_PERSON}, their clothing, the perspective and everything else around them",
        f"{ziel} is bright yellow"), fest=True)
    dazu("Als Gruppe", "", art="gruppe")

    # Licht -- noch ganz fotografisch.
    for titel, baustein in [
        ("Goldene Stunde", "golden hour sunlight, long warm shadows, glowing rim light"),
        ("Blaue Stunde", "blue hour twilight, cool ambient light, deep sky gradient"),
        ("Morgennebel", "misty morning light, diffused haze, soft pastel tones"),
        ("Gegenlicht", "strong backlight, the person rimmed in light, lens flare"),
        ("Hartes Seitenlicht", "dramatic side lighting, one half in deep shadow"),
    ]:
        dazu(titel, _stil(_ALLES_KURZ, baustein))

    # Es wird kreativer und duesterer.
    for titel, baustein in [
        ("Erste Trübung", "the colours drained, the paint faded, the place slightly run down"),
        ("Dystopisch", "dystopian atmosphere, decaying concrete, smog, muted desaturated palette"),
        ("Regen", "dystopian, heavy rain, wet cracked ground, low black clouds"),
        ("Rauch", "dystopian, smoke drifting through the frame, broken windows behind, "
                  "abandoned and silent"),
        ("Asche", "post-apocalyptic, ash falling from a brown sky, dead vegetation, "
                  "the ground split open"),
        ("Ruinen", "post-apocalyptic ruin, a collapsed city skyline behind, "
                   "sickly orange light through dust"),
    ]:
        dazu(titel, _stil(_PERSON_KURZ, baustein))

    # Malerei und Comic.
    for titel, baustein in [
        ("Aquarell", "watercolor painting, soft bleeding pigments, visible paper texture"),
        ("Ölgemälde", "oil painting, thick visible brush strokes, rich impasto"),
        ("Comic", "graphic novel panel, heavy ink outlines, halftone shading, "
                  "flat saturated colours"),
        ("Zeichentrick", "classic hand-drawn cartoon, bold outlines, flat bright colours"),
        ("Anime", "anime illustration, cel shading, clean line art, expressive"),
    ]:
        dazu(titel, _stil(_PERSON_KURZ, baustein))

    # Cyberpunk, dann immer knalliger.
    for titel, baustein in [
        ("Cyberpunk", "cyberpunk aesthetic, rain-slick ground, holographic signage, deep blacks"),
        ("Neonschilder", "cyberpunk, dense neon signage filling the background, wet reflections"),
        ("Achtziger", "1980s retro aesthetic, chrome and magenta, grainy analog film, "
                      "VHS colour fringing"),
        ("Neon-Kante", "glowing neon rim light on the person, magenta on one side, "
                       "cyan on the other, dark surroundings"),
        ("Gesättigt", "heavily saturated neon colours, everything glowing, "
                      "electric blue and hot pink"),
        ("Lichtspuren", "extreme neon, long light trails streaking through the frame, "
                        "colours pushed far beyond natural"),
        ("Grell", "the whole frame in blinding neon, blown-out magenta and cyan, "
                  "maximum colour intensity"),
    ]:
        dazu(titel, _stil(_PERSON_KURZ, baustein))

    # Und wieder zurueck.
    for titel, baustein in [
        ("Neon verglüht", "the neon fading out, colours settling back towards natural, "
                          "still faintly glowing"),
        ("Fast wieder Foto", "a stylised but nearly photographic look, muted colours, "
                             "soft daylight returning"),
        ("Foto", "a photograph again, natural daylight, light colour grading"),
        ("Wie am Anfang", "a plain realistic photograph, natural colours, overcast daylight, "
                          "no stylisation at all"),
    ]:
        dazu(titel, _stil(_ALLES_KURZ, baustein))

    return schritte


# Basisbild + Abwandlungen + zwei Rueckgriffe auf das Basisbild.
ANZAHL = 1 + len(folge()) + 2


def available() -> dict:
    pfad = shutil.which("ffmpeg")
    return {"available": True, "video": bool(pfad), "steps": ANZAHL,
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
