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
import torwache
import projekte
from kataloge import (
    CAMERAS, EINSTELLUNGEN, GEZEICHNET, HALTUNGEN, MIMIK, NICHT_FOTO,
    STYLES, VIEWS,
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
    """Streicht die Personennamen aus der Handlung.

    Danach bleibt ein Satz wie "smiles happily holding a basket" -- wer das
    tut, sagt der Baustein davor. Und "Anna" im Prompt bringt das Modell sonst
    dazu, den Namen ins Bild zu schreiben.

    Nur Personen. Orte und Gegenstaende heissen gern wie das, was sie sind --
    ein Ort "Deck" machte aus "runs across the deck" ein "runs across the".
    Dass der Ort zweimal im Prompt steht, stoert dagegen kein Bild.
    """
    for b in teile:
        if b.get("art") != "person":
            continue
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
    # Verlangt die Einstellung eine Grossaufnahme, zaehlt allein das Gesicht:
    # eine Hose im Prompt zieht die Kamera wieder zurueck. Der Ort faellt aus
    # demselben Grund weg.
    e = EINSTELLUNGEN.get(szene.get("einstellung") or "") or {}
    nur_gesicht = bool(e.get("nur_gesicht"))

    stuecke = []
    person = nach_kennung.get(szene.get("person"))
    if person:
        stuecke.append(bausteine.person_text(
            person, person.get("variablen") or {}, nur_gesicht=nur_gesicht,
            kleidung=szene.get("kleidung") or ""))
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
    if gegenstand and not nur_gesicht:
        stuecke.append(bausteine.einsetzen(gegenstand.get("prompt") or "",
                                           gegenstand.get("variablen") or {}))
    ort = nach_kennung.get(szene.get("ort"))
    if ort and not nur_gesicht:
        stuecke.append(bausteine.einsetzen(ort.get("prompt") or "",
                                           ort.get("variablen") or {}))
    stil = _stil(szene.get("stil") or "")
    if stil:
        stuecke.append(stil)

    sauber = [t.strip().rstrip(".") for t in stuecke if t and t.strip()]
    if not sauber:
        return ""
    return ", ".join([sauber[0]] + [bausteine._klein(t) for t in sauber[1:]])


def zu_bloecken(szenen: list[dict], teile: list[dict],
                eigene: dict | None = None) -> list[dict]:
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
        # Was diese Szene nicht zeigen soll, faellt hier heraus -- derselbe
        # Torwaechter wie beim einzelnen Auftrag.
        if (szene.get("ausschluss") or "").strip():
            text = torwache.torwaechter(text, szene["ausschluss"])[0]
        # Die Kameraeinstellung steht hinter der Szene: erst was zu sehen
        # ist, dann von wo aus. Ein Paar ergibt zwei Bilder.
        fassungen = mit_einstellung(text, szene.get("einstellung") or "",
                                    szene.get("spiegelung") or "", eigene)
        stil = szene.get("stil") or ""
        name = STYLES[stil][0] if stil in STYLES else "Szene"
        if bloecke and bloecke[-1]["stil"] == stil:
            bloecke[-1]["bausteine"] += fassungen
        else:
            bloecke.append({"titel": name, "referenz": "start",
                            "vorlage": "geschichte", "bleibt": BLEIBT,
                            "zurueck": False, "stil": stil,
                            "bausteine": list(fassungen)})
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


# Ein Baustein laesst sich gleich in der Szene erklaeren:
#   /Susi "weisse Frau, Mitte dreissig"
# Der Name steht wie immer hinter dem Schraegstrich, die Erklaerung in
# Anfuehrungszeichen dahinter. Sie ist eine Anweisung an das Programm und
# gehoert nicht in den Bildprompt -- sie wird deshalb herausgeschnitten.
DEFINITION = re.compile(
    r"/([A-Za-zÄÖÜäöüß][\wÄÖÜäöüß-]{1,39})\s*"
    r"""(?:"([^"]{0,200})"|„([^“]{0,200})“|»([^«]{0,200})«|'([^']{0,200})')""")


def definitionen(zeile: str) -> tuple[str, dict]:
    """Trennt die Erklaerungen ab. Zurueck: (Zeile ohne sie, {Name: Text}).

    Der /Name selbst bleibt stehen -- er ist der Verweis, und der wird noch
    gebraucht. Nur die Anfuehrungszeichen und was darin steht fallen weg.
    """
    gefunden = {}

    def ersatz(treffer):
        # Leere Anfuehrungszeichen sind das Angebot, etwas hineinzuschreiben.
        # Sie gehoeren so wenig in den Prompt wie eine gefuellte Erklaerung.
        text = next((g for g in treffer.groups()[1:] if g), "").strip()
        if text:
            gefunden[treffer.group(1)] = text
        return "/" + treffer.group(1)

    ohne = DEFINITION.sub(ersatz, zeile or "")
    return re.sub(r"\s{2,}", " ", ohne).strip(), gefunden


def verweise(zeile: str, teile: list[dict]) -> tuple[str, list[dict]]:
    """Loest /Name gegen die Bausteine auf.

    Zurueck kommt die Zeile ohne die Schraegstriche -- damit sie sich lesen
    laesst -- und die gefundenen Bausteine. Ein Name, den es nicht gibt,
    bleibt als Wort stehen; stillschweigend verschlucken waere schlimmer als
    ihn im Text zu lassen.
    """
    # Auch die Zweitnamen treffen den Baustein: dieselbe Figur heisst in
    # Szene drei anders als in Szene zwoelf.
    nach_name = {n.lower(): b for b in teile for n in bausteine.namen(b) if n}
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
            "einstellung": zeile.get("einstellung") or "",
            # Die uebersetzte Fassung schlaegt die getippte: beim Schreiben
            # der Prompts wurde sie schon ins Englische gebracht.
            "spiegelung": p.get("spiegelung") or zeile.get("spiegelung") or "",
            # Wie bei der Spiegelung: die uebersetzte Fassung schlaegt die
            # getippte, denn im Prompt steht Englisch.
            "ausschluss": p.get("ausschluss") or zeile.get("ausschluss") or "",
            "titel": (zeile.get("text") or "")[:60] or f"Bild {i}",
            "person": erster("person"),
            "ort": zeile.get("ort") or erster("ort"),
            "gegenstand": erster("gegenstand"),
            "handlung": text,
            "mimik": p.get("mimik") or "",
            "kleidung": p.get("kleidung") or "",
            "stil": stil,
        })
    return szenen



