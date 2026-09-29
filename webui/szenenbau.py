"""Eine Szene in Stufen bauen statt in einem Zug.

Der kurze Weg -- alle Musterbilder auf einmal ins Modell -- hat zwei
Schwaechen. Die Musterbilder zeigen jede Figur stehend vor neutralem Grund,
und das Modell stellt sie dann auch in der Szene hin, egal was der Satz
sagt. Und mehr als vier Vorlagen nimmt es ueberhaupt nicht.

Deshalb der lange Weg, Stufe um Stufe:

    1  Kulisse            der Raum allein, ohne Person
    2  je Figur eine Pose freigestellt, in der Haltung dieser Szene,
                          das Musterbild als Vorlage fuer das Gesicht
    3  Spiegelung         das Gesicht, das sich spiegeln soll, eigens
    4  Zusammensetzen     eine Figur nach der anderen in das Bild davor

Jede Stufe ist ein eigenes Bild und bleibt liegen. Die Posen haengen sich
an ihren Baustein: wer Malva einmal liegend hat, braucht sie beim naechsten
Mal nicht neu.

Hier steht nur die Rechnung -- was erzeugt wird, in welcher Reihenfolge und
worauf es aufsetzt. Das Erzeugen selbst steht in `auftraege.py`.
"""

import bausteine
from kataloge import GEZEICHNET, STYLES

# Eine Pose soll die Figur zeigen, nicht die Umgebung: das Zusammensetzen
# schneidet sie sonst mitsamt einem Stueck fremdem Zimmer in die Kulisse.
# Die Pose braucht oft etwas, worauf die Figur liegt oder sitzt -- ein Bett,
# einen Stuhl. Das darf nicht mit ins Bild: es wuerde beim Zusammensetzen als
# zweites Bett in der Kulisse landen. Also die Haltung ohne das Moebel,
# ausdruecklich gesagt, sonst malt das Modell es doch dazu.
FREI = ("full figure, the entire body within the frame, "
        "on a plain seamless neutral grey background, nothing else in the "
        "picture: no furniture, no props, no floor line, no cast shadow. "
        "The figure holds the pose in mid-air as though the furniture it "
        "rests on were invisible.")

# Ein Posenbild entsteht ohne Vorlage.
#
# Zweimal gemessen, mit zwei Formulierungen: mit dem Musterbild als Vorlage
# blieb die Figur stehen, obwohl die Szene sie liegend wollte -- auch dann
# noch, als die Haltung ganz vorn stand und der Text ausdruecklich sagte,
# sie schlage die Vorlage. Das Referenzbild haelt die Koerperhaltung fest,
# und kein Satz redet ihm das aus. Ohne Vorlage, allein aus dem Text des
# Bausteins, lag sie beim ersten Versuch richtig.
#
# Die Wiedererkennbarkeit leidet nicht so, wie es zunaechst aussieht: das
# Musterbild ist selbst nichts anderes als dieser Text ohne Haltung. Wer
# beides nebeneinanderlegt, sieht dieselbe Person.

# Ein gespiegeltes Gesicht ist kein zweites Portraet: es liegt flach in der
# Flaeche, ist blasser als der Raum und laeuft mit dessen Licht.
SPIEGEL_BILD = ("a face seen as a reflection, frontal, softly lit, "
                "on a plain dark background, the face slightly faded and "
                "low in contrast, as a reflection in glass looks")

SPIEGEL_SETZEN = (
    "Add the face from the second reference image as a reflection {wo}. "
    "It is a reflection, not a person in the room: flat in the surface, "
    "fainter than what is around it, following the light of the scene, and "
    "it must not cast a shadow or stand anywhere in the room. It is also "
    "not a picture: no frame around it, no border, no canvas, no poster, "
    "and it does not cover the surface -- what lies behind the glass stays "
    "faintly visible through it. Everything else in the first reference "
    "image stays exactly as it is.")

# Die Stelle im Raum steht getrennt von der Haltung und ausdruecklich vorn.
# Gemessen: "standing next to the bed" in einem Stueck ergab eine Figur, die
# auf dem Bett stand. Die Haltung kam an, die Stelle nicht -- das Modell
# setzt die Figur dorthin, wo im Bild Platz ist, wenn man ihm nicht sagt,
# worauf ihr Gewicht ruhen soll.
SETZEN = (
    "Place the figure from the second reference image into the scene of the "
    "first reference image. Where it goes: {platz}. What its body does: "
    "{pose}. Its weight rests on what the position names and on nothing "
    "else -- if it stands on the floor, it does not stand on the furniture, "
    "and its feet are at floor level, not raised. Keep the figure exactly "
    "as in its reference: face, hair, clothing, colours and its visual "
    "style. Match only its size to the scene and give it a contact shadow "
    "where it touches. Everything else in the first reference image stays "
    "exactly as it is: the room, the light, the other figures.")


