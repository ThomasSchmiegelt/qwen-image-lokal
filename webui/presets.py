"""Vorgefertigte Prompt-Bausteine fuer Stil, Licht und Kameraperspektive.

Die Bezeichnungen sind deutsch, die Textbausteine englisch -- das Modell folgt
englischen Bildbeschreibungen deutlich zuverlaessiger.
"""

STYLES = {
    "foto": ("Fotorealistisch", "photorealistic, sharp focus, natural colors, high detail"),
    "zeichentrick": ("Zeichentrick", "classic hand-drawn cartoon style, bold outlines, flat bright colors, playful"),
    "anime": ("Anime", "anime illustration, cel shading, expressive eyes, clean line art"),
    "comic": ("Comic", "graphic novel panel, heavy ink lines, halftone shading, saturated colors"),
    "aquarell": ("Aquarell", "watercolor painting, soft bleeding pigments, visible paper texture"),
    "oel": ("Ölgemälde", "oil painting, thick visible brush strokes, rich impasto, gallery lighting"),
    "dystopisch": ("Dystopisch", "dystopian atmosphere, decaying concrete, smog and ash, muted desaturated palette, oppressive mood"),
    "utopisch": ("Utopisch", "utopian solarpunk vision, clean white architecture overgrown with greenery, bright optimistic light"),
    "cyberpunk": ("Cyberpunk", "cyberpunk aesthetic, neon signage, rain-slick streets, holographic advertising, deep blacks"),
    "sportlich": ("Sportlich", "dynamic sports photography, frozen motion, sweat and dust particles, powerful athletic energy"),
    "technisch": ("Technisch", "technical product rendering, precise engineering detail, clean studio backdrop, exploded-view clarity"),
    "erotisch": ("Sinnlich", "sensual boudoir style, intimate and tasteful, soft warm skin tones, silk fabrics, suggestive rather than explicit"),
    "draussen": ("Draußen", "outdoor location shot, natural environment, open sky, authentic weather and atmosphere"),
    "noir": ("Film Noir", "film noir, high contrast black and white, deep shadows, venetian blind light, 1940s mood"),
    "retro": ("Retro 80er", "1980s retro aesthetic, chrome and magenta, grainy analog film, VHS color fringing"),
    "maerchen": ("Märchenhaft", "storybook fairytale illustration, warm glow, whimsical detail, enchanted atmosphere"),
    "minimal": ("Minimalistisch", "minimalist composition, large negative space, few elements, calm restrained palette"),
}

LIGHTS = {
    "golden": ("Goldene Stunde", "golden hour sunlight, long warm shadows, glowing rim light"),
    "blau": ("Blaue Stunde", "blue hour twilight, cool ambient light, deep sky gradient"),
    "mittag": ("Hartes Mittagslicht", "harsh midday sun, short hard shadows, high contrast"),
    "studio": ("Softbox / Studio", "clean studio lighting, large softbox, gentle falloff, seamless backdrop"),
    "neon": ("Neon", "neon lighting, magenta and cyan color spill, glowing reflections"),
    "kerze": ("Kerzenlicht", "candlelight, warm flickering glow, soft deep shadows"),
    "gegenlicht": ("Gegenlicht", "strong backlight, subject rimmed in light, lens flare, silhouette edges"),
    "nebel": ("Nebliger Morgen", "misty morning light, diffused haze, soft pastel tones, visible light beams"),
    "seitenlicht": ("Dramatisches Seitenlicht", "dramatic side lighting, chiaroscuro, one half in deep shadow"),
    "bewoelkt": ("Bewölkt", "overcast diffuse daylight, soft even shadows, muted natural colors"),
}

# Umrundung einer Person. Die Reihenfolge ist der Flug: vorne herum bis hinten
# und zurueck, danach die beiden Sonderwinkel von oben und unten.
VIEWS = {
    "vorne":        ("Vorne (0°)", "front view, the person facing the camera directly"),
    "halblinks":    ("Halb links (45°)", "three-quarter view from the front left, the person turned about 45 degrees"),
    "links":        ("Linkes Profil (90°)", "full profile view from the left side, 90 degrees to the camera"),
    "hintenlinks":  ("Hinten links (135°)", "three-quarter view from behind on the left, mostly showing the back"),
    "hinten":       ("Hinten (180°)", "back view from directly behind the person, seen from the rear, face not visible"),
    "hintenrechts": ("Hinten rechts (225°)", "three-quarter view from behind on the right, mostly showing the back"),
    "rechts":       ("Rechtes Profil (270°)", "full profile view from the right side, 90 degrees to the camera"),
    "halbrechts":   ("Halb rechts (315°)", "three-quarter view from the front right, the person turned about 45 degrees"),
    "oben":         ("Von oben", "high angle shot from directly above, looking straight down at the person"),
    "unten":        ("Von unten", "low angle shot from near the ground, camera looking steeply up at the person"),
}