# --- Mehrere Bilder je Szene --------------------------------------------
# Gewuerfelt wird der Blick auf den Augenblick: Objektiv, Standpunkt oder
# eine der Szenen-Einstellungen. Und davon genau eines je Bild.
#
# Die Einstellungen sind ausdruecklich dabei -- auf Wunsch. Sie aendern mehr
# als den Blick: eine gewuerfelte Grossaufnahme oder ein Zellengitter macht
# aus dem Augenblick einen anderen. Wer breit streuen will, nimmt das in
# Kauf; wer es nicht will, setzt die Bildzahl je Szene auf eins.
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
    bekannt = {n.lower() for b in teile for n in bausteine.namen(b) if n}
    offen, gesehen = [], set()
    for z in zeilen or []:
        text = z if isinstance(z, str) else (z.get("text") or "")
        for name in VERWEIS.findall(text):
            klein = name.lower()
            if klein not in bekannt and klein not in gesehen:
                gesehen.add(klein)
                offen.append(name)
    return offen



# Woran man Kleidung im allgemeinen Prompt erkennt. Keine Wissenschaft, nur
# die Stuecke, die das Sprachmodell dort immer wieder unterbringt.
# Hauttoene, Haar- und Augenfarben. Stehen im allgemeinen Prompt andere als
# im Gesicht, zeigt das Ganzbild einen anderen Menschen als die
# Grossaufnahme -- und niemand merkt es, bis beide Bilder nebeneinander
# liegen.
HAUTWORT = ("pale", "fair", "light-skinned", "olive", "tan", "tanned",
            "brown-skinned", "dark-skinned", "black", "ebony", "freckled",
            "sun-darkened", "weathered", "ruddy", "sallow")
