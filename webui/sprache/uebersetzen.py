"""Deutsch nach Englisch, nur wo noetig.

Das Bildmodell folgt englischen Beschreibungen zuverlaessiger. Uebersetzt wird
darum jedes Feld, das deutsch aussieht -- und nur dieses.
"""

import json
import re

from .ollama import MODEL, antwort

# eintippt, soll das trotzdem koennen: der Server uebersetzt vor dem Auftrag.
GERMAN = re.compile(
    r"[äöüßÄÖÜ]|(?<!\w)("
    r"der|die|das|den|dem|des|ein|eine|einen|einem|eines|und|oder|nicht|kein|keine|"
    r"mit|ohne|auf|aus|von|vom|im|in|an|am|zum|zur|bei|fuer|für|ist|sind|war|soll|"
    r"sollen|bleibt|bleiben|ändere|aendere|ändern|wechseln|zeige|zeig|mache|mach|"
    r"erstelle|hintergrund|farbe|kleidung|bild|bilder|person|auto|nur|auch|sehr|"
    r"vorne|hinten|links|rechts|oben|unten"
    r")(?!\w)", re.I)

TRANSLATE_SYSTEM = """Du übersetzt Eingaben für ein Bildgenerierungsmodell ins Englische.

Du bekommst ein JSON-Objekt. Gib dasselbe Objekt mit denselben Schlüsseln zurück,
aber jeder Wert auf Englisch. Antworte ausschließlich mit JSON.

Regeln:
- Übersetze sinngemäß und bildhaft, nicht Wort für Wort.
- Ist ein Wert bereits englisch, gib ihn unverändert zurück.
- Erfinde nichts dazu und lass nichts weg.
- Ein leerer Wert bleibt leer."""


def looks_german(text: str) -> bool:
    """Grobe Erkennung. Lieber einmal zu viel uebersetzen als zu wenig --
    englischer Text kommt unveraendert zurueck."""
    return bool(text and GERMAN.search(text))


def translate(fields: dict[str, str], model: str | None = None) -> dict[str, str]:
    """Uebersetzt die uebergebenen Felder in einem einzigen Aufruf.

    Zurueck kommen nur die Felder, die sich tatsaechlich geaendert haben. Faellt
    Ollama aus, kommt ein leeres Ergebnis -- der Auftrag laeuft dann mit dem
    Originaltext weiter, statt zu scheitern.
    """
    offen = {k: v for k, v in fields.items() if v and v.strip() and looks_german(v)}
    if not offen:
        return {}

    body = {
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 800},
        "messages": [
            {"role": "system", "content": TRANSLATE_SYSTEM},
            {"role": "user", "content": json.dumps(offen, ensure_ascii=False)},
        ],
    }
    raw = antwort(body)
    if not isinstance(raw, dict):
        return {}
    return {k: raw[k].strip() for k in offen
            if isinstance(raw.get(k), str) and raw[k].strip() and raw[k].strip() != offen[k]}
