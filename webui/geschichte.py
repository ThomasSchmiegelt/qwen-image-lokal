"""Aus einer Handlung eine Bildfolge machen.

Eingabe ist ein deutscher Text -- was passiert -- und eine Auswahl aus den
Bausteinen des Projekts: wer vorkommt, wo es spielt, welche Gegenstaende eine
Rolle spielen. Das Sprachmodell zerlegt die Handlung in Szenen und sagt zu
jeder, wer darin vorkommt, was geschieht, wie die Person schaut und in
welchem Stil.

Herauskommt die Blockstruktur aus `ablauf.py`. Damit greift alles, was es
schon gibt: der Block-Editor zum Gegenlesen, `schritte()`, der Ablauflauf und
der Videobau. Eine Geschichte ist also nur eine besonders bequeme Art, einen
Ablauf zu schreiben.

Alle Szenen setzen auf dem Startbild auf, nicht aufeinander. Sonst wandert
die Person von Szene zu Szene immer weiter weg von sich selbst -- gemessen
war das schon bei den Abwandlungen der Grund, den Bezug beim Ausgangsbild zu
lassen.
"""

import re

import bausteine
from kataloge import MIMIK, STYLES

# Wie die Person bewahrt wird, waehrend Ort, Handlung und Stil wechseln.
BLEIBT = "the person, their face and their build"


def _stil(schluessel: str) -> str:
    eintrag = STYLES.get(schluessel)
    return eintrag[1] if eintrag else ""


def _mimik(schluessel: str) -> str:
    eintrag = MIMIK.get(schluessel)
    return eintrag[1] if eintrag else ""


def _ohne_namen(text: str, teile) -> str:
    """Streicht die Namen der Bausteine aus der Handlung.

    Danach bleibt ein Satz wie "smiles happily holding a basket" -- wer das
    tut, sagt der Baustein davor.
    """
    for b in teile:
        name = (b.get("name") or "").strip()
        if len(name) < 3:
            continue
        text = re.sub(rf"\b{re.escape(name)}\b\s*", "", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip().lstrip(",").strip()


def szene_zu_text(szene: dict, nach_kennung: dict) -> str:
    """Eine Szene als ein Prompt-Baustein.

    Reihenfolge: wer und wie er schaut, was er tut, womit, wo, in welchem
    Stil. Das Modell haengt die Bildkomposition am Anfang auf, deshalb steht
    die Person vorn und der Stil zum Schluss.
    """
    stuecke = []
    person = nach_kennung.get(szene.get("person"))
    if person:
        stuecke.append(bausteine.einsetzen(person.get("prompt") or "",
                                           person.get("variablen") or {}))
    ausdruck = _mimik(szene.get("mimik") or "")
    if ausdruck:
        stuecke.append(ausdruck)

    # Namen gehoeren nicht in den Prompt: wer gemeint ist, steht schon in der
    # Beschreibung des Bausteins, und "Anna" bringt das Modell allenfalls
    # dazu, den Namen ins Bild zu schreiben.
    handlung = _ohne_namen((szene.get("handlung") or "").strip().rstrip("."),
                           nach_kennung.values())
    if handlung:
        stuecke.append(handlung)

    gegenstand = nach_kennung.get(szene.get("gegenstand"))
    if gegenstand:
        stuecke.append(bausteine.einsetzen(gegenstand.get("prompt") or "",
                                           gegenstand.get("variablen") or {}))
    ort = nach_kennung.get(szene.get("ort"))
    if ort:
        stuecke.append(bausteine.einsetzen(ort.get("prompt") or "",
                                           ort.get("variablen") or {}))
    stil = _stil(szene.get("stil") or "")
    if stil:
        stuecke.append(stil)

    sauber = [t.strip().rstrip(".") for t in stuecke if t and t.strip()]
    if not sauber:
        return ""
    return ", ".join([sauber[0]] + [bausteine._klein(t) for t in sauber[1:]])


def zu_bloecken(szenen: list[dict], teile: list[dict]) -> list[dict]:
    """Die Szenen als Bloecke, wie der Ablauf-Reiter sie erwartet.

    Ein Block je Stil: aufeinanderfolgende Szenen im selben Stil teilen sich
    einen, weil sie ohnehin denselben Bezug haben und so in einem Ladevorgang
    durchlaufen. Der Titel nennt den Stil, damit der Block im Editor
    wiedererkennbar ist.
    """
    nach_kennung = {b["id"]: b for b in teile}
    bloecke: list[dict] = []
    for szene in szenen:
        text = szene_zu_text(szene, nach_kennung)
        if not text:
            continue
        stil = szene.get("stil") or ""
        name = STYLES[stil][0] if stil in STYLES else "Szene"
        if bloecke and bloecke[-1]["stil"] == stil:
            bloecke[-1]["bausteine"].append(text)
        else:
            bloecke.append({"titel": name, "referenz": "start",
                            "vorlage": "verwandeln", "bleibt": BLEIBT,
                            "zurueck": False, "stil": stil,
                            "bausteine": [text]})
    # `stil` ist nur die Hilfsgroesse fuers Buendeln und hat im Block nichts
    # zu suchen -- der Editor kennt das Feld nicht.
    for block in bloecke:
        block.pop("stil", None)
    return bloecke


def startbild(szenen: list[dict], teile: list[dict]) -> str:
    """Das Bild der Person, die am haeufigsten vorkommt -- falls sie eines hat.

    Damit setzt der Ablauf auf einem Gesicht auf, statt eines zu erfinden.
    """
    haeufig: dict[str, int] = {}
    for szene in szenen:
        kennung = szene.get("person")
        if kennung:
            haeufig[kennung] = haeufig.get(kennung, 0) + 1
    if not haeufig:
        return ""
    beste = max(haeufig, key=lambda k: haeufig[k])
    for b in teile:
        if b["id"] == beste:
            return b.get("bild") or ""
    return ""