CAMERAS = {
    "portraet": ("Porträt (85 mm)", "85mm portrait lens, shallow depth of field, creamy bokeh, head and shoulders"),
    "weitwinkel": ("Weitwinkel", "24mm wide angle lens, expansive perspective, slight edge distortion"),
    "tele": ("Teleobjektiv", "200mm telephoto compression, flattened perspective, isolated subject"),
    "makro": ("Makro", "extreme macro close-up, fine surface texture, razor-thin focus plane"),
    "frosch": ("Froschperspektive", "low angle shot from ground level looking up, subject towering"),
    "vogel": ("Vogelperspektive", "high overhead angle looking down, bird's eye view"),
    "drohne": ("Drohne", "aerial drone shot, wide landscape context, slight top-down tilt"),
    "schulter": ("Über die Schulter", "over-the-shoulder shot, foreground framing, cinematic depth"),
    "dutch": ("Dutch Angle", "tilted dutch angle, unsettling diagonal horizon"),
    "ganz": ("Ganzkörper", "full body shot, subject fully in frame, environment visible"),
    "fisch": ("Fischauge", "fisheye lens, strong barrel distortion, curved horizon"),
}

# Anweisungen, die je nach Modus vor den Benutzertext gesetzt werden.
TEMPLATES = {
    "gruppe": (
        "A single group photograph showing all {n} people from the reference images together "
        "in one frame, side by side. Keep every person's face, hair and identity clearly "
        "recognizable and consistent with their reference image. {extra}"
    ),
    "person": (
        "The same person as in the reference image, {extra}. Keep the person's identity, "
        "hairstyle, build and outfit consistent with the reference image, in the same setting."
    ),
}

TRANSPARENT_TEMPLATE = (
    "This is an RGBA image with transparency. {extra} "
    "The image has alpha channel and the background is transparent."
)


def catalog() -> dict:
    """Fuer die Weboberflaeche: Schluessel + Anzeigename je Gruppe."""
    return {
        "styles": [{"key": k, "label": v[0]} for k, v in STYLES.items()],
        "lights": [{"key": k, "label": v[0]} for k, v in LIGHTS.items()],
        "cameras": [{"key": k, "label": v[0]} for k, v in CAMERAS.items()],
        "views": [{"key": k, "label": v[0]} for k, v in VIEWS.items()],
        "paints": [{"key": k, "label": v[0]} for k, v in PAINTS.items()],
        "scenes": [{"key": k, "label": v[0]} for k, v in SCENES.items()],
        "angles": [{"key": k, "label": v[0]} for k, v in ANGLES.items()],
        "devices": [{"key": k, "label": v[0]} for k, v in DEVICES.items()],
        "templates": TEMPLATES,
        "effects": [{"key": k, "label": v["label"], "alias": v["alias"],
                     "needs_image": v["needs_image"], **overrides(v)}
                    for k, v in EFFECTS.items()],
        "forms": [{"key": k, "label": v["label"], **overrides(v)} for k, v in FORMS.items()],
    }


def fragment(group: dict, key: str | None) -> str | None:
    """Textbaustein zu einem Schluessel, oder None wenn nichts gewaehlt ist."""
    entry = group.get(key or "")
    return entry[1] if entry else None


