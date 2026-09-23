"""Abläufe: eine Bildfolge als Datenstruktur statt als fest verdrahteter Code.

Ein Ablauf besteht aus Blöcken. Jeder Block erzeugt mehrere Bilder, die sich
in genau einem Merkmal unterscheiden, und sagt dabei drei Dinge:

  referenz   worauf das Bild aufsetzt -- "start" (das Ausgangsbild) oder
             "letztes" (das letzte Bild des vorigen Blocks)
  vorlage    "behutsam" bewahrt und ändert eine Kleinigkeit,
             "verwandeln" stellt den Stilwechsel nach vorn,
             "aktion" lässt die Person sich bewegen
  fest       gleicher Seed wie das Ausgangsbild? Nur für behutsame Blöcke
             sinnvoll -- bei Stilwechseln bleibt der Stil sonst blass

Optional sagt `anzahl`, wie viele Bilder der Block liefern soll -- sind es
mehr als Bausteine, werden die Bausteine der Reihe nach wiederholt.

Nach jedem Block kann das Ausgangsbild wieder eingeblendet werden
(`zurueck`), ohne dass es neu berechnet wird.
"""

from demo import KULISSEN
from presets import VARIANT_TEMPLATE

# Wortlaut für die beiden Prompt-Vorlagen.
_BEHUTSAM = VARIANT_TEMPLATE
_VERWANDELN = (
    "Redraw the entire scene from the reference image in this style: {stil}. "
    "The whole picture takes on that look -- the light, the colours, the surfaces, "
    "the background and the mood all change with it. Only one thing stays: {bleibt} "
    "must stay recognisable and in the same place in the frame."
)

# Bewegung ist weder eine behutsame Aenderung noch ein Stilwechsel: die Pose
# aendert sich stark, Mensch und Ort bleiben. Dafuer eine eigene Vorlage.
_AKTION = (
    "The same person in the same place as in the reference image, but now: {aktion}. "
    "Capture it as a real photograph of that moment, with the body in full motion "
    "and everything that moves with it -- clothing, hair, dust, shadows. "
    "{bleibt} must stay clearly recognisable."
)

# Zaehne geraten Diffusionsmodellen notorisch schief -- zu viele, verschmiert,
# doppelte Reihen. Ein knapper Hinweis am Ende jeder Anweisung hilft spuerbar.
_ZAEHNE = ("If teeth are visible, draw them cleanly: even, correctly shaped, "
           "the right number, never smeared or doubled.")

PERSON = "the person, their face and their pose"
PERSON_ORT = "the person, their face, their pose and their position in the frame"
ALLES = "the person, their clothing and the surroundings"
PERSON_GESICHT = "the person's face, their clothing and the surroundings"


def prompt_fuer(block: dict, baustein: str) -> str:
    if block.get("vorlage") == "aktion":
        text = _AKTION.format(aktion=baustein,
                              bleibt=block.get("bleibt") or PERSON_GESICHT)
    elif block.get("vorlage") == "verwandeln":
        text = _VERWANDELN.format(stil=baustein, bleibt=block.get("bleibt") or PERSON)
    else:
        kopf = _BEHUTSAM.format(keep=block.get("bleibt") or PERSON_ORT, extra="").strip()
        text = f"{kopf}, {baustein}"
    return f"{text} {_ZAEHNE}"


def bausteine_von(block: dict) -> list[str]:
    """Die Bausteine eines Blocks, auf seine Anzahl gebracht.

    Ohne Angabe ergibt jede Zeile ein Bild. Steht eine Anzahl darüber, werden
    die Zeilen der Reihe nach wiederholt -- fünf Zeilen und Anzahl zehn heißt
    also jede Zeile zweimal, mit verschiedenen Seeds. Eine kleinere Anzahl
    schneidet ab.
    """
    liste = [z for z in (block.get("bausteine") or [])]
    anzahl = block.get("anzahl")
    try:
        anzahl = int(anzahl)
    except (TypeError, ValueError):
        anzahl = 0
    if anzahl <= 0 or not liste:
        return liste
    return [liste[i % len(liste)] for i in range(anzahl)]