HAARWORT = ("blonde", "blond", "brown", "dark", "black", "red", "ginger",
            "grey", "gray", "white", "auburn", "silver")
AUGENWORT = ("blue", "green", "brown", "grey", "gray", "hazel", "amber",
             "dark")


def _woerter(text: str, liste) -> set:
    """Welche der Woerter im Text vorkommen, klein geschrieben."""
    klein = (text or "").lower()
    return {w for w in liste if re.search(rf"\b{re.escape(w)}\b", klein)}


KLEIDUNGSWORT = ("jacket", "coat", "dress", "shirt", "blouse", "trousers",
                 "pants", "jeans", "boot", "shoe", "hat", "cap", "uniform",
                 "suit", "jumper", "sweater", "hoodie", "skirt", "scarf",
                 "overall", "apron", "robe", "cloak")


def pruefen(roh: list[dict], alle: list[dict],
            eigene: dict | None = None) -> list[dict]:
    """Durchsehen, ob die Gliederung vollstaendig ist.

    Gefunden wird, was spaeter ein schlechtes Bild ergibt, aber jetzt noch
    leicht zu beheben ist: eine Szene ohne Baustein bekommt eine erfundene
    Person, ein nicht angelegter Name landet als blosses Wort im Prompt, und
    eine Grossaufnahme ohne Gesichtsbeschreibung zeigt irgendein Gesicht.

    Zurueck kommt je Fund ein Eintrag mit Szenennummer, Schwere und Text.
    """
    nach_name = {n.lower(): b for b in alle for n in bausteine.namen(b) if n}
    funde = []

    def fund(nr, schwere, text):
        funde.append({"nr": nr, "schwere": schwere, "text": text})

    benutzt = set()
    for i, z in enumerate(roh, 1):
        getippt = str(z.get("text") or "")
        if not getippt.strip():
            fund(i, "warnung", "Die Zeile ist leer.")
            continue
        ohne_raute, _, _ = hinweise_von(getippt)
        ohne_def, _ = definitionen(ohne_raute)
        text, einst, _ = einstellung_von(ohne_def, eigene)
        namen = VERWEIS.findall(text)
        fehlend = [n for n in dict.fromkeys(namen) if n.lower() not in nach_name]
        teile = [nach_name[n.lower()] for n in namen if n.lower() in nach_name]
        benutzt |= {b["id"] for b in teile}

        if not namen:
            fund(i, "warnung", "Kein Baustein genannt — das Bild erfindet sich "
                               "Person und Ort selbst.")
        # Nach einem Zusammenfuehren kann "/Frau trifft /Nora" zu "/Nora
        # trifft /Nora" geworden sein. Der Baustein zaehlt dann einmal, der
        # Satz aber sagt zwei Personen.
        for name in dict.fromkeys(namen):
            if sum(1 for n in namen if n.lower() == name.lower()) > 1:
                fund(i, "warnung", f"/{name} steht zweimal in der Zeile — "
                                   "das Bild zeigt die Figur sonst doppelt.")
        for n in fehlend:
            fund(i, "fehler", f"/{n} ist nicht angelegt.")
        # Solange ein Name fehlt, sind Person und Ort noch nicht entschieden:
        # beides klaert sich, sobald der Baustein angelegt ist. Es jetzt zu
        # melden waere dreimal dasselbe.
        if not fehlend:
            if namen and not any(b.get("art") == "person" for b in teile):
                fund(i, "hinweis", "Keine Person in der Szene.")
            if not (z.get("ort") or "").strip() \
                    and not any(b.get("art") == "ort" for b in teile):
                fund(i, "hinweis", "Kein Ort — die Umgebung wird erfunden.")

        e = EINSTELLUNGEN.get(einst) or {}
        if e.get("nur_gesicht"):
            ohne = [b for b in teile if b.get("art") == "person"
                    and not (b.get("gesicht") or "").strip()]
            for b in ohne:
                fund(i, "warnung", f"Grossaufnahme, aber /{b['name']} hat keine "
                                   "Gesichtsbeschreibung.")
            if not fehlend and not any(b.get("art") == "person" for b in teile):
                fund(i, "warnung", "Grossaufnahme ohne Person.")
        if e.get("vorgabe") and not (z.get("spiegelung") or "").strip():
            luecke = next(iter(e["vorgabe"]))
            if f"\\{einst}(" not in getippt:
                fund(i, "hinweis",
                     f"{e['label']}: ohne Klammer gilt die Vorgabe für "
                     f"{luecke}.")

    # Und die benutzten Bausteine selbst: was hier fehlt, faellt in jedem
    # Bild auf, in dem sie vorkommen.
    for b in alle:
        if b["id"] not in benutzt:
            continue
        text = (b.get("prompt") or "").strip()
        if not text:
            fund(0, "fehler", f"/{b['name']} hat keinen Prompt.")
            continue
        # Gemessen: unter vierzig Zeichen steht dort "in a workshop" oder
        # "a machine", und das Modell baut jedes Mal etwas anderes daraus.
        if len(text) < 40:
            fund(0, "warnung", f"/{b['name']} ist sehr knapp beschrieben — "
                               "das Bild fällt jedes Mal anders aus.")
        if b.get("art") == "person":
            for feld, was in (("gesicht", "keine Gesichtsbeschreibung"),
                              ("kleidung", "keine Kleidung"),
                              ("haut", "keinen Hautton")):
                if not (b.get(feld) or "").strip():
                    fund(0, "hinweis", f"/{b['name']} hat {was}.")
            # Hautton und Haarfarbe muessen in beiden Texten dieselben
            # sein. Die Grossaufnahme zeigt sonst einen anderen Menschen als
            # das Ganzbild.
            # Steht der Hautton im eigenen Feld, kann er nicht mehr
            # auseinanderlaufen -- dann ist hier nichts zu pruefen.
            gesicht = (b.get("gesicht") or "").strip()
            if gesicht and not (b.get("haut") or "").strip():
                for liste, was in ((HAUTWORT, "Hautton"),
                                   (HAARWORT, "Haarfarbe")):
                    a, c = _woerter(text, liste), _woerter(gesicht, liste)
                    if a and c and not (a & c):
                        fund(0, "fehler",
                             f"/{b['name']}: {was} „{', '.join(sorted(a))}“ im "
                             f"Prompt, „{', '.join(sorted(c))}“ im Gesicht — "
                             "die Grossaufnahme zeigt sonst jemand anderen.")
            # Kleidung an zwei Stellen widerspricht sich im Bild: der
            # allgemeine Prompt sagt Arbeitsjacke, das Kleidungsfeld Mantel.
            if (b.get("kleidung") or "").strip():
                doppelt = [w for w in KLEIDUNGSWORT
                           if re.search(rf"\b{w}s?\b", text, re.I)]
                if doppelt:
                    fund(0, "warnung",
                         f"/{b['name']}: „{doppelt[0]}“ steht im allgemeinen "
                         "Prompt und die Kleidung noch einmal daneben.")
    return funde


