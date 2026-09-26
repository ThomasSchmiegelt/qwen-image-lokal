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
from kataloge import MIMIK, STYLES  # noqa: E402

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


def gliederung(zeilen: list[str], stil: str = "", model: str | None = None,
               fortschritt=None) -> list[dict]:
    """Aus den Zeilen einer Gliederung die Bildprompts, der Reihe nach.

    Je Zeile ein Aufruf, damit das Modell die vorigen Bilder kennt. Das
    Modell bleibt dabei geladen (`keep_alive`) -- sonst kostete jede Szene
    erneut das Laden von 16,5 GB. Freigegeben wird am Schluss.
    """
    name = model or GROSS
    system = GLIEDERUNG_SYSTEM.format(mimik=", ".join(MIMIK))
    if stil in STYLES:
        system += f"\n\nDie ganze Folge ist im Stil: {STYLES[stil][1]}"

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
