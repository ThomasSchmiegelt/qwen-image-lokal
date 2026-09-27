"""Bausteine: Personen, Orte und Gegenstaende zum Wiederverwenden.

Ein Baustein ist ein Stueck Prompt mit einem Namen, einem Bild und Luecken:

    { "id": "person-anna",
      "art": "person",
      "name": "Anna",
      "prompt": "a woman in her thirties, short dark hair, {kleidung}, {schuhe}",
      "variablen": {"kleidung": "a red wool coat", "schuhe": "brown leather boots"},
      "bild": "20260926-101500_t2i_01_seed42.png" }

Die Luecken in geschweiften Klammern werden beim Benutzen gefuellt; was in
`variablen` steht, ist nur die Vorgabe. Genau das macht eine Serie moeglich,
in der dieselbe Person vier Jacken durchprobiert.

Gespeichert wird je Projekt in `bausteine.json`. Bausteine gehoeren zum
Vorhaben, nicht zum Programm -- wer ein Projekt loescht, wird sie auch los.
"""

import json
import os
import re
import shutil
import time

import projekte
from kataloge import GEZEICHNET, NICHT_FOTO, STYLES

# "szene" entsteht nicht von Hand, sondern beim Zusammenstellen: die fertige
# Mischung aus Person, Gegenstand und Ort, mit ihren Luecken, ihrem Bild und
# den Werten, mit denen sie erzeugt wurde. Damit laesst sie sich spaeter
# wiederholen oder weiterverwenden.
ARTEN = {"person": "Person", "ort": "Ort", "gegenstand": "Gegenstand",
         "szene": "Szene"}

# Eine Luecke: {kleidung}. Nur schlichte Namen, damit sich nichts mit den
# geschweiften Klammern beisst, die in Prompt-Vorlagen vorkommen.
LUECKE = re.compile(r"\{([a-zA-Z][a-zA-Z0-9_]{0,29})\}")


def _datei(projekt: str) -> str:
    return os.path.join(projekte.ordner(projekt), "bausteine.json")


def liste(projekt: str) -> list[dict]:
    """Alle Bausteine eines Projekts, nach Art und Namen sortiert."""
    try:
        with open(_datei(projekt), encoding="utf-8") as fh:
            daten = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(daten, list):
        return []
    reihung = list(ARTEN)
    return sorted((b for b in daten if isinstance(b, dict)),
                  key=lambda b: (reihung.index(b.get("art"))
                                 if b.get("art") in ARTEN else 9,
                                 (b.get("name") or "").lower()))


def _schreiben(projekt: str, daten: list[dict]) -> None:
    with open(_datei(projekt), "w", encoding="utf-8") as fh:
        json.dump(daten, fh, ensure_ascii=False, indent=2)


def variablen(prompt: str) -> list[str]:
    """Die Luecken eines Prompts, in der Reihenfolge ihres Auftretens."""
    gesehen, raus = set(), []
    for name in LUECKE.findall(prompt or ""):
        if name not in gesehen:
            gesehen.add(name)
            raus.append(name)
    return raus


# Eine Luecke samt dem Bindewort davor. Faellt die Luecke weg, muss das Wort
# mit -- "made of {material}" ohne Material ergaebe sonst "made of ,".
# Mehrwortige zuerst: in der Alternative gewinnt der erste Treffer, sonst
# schnappt "of" zu und von "made of" bliebe "made" stehen.
VERBINDER = "|".join((
    r"made\s+of", r"in\s+front\s+of", r"next\s+to", r"dressed\s+in",
    "featuring", "carrying", "standing", "wearing", "holding", "showing",
    "against", "between", "through", "outside", "beneath", "besides",
    "during", "beside", "behind", "inside", "around", "across", "above",
    "under", "over", "near", "onto", "into", "with", "from", "and",
    "for", "of", "in", "on", "at", "by", "to",
))
LUECKE_MIT = re.compile(r"(\s*\b(?:" + VERBINDER + r")\b)?\s*"
                        r"\{([a-zA-Z][a-zA-Z0-9_]{0,29})\}")


