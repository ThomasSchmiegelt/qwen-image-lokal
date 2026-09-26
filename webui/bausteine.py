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
import time

import projekte

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


def speichern(projekt: str, baustein: dict) -> dict:
    """Legt einen Baustein an oder ersetzt einen vorhandenen."""
    art = baustein.get("art") if baustein.get("art") in ARTEN else "person"
    name = (baustein.get("name") or "").strip() or "ohne Namen"
    prompt = (baustein.get("prompt") or "").strip()
    kennung = (baustein.get("id") or "").strip() or f"{art}-{int(time.time() * 1000)}"

    # Nur Vorgaben zu Luecken, die es auch gibt -- sonst sammeln sich Reste
    # von Prompts an, die laengst umgeschrieben wurden.
    offen = variablen(prompt)
    roh = baustein.get("variablen") or {}
    vorgaben = {k: str(roh.get(k) or "").strip() for k in offen}

    neu = {"id": kennung, "art": art, "name": name, "prompt": prompt,
           "variablen": vorgaben, "bild": baustein.get("bild") or ""}

    daten = [b for b in liste(projekt) if b.get("id") != kennung]
    # Ein vorhandenes Bild nicht verlieren, wenn der Aufrufer keines mitschickt.
    for alt in liste(projekt):
        if alt.get("id") == kennung and not neu["bild"]:
            neu["bild"] = alt.get("bild") or ""
    daten.append(neu)
    _schreiben(projekt, daten)
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


def zusammensetzen(teile: list[dict], werte: dict | None = None) -> str:
    """Person, Ort und Gegenstand zu einem Prompt verbinden.

    Die Reihenfolge ist Person, Gegenstand, Ort -- erst wer, dann womit, dann
    wo. Das Modell haengt die Bildkomposition am ersten Satzglied auf, und ein
    Ort am Anfang draengt die Person an den Rand.
    """
    werte = werte or {}
    reihung = {"person": 0, "gegenstand": 1, "ort": 2, "szene": 3}
    geordnet = sorted(teile, key=lambda b: reihung.get(b.get("art"), 9))
    stuecke = [einsetzen(b.get("prompt") or "", werte) for b in geordnet]
    stuecke = [s.rstrip(".") for s in stuecke if s]
    return ", ".join([stuecke[0]] + [_klein(s) for s in stuecke[1:]]) if stuecke else ""