# --- Kameraeinstellung je Szene -----------------------------------------
# Mit einem Rueckwaertsschraegstrich und Namen setzt eine Zeile die Anordnung
# von Kamera und Figuren, so wie der Schraegstrich einen Baustein holt. Zwei Zeichen, zwei Bedeutungen: wer und wie.
# \name, dahinter in Klammern, was sich spiegeln soll:
#   \augen(das brennende Schiff)
EINSTELLUNG = re.compile(
    r"\\([A-Za-zÄÖÜäöüß0-9][\wÄÖÜäöüß-]{0,29})(?:\(([^)]{1,120})\))?")

# Frueher hiess "raus" einmal "zelle". Eine gespeicherte Geschichte, die den
# alten Namen fuehrt, soll nicht schweigend ohne Kamera dastehen.
ALTE_NAMEN = {"zelle": "raus"}

# Die Angabe in der Klammer ist deutsch getippt, der Prompt ist englisch.
# Hoehen und Entfernungen lassen sich hier uebersetzen, ohne dafuer das
# Sprachmodell zu bemuehen -- es sind eine Handvoll Woerter.
ZAHLWORT = {"ein": 1, "eine": 1, "eins": 1, "zwei": 2, "drei": 3, "vier": 4,
            "fuenf": 5, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8,
            "neun": 9, "zehn": 10, "elf": 11, "zwoelf": 12, "zwölf": 12,
            "zwanzig": 20, "dreissig": 30, "dreißig": 30, "halb": 0.5}