# Das Sprachmodell antwortet auf "worin spiegelt es sich" gern mit dem
# blossen Gegenstand: "the window". Eingesetzt ergaebe das "as a reflection
# the window". Fehlt das Verhaeltniswort, kommt "in" davor.
VORWORT = ("in", "on", "at", "against", "across", "behind", "inside",
           "within", "over", "under", "through", "above", "below", "off")


def _worin(wo: str) -> str:
    text = (wo or "").strip().rstrip(". ")
    if not text:
        return "in the window"
    if text.split()[0].lower() in VORWORT:
        return text
    return f"in {text}"


def _stil(schluessel: str) -> str:
    eintrag = STYLES.get(schluessel or "")
    if not eintrag:
        return ""
    text = eintrag[1]
    if schluessel in GEZEICHNET:
        text += " Not a photograph."
    return text


def _mit_stil(text: str, stil: str) -> str:
    zusatz = _stil(stil)
    return f"{text.rstrip('. ')}, {bausteine._klein(zusatz)}" if zusatz \
        else text


def kulisse_prompt(ort: dict | None, aus_plan: str, stil: str) -> str:
    """Der Raum allein. Der Baustein schlaegt die Lesung des Satzes: er ist
    das, was der Benutzer festgelegt hat."""
    if ort:
        text = bausteine.einsetzen(ort.get("prompt") or "",
                                   ort.get("variablen") or {}).rstrip(".")
        eigen = bausteine.eigener_stil(ort)
        if eigen:
            return f"{text}, {bausteine._klein(eigen)}"
        return _mit_stil(text, stil)
    if not (aus_plan or "").strip():
        return ""
    # Weit genug, dass der Boden zu sehen ist. Sonst hat eine Figur, die
    # neben dem Bett stehen soll, keine Stelle, auf die sie gehoert -- und
    # das Modell setzt sie aufs Bett, weil dort Platz im Bild ist.
    return _mit_stil(f"a wide shot of an empty room, no people in the "
                     f"picture, the floor visible across the whole width, "
                     f"{aus_plan.strip().rstrip('.')}", stil)


def pose_prompt(person: dict, pose: str) -> str:
    """Die Figur in der Haltung dieser Szene, freigestellt.

    Die Haltung steht vorn, nicht hinten: das Modell haengt die Komposition
    am Anfang des Prompts auf. Hinten angehaengt kam sie gegen das
    Musterbild nicht an, und die Figur stand weiter aufrecht da.

    Der eigene Stil des Bausteins bleibt daran haengen -- er gehoert der
    Figur, nicht dem Bild, und ueberlebt so das Zusammensetzen.
    """
    text = bausteine.person_text(person, person.get("variablen") or {})
    if not text.strip():
        return ""
    haltung = (pose or "").strip().rstrip(".")
    kopf = f"a full-body shot of one person, {haltung}" if haltung \
        else "a full-body shot of one person"
    return f"{kopf}. {text.rstrip('. ')}. {FREI}"


# Die Bildseiten, in der Reihenfolge, in der sie vergeben werden.
SEITEN = ("on the left", "on the right", "in the middle",
          "at the left edge", "at the right edge")


def _seite_von(text: str) -> str:
    """Welche Bildseite eine Ortsangabe nennt, falls eine darin steht."""
    klein = (text or "").lower()
    for seite in SEITEN:
        if seite in klein:
            return seite
    return ""


def _andere_seite(stelle: str, belegt: list[str]) -> str:
    """Eine schon vergebene Bildseite gegen eine freie tauschen."""
    seiten = [_seite_von(t) for t in belegt]
    meine = _seite_von(stelle)
    if meine and meine not in seiten:
        return stelle
    frei = next((s for s in SEITEN if s not in seiten), "")
    if not frei:
        return stelle
    if meine:
        return stelle.replace(meine, frei, 1)
    return f"{frei}, {stelle}"


def _feld_von(eintrag, feld: str) -> str:
    """Ein Feld aus einem Planeintrag, oder leer."""
    if not isinstance(eintrag, dict):
        return ""
    return (eintrag.get(feld) or "").strip().rstrip(".")


def _pose_von(eintrag) -> str:
    """Die Haltung aus einem Planeintrag, oder leer."""
    return _feld_von(eintrag, "pose")


