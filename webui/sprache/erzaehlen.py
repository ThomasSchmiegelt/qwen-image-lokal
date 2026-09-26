"""Eine Handlung in Szenen zerlegen.

Das Sprachmodell bekommt den deutschen Handlungstext, die Bausteine des
Projekts mit ihren Kennungen und die erlaubten Werte fuer Mimik und Stil. Es
darf nur aus diesen Listen waehlen -- was es trotzdem erfindet, faellt beim
Nachpruefen heraus. Ein 4B-Modell haelt sich nicht an Vorgaben, es haelt sich
ungefaehr daran.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kataloge import GEZEICHNET, MIMIK, STYLES  # noqa: E402

from .ollama import GROSS, MODEL, antwort, entladen  # noqa: E402

MAX_SZENEN = 24


def _system(teile: list[dict], anzahl: int) -> str:
    def zeilen(art):
        passend = [b for b in teile if b.get("art") == art]
        return ("\n".join(f'  {b["id"]} = {b["name"]}' for b in passend)
                or "  (keine)")

    return f"""Du zerlegst eine Handlung in genau {anzahl} Bilder.

Antworte ausschließlich mit JSON: {{"szenen": [ … ]}}. Jede Szene ist ein
Objekt mit genau diesen Schlüsseln:

"titel"      Drei bis fünf Wörter auf Deutsch, nur zur Orientierung.
"person"     Eine Kennung aus der Personenliste, oder "".
"ort"        Eine Kennung aus der Ortsliste, oder "".
"gegenstand" Eine Kennung aus der Gegenstandsliste, oder "".
"handlung"   Was in diesem Bild zu sehen ist, auf ENGLISCH, ein kurzer
             Halbsatz. Keine Namen, keine Vorgeschichte, kein "then" oder
             "later" -- ein Bild zeigt einen Augenblick, keine Abfolge.
"mimik"      Ein Schlüssel aus der Mimikliste, oder "".
"stil"       Ein Schlüssel aus der Stilliste, oder "".

Personen:
{zeilen("person")}

Orte:
{zeilen("ort")}

Gegenstände:
{zeilen("gegenstand")}

Mimik: {", ".join(MIMIK)}

Stil: {", ".join(STYLES)}

Regeln:
- Genau {anzahl} Szenen, in der Reihenfolge der Handlung.
- Nimm nur Kennungen aus den Listen. Passt nichts, schreib "".
- Die Mimik folgt der Handlung: wer etwas verliert, lacht nicht.
- Bleib beim selben Stil, solange die Handlung nicht einen Bruch verlangt."""


def geschichte(text: str, teile: list[dict], anzahl: int = 8,
               model: str | None = None) -> dict:
    """Die Handlung als Liste geprüfter Szenen."""
    anzahl = max(2, min(int(anzahl or 8), MAX_SZENEN))
    erlaubt = {b["id"] for b in teile}
    roh = antwort({
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.4, "num_predict": 1400},
        "messages": [{"role": "system", "content": _system(teile, anzahl)},
                     {"role": "user", "content": text}],
    }, timeout=300)
    if not isinstance(roh, dict) or not isinstance(roh.get("szenen"), list):
        return {"szenen": [], "hinweis": "Das Sprachmodell hat keine Szenen geliefert."}

    def kennung(wert):
        wert = str(wert or "").strip()
        return wert if wert in erlaubt else ""

    def aus(wert, tabelle):
        wert = str(wert or "").strip()
        return wert if wert in tabelle else ""

    szenen = []
    for s in roh["szenen"][:MAX_SZENEN]:
        if not isinstance(s, dict):
            continue
        handlung = str(s.get("handlung") or "").strip()[:220]
        if not handlung:
            continue
        szenen.append({
            "titel": str(s.get("titel") or "").strip()[:60] or f"Bild {len(szenen) + 1}",
            "person": kennung(s.get("person")),
            "ort": kennung(s.get("ort")),
            "gegenstand": kennung(s.get("gegenstand")),
            "handlung": handlung,
            "mimik": aus(s.get("mimik"), MIMIK),
            "stil": aus(s.get("stil"), STYLES),
        })

    hinweis = ""
    if len(szenen) != anzahl:
        hinweis = (f"{len(szenen)} Szenen statt {anzahl} — das Sprachmodell hält "
                   "sich nicht immer an die Zahl. Im Ablauf nachbessern.")
    return {"szenen": szenen, "hinweis": hinweis}



# --- Inhaltsverzeichnis -> Prompts ---------------------------------------
# Der andere Weg: nicht ein Fliesstext, den das Modell zerschneidet, sondern
# eine Gliederung, die der Benutzer selbst geschrieben hat. Je Zeile eine
# Szene, der Ort steht daneben, der Stil gilt fuer die ganze Folge. Das Modell
# hat dann nur noch eine Aufgabe -- aus einer deutschen Zeile ein englisches
# Bild machen -- und die kann es gut.

GLIEDERUNG_SYSTEM = """Du schreibst Bildprompts für eine Bilderfolge.