# --- Effekte -------------------------------------------------------------
# Die meisten "Kurzbefehle" sind keine eigenen Modelle, sondern Anweisungen an
# den Bearbeiten-Pfad. Jeder Eintrag kann zusaetzlich Einstellungen umstellen
# (Kamera, Transparenz, Serienart), die sonst von Hand gesetzt wuerden.
EFFECTS = {
    "removebg": {
        "alias": "/remove bg", "label": "Hintergrund entfernen", "needs_image": True,
        "transparent": True,
        "instruction": "Remove the background completely and keep only the main subject, "
                       "cleanly separated at the edges including fine detail like hair.",
    },
    "magazine": {
        "alias": "/magazine cover", "label": "Magazin-Cover", "needs_image": True,
        "instruction": "Turn this into a glossy magazine cover: masthead across the top, "
                       "cover lines down the sides, barcode and issue date, professional layout.",
    },
    "explosion": {
        "alias": "/ptexplosion", "label": "Explosionszeichnung", "needs_image": True,
        "instruction": "Show this product as an exploded view: the parts separated along their "
                       "assembly axes and floating apart, clean studio backdrop.",
    },
    "lifestyle": {
        "alias": "/lifestyle shot", "label": "Lifestyle-Aufnahme", "needs_image": True,
        "instruction": "Place this product into a natural lifestyle setting where it would "
                       "really be used, with believable surroundings, props and daylight.",
    },
    "expand": {
        # Qwen-Image 2.1 hat keinen Masken-Eingang und kein Outpainting: einen
        # freigelassenen Rand fuellt es nicht auf. Es zeichnet die Szene aber
        # zuverlaessig im neuen Format neu -- die Mitte ist danach nicht
        # pixelgleich, dafuer stimmen Person, Umgebung und Licht.
        "alias": "/expand", "label": "Bildausschnitt erweitern", "needs_image": True,
        "instruction": "Show this exact same scene as a much wider shot: the camera pulls back "
                       "and reveals more of the surroundings on the left and right. Keep the "
                       "subject, the clothing, the setting, the light and the style identical.",
    },
    "colorize": {
        "alias": "/colorize", "label": "Einfärben", "needs_image": True,
        "instruction": "Colorize this black and white photograph with natural, period-accurate "
                       "colors, keeping every detail and the original grain intact.",
    },
    "doubleexposure": {
        "alias": "double exposure", "label": "Doppelbelichtung", "needs_image": True,
        "instruction": "Render this as a double exposure: the silhouette of the subject filled "
                       "with a second scene blending through it.",
    },
    "glass": {
        "alias": "/glass", "label": "Glaseffekt", "needs_image": True,
        "instruction": "Seen through thick textured glass, with refraction, distortion and "
                       "condensation breaking up the shapes.",
    },
    "restore": {
        "alias": "/restore", "label": "Altes Foto auffrischen", "needs_image": True,
        "instruction": "Restore this damaged old photograph: repair scratches, tears and stains, "
                       "recover sharpness and contrast, keep the original composition and faces "
                       "exactly as they are.",
    },
    "tinyhumans": {
        "alias": "/tinyhumans", "label": "Winzige Menschen", "needs_image": True,
        "instruction": "Add tiny miniature people working on and around the subject, "
                       "tilt-shift miniature effect, the subject towering over them.",
    },
    "blueprint": {
        "alias": "/blueprint", "label": "Bauplan", "needs_image": True,
        "instruction": "Turn this into a technical blueprint drawing: white line work on blue "
                       "paper, dimension lines, callouts and a title block.",
    },
    "handwritten": {
        "alias": "/handwritten", "label": "Handschrift", "needs_image": True,
        "instruction": "Redraw the lettering in this image as natural handwriting with ink pen, "
                       "slight irregularity, on paper texture.",
    },
    # Diese beiden stellen nur vorhandene Regler um.
    "droneview": {
        "alias": "/droneview", "label": "Drohnenperspektive", "needs_image": False,
        "camera": "drohne",
    },
    "extremewide": {
        "alias": "extreme wide", "label": "Extremes Weitwinkel", "needs_image": False,
        "camera": "fisch",
    },
    "orbit": {
        "alias": "/360 view", "label": "Rundum-Ansicht", "needs_image": True,
        "mode": "person", "sweep": "view", "count": 10, "lock_seed": True,
    },
}