def schritte(plan: dict, teile: list[dict], stil: str = "") -> list[dict]:
    """Der Bauplan als Liste von Stufen.

    Jede Stufe sagt, was sie erzeugt (`art`), mit welchem Prompt, welche
    frueheren Stufen ihr als Vorlage dienen (`vorlagen`, Stellen in dieser
    Liste) und welchem Baustein das Bild gehoert (`baustein`).
    """
    nach_id = {b["id"]: b for b in teile}
    nach_name = {b["name"].lower(): b for b in teile}
    personen = [b for b in teile if b.get("art") == "person"]
    ort = next((b for b in teile if b.get("art") == "ort"), None)

    folge: list[dict] = []

    kulisse = kulisse_prompt(ort, plan.get("kulisse") or "", stil)
    if not kulisse:
        return []
    folge.append({"art": "kulisse", "titel": "Kulisse", "prompt": kulisse,
                  "baustein": (ort or {}).get("id", ""),
                  "feld": "", "vorlagen": [], "aktion": ""})

    # --- Je Figur eine Pose ------------------------------------------
    # Wer keine eigene Haltung hat, braucht kein neues Bild: sein
    # Musterbild zeigt ihn bereits stehend und freigestellt. Ein Schritt
    # weniger ist anderthalb Minuten weniger.
    posen = {}
    nach_plan = {str(f.get("name") or "").lower(): f
                 for f in (plan.get("figuren") or [])}
    for person in personen:
        haltung = _pose_von(nach_plan.get(person["name"].lower()))
        posen[person["id"]] = len(folge)
        if not haltung:
            folge.append({"art": "figur",
                          "titel": f"Musterbild: {person['name']}",
                          "prompt": "", "baustein": "", "feld": "",
                          "vorlagen": [], "aktion": "",
                          "vorhanden": "musterbild:" + person["id"]})
            continue
        folge.append({"art": "figur", "titel": f"Pose: {person['name']}",
                      "prompt": pose_prompt(person, haltung),
                      "baustein": person["id"], "feld": "posen",
                      "vorlagen": [], "aktion": ""})

    # --- Die Spiegelung als eigenes Bild -------------------------------
    spiegel = plan.get("spiegelung") or {}
    spiegel_stelle = None
    if (spiegel.get("wo") or "").strip():
        wer = nach_name.get(str(spiegel.get("name") or "").lower())
        if wer and wer.get("art") == "person":
            gesicht = bausteine.person_text(
                wer, wer.get("variablen") or {}, nur_gesicht=True)
            vorlage = []
            besitzer, feld = wer["id"], "spiegelbilder"
        else:
            # Niemand aus dem Katalog: dann eben ein Gesicht, das zur Szene
            # passt. Es gehoert keinem Baustein und bleibt beim Bild.
            gesicht = "the face of a woman"
            vorlage, besitzer, feld = [], "", ""
        if gesicht.strip():
            spiegel_stelle = len(folge)
            folge.append({"art": "spiegelung", "titel": "Spiegelbild",
                          "prompt": f"{gesicht.rstrip('. ')}, {SPIEGEL_BILD}",
                          "baustein": besitzer, "feld": feld,
                          "vorlagen": vorlage, "aktion": ""})

    # --- Zusammensetzen, eine Figur nach der anderen --------------------
    belegt: list[str] = []
    # Nacheinander statt alles auf einmal: das Modell nimmt hoechstens vier
    # Vorlagen, und es haelt zwei Bilder besser auseinander als fuenf.
    stand = 0
    for person in personen:
        if person["id"] not in posen:
            continue
        eintrag = nach_plan.get(person["name"].lower())
        wohin = _pose_von(eintrag) or "standing upright"
        stelle = _feld_von(eintrag, "platz") \
            or "in the middle of the picture, standing on the floor"
        # Zwei Figuren auf derselben Bildseite stehen uebereinander, und
        # die hintere verschwindet: beim Einsetzen der zweiten sieht das
        # Modell die erste als Platz, nicht als Hindernis.
        stelle = _andere_seite(stelle, belegt)
        belegt.append(stelle)
        folge.append({"art": "setzen", "titel": f"Einsetzen: {person['name']}",
                      "prompt": SETZEN.format(pose=wohin, platz=stelle),
                      "baustein": "", "feld": "",
                      "vorlagen": [stand, posen[person["id"]]],
                      "aktion": "einsetzen"})
        stand = len(folge) - 1

    if spiegel_stelle is not None:
        folge.append({"art": "setzen", "titel": "Spiegelung einsetzen",
                      "prompt": SPIEGEL_SETZEN.format(
                          wo=_worin(spiegel.get("wo"))),
                      "baustein": "", "feld": "",
                      "vorlagen": [stand, spiegel_stelle],
                      "aktion": "einsetzen"})
        stand = len(folge) - 1

    for i, schritt in enumerate(folge):
        schritt["nr"] = i
        schritt["ergebnis"] = i == stand
    return folge


def uebersicht(folge: list[dict]) -> list[dict]:
    """Was die Oberflaeche vor dem Start zeigt: Titel und Prompt je Stufe."""
    return [{"nr": s["nr"], "titel": s["titel"], "art": s["art"],
             "prompt": s["prompt"], "ergebnis": s["ergebnis"]}
            for s in folge]