Du bekommst Szene für Szene eine deutsche Zeile und antwortest jedes Mal mit
JSON und genau diesen Schlüsseln:

"prompt"  Was in diesem Bild zu sehen ist, auf ENGLISCH, ein bis zwei Sätze.
          Beschreibe einen Augenblick, keine Abfolge -- kein "then", kein
          "after". Keine Eigennamen: wer gemeint ist, steht schon in der
          Figurenbeschreibung, die separat davorgesetzt wird. Beschreibe
          Haltung, Handlung, Blickrichtung und was im Bild zu sehen ist.
          Nenne den Ort nur, wenn er in der Zeile steht -- sonst wird er
          separat ergänzt.
"mimik"   Ein Schlüssel aus der Liste, oder "".

Mimik: {mimik}

Die Folge hängt zusammen: du siehst, was du für die vorigen Bilder
geschrieben hast. Halte Kleidung, Tageszeit und Stimmung stimmig, es sei
denn, die Zeile verlangt einen Bruch."""


def gliederung(zeilen: list[str], stil: str = "", welt: str = "",
               kurz: str = "", fiktion=None, model: str | None = None,
               fortschritt=None) -> list[dict]:
    """Aus den Zeilen einer Gliederung die Bildprompts, der Reihe nach.

    Je Zeile ein Aufruf, damit das Modell die vorigen Bilder kennt. Das
    Modell bleibt dabei geladen (`keep_alive`) -- sonst kostete jede Szene
    erneut das Laden von 16,5 GB. Freigegeben wird am Schluss.
    """
    name = model or GROSS
    system = GLIEDERUNG_SYSTEM.format(mimik=", ".join(MIMIK))
    if kurz.strip():
        system += f"\n\nWorum es geht: {kurz.strip()}"
    # Die Weltzuordnung zuerst: ohne sie biegt das Modell eine Fantasiehandlung
    # so lange zurecht, bis sie alltagstauglich wird.
    if welt in WELTEN:
        system += f"\n\n{WELTEN[welt][1]}"
    _, satz = grad(fiktion)
    if satz:
        system += f"\n\n{satz}"
    if stil in STYLES:
        system += f"\n\nDie ganze Folge ist im Stil: {STYLES[stil][1]}"
        if stil in GEZEICHNET:
            system += (" Es ist eine Zeichnung, kein Foto -- beschreibe nichts "
                       "Fotografisches wie Objektive, Filmkorn oder Blende.")

    verlauf, szenen = [], []
    try:
        for nr, zeile in enumerate(zeilen, 1):
            text = (zeile or "").strip()
            if not text:
                continue
            if fortschritt:
                fortschritt(nr, len(zeilen))
            roh = antwort({
                "model": name,
                "format": "json",
                "keep_alive": "10m",          # zwischen den Szenen geladen lassen
                "options": {"temperature": 0.7, "num_predict": 500},
                "messages": [{"role": "system", "content": system},
                             *verlauf,
                             {"role": "user",
                              "content": f"Szene {nr} von {len(zeilen)}: {text}"}],
            }, timeout=600)
            if not isinstance(roh, dict) or not str(roh.get("prompt") or "").strip():
                szenen.append({"nr": nr, "zeile": text, "prompt": "", "mimik": ""})
                continue
            prompt = str(roh["prompt"]).strip()[:400]
            mimik = str(roh.get("mimik") or "").strip()
            szenen.append({"nr": nr, "zeile": text, "prompt": prompt,
                           "mimik": mimik if mimik in MIMIK else ""})
            verlauf += [{"role": "user", "content": f"Szene {nr}: {text}"},
                        {"role": "assistant", "content": prompt}]
            del verlauf[:-12]
    finally:
        entladen(name)                        # die Karte braucht gleich das Bildmodell
    return szenen


PROSA_SYSTEM = """Du schreibst den Text zu einer Bilderfolge.

