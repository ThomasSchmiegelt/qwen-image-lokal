"""Eine Szene in einen Bauplan zerlegen: Kulisse, Posen, Spiegelung.

Der Katalog liefert von jeder Figur ein Musterbild, und das zeigt sie
stehend vor neutralem Grund. Eine Szene will sie aber liegend, kniend, von
hinten. Wer das Musterbild unveraendert einsetzt, bekommt eine stehende
Figur in ein Bett gelegt.

Deshalb vorweg die Frage an das Sprachmodell: wer nimmt in diesem Satz
welche Haltung ein, was ist der Raum, und spiegelt sich etwas. Aus der
Antwort baut `szenenbau.py` die Stufen.
"""

import re

from .ollama import MODEL, antwort

# Kein Beispielsatz im Systemtext: das kleine Modell schreibt ihn wortwoertlich
# zurueck. Gemessen an den Personenprompts -- dort kam der Beispielmensch aus
# der Anleitung als Antwort heraus. Deshalb nur Platzhalter in spitzen
# Klammern, die sich nicht abschreiben lassen.
BAUPLAN_SYSTEM = """Du zerlegst die Beschreibung eines Bildes in einen Bauplan.

Du bekommst einen Satz und eine Liste von Namen. Antworte nur mit JSON:

{"kulisse": "<der Raum allein, englisch, ohne jede Person>",
 "figuren": [{"name": "<Name aus der Liste>",
              "pose": "<was diese Figur tut, englisch>"}],
 "spiegelung": {"name": "<Name aus der Liste oder leer>",
                "wo": "<worin sie sich spiegelt, englisch>"}}

Regeln:
- Jeder Name aus der Liste kommt genau einmal in "figuren" vor, in der
  Reihenfolge der Liste. Keine weiteren Namen erfinden.
- "pose" nennt nur Koerperhaltung, Platz im Bild und Blickrichtung.
  Kein Aussehen, keine Kleidung, keine Haut-, Haar- oder Augenfarbe, kein
  Name -- das alles steht schon woanders.
- "kulisse" nennt Raum, Licht und Gegenstaende. Keine Person, auch keine
  angedeutete.
- "spiegelung" nur ausfuellen, wenn der Satz wirklich von einer Spiegelung,
  einem Spiegelbild oder einem Abbild in einer Flaeche spricht. Sonst
  beide Felder leer lassen.
- Steht in der Spiegelung jemand, der nicht in der Liste ist, bleibt
  "name" leer und "wo" beschreibt die Flaeche trotzdem.
"""


def bauplan(text: str, namen: list[str], modell: str | None = None) -> dict:
    """Kulisse, Pose je Figur und Spiegelung aus einem Satz.

    Die Antwort ist nach Namen verschluesselt, nicht nach Reihenfolge: das
    Modell laesst gern eine Figur aus, und dann rutscht bei einer
    Positionsliste jede folgende Pose an die falsche Person.
    """
    leer = {"kulisse": "", "figuren": [], "spiegelung": {}}
    if not (text or "").strip() or not namen:
        return leer
    frage = (f"Namen: {', '.join(namen)}\n\nSatz: {text.strip()}")
    roh = antwort({
        "model": modell or MODEL,
        "format": "json",
        # Je Figur rund achtzig Zeichen, dazu Kulisse und Spiegelung. Zu
        # knapp bemessen bricht das JSON mittendrin ab, und dann fehlt die
        # letzte Figur, ohne dass es auffaellt.
        "options": {"temperature": 0.2,
                    "num_predict": 240 + 120 * len(namen)},
        "messages": [{"role": "system", "content": BAUPLAN_SYSTEM},
                     {"role": "user", "content": frage}],
    })
    if not isinstance(roh, dict):
        return leer
    return _ordnen(roh, namen)


def _ordnen(roh: dict, namen: list[str]) -> dict:
    """Die Antwort auf die gefragten Namen zurechtlegen.

    Fehlt eine Figur, bekommt sie eine leere Pose statt gar keinen Eintrag:
    sie gehoert ins Bild, auch wenn das Modell nichts ueber sie sagt.
    """
    nach_name = {}
    for eintrag in (roh.get("figuren") or []):
        if not isinstance(eintrag, dict):
            continue
        name = str(eintrag.get("name") or "").strip()
        treffer = next((n for n in namen if n.lower() == name.lower()), "")
        if treffer:
            nach_name[treffer] = _pose(str(eintrag.get("pose") or ""))
    figuren = [{"name": n, "pose": nach_name.get(n, "")} for n in namen]

    spiegel = roh.get("spiegelung")
    spiegel = spiegel if isinstance(spiegel, dict) else {}
    wo = str(spiegel.get("wo") or "").strip()[:160]
    wer = str(spiegel.get("name") or "").strip()
    wer = next((n for n in namen if n.lower() == wer.lower()), "")
    return {"kulisse": str(roh.get("kulisse") or "").strip()[:300],
            "figuren": figuren,
            "spiegelung": {"name": wer, "wo": wo} if wo else {}}


# Namen, Aussehen und Kleidung gehoeren nicht in die Pose: sie stehen im
# Baustein, und zweimal gesagt widersprechen sie sich frueher oder spaeter.
AUSSEHEN = re.compile(
    r"\b(?:wearing|dressed in|clad in|with (?:her|his|their) )"
    r"[^,.;]{0,80}", re.I)


def _pose(text: str) -> str:
    """Die Pose allein: ohne Namen davor und ohne Kleidung darin."""
    text = (text or "").strip().rstrip(".")
    text = AUSSEHEN.sub("", text)
    # "Malva is lying on the bed" -> "lying on the bed". Der Name wuerde das
    # Bildmodell allenfalls dazu bringen, ihn ins Bild zu schreiben.
    text = re.sub(r"^\s*[A-ZÄÖÜ][\wÄÖÜäöüß-]*\s+(?:is|are|steht|liegt|sitzt)\s+",
                  "", text)
    text = re.sub(r"^(?:she|he|they)\s+(?:is|are)\s+", "", text, flags=re.I)
    text = re.sub(r"\s{2,}", " ", text).strip(" ,;")
    return text[:200]
