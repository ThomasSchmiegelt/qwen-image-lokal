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

import json
import os
import random
import re
import time

import bausteine
import projekte
from kataloge import (
    CAMERAS, GEZEICHNET, HALTUNGEN, MIMIK, NICHT_FOTO, STYLES, VIEWS,
)

# Wie die Person bewahrt wird, waehrend Ort, Handlung und Stil wechseln.
BLEIBT = "the person's face, hair and build"


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
                            "vorlage": "geschichte", "bleibt": BLEIBT,
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



# --- Gliederung ----------------------------------------------------------
# Der zweite Weg zur Geschichte: das Inhaltsverzeichnis steht zuerst. Je Zeile
# eine Szene, mit /Name auf einen Baustein verweisend, der Ort daneben, der
# Stil fuer die ganze Folge. Erst danach schreibt das Sprachmodell die
# Prompts -- es hat dann nur noch eine Aufgabe statt drei.

VERWEIS = re.compile(r"/([A-Za-zÄÖÜäöüß][\wÄÖÜäöüß-]{1,39})")


def verweise(zeile: str, teile: list[dict]) -> tuple[str, list[dict]]:
    """Loest /Name gegen die Bausteine auf.

    Zurueck kommt die Zeile ohne die Schraegstriche -- damit sie sich lesen
    laesst -- und die gefundenen Bausteine. Ein Name, den es nicht gibt,
    bleibt als Wort stehen; stillschweigend verschlucken waere schlimmer als
    ihn im Text zu lassen.
    """
    nach_name = {(b.get("name") or "").lower(): b for b in teile}
    gefunden, gesehen = [], set()

    def ersatz(treffer):
        b = nach_name.get(treffer.group(1).lower())
        if not b:
            return treffer.group(0)
        if b["id"] not in gesehen:
            gesehen.add(b["id"])
            gefunden.append(b)
        return b.get("name") or treffer.group(1)

    return VERWEIS.sub(ersatz, zeile or "").strip(), gefunden


def gliederung_zu_szenen(zeilen: list[dict], prompts: list[dict],
                         teile: list[dict], stil: str) -> list[dict]:
    """Die Gliederung und die geschriebenen Prompts zu Szenen zusammenfuehren.

    Die Zuordnung Person/Ort/Gegenstand kommt aus der Gliederung, nicht vom
    Sprachmodell -- der Benutzer hat sie ja selbst festgelegt.
    """
    nach_nr = {p.get("nr"): p for p in prompts}
    szenen = []
    for i, zeile in enumerate(zeilen, 1):
        p = nach_nr.get(i) or {}
        text = p.get("prompt") or ""
        if not text:
            continue
        benutzt = {b["id"]: b for b in (zeile.get("teile") or [])}
        def erster(art):
            return next((k for k, b in benutzt.items() if b.get("art") == art), "")
        szenen.append({
            "titel": (zeile.get("text") or "")[:60] or f"Bild {i}",
            "person": erster("person"),
            "ort": zeile.get("ort") or erster("ort"),
            "gegenstand": erster("gegenstand"),
            "handlung": text,
            "mimik": p.get("mimik") or "",
            "stil": stil,
        })
    return szenen



# --- Mehrere Bilder je Szene --------------------------------------------
# Gewuerfelt wird nur der Blick auf den Augenblick: Objektiv oder Standpunkt.
# Und davon genau eines je Bild.
#
# Nicht gewuerfelt werden Stil, Ort, Farbstimmung und Kleidung -- die gehoeren
# der Geschichte, nicht dem Zufall. Ausdruecklich auch nicht die Kameraart:
# eine gewuerfelte Ueberwachungskamera machte aus einem Manga mittendrin ein
# Lichtbild. Und nicht die Koerperhaltung: die Szene sagt schon, was die
# Person tut, und "rennend" plus "mit verschraenkten Armen" ergibt wieder den
# Widerspruch, der anderswo die doppelten Gliedmassen erzeugt hat.
STREUACHSEN = (CAMERAS, VIEWS)