Du bekommst die Szenen als Liste. Antworte mit JSON:
{"absaetze": ["…", "…"]} -- genau ein deutscher Absatz je Szene, zwei bis
vier Sätze, erzählend und in der Reihenfolge der Szenen. Kein Vorspann, keine
Überschriften, keine Nummern."""


def prosa(szenen: list[dict], model: str | None = None) -> list[str]:
    """Zu jeder Szene ein Absatz Prosa -- aus der Gliederung, nicht erfunden."""
    if not szenen:
        return []
    name = model or GROSS
    liste = "\n".join(f"{s.get('nr', i + 1)}. {s.get('zeile') or s.get('prompt')}"
                       for i, s in enumerate(szenen))
    try:
        roh = antwort({
            "model": name,
            "format": "json",
            "keep_alive": "10m",
            "options": {"temperature": 0.8, "num_predict": 1600},
            "messages": [{"role": "system", "content": PROSA_SYSTEM},
                         {"role": "user", "content": liste}],
        }, timeout=600)
    finally:
        entladen(name)
    if not isinstance(roh, dict) or not isinstance(roh.get("absaetze"), list):
        return []
    return [str(a or "").strip()[:900] for a in roh["absaetze"]][:len(szenen)]



# --- Expose --------------------------------------------------------------
# Vor der ersten Szene: worum geht es, in welchem Stil, und spielt das in der
# wirklichen Welt oder einer erfundenen? Das Letzte ist kein Beiwerk. Ein
# Modell, dem niemand sagt, dass Drachen vorkommen duerfen, versucht die
# Handlung zurechtzubiegen, bis sie plausibel wird.

WELTEN = {
    "wirklich": ("Wirklichkeit",
                 "Die Geschichte spielt in der wirklichen Welt. Alles muss "
                 "physikalisch moeglich und alltaeglich glaubhaft sein."),
    "fantasie": ("Fantasie",
                 "Die Geschichte spielt in einer erfundenen Welt. Magie, "
                 "Fabelwesen und unmoegliche Orte sind ausdruecklich erlaubt "
                 "und sollen nicht wegerklaert werden."),
    "scifi":    ("Zukunft",
                 "Die Geschichte spielt in der Zukunft. Technik darf weit "
                 "ueber das Heutige hinausgehen, soll aber in sich stimmig "
                 "bleiben."),
    "maerchen": ("Märchen",
                 "Die Geschichte ist ein Maerchen. Sprechende Tiere, Zauber "
                 "und Wunder gehoeren dazu; Logik tritt hinter das Bild."),
}

# Wie wirklich soll es sein? Ein Regler von 0 bis 10 statt einer Ja-Nein-
# Frage: das Spannende liegt oft dazwischen -- eine Welt, die fast die unsere
# ist, in der aber eine Sache nicht stimmt und niemand sich daran stoert.
GRADE = (
    (1,  ["wirklich"],
     "Nichts Uebernatuerliches. Alles muss physikalisch moeglich und "
     "alltaeglich glaubhaft sein."),
    (3,  ["wirklich"],
     "Die wirkliche Welt, aber am Rand ein Hauch von Unwirklichem -- nie "
     "erklaert, nie ausgesprochen."),
    (5,  ["wirklich", "scifi"],
     "Die Grenze zum Unmoeglichen ist durchlaessig: einzelne Dinge duerfen "
     "nicht stimmen, ohne dass jemand darueber staunt."),
    (7,  ["scifi", "fantasie"],
     "Eine erfundene Welt mit eigenen Regeln. Sie darf weit von der unseren "
     "abweichen, muss aber in sich folgerichtig bleiben."),
    (9,  ["fantasie", "maerchen"],
     "Magie und Fabelwesen gehoeren dazu und werden nicht wegerklaert."),
    (10, ["maerchen"],
     "Maerchenlogik: Wunder brauchen keine Begruendung, das Bild geht vor "
     "der Erklaerung."),
)


def grad(fiktion) -> tuple[list[str], str]:
    """Aus dem Regler die erlaubten Welten und den Satz fuer das Modell.

    Nimmt auch True/False -- der Regler ersetzte einen Haken, und alte
    Aufrufe sollen nicht brechen.
    """
    if fiktion is None:
        return list(WELTEN), ""
    if fiktion is True:
        fiktion = 9
    elif fiktion is False:
        fiktion = 0
    try:
        wert = max(0, min(int(fiktion), 10))
    except (TypeError, ValueError):
        return list(WELTEN), ""
    for grenze, welten, satz in GRADE:
        if wert <= grenze:
            return welten, satz
    return list(WELTEN), ""


EXPOSE_SYSTEM = """Du planst eine Bilderfolge.

