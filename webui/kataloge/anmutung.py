"""Wie ein Bild aussieht: Stil, Licht, Blickwinkel, Objektiv, Farbe.

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
    "manga": ("Manga", "black and white manga artwork, crisp ink linework, screentone shading, dynamic speed lines, expressive panel composition"),
    "scifi": ("Science-Fiction", "hard science fiction look, brushed metal and composite surfaces, glowing accent edges, cool blue-white palette, believable engineering"),
    "kitsch": ("Kitschig", "unashamedly kitsch, candy colours, glitter and sparkles, rainbow gradients, hearts and stars, glossy greeting-card sheen"),
    "plastik": ("Plastik-Look", "made of glossy injection-moulded plastic like a collectible toy figure, smooth rounded edges, visible mould seams, saturated toy colours"),
    "bleistift": ("Bleistift", "graphite pencil drawing on textured paper, visible hatching and cross-hatching, soft smudged shading, eraser highlights, no colour"),
    "schillernd": ("Schillernd", "iridescent holographic look, rainbow sheen sliding across every surface, oil-slick colour shift, prismatic highlights, mirror-bright foil and chrome, wet-looking reflective fabric"),
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
    # Die Liste war gedeckt bis zur Langeweile -- kein Braun zwar, aber auch
    # nichts, was knallt. Diese fuenf sind ausdruecklich grell.
    "pink":       ("Pink", "vivid hot pink"),
    "tuerkis":    ("Türkis", "bright turquoise"),
    "limette":    ("Limettengrün", "electric lime green"),
    "lila":       ("Lila", "vivid purple"),
    "knallorange": ("Knallorange", "glowing neon orange"),
    "neon":       ("Neon", "a fluorescent neon finish that looks lit from within"),
    "neongruen":  ("Neongrün", "fluorescent neon green"),
    "neonpink":   ("Neonpink", "fluorescent neon pink"),
}


# Die Farbstimmung des ganzen Bildes -- etwas anderes als PAINTS, das immer nur
# einen benannten Gegenstand umlackiert und ohne Ziel sogar ganz entfaellt.
# Ohne diese Achse bestimmen Umgebung und Licht die Palette allein, und die
# sind erdlastig: Schotter, Feldweg, Wald, Baustelle, dazu Filmkorn und flauer
# Ueberwachungskontrast. Daher der Braunstich.
PALETTEN = {
    "knallig":    ("Knallig", "a loud saturated colour palette, pure strong hues, high chroma, nothing muted"),
    "pastell":    ("Pastell", "a soft pastel palette, pale tints, milky light, gentle low-contrast colours"),
    "neon":       ("Neon", "a neon palette, glowing magenta cyan and acid green against deep darks"),
    "kitschbunt": ("Kitschbunt", "a gaudy kitsch palette, candy pink lemon yellow and sky blue all at once, rainbow sparkle"),
    "metallic":   ("Metallic", "a metallic palette, polished chrome silver and gold, specular highlights, cool reflective sheen"),
    "monochrom":  ("Monochrom", "a monochrome palette, a single hue in many values, almost no other colour"),
    "erdig":      ("Erdig", "an earthy palette, ochre umber moss and sand, warm muted natural tones"),
    "kalt":       ("Kühl", "a cold palette, steel blue slate and cyan, no warm tones at all"),
    "warm":       ("Warm", "a warm palette, amber terracotta and deep red, sunlit and glowing"),
    "irisierend": ("Irisierend", "an iridescent palette, colours shifting through the spectrum with the angle, oil-slick greens violets and cyans over a bright base"),
}


# Gesichtsausdruck. Fuer Geschichten: die Mimik soll aus der Handlung kommen,
# und ausformuliert trifft sie das Modell zuverlaessiger als ein einzelnes
# Wort wie "traurig". Bewusst knapp gehalten -- der Rest des Prompts hat auch
# noch Platzbedarf.
MIMIK = {
    "lachen":       ("Lachen", "laughing openly, eyes crinkled, head slightly back"),
    "laecheln":     ("Lächeln", "a warm quiet smile, relaxed eyes"),
    "weinen":       ("Weinen", "crying, wet cheeks, reddened eyes, mouth tight"),
    "erschrocken":  ("Erschrocken", "startled, eyes wide, eyebrows high, mouth open"),
    "wuetend":      ("Wütend", "angry, jaw set, brows drawn together, hard stare"),
    "nachdenklich": ("Nachdenklich", "thoughtful, gaze turned away, faint furrow between the brows"),
    "ueberrascht":  ("Überrascht", "surprised, eyebrows raised, a small open smile"),
    "muede":        ("Müde", "tired, heavy eyelids, slack mouth, shoulders low"),
    "entschlossen": ("Entschlossen", "determined, chin up, steady direct gaze"),
    "verlegen":     ("Verlegen", "embarrassed, looking down, a shy half-smile"),
    "ernst":        ("Ernst", "serious, neutral mouth, calm level gaze"),
    "erleichtert":  ("Erleichtert", "relieved, shoulders dropping, a breath let out"),
    "besorgt":      ("Besorgt", "worried, brows drawn up, lips pressed together"),
    "verzweifelt":  ("Verzweifelt", "desperate, face drawn, searching gaze, hands unsteady"),
    "stolz":        ("Stolz", "proud, chin lifted, a small satisfied smile"),
}


# Koerperhaltung. Eine eigene Achse, weil sie das Bild staerker praegt als
# Kleidung oder Licht -- dieselbe Person wirkt stehend, hockend und im Sprung
# wie drei verschiedene Aufnahmen.
HALTUNGEN = {
    "stehen":      ("Aufrecht stehend", "standing upright, weight evenly on both feet, arms relaxed"),
    "kontrapost":  ("Standbein", "standing with the weight on one leg, hip shifted, the other knee loose"),
    "gehen":       ("Im Gehen", "caught mid-stride, walking towards the camera"),
    "sitzen":      ("Sitzend", "sitting, back straight, hands resting on the knees"),
    "hocken":      ("Hockend", "crouching low on the balls of the feet, elbows on the knees"),
    "lehnen":      ("Angelehnt", "leaning against a wall, one shoulder taking the weight"),
    "verschraenkt": ("Arme verschränkt", "standing with the arms folded across the chest"),
    "hueften":     ("Hände in den Hüften", "hands on the hips, elbows out"),
    "zurueck":     ("Zurückgelehnt", "leaning back, relaxed, chin slightly raised"),
    "vorgebeugt":  ("Vorgebeugt", "leaning forward, shoulders rounded, intent"),
    "gedreht":     ("Über die Schulter", "torso turned away, head looking back over the shoulder"),
    "sprung":      ("Im Sprung", "caught mid-jump, both feet off the ground, clothing in motion"),
    "knien":       ("Kniend", "kneeling on one knee"),
    "liegen":      ("Liegend", "lying propped on one elbow"),
}

# Bekleidung als eigene Achse. Fuer "dieselbe Person in zehn Hosen" ist die
# Luecke im Baustein ({hose} mit zehn Zeilen) genauer -- diese Achse streut
# ueber ganze Aufmachungen, wenn man breit variieren will.
BEKLEIDUNGEN = {
    "jeans":    ("Jeans und Shirt", "wearing blue jeans and a plain t-shirt"),
    "anzug":    ("Anzug", "wearing a well-cut dark suit"),
    "kleid":    ("Sommerkleid", "wearing a light summer dress"),
    "mantel":   ("Wollmantel", "wearing a long wool coat over dark trousers"),
    "sport":    ("Sportkleidung", "wearing running gear in technical fabric"),
    "arbeit":   ("Arbeitskleidung", "wearing sturdy canvas work trousers and a worn jacket"),
    "regen":    ("Regenzeug", "wearing a rain jacket and waterproof trousers"),
    "abend":    ("Abendgarderobe", "wearing formal evening wear"),
    "strick":   ("Strick und Cord", "wearing a chunky knitted sweater and corduroy trousers"),
    "leder":    ("Lederjacke", "wearing a leather jacket and black trousers"),
    "leinen":   ("Leinen", "wearing loose linen clothing in natural tones"),
    "uniform":  ("Uniform", "wearing a plain unmarked uniform"),
    "schlaf":   ("Hausanzug", "wearing soft loungewear"),
    "winter":   ("Winterkleidung", "wearing a padded winter coat, scarf and gloves"),
}


# Kerzenlicht auf einem Auto im Hof ergibt keine brauchbare Variante, deshalb
# hier ohne. Wer es doch will, stellt die Lichtachse von Hand ein.
VARIANT_LIGHTS = {k: v for k, v in LIGHTS.items() if k != "kerze"}