def schritte(ablauf: list[dict]) -> list[dict]:
    """Rechnet die Blöcke in eine flache Liste von Bildern um."""
    flach = []
    for block in ablauf:
        gefuellt = bausteine_von(block)
        for nummer, baustein in enumerate(gefuellt):
            flach.append({
                "titel": f"{block['titel']} {nummer + 1}",
                "prompt": prompt_fuer(block, baustein),
                "referenz": block.get("referenz", "start"),
                "fest": bool(block.get("fest")),
                "block": block["titel"],
                "letzter_im_block": nummer == len(gefuellt) - 1,
                "zurueck": bool(block.get("zurueck")) and nummer == len(gefuellt) - 1,
                "gruppe": block.get("art") == "gruppe",
            })
    return flach


def anzahl_bilder(ablauf: list[dict]) -> int:
    """Wie viele Bilder das Video zeigt -- samt der Rückgriffe aufs Startbild."""
    return 1 + sum(len(bausteine_von(b)) + (1 if b.get("zurueck") else 0) for b in ablauf)


def zu_erzeugen(ablauf: list[dict]) -> int:
    return 1 + sum(len(bausteine_von(b)) for b in ablauf)


def mit_beschreibung(ablauf: list[dict], beschreibung: str) -> list[dict]:
    """Traegt die Beschreibung des Startbilds in die Bewahrungsklauseln ein.

    "die Person muss gleich bleiben" trifft das Modell besser, wenn dort steht,
    wen es gleich lassen soll. Angehaengt wird nur dort, wo ueberhaupt von
    einer Person die Rede ist.
    """
    text = (beschreibung or "").strip()
    if not text:
        return ablauf
    zusatz = f" ({text})"
    for block in ablauf:
        bleibt = block.get("bleibt") or ""
        if "person" in bleibt.lower() and zusatz not in bleibt:
            block["bleibt"] = bleibt + zusatz
    return ablauf