def einsetzen(prompt: str, werte: dict | None = None) -> str:
    """Fuellt die Luecken und raeumt auf, was eine leere Luecke hinterlaesst.

    Ohne Aufraeumen bliebe von "a basket made of {material}, featuring
    {farbe}" bei leeren Werten "a basket made of , featuring ." stehen. Das
    Bindewort faellt deshalb mit der Luecke, und haengende Satzzeichen danach
    ebenso.
    """
    werte = werte or {}

    def ersatz(treffer):
        wert = str(werte.get(treffer.group(2), "") or "").strip()
        if not wert:
            return ""
        # Das Leerzeichen immer selbst setzen: der Ausdruck verschluckt es vor
        # der Luecke auch dann, wenn gar kein Bindewort davorstand -- aus
        # "under {wetter}" wurde sonst "undersunny". Doppelte werden unten
        # wieder eingedampft.
        return (treffer.group(1) or "") + " " + wert

    text = LUECKE_MIT.sub(ersatz, prompt or "")
    text = re.sub(r"\s*,\s*(?=[,.])", "", text)        # leere Aufzaehlungsglieder
    text = re.sub(r"\s*,\s*(?=$)", "", text)           # haengendes Komma am Ende
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = re.sub(r"[\s,]+\.", ".", text)              # " ." und " , ."
    # Ein Bindewort am Schluss hat sein Ziel verloren.
    text = re.sub(r"\s+\b(?:" + VERBINDER + r")\b\s*[.,]?\s*$", "", text)
    return text.strip().strip(",").strip()


def _klein(text: str) -> str:
    """Den Satzanfang kleinschreiben, wenn es nur Satzanfang war.

    Die Teile werden aneinandergehaengt; ein "A woven basket" mitten im Satz
    sieht falsch aus. Ein durchgaengig grosses Wort oder ein Name bleibt.
    """
    erstes = text.split(" ", 1)[0]
    # Ein Kuerzel wie CAD oder NASA bleibt. Alles andere -- auch ein einzelnes
    # "A" -- wird klein; das zweite Zeichen zu pruefen ging daneben, weil dort
    # bei "A woven" ein Leerzeichen steht.
    if text[:1].isupper() and not (len(erstes) > 1 and erstes.isupper()):
        return text[0].lower() + text[1:]
    return text


def _freie_kennung(art: str, daten: list[dict]) -> str:
    """Eine Kennung, die es noch nicht gibt.

    Die Millisekunde allein genuegt nicht: zwei Speichervorgaenge im selben
    Augenblick bekaemen dieselbe, und der zweite ueberschriebe den ersten.
    """
    vergeben = {b.get("id") for b in daten}
    stamm = f"{art}-{int(time.time() * 1000)}"
    kennung, n = stamm, 2
    while kennung in vergeben:
        kennung, n = f"{stamm}-{n}", n + 1
    return kennung


def speichern(projekt: str, baustein: dict) -> dict:
    """Legt einen Baustein an oder ersetzt einen vorhandenen."""
    art = baustein.get("art") if baustein.get("art") in ARTEN else "person"
    name = (baustein.get("name") or "").strip() or "ohne Namen"
    prompt = (baustein.get("prompt") or "").strip()
    daten = liste(projekt)
    kennung = (baustein.get("id") or "").strip() or _freie_kennung(art, daten)

    # Nur Vorgaben zu Luecken, die es auch gibt -- sonst sammeln sich Reste
    # von Prompts an, die laengst umgeschrieben wurden.
    offen = variablen(prompt)
    roh = baustein.get("variablen") or {}
    vorgaben = {k: str(roh.get(k) or "").strip() for k in offen}

    # Bei einer Person drei getrennte Prompts: wer sie ist, wie ihr Gesicht
    # aussieht, was sie traegt. Eine Grossaufnahme braucht das Gesicht ohne
    # Kleiderbeschreibung, und eine Szene darf die Kleidung austauschen, ohne
    # die Person anzufassen.
    neu = {"id": kennung, "art": art, "name": name, "prompt": prompt,
           "gesicht": (baustein.get("gesicht") or "").strip(),
           "kleidung": (baustein.get("kleidung") or "").strip(),
           # Der Stil gehoert zum Musterbild, nicht zum Baustein: er sagt,
           # wie das Bild entstanden ist. Der Prompt selbst bleibt stilfrei,
           # damit dieselbe Person in der naechsten Geschichte als Manga
           # auftreten kann.
           "stil": (baustein.get("stil") or "").strip(),
           "variablen": vorgaben, "bild": baustein.get("bild") or ""}

    # Nichts verlieren, was der Aufrufer nicht mitschickt.
    for vorher in daten:
        if vorher.get("id") != kennung:
            continue
        for feld in ("bild", "gesicht", "kleidung", "stil"):
            if not neu[feld]:
                neu[feld] = vorher.get(feld) or ""
    rest = [b for b in daten if b.get("id") != kennung]
    rest.append(neu)
    _schreiben(projekt, rest)
    return neu