EINHEIT = {"meter": "metres", "metern": "metres", "m": "metres",
           "zentimeter": "centimetres", "zentimetern": "centimetres",
           "cm": "centimetres", "kilometer": "kilometres", "km": "kilometres"}


def _masse_englisch(angabe: str) -> str:
    r"""\decke(fuenf Meter) -> "five metres". Was nicht passt, bleibt.

    Nur Zahl und Einheit: alles andere waere geraten. Steht etwas anderes in
    der Klammer, geht es unveraendert in den Prompt -- englisch getippt ist
    es dann ohnehin richtig.
    """
    teile = (angabe or "").strip().lower().split()
    if len(teile) != 2:
        return angabe
    zahl, einheit = teile
    if einheit not in EINHEIT:
        return angabe
    if zahl in ZAHLWORT:
        wert = ZAHLWORT[zahl]
    else:
        try:
            wert = float(zahl.replace(",", "."))
        except ValueError:
            return angabe
    schoen = f"{wert:g}"
    return f"{schoen} {EINHEIT[einheit]}"


def einstellung_von(zeile: str, eigene: dict | None = None) -> tuple[str, str, str]:
    r"""Trennt \Name von der Zeile. Zurueck kommt (Text ohne, Schluessel).

    `eigene` sind die gemerkten Prompts des Projekts, unter Name und Nummer:
    \augen-makro oder \7 holt einen davon. Die festen Einstellungen gehen
    vor -- sie heissen schon so, seit es die gemerkten noch nicht gab.

    Ein unbekannter Name bleibt stehen -- wie bei den Bausteinen soll nichts
    stillschweigend verschwinden.
    """
    gefunden, angabe = "", ""

    def ersatz(treffer):
        nonlocal gefunden, angabe
        name = ALTE_NAMEN.get(treffer.group(1).lower(), treffer.group(1).lower())
        if (name in EINSTELLUNGEN or name in (eigene or {})) and not gefunden:
            gefunden = name
            angabe = _masse_englisch((treffer.group(2) or "").strip())
            return ""
        return treffer.group(0)

    text = EINSTELLUNG.sub(ersatz, zeile or "")
    return re.sub(r"\s{2,}", " ", text).strip(), gefunden, angabe


# --- Erwartung und Ausschluss je Szene ------------------------------------
# Mit einer Raute sagt eine Zeile, was im Bild sein soll; mit #- was nicht.
# Beides gilt genau fuer diese eine Szene:
#   Nora am Fenster #dichter Nebel draussen #-keine anderen Menschen
HINWEIS = re.compile(r"#(-?)([^#\n]{1,200})")


def hinweise_von(zeile: str) -> tuple[str, str, str]:
    """Trennt die #-Hinweise ab. Zurueck: (Text, Erwartung, Ausschluss).

    Mehrere Hinweise derselben Art werden mit Komma verbunden -- so, wie das
    Feld "was nicht ins Bild soll" es ohnehin erwartet.
    """
    will, nicht = [], []

    def ersatz(treffer):
        (nicht if treffer.group(1) else will).append(treffer.group(2).strip())
        return ""

    text = HINWEIS.sub(ersatz, zeile or "")
    return (re.sub(r"\s{2,}", " ", text).strip(),
            ", ".join(t for t in will if t),
            ", ".join(t for t in nicht if t))