# --- Vorlagen ------------------------------------------------------------
# Geruest fuer einen Bildtyp. `{extra}` ist das, was der Benutzer eintippt.
FORMS = {
    "portraet": {
        "label": "Porträt", "aspect": "3:4", "style": "foto", "camera": "portraet",
        "template": "A professional portrait photograph of {extra}, "
                    "sharp eyes, flattering framing, clean background.",
    },
    "logo": {
        "label": "Logo", "aspect": "1:1", "transparent": True, "style": "minimal",
        "template": "A clean flat vector logo for {extra}. Simple bold shapes, "
                    "balanced negative space, legible at small size, no photographic detail.",
    },
    "illustration": {
        "label": "Illustration", "aspect": "3:2", "style": "aquarell",
        "template": "An illustration of {extra}, coherent palette, clear focal point.",
    },
    "buchumschlag": {
        "label": "Buchumschlag", "aspect": "2:3",
        "template": "A book cover for {extra}. Title lettering at the top, author name at the "
                    "bottom, strong central image, the typography sharp and correctly spelled.",
    },
    "verpackung": {
        "label": "Produktverpackung", "aspect": "1:1", "style": "technisch",
        "template": "Retail packaging design for {extra}, shown as a product photo of the box "
                    "on a clean surface, readable label, realistic material and print.",
    },
    "symbolbild": {
        "label": "Symbolbild / Icon", "aspect": "1:1", "transparent": True, "style": "minimal",
        "template": "A single clear pictogram icon representing {extra}. "
                    "One centred symbol, uniform stroke weight, no text, no frame.",
    },
    "webseite": {
        "label": "Webseiten-Muster", "aspect": "16:9", "style": "minimal",
        "template": "A clean website landing page mockup for {extra}: header with navigation, "
                    "hero section with headline and button, content cards below, shown flat.",
    },
    "app": {
        "label": "App-Muster", "aspect": "9:16", "style": "minimal",
        "template": "A mobile app screen mockup for {extra}: status bar, title, list of content "
                    "cards, bottom tab bar, modern flat interface design.",
    },
}

# Einstellungen, die ein Effekt oder eine Vorlage mitbringen darf.
OVERRIDE_KEYS = ("aspect", "style", "light", "camera", "view", "mode",
                 "sweep", "count", "lock_seed", "transparent")


def parse_command(text: str) -> tuple[str | None, str]:
    """Erkennt einen fuehrenden Kurzbefehl und gibt (Effekt-Schluessel, Resttext).

    Laengere Befehle zuerst, damit "/remove bg" nicht an "/remove" haengenbleibt.
    """
    lowered = text.strip().lower()
    for key, spec in sorted(EFFECTS.items(), key=lambda kv: -len(kv[1]["alias"])):
        alias = spec["alias"]
        if lowered.startswith(alias):
            return key, text.strip()[len(alias):].lstrip(" :,")
    return None, text


def overrides(spec: dict) -> dict:
    """Die Einstellungen, die ein Effekt oder eine Vorlage mitbringt."""
    return {k: spec[k] for k in OVERRIDE_KEYS if k in spec}


# --- Varianten ------------------------------------------------------
# Vervielfaeltigung eines Basisbilds: alles darf sich aendern ausser dem
# Gegenstand, auf den es ankommt. Die Bausteine sind als vollstaendige
# Aussagen formuliert, damit sie hinter der Unveraenderlichkeits-Anweisung
# stehen koennen, ohne den Satzbau zu zerlegen.
# Nur die Farbe. Woran sie haftet, bestimmt PAINT_TARGET bzw. die Eingabe des
# Benutzers -- "die Karosserie" beim Auto, "die Kleidung der Person" bei einem
# Portraet. Vorher stand "the vehicle body" fest im Baustein, was den Regler
# fuer alles ausser Fahrzeugen unbrauchbar machte.
PAINT_TARGET = "the vehicle body"
PAINTS = {
    "rot":        ("Rot", "bright red"),
    "weiss":      ("Weiß", "plain white"),
    "schwarz":    ("Schwarz", "glossy black"),
    "silber":     ("Silber", "metallic silver"),
    "dunkelgrau": ("Dunkelgrau", "dark grey"),
    "dunkelgruen": ("Dunkelgrün", "dark green"),
    "beige":      ("Beige", "beige"),
    "gelb":       ("Gelb", "bright yellow"),
    "orange":     ("Orange", "orange"),
    "dunkelblau": ("Dunkelblau", "deep navy blue"),
    "bordeaux":   ("Bordeaux", "dark burgundy red"),
    "matt":       ("Mattlack", "a matte grey wrap with no gloss"),
}