# --- Mitgelieferte Abläufe ----------------------------------------------
def reise(kulisse: str = "auto", weiblich: bool | None = None) -> list[dict]:
    """Die Reise nimmt keinen Bezug auf die Kulisse -- sie tauscht den
    Hintergrund ohnehin komplett aus.

    `weiblich` kommt aus der Betrachtung des Startbilds. Ist dort eine Frau
    zu sehen, ergibt ein Bart-Schritt keinen Sinn; statt dessen wechselt
    die Haarfarbe. Bei None bleibt es beim Regelfall.
    """
    zweiter = ("the person now has bright copper red hair, the same hairstyle"
               if weiblich else "the person now has a full beard")
    return [
        {"titel": "Beleuchtung", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": PERSON_ORT, "zurueck": True, "bausteine": [
            "golden hour sunlight, long warm shadows, glowing rim light",
            "blue hour twilight, cool ambient light, deep sky gradient",
            "harsh midday sun, short hard shadows, very high contrast",
            "heavy overcast storm light, flat and grey, rain in the air",
            "strong backlight, the person rimmed in light, lens flare"]},

        {"titel": "Kameraperspektive", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": PERSON, "zurueck": True, "bausteine": [
            "shot on a 24mm wide angle lens from close up, expansive perspective",
            "shot on a 200mm telephoto lens, compressed perspective, isolated subject",
            "a low angle shot from ground level looking up, the person towering",
            "a high overhead angle looking down, bird's eye view",
            "a tilted dutch angle with an unsettling diagonal horizon"]},

        # Kein fester Seed: gesperrt bleibt das Bild so nah an der Vorlage,
        # dass der Mensch kaum wechselt. Gemessen -- mit gesperrtem Seed blieb
        # derselbe Mann mit etwas laengerem Haar, mit freiem wurde daraus eine
        # Frau bei gleicher Kleidung, Kulisse und Haltung.
        {"titel": "Person", "referenz": "start", "vorlage": "behutsam",
         "bleibt": "the clothing, the pose, the framing and the whole background",
         "zurueck": True, "bausteine": [
            "the person now has long hair tied up in a bun",
            zweiter,
            "the person is now about twenty years older, grey hair and a lined face",
            "the person is now noticeably thinner, a slim build",
            "the person is now athletic and muscular with broad shoulders"]},

        {"titel": "Kameraschwenk", "referenz": "start", "vorlage": "behutsam",
         "bleibt": "the person, their clothing and the surroundings", "zurueck": True,
         "bausteine": [
            "seen from the front, facing the camera",
            "seen from sixty degrees to the left",
            "seen from the side in full profile",
            "seen from behind at an angle, mostly the back",
            "seen from directly behind",
            "seen from sixty degrees to the right"]},

        {"titel": "Bewegung", "referenz": "start", "vorlage": "aktion",
         "bleibt": PERSON_GESICHT, "zurueck": True, "bausteine": [
            "jumping high into the air, both feet well off the ground, arms raised",
            "in the middle of a backward somersault, upside down in mid air",
            "sprinting at full speed towards the camera, the background streaked with motion",
            "dropping into a deep lunge, one knee low, arms braced, dust kicked up",
            "leaping sideways with a high kick, the body stretched out horizontally"]},

        {"titel": "Hintergrund", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": PERSON_ORT, "zurueck": True, "bausteine": [
            "standing in a vast sand desert with dunes to the horizon",
            "standing on a blue glacier between ice walls",
            "standing in a busy asian street at night, signs and lanterns",
            "standing on the surface of an alien planet, two moons in a violet sky",
            "standing in a drawn cartoon landscape with rolling hills and a bright sky"]},

        {"titel": "Rolle", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": "the person and their face", "zurueck": True, "bausteine": [
            "as a medieval knight in polished plate armour, a sword at their side",
            "as a glowing translucent blue spirit figure with luminous edges",
            "as an astronaut in a white spacesuit, helmet under the arm",
            "as an athlete in running gear mid-training, sweat and effort",
            "as a stone age human in furs with a wooden spear"]},

        {"titel": "Szene", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": PERSON, "bausteine": [
            "dystopian atmosphere, decaying concrete, smog, muted desaturated palette",
            "dynamic sports photography, frozen motion, dust and energy",
            "sensual boudoir style, intimate and tasteful, soft warm skin tones, silk",
            "anime illustration, cel shading, clean line art, expressive eyes",
            "cyberpunk aesthetic, rain-slick ground, neon signage, deep blacks"]},

        # Bleibt im Cyberpunk: setzt auf dem letzten Bild des vorigen Blocks auf.
        {"titel": "Neonkleidung", "referenz": "letztes", "vorlage": "behutsam",
         "bleibt": "the person, their face, their pose and the cyberpunk surroundings",
         "bausteine": [
            "wearing a neon pink cropped bomber jacket that glows",
            "wearing an electric cyan translucent raincoat",
            "wearing an acid green tech vest with glowing seams",
            "wearing a hot magenta hooded jacket with light strips",
            "wearing a neon orange padded coat that lights the face"]},

        # Beide Vorlagen zeigen dieselbe Person. Ohne den Zusatz verschmilzt das
        # Modell sie zu einer Figur -- geprueft: mit Zusatz stehen beide Looks
        # nebeneinander im Bild.
        {"titel": "Gruppe", "referenz": "letztes", "art": "gruppe", "bausteine": [
            "The two reference images show the same person in two different looks. "
            "Show both versions as two separate figures standing side by side."]},
    ]