def zeilen_lesen(roh: list[dict], alle: list[dict],
                 eigene: dict | None = None) -> list[dict]:
    r"""Das Inhaltsverzeichnis, wie es die Seite schickt, in fertige Zeilen.

    Die Seite fuehrt je Zeile nur den getippten Text und die Bildzahl. Alles
    Weitere -- die Einstellung hinter dem \, die Bausteine hinter dem / --
    liest der Server heraus. Beide Endpunkte tun das gleich, sonst kaeme in
    den Prompts eine Einstellung vor, die in den Bildern fehlt.
    """
    zeilen = []
    for z in roh:
        # Erst die Kameraeinstellung heraus, dann die Bausteine: das
        # Sprachmodell soll die Anordnung nicht auch noch beschreiben.
        ohne_raute, will, nicht = hinweise_von(str(z.get("text") or ""))
        ohne_def, erklaert = definitionen(ohne_raute)
        roh_text, einst, spieg = einstellung_von(ohne_def, eigene)
        text, teile = verweise(roh_text, alle)
        if not text:
            continue
        zeilen.append({"text": text, "ort": str(z.get("ort") or ""),
                       "einstellung": einst, "spiegelung": spieg,
                       "erwartung": will, "ausschluss": nicht,
                       # Die Prosa sagt oft mehr ueber das Bild als die
                       # Stichzeile. Sie geht deshalb mit ans Sprachmodell.
                       "prosa": str(z.get("prosa") or ""),
                       "definitionen": erklaert, "teile": teile})
    return zeilen


# Die Einstellung muss vor die Szene, nicht dahinter, und sie muss dem
# Startbild widersprechen duerfen. Gemessen: hinten angehaengt kam von fuenf
# Einstellungen nur eine durch -- das Startbild ist eine Ganzkoerperaufnahme,
# und die Vorlage bewahrt sie so hartnaeckig, dass "extreme close-up"
# wirkungslos blieb.
VORRANG = ("The framing of this picture is fixed by the shot described above "
           "and overrides the reference image: show only what this shot sees, "
           "even if that means the full figure is not visible.")


def mit_einstellung(text: str, schluessel: str, angabe: str = "",
                    eigene: dict | None = None) -> list[str]:
    r"""Die Szene mit der Einstellung. Ein Paar ergibt zwei Fassungen.

    `angabe` fuellt die Luecke der Einstellung -- bei einem Blick in die
    Augen also das, was sich darin spiegelt. Ohne Angabe gilt die Vorgabe.

    Steht hinter dem \ ein gemerkter Prompt statt einer festen Einstellung,
    tritt der an dessen Stelle: ein Prompt, der sich einmal bewaehrt hat,
    soll sich genauso aufrufen lassen wie "augen" oder "spiegel".
    """
    e = EINSTELLUNGEN.get(schluessel)
    if not e and schluessel in (eigene or {}):
        e = {"text": eigene[schluessel]}
    if not e:
        return [text]
    werte = dict(e.get("vorgabe") or {})
    # Ein gemerkter Prompt bringt keine Vorgaben mit. Hat er trotzdem eine
    # Luecke, fuellt die Angabe sie -- so laesst sich ein guter Prompt mit
    # wechselndem Inhalt wiederverwenden.
    if not werte and angabe:
        offen = re.findall(r"\{(\w+)\}", e["text"])
        if offen:
            werte = {offen[0]: angabe}
    elif angabe and werte:
        werte[next(iter(werte))] = angabe

    def bauen(anordnung):
        for name, wert in werte.items():
            anordnung = anordnung.replace("{" + name + "}", wert)
        return f"{anordnung}. {text}. {VORRANG}"

    if "gegentext" in e:
        return [bauen(e["text"]), bauen(e["gegentext"])]
    return [bauen(e["text"])]