SCENES = {
    "hof":      ("Hofeinfahrt", "standing on a paved driveway in front of a house"),
    "schotter": ("Schotterplatz", "standing on a gravel yard"),
    "wiese":    ("Feldweg", "standing on a dirt track next to a green field"),
    "wald":     ("Waldweg", "standing on a forest track surrounded by trees"),
    "tiefgarage": ("Tiefgarage", "standing in an underground car park with concrete pillars"),
    "werkstatt": ("Werkstatt", "standing inside a repair workshop with tools on the walls"),
    "schnee":   ("Schnee", "standing on a snow-covered surface in winter"),
    "stadt":    ("Stadtstraße", "parked at the kerb of a city street with buildings behind"),
    "strand":   ("Strandparkplatz", "standing on a sandy car park near the sea"),
    "regen":    ("Nasse Fahrbahn", "standing on wet asphalt with rain puddles"),
    "halle":    ("Lagerhalle", "standing inside a bright warehouse hall"),
    "baustelle": ("Baustelle", "standing on a muddy construction site"),
}

# Blickwinkel auf einen Gegenstand -- nicht zu verwechseln mit VIEWS, die eine
# Person umrunden.
ANGLES = {
    "gerade":     ("Gerade von hinten", "seen straight from behind at bumper height"),
    "linksleicht": ("Leicht von links", "seen from slightly left of centre"),
    "rechtsleicht": ("Leicht von rechts", "seen from slightly right of centre"),
    "linksschraeg": ("Schräg von links", "seen at a 40 degree angle from the left rear"),
    "rechtsschraeg": ("Schräg von rechts", "seen at a 40 degree angle from the right rear"),
    "tief":       ("Bodennah", "seen from a low camera position close to the ground"),
    "erhoeht":    ("Erhöht", "seen from slightly above, looking down at the rear"),
    "nah":        ("Nahaufnahme", "a close-up filling most of the frame"),
    "weit":       ("Abstand", "seen from further away with the whole rear of the vehicle visible"),
    "hochkant":   ("Aufrecht", "an upright portrait framing of the rear"),
}

# Aufnahmegeraet statt Objektiv: fuer Trainingsdaten ist die Bildanmutung der
# Kamera wichtiger als die Brennweite. Die CAMERAS-Tabelle passt hier nicht,
# ihre Eintraege sind auf Personen gemuenzt ("Kopf und Schultern").
DEVICES = {
    "handy":       ("Smartphone", "shot on a smartphone camera, slightly over-processed"),
    "spiegelreflex": ("Spiegelreflex", "shot on a DSLR with a 50mm lens, clean and sharp"),
    "weitwinkel":  ("Weitwinkel", "shot with a wide angle lens, slight barrel distortion"),
    "tele":        ("Teleobjektiv", "shot with a telephoto lens, compressed perspective"),
    "action":      ("Action-Kamera", "shot on an action camera, very wide, mild fisheye"),
    "dashcam":     ("Dashcam", "a dashcam still, slightly soft with over-sharpened edges"),
    "ueberwachung": ("Überwachungskamera", "a surveillance camera still, low contrast, visible noise"),
    "kompakt":     ("Kompaktkamera", "a compact camera snapshot with direct flash"),
    "analog":      ("Analogfilm", "shot on 35mm colour film with visible grain"),
}

# Sonderwert einer Achse: gar nicht anfassen. Zu unterscheiden von "" -- das
# heisst im Varianten-Modus wuerfeln.
AXIS_OFF = "-"

# Vor den Benutzertext im Varianten-Modus. Die Unveraenderlichkeit steht
# bewusst zweimal drin -- einmal als Anweisung, einmal als Aufzaehlung der
# Merkmale. Ein Diffusionsmodell ueberschreibt sonst gern mit.
VARIANT_TEMPLATE = (
    "A photograph of the same subject as in the reference image. "
    "{keep} must remain exactly identical to the reference: same model, same shape, "
    "same size, same colour, same finish, same mounting position and the same "
    "proportions relative to the vehicle. Do not redesign it, do not move it, "
    "do not change its colour. Everything else in the picture may differ. {extra}"
)

# Kerzenlicht auf einem Auto im Hof ergibt keine brauchbare Variante, deshalb
# hier ohne. Wer es doch will, stellt die Lichtachse von Hand ein.
VARIANT_LIGHTS = {k: v for k, v in LIGHTS.items() if k != "kerze"}

VARIANT_AXES = {"paint": PAINTS, "scene": SCENES, "light": VARIANT_LIGHTS,
                "device": DEVICES, "angle": ANGLES}

# Nachtraeglich eingehaengt, weil die Vorlage weiter unten steht als TEMPLATES.
TEMPLATES["varianten"] = VARIANT_TEMPLATE