# Der erste Ablauf: konservativ beginnen, langsam kreativ und dystopisch
# werden, ueber Comic und Cyberpunk ins grelle Neon und wieder zurueck.
def bogen(kulisse: str = "auto", weiblich: bool | None = None) -> list[dict]:
    """`kulisse` ist das, was hinter der Person steht -- Auto, Raumschiff,
    Fangemeinde. Zwei Schritte nehmen ausdruecklich darauf Bezug.

    `weiblich` spielt hier keine Rolle: dieser Ablauf tauscht die Person
    ohnehin komplett aus, statt einzelne Merkmale zu aendern."""
    hinten = KULISSEN.get(kulisse, KULISSEN["auto"])[2]
    return [
        # Kein fester Seed: gesperrt bleibt das Bild so nah an der Vorlage,
        # dass der Mensch kaum wechselt. Gemessen -- mit gesperrtem Seed blieb
        # derselbe Mann mit etwas laengerem Haar, mit freiem wurde daraus eine
        # Frau bei gleicher Kleidung, Kulisse und Haltung.
        {"titel": "Person", "referenz": "start", "vorlage": "behutsam",
         "zurueck": True,
         "bleibt": "the clothing, the pose, the framing, the lighting and the whole "
            f"background including {hinten}",
         "bausteine": [
            "the person is now a woman in her early thirties with shoulder-length brown hair",
            "the person is now an older man with grey hair and a short beard",
            "the person is now a young man with glasses and curly hair",
            "the person is now a woman with long dark hair tied back",
            "the person is now a man with a shaved head and stubble"]},

        {"titel": "Behutsam", "referenz": "start", "vorlage": "behutsam", "fest": True,
         "bleibt": PERSON_ORT, "bausteine": [
            "the person's jacket is bright red",
            "seen from the side in profile",
            "on a sandy beach by the sea",
            f"{hinten} in the background is bright yellow"]},

        {"titel": "Gruppe", "referenz": "start", "art": "gruppe", "bausteine": [
            "The two reference images show the same person in two different looks. "
            "Show both versions as two separate figures standing side by side."]},

        {"titel": "Licht", "referenz": "start", "vorlage": "verwandeln", "bleibt": ALLES,
         "bausteine": [
            "golden hour sunlight, long warm shadows, glowing rim light",
            "blue hour twilight, cool ambient light, deep sky gradient",
            "misty morning light, diffused haze, soft pastel tones",
            "strong backlight, the person rimmed in light, lens flare",
            "dramatic side lighting, one half in deep shadow"]},

        {"titel": "Dystopie", "referenz": "start", "vorlage": "verwandeln", "bleibt": PERSON,
         "bausteine": [
            "the colours drained, the paint faded, the place slightly run down",
            "dystopian atmosphere, decaying concrete, smog, muted desaturated palette",
            "dystopian, heavy rain, wet cracked ground, low black clouds",
            "dystopian, smoke drifting through the frame, broken windows behind",
            "post-apocalyptic, ash falling from a brown sky, dead vegetation",
            "post-apocalyptic ruin, a collapsed city skyline behind, sickly orange light"]},

        {"titel": "Malerei", "referenz": "start", "vorlage": "verwandeln", "bleibt": PERSON,
         "bausteine": [
            "watercolor painting, soft bleeding pigments, visible paper texture",
            "oil painting, thick visible brush strokes, rich impasto",
            "graphic novel panel, heavy ink outlines, halftone shading, flat colours",
            "classic hand-drawn cartoon, bold outlines, flat bright colours",
            "anime illustration, cel shading, clean line art"]},

        {"titel": "Neon", "referenz": "start", "vorlage": "verwandeln", "bleibt": PERSON,
         "bausteine": [
            "cyberpunk aesthetic, rain-slick ground, holographic signage, deep blacks",
            "cyberpunk, dense neon signage filling the background, wet reflections",
            "1980s retro aesthetic, chrome and magenta, grainy analog film",
            "glowing neon rim light, magenta on one side, cyan on the other",
            "heavily saturated neon colours, everything glowing, electric blue and hot pink",
            "extreme neon, long light trails streaking through the frame",
            "the whole frame in blinding neon, blown-out magenta and cyan"]},

        {"titel": "Zurück", "referenz": "start", "vorlage": "verwandeln", "bleibt": ALLES,
         "zurueck": True, "bausteine": [
            "the neon fading out, colours settling back towards natural",
            "a stylised but nearly photographic look, muted colours",
            "a photograph again, natural daylight, light colour grading",
            "a plain realistic photograph, natural colours, no stylisation at all"]},
    ]

