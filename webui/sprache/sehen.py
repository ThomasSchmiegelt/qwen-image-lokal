"""Bilder ansehen: beschreiben, Geschlecht erkennen, Prompt rueckwaerts.

Das Sprachmodell ist multimodal, es kann also selbst ins Bild schauen. Genutzt
wird das beim Ablauf (wen soll das Modell bewahren?) und um aus einem
mitgebrachten Foto den Prompt zu schreiben.
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kataloge import CAMERAS, LIGHTS, STYLES  # noqa: E402

from .ollama import MODEL, antwort  # noqa: E402

# Fragen, mit denen sich ein Ablauf an das Startbild anpassen lässt.
def bild_frage(bild_bytes: bytes, frage: str, model: str | None = None) -> str:
    """Eine Frage zu einem Bild. Leerer String, wenn Ollama nicht antwortet."""
    body = {
        "model": model or MODEL,
        "options": {"temperature": 0.0, "num_predict": 20},
        "messages": [{"role": "user", "content": frage,
                      "images": [base64.b64encode(bild_bytes).decode("ascii")]}],
    }
    return antwort(body) or ""


def ist_weiblich(bild_bytes: bytes, model: str | None = None) -> bool | None:
    """True bei einer Frau, False bei einem Mann, None wenn unklar.

    Wird gebraucht, um Schritte auszulassen, die nicht passen -- einen Bart
    etwa. Im Zweifel None: dann bleibt es beim Regelfall, statt zu raten.
    """
    antwort = bild_frage(
        bild_bytes,
        "Zeigt dieses Bild eine Frau, einen Mann oder ist es nicht eindeutig? "
        "Antworte mit genau einem Wort: frau, mann oder unklar.",
        model).lower()
    if "frau" in antwort or "weiblich" in antwort or "woman" in antwort:
        return True
    if "mann" in antwort or "männlich" in antwort or "man" in antwort:
        return False
    return None


BILD_SYSTEM = """Du beschreibst ein Foto für ein Bildgenerierungsmodell.

Antworte ausschließlich mit JSON und genau diesen Schlüsseln:

"geschlecht"   "frau", "mann" oder "unklar"
"beschreibung" EIN kurzer englischer Halbsatz, der die abgebildete Person
               greifbar macht: ungefähres Alter, Haare, auffällige Kleidung.
               Keine Wertung, keine Namen, keine Vermutungen über Herkunft.
               Beispiel: "a woman in her thirties with shoulder-length dark
               hair, wearing a grey hooded jacket"
"umgebung"     EIN kurzer englischer Halbsatz zur Umgebung.

Ist keine Person zu sehen, setze "geschlecht" auf "unklar" und beschreibe in
"beschreibung" den Hauptgegenstand."""


def bild_lesen(bild_bytes: bytes, model: str | None = None) -> dict:
    """Liest Geschlecht, Personenbeschreibung und Umgebung aus einem Bild.

    Die Beschreibung wandert spaeter in die Anweisungen: was das Modell
    bewahren soll, trifft es besser, wenn dort steht, wen es bewahren soll.
    Faellt Ollama aus, kommt ein leeres Ergebnis und alles laeuft wie bisher.
    """
    body = {
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.0, "num_predict": 200},
        "messages": [
            {"role": "system", "content": BILD_SYSTEM},
            {"role": "user", "content": "Beschreibe dieses Bild.",
             "images": [base64.b64encode(bild_bytes).decode("ascii")]},
        ],
    }
    roh = antwort(body)
    if not isinstance(roh, dict):
        return {"geschlecht": "unklar", "beschreibung": "", "umgebung": ""}

    geschlecht = str(roh.get("geschlecht") or "").strip().lower()
    if geschlecht not in ("frau", "mann"):
        geschlecht = "unklar"
    return {
        "geschlecht": geschlecht,
        "beschreibung": str(roh.get("beschreibung") or "").strip()[:200],
        "umgebung": str(roh.get("umgebung") or "").strip()[:200],
    }


# --- Rueckwaerts: aus einem Bild einen Prompt ----------------------------
# Die Regler werden gleich mitgeraten. Die erlaubten Schluessel stehen im
# Systemtext, damit nichts erfunden wird -- geprueft wird trotzdem, denn ein
# 4B-Modell haelt sich nicht immer daran.
def _rueckwaerts_system() -> str:
    def liste(tabelle):
        return ", ".join(f"{k} ({v[0]})" for k, v in tabelle.items())
    return f"""Du siehst ein Bild und schreibst den Prompt, mit dem man es
nachbauen koennte.

Antworte ausschliesslich mit JSON und genau diesen Schluesseln:

"prompt"  Die Bildbeschreibung auf ENGLISCH, ein bis drei Saetze. Nenne das
          Hauptmotiv, was es tut, die Umgebung, die Kleidung oder Oberflaeche,
          die Bildkomposition und die Stimmung. Keine Kamerawerte, keine
          Markennamen, keine Namen von Personen.
"stil"    genau einer dieser Schluessel oder "": {liste(STYLES)}
"licht"   genau einer dieser Schluessel oder "": {liste(LIGHTS)}
"kamera"  genau einer dieser Schluessel oder "": {liste(CAMERAS)}

Passt nichts, lass das Feld leer. Rate nicht."""


def bild_zu_prompt(bild_bytes: bytes, model: str | None = None) -> dict:
    """Liest ein Bild und schreibt den Prompt dazu, samt Reglervorschlag.

    Gedacht fuer ein mitgebrachtes Foto: es sagt, wie man so etwas beschreibt,
    und stellt Stil, Licht und Objektiv gleich passend ein. Faellt Ollama aus,
    kommt ein leeres Ergebnis -- die Seite meldet das, mehr passiert nicht.
    """
    leer = {"prompt": "", "stil": "", "licht": "", "kamera": ""}
    body = {
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 400},
        "messages": [
            {"role": "system", "content": _rueckwaerts_system()},
            {"role": "user", "content": "Schreibe den Prompt zu diesem Bild.",
             "images": [base64.b64encode(bild_bytes).decode("ascii")]},
        ],
    }
    roh = antwort(body)
    if not isinstance(roh, dict):
        return leer

    def gueltig(wert, tabelle):
        wert = str(wert or "").strip()
        return wert if wert in tabelle else ""

    return {
        "prompt": str(roh.get("prompt") or "").strip()[:900],
        "stil": gueltig(roh.get("stil"), STYLES),
        "licht": gueltig(roh.get("licht"), LIGHTS),
        "kamera": gueltig(roh.get("kamera"), CAMERAS),
    }