def loeschen(projekt: str, kennung: str) -> bool:
    daten = liste(projekt)
    rest = [b for b in daten if b.get("id") != kennung]
    if len(rest) == len(daten):
        return False
    _schreiben(projekt, rest)
    return True


def bild_setzen(projekt: str, kennung: str, datei: str) -> bool:
    """Haengt das erzeugte Bild an den Baustein. Ruft der Auftragslauf auf,
    wenn ein Auftrag mit einer Bausteinkennung fertig geworden ist."""
    daten = liste(projekt)
    for b in daten:
        if b.get("id") == kennung:
            b["bild"] = datei
            _schreiben(projekt, daten)
            return True
    return False


def vorlage(teile: list[dict]) -> str:
    """Dieselbe Mischung, aber mit offenen Luecken.

    Was beim Zusammenstellen als Szene gespeichert wird, soll wieder Luecken
    haben -- sonst liesse sich die Person darin nie wieder umziehen.
    """
    reihung = {"person": 0, "gegenstand": 1, "ort": 2, "szene": 3}
    geordnet = sorted(teile, key=lambda b: reihung.get(b.get("art"), 9))
    stuecke = [(b.get("prompt") or "").strip().rstrip(".") for b in geordnet]
    stuecke = [t for t in stuecke if t]
    return ", ".join([stuecke[0]] + [_klein(t) for t in stuecke[1:]]) if stuecke else ""


def ohne_leere_luecken(prompt: str, werte: dict) -> tuple[str, dict]:
    """Luecken ohne Vorgabe aus dem Prompt herausnehmen.

    Das Sprachmodell setzt manchmal eine Luecke und liefert nichts dazu --
    "a cube with a {blue} glow" mit leerem Wert. Fuer einen Baustein, den
    jemand von Hand angelegt hat, mag das angehen; fuer einen automatisch
    vorgeschlagenen ist es eine Falle, die erst im Bild auffaellt.
    """
    leer = [k for k, v in (werte or {}).items() if not str(v or "").strip()]
    if not leer:
        return prompt, dict(werte or {})
    # einsetzen() raeumt Bindewort und Satzzeichen gleich mit weg.
    sauber = einsetzen(prompt, {k: "" for k in leer})
    return sauber, {k: v for k, v in werte.items() if k not in leer}


def zusammensetzen(teile: list[dict], werte: dict | None = None) -> str:
    """Person, Ort und Gegenstand zu einem Prompt verbinden.

    Die Reihenfolge ist Person, Gegenstand, Ort -- erst wer, dann womit, dann
    wo. Das Modell haengt die Bildkomposition am ersten Satzglied auf, und ein
    Ort am Anfang draengt die Person an den Rand.
    """
    werte = werte or {}
    reihung = {"person": 0, "gegenstand": 1, "ort": 2, "szene": 3}
    geordnet = sorted(teile, key=lambda b: reihung.get(b.get("art"), 9))
    # Eine Person kommt angezogen: die Vorzugskleidung steht seit der Trennung
    # in einem eigenen Feld, und ohne sie erfindet das Modell eine.
    stuecke = [person_text(b, werte) if b.get("art") == "person"
               else einsetzen(b.get("prompt") or "", werte) for b in geordnet]
    stuecke = [s.rstrip(".") for s in stuecke if s]
    return ", ".join([stuecke[0]] + [_klein(s) for s in stuecke[1:]]) if stuecke else ""


# Das Bild zu einem Baustein ist ein Musterbild, keine Szene: es zeigt, wen
# oder was man spaeter einsetzt. Deshalb ganz und vor nichts -- ein Baustein,
# der halb hinter einem Tisch steht, taugt weder zum Wiedererkennen noch als
# Vorlage fuer ein Folgebild.
FREISTELLEN = {
    "person": ("full body from head to toe, the whole figure inside the frame "
               "with room above and below, standing upright and facing the "
               "camera, on a plain seamless neutral grey background, even "
               "studio lighting, no room, no furniture, no scenery, no props"),
    "gegenstand": ("the entire object inside the frame, seen at a slight "
                   "angle, on a plain seamless neutral grey background, even "
                   "studio lighting, no surroundings, no hands, no props"),
}