# --- Klassisch: Porträtstudio -------------------------------------------
def klassisch(kulisse: str = "auto", weiblich: bool | None = None) -> list[dict]:
    """Ruhig und fotografisch: Lichtführung, Brennweite, Hintergrund, Schwarzweiß.

    Keine Stilbrüche -- dieser Ablauf zeigt, wie viel sich allein mit den
    Mitteln eines Fotostudios ändern lässt.
    """
    return [
        {"titel": "Lichtführung", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": PERSON_ORT, "zurueck": True, "bausteine": [
            "classic Rembrandt lighting, a small triangle of light on the shadowed cheek",
            "butterfly lighting from straight above, a small shadow under the nose",
            "split lighting, one half of the face lit, the other in darkness",
            "soft window light from the side, gentle falloff, no harsh shadow",
            "high key lighting, bright and almost shadowless, airy",
            "low key lighting, deep shadows, only the face picked out"]},

        {"titel": "Brennweite", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": PERSON, "zurueck": True, "bausteine": [
            "shot on a 35mm lens, full body with room around them",
            "shot on a 50mm lens, natural perspective, waist up",
            "shot on an 85mm portrait lens, head and shoulders, creamy bokeh",
            "shot on a 135mm lens, a tight portrait, background fully blurred",
            "an over the shoulder shot with a soft foreground edge"]},

        {"titel": "Hintergrund", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": PERSON_ORT, "zurueck": True, "bausteine": [
            "in front of seamless mid grey studio paper",
            "in front of deep black velvet, the edges falling into darkness",
            "in front of clean white, brightly lit, no visible horizon",
            "in front of a mottled painted canvas backdrop, old master style",
            "in front of weathered wooden boards"]},

        {"titel": "Schwarzweiß", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": ALLES, "bausteine": [
            "a classic black and white photograph, full tonal range, fine grain",
            "high contrast black and white, deep blacks and bright whites",
            "warm sepia toned, like an old print",
            "a platinum print, soft silvery greys, matte paper"]},
    ]


# --- Zeitreise -----------------------------------------------------------
def zeitreise(kulisse: str = "auto", weiblich: bool | None = None) -> list[dict]:
    """Dieselbe Person durch zwölf Epochen und sechs Aufnahmeverfahren."""
    return [
        {"titel": "Epoche", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": "the person and their face", "zurueck": True, "bausteine": [
            "as a stone age human in furs beside a cave wall with painted animals",
            "as an ancient egyptian in linen beside carved hieroglyphs",
            "as a roman citizen in a toga on marble steps",
            "as a medieval villager in rough wool in a muddy lane",
            "as a renaissance merchant in velvet, painted in oil",
            "as a baroque noble in lace and a powdered wig",
            "as a victorian in a stiff collar, photographed in a studio",
            "in 1920s dress on a city street with early motor cars",
            "in 1950s clothing beside a chrome car diner",
            "in 1970s clothing with warm faded film colours",
            "in 1990s clothing photographed on grainy consumer film",
            "in near future clothing, clean materials, soft technology"]},

        {"titel": "Aufnahmeverfahren", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": ALLES, "bausteine": [
            "a daguerreotype, mirror like silver surface, slight tarnish at the edges",
            "a wet plate tintype, dark and scratched, shallow depth",
            "an autochrome, soft pastel colours, visible starch grain",
            "a kodachrome slide, saturated reds, fine grain",
            "an instant polaroid with a white border and colour shift",
            "a modern phone photograph, over sharpened, slightly too bright"]},
    ]