def streuung(text: str, anzahl: int, seed: int, stil: str = "") -> list[str]:
    """`anzahl` Fassungen desselben Augenblicks.

    Die erste bleibt unangetastet -- sie ist die Szene, wie sie gemeint war.
    Die uebrigen bekommen je einen anderen Blick darauf.
    """
    anzahl = max(1, min(int(anzahl or 1), 20))
    fassungen = [text]
    if anzahl == 1:
        return fassungen
    rng = random.Random(seed)
    benutzt = set()
    for _ in range(anzahl - 1):
        # Genau eine Angabe je Bild, und moeglichst keine zweimal.
        tabelle = STREUACHSEN[rng.randrange(len(STREUACHSEN))]
        offen = [k for k in tabelle if (id(tabelle), k) not in benutzt] or list(tabelle)
        wahl = rng.choice(offen)
        benutzt.add((id(tabelle), wahl))
        fassungen.append(f"{text}, {tabelle[wahl][1]}")
    # Bei einem gezeichneten Stil ausdruecklich sagen, dass kein Foto
    # entsteht: die Objektivangaben ziehen sonst dorthin.
    if stil in GEZEICHNET:
        fassungen = [f"{f} {NICHT_FOTO}" for f in fassungen]
    return fassungen


def mit_streuung(bloecke: list[dict], je_szene: list[int], stil: str = "",
                 seed: int = 42) -> list[dict]:
    """Jede Szene eines Ablaufs auf ihre Bildzahl bringen.

    `je_szene` ist so lang wie die Szenenfolge; fehlt ein Wert, bleibt es bei
    einem Bild. Die Bloecke behalten ihre Struktur, nur ihre Bausteinliste
    waechst.
    """
    nr = 0
    for block in bloecke:
        neue = []
        for text in block.get("bausteine") or []:
            anzahl = je_szene[nr] if nr < len(je_szene) else 1
            neue += streuung(text, anzahl, seed + nr * 101, stil)
            nr += 1
        block["bausteine"] = neue
    return bloecke



# --- Zwischenspeicher ----------------------------------------------------
# Eine Geschichte entsteht nicht in einem Zug: umreissen, gliedern, Prompts
# schreiben lassen, nachbessern. Dazwischen soll man den Reiter verlassen
# duerfen, ohne alles zu verlieren. Je Projekt ein Stand -- mehrere
# Geschichten nebeneinander waeren eine eigene Verwaltung, und danach hat
# niemand gefragt.
def _stand_datei(projekt: str) -> str:
    return os.path.join(projekte.ordner(projekt), "geschichte.json")


FELDER = ("idee", "kurz", "titel", "stil", "welt", "fiktion", "modell",
          "zeilen", "prompts", "prosa")


def stand_lesen(projekt: str) -> dict:
    try:
        with open(_stand_datei(projekt), encoding="utf-8") as fh:
            daten = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return daten if isinstance(daten, dict) else {}


def stand_schreiben(projekt: str, daten: dict) -> dict:
    """Nur die bekannten Felder -- was die Seite sonst noch mitschickt,
    gehoert nicht in die Ablage."""
    stand = {k: daten.get(k) for k in FELDER if k in daten}
    stand["geaendert"] = time.strftime("%Y-%m-%d %H:%M")
    with open(_stand_datei(projekt), "w", encoding="utf-8") as fh:
        json.dump(stand, fh, ensure_ascii=False, indent=2)
    return stand


def offene_verweise(zeilen, teile: list[dict]) -> list[str]:
    """Namen mit Schraegstrich, zu denen es noch keinen Baustein gibt.

    Wer `/Nachbarin` schreibt, hat damit gesagt, dass es eine Nachbarin
    geben soll. Das ist eine Arbeitsanweisung und gehoert sichtbar in den
    Katalog, statt stillschweigend als Wort im Prompt zu landen.
    """
    bekannt = {(b.get("name") or "").lower() for b in teile}
    offen, gesehen = [], set()
    for z in zeilen or []:
        text = z if isinstance(z, str) else (z.get("text") or "")
        for name in VERWEIS.findall(text):
            klein = name.lower()
            if klein not in bekannt and klein not in gesehen:
                gesehen.add(klein)
                offen.append(name)
    return offen