def mit_stil(prompt: str, stil: str) -> str:
    """Den Stil an ein Musterbild haengen.

    Nur ans Bild, nie an den Baustein: die Person soll in der naechsten
    Geschichte als Manga auftreten duerfen, auch wenn ihr erstes Bild ein
    Foto war.
    """
    eintrag = STYLES.get(stil or "")
    prompt = (prompt or "").strip().rstrip(".")
    if not eintrag or not prompt:
        return prompt
    text = f"{prompt}, {eintrag[1]}"
    if stil in GEZEICHNET:
        text += f" {NICHT_FOTO}"
    return text


def freigestellt(prompt: str, art: str) -> str:
    """Den Prompt eines Musterbildes vor einen neutralen Hintergrund stellen.

    Nur Personen und Gegenstaende. Ein Ort *ist* der Hintergrund -- ihn
    freizustellen ergibt ein leeres Bild.
    """
    zusatz = FREISTELLEN.get(art)
    prompt = (prompt or "").strip().rstrip(".")
    if not zusatz or not prompt:
        return prompt
    return f"{prompt}, {zusatz}"


# --- Katalog ueber alle Projekte -----------------------------------------
def katalog() -> list[dict]:
    """Alle Bausteine aller Projekte, jeder mit seiner Herkunft.

    Die Bibliothek wird mit der Zeit groesser als ein Projekt: wer eine Person
    einmal beschrieben hat, will sie im naechsten Vorhaben wiedersehen, ohne
    sie neu zu bauen.
    """
    raus = []
    for projekt in projekte.liste():
        for b in liste(projekt["key"]):
            raus.append({**b, "projekt": projekt["key"],
                         "projektname": projekt["label"]})
    return raus


def kopieren(von: str, nach: str, kennung: str) -> dict | None:
    """Einen Baustein in ein anderes Projekt uebernehmen.

    Das Bild wandert mit: es liegt im Bildordner des Ursprungsprojekts, und
    ein Verweis dorthin waere nach dem Loeschen jenes Projekts tot. Lieber
    eine Kopie, die zum neuen Projekt gehoert.
    """
    if von == nach:
        return None
    quelle = next((b for b in liste(von) if b.get("id") == kennung), None)
    if not quelle:
        return None

    bild = quelle.get("bild") or ""
    if bild:
        herkunft = os.path.join(projekte.bilder(von), os.path.basename(bild))
        ziel = os.path.join(projekte.bilder(nach), os.path.basename(bild))
        if os.path.isfile(herkunft) and not os.path.isfile(ziel):
            shutil.copy2(herkunft, ziel)
        elif not os.path.isfile(herkunft):
            bild = ""                     # Bild ist weg, Baustein bleibt

    # Ohne Kennung: das Ziel vergibt eine eigene, sonst kollidierte sie mit
    # einem gleich benannten Baustein, der dort schon liegt.
    return speichern(nach, {"art": quelle.get("art"), "name": quelle.get("name"),
                            "prompt": quelle.get("prompt"),
                            "variablen": quelle.get("variablen"), "bild": bild})



def person_text(b: dict, werte: dict | None = None, nur_gesicht: bool = False,
                kleidung: str = "") -> str:
    """Die Beschreibung einer Person fuer einen Prompt.

    `nur_gesicht` nimmt die Gesichtsbeschreibung allein -- eine Makro-
    Grossaufnahme braucht keine Hose. `kleidung` ersetzt die bevorzugte
    Kleidung, wenn die Szene eine andere verlangt.
    """
    if nur_gesicht and (b.get("gesicht") or "").strip():
        return einsetzen(b["gesicht"], werte)
    stuecke = [einsetzen(b.get("prompt") or "", werte).rstrip(".")]
    if not nur_gesicht:
        was = (kleidung or b.get("kleidung") or "").strip()
        if was:
            # Die Kleidung haengt mitten im Satz -- ein grosses "Worn wool
            # coat" dort liest sich wie ein neuer Anfang.
            stuecke.append(_klein(einsetzen(was, werte).rstrip(".")))
    return ", ".join(t for t in stuecke if t)
