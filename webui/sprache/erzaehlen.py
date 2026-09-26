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

from .ollama import MODEL, antwort  # noqa: E402

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