Der Benutzer nennt eine Idee. Antworte ausschließlich mit JSON und genau
diesen Schlüsseln:

"kurz"    Drei bis fünf deutsche Sätze: worum es geht, wer vorkommt, wie es
          ausgeht. Kein Vorspann, keine Überschrift.
"welt"    Einer dieser Schlüssel: {welten}
          Wähle ehrlich. Kommen Drachen oder Magie vor, ist es "fantasie",
          auch wenn die Idee nüchtern klingt.
"stil"    Ein Schlüssel aus der Stilliste, der zur Geschichte passt und für
          ALLE Bilder gelten soll: {stile}
"titel"   Zwei bis vier Wörter, deutsch.
"szenen"  Vorschlag für die Gliederung: eine Liste deutscher Zeilen, je eine
          Szene, fünf bis zehn Stück. Eine Zeile sagt, was in diesem einen
          Bild zu sehen ist."""


def expose(idee: str, fiktion=None, model: str | None = None) -> dict:
    """Aus einer Idee die Kurzbeschreibung samt Stil und Weltzuordnung.

    `fiktion` ist der Regler des Benutzers, 0 bis 10, und schlaegt das
    Urteil des Modells. None laesst es selbst entscheiden.
    """
    leer = {"kurz": "", "welt": "wirklich", "stil": "", "titel": "", "szenen": []}
    if not (idee or "").strip():
        return leer
    name = model or GROSS
    erlaubt, satz = grad(fiktion)
    system = EXPOSE_SYSTEM.format(
        welten=", ".join(f'"{k}" ({WELTEN[k][0]})' for k in erlaubt),
        stile=", ".join(STYLES))
    if satz:
        system += f"\n\nDer Benutzer hat den Wirklichkeitsgrad vorgegeben: {satz}"
    try:
        roh = antwort({
            "model": name, "format": "json", "keep_alive": "10m",
            "options": {"temperature": 0.8, "num_predict": 900},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": idee}],
        }, timeout=600)
    finally:
        entladen(name)
    if not isinstance(roh, dict):
        return leer
    welt = str(roh.get("welt") or "").strip()
    if welt not in erlaubt:
        welt = erlaubt[0]
    stil = str(roh.get("stil") or "").strip()
    szenen = [str(z or "").strip()[:200] for z in (roh.get("szenen") or [])
              if str(z or "").strip()]
    return {
        "kurz": str(roh.get("kurz") or "").strip()[:900],
        "welt": welt,
        "stil": stil if stil in STYLES else "",
        "titel": str(roh.get("titel") or "").strip()[:60],
        "szenen": szenen[:MAX_SZENEN],
    }