# --- Comicheft -----------------------------------------------------------
def comicheft(kulisse: str = "auto", weiblich: bool | None = None) -> list[dict]:
    """Durch die Zeichenstile und dann immer weiter ins Heft hinein."""
    return [
        {"titel": "Zeichenstil", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": PERSON, "zurueck": True, "bausteine": [
            "ligne claire, even black outlines, flat colours, no hatching",
            "manga, screentone shading, large expressive eyes, speed lines",
            "american superhero comic, heavy inks, dramatic musculature, bold colours",
            "underground comix, scratchy nervous pen work, sour colours",
            "a woodcut print, coarse carved lines, two colours only",
            "a watercolour comic page, soft washes over loose ink",
            "a newspaper strip, four flat colours and a coarse dot screen",
            "pop art, benday dots, thick black outline, primary colours",
            "a noir graphic novel, heavy black shadows, one spot colour",
            "a children's picture book, soft crayon texture, friendly shapes"]},

        # Aufeinander aufbauend: das Heft wird Seite um Seite lauter.
        {"titel": "Ins Heft", "referenz": "letztes", "vorlage": "verwandeln",
         "bleibt": PERSON, "bausteine": [
            "drawn as one comic panel with a black border and a caption box",
            "with a speech bubble above them and bold lettering",
            "with a big hand drawn sound effect bursting across the panel",
            "the panel exploding into radiating speed lines and impact stars",
            "the halftone dots blown up until the whole page is raster"]},
    ]


# --- Neonstadt -----------------------------------------------------------
def neonstadt(kulisse: str = "auto", weiblich: bool | None = None) -> list[dict]:
    """Eine Eskalation: jeder Schritt setzt auf dem vorigen auf, es wird lauter."""
    return [
        {"titel": "Eskalation", "referenz": "letztes", "vorlage": "verwandeln",
         "bleibt": PERSON, "bausteine": [
            "a cyberpunk street at night, wet asphalt, a few neon signs",
            "denser neon signage in three languages filling the background",
            "heavy rain falling, every light smeared into long reflections",
            "holographic advertisements drifting through the air around them",
            "chrome implants at the temple and along the jaw, faintly lit",
            "seen from a drone high above, the street a canyon of light",
            "the image glitching, scanlines and colour channels torn apart",
            "total neon overload, the frame blown out in magenta and cyan"]},

        {"titel": "Zurück auf die Straße", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": ALLES, "bausteine": [
            "the neon fading, a quiet rainy street at dawn",
            "a plain photograph again, natural daylight, no stylisation"]},
    ]


# --- Elemente und Werkstoffe ---------------------------------------------
def elemente(kulisse: str = "auto", weiblich: bool | None = None) -> list[dict]:
    """Vier Elemente, sechs Werkstoffe, drei Bewegungen -- der schrägste Ablauf."""
    return [
        {"titel": "Element", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": PERSON, "zurueck": True, "bausteine": [
            "made of fire, the body formed from flame and rising embers",
            "made of water, the body a clear standing wave, droplets in the air",
            "made of earth, the body of cracked soil with moss and small stones",
            "made of air, the body half transparent, dust and wind passing through"]},

        {"titel": "Werkstoff", "referenz": "start", "vorlage": "verwandeln",
         "bleibt": "the person's shape and pose", "zurueck": True, "bausteine": [
            "as a polished bronze statue on a low plinth, green patina in the folds",
            "as a white marble sculpture, chisel marks still visible",
            "as a figure of clear glass, light refracting through the body",
            "as a carved wooden figure, visible grain and tool marks",
            "as folded paper, an origami figure of sharp creases",
            "built from interlocking plastic bricks, visible studs and seams"]},

        {"titel": "In Bewegung", "referenz": "start", "vorlage": "aktion",
         "bleibt": PERSON_GESICHT, "bausteine": [
            "leaping forward with both arms thrown back, coat flying",
            "spinning on one heel, everything loose swinging outward",
            "landing hard from a height, dust bursting from under the feet"]},
    ]


ABLAEUFE = {
    "bogen": {"label": "Bogen: konservativ bis Neon und zurück", "bauen": bogen},
    "reise": {"label": "Reise durch alles", "bauen": reise},
    "klassisch": {"label": "Klassisch: Porträt im Studio", "bauen": klassisch},
    "zeitreise": {"label": "Zeitreise: Epochen und Aufnahmeverfahren", "bauen": zeitreise},
    "comicheft": {"label": "Comicheft: durch alle Zeichenstile", "bauen": comicheft},
    "neonstadt": {"label": "Neonstadt: Cyberpunk-Eskalation", "bauen": neonstadt},
    "elemente": {"label": "Elemente und Werkstoffe", "bauen": elemente},
}
