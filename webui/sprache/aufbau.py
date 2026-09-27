"""Aus einer ganzen Geschichte eine Gliederung bauen -- Stueck fuer Stueck.

Der Grund fuer diese Datei: eine Vorlage von anderthalb Seiten und der
Wunsch nach sechzig Bildern gingen in einem einzigen Aufruf nicht gut aus.
Das Modell faengt vorn an, erzaehlt frei weiter und kommt am Ende nicht an
-- die Schlussszene fehlte schlicht.

Der Weg hier ist ein anderer:

1. **Rahmen** -- Titel, Kurzfassung, erste und letzte Szene. Das Ende steht
   damit fest, bevor die Mitte geschrieben wird.
2. **Abschnitte** -- der Text wird im Python-Code in gleich grosse Stuecke
   geteilt, an Absatz- und Satzgrenzen. Keine Ermessensfrage: jedes Stueck
   kommt dran, also kommt auch das letzte dran.
3. **Szenen je Abschnitt** -- jedes Stueck bekommt seinen Anteil an Szenen,
   und das Modell sieht nur dieses Stueck. Der letzte Abschnitt weiss, dass
   er auf die Schlussszene zulaeuft.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kataloge import STYLES  # noqa: E402

from .erzaehlen import MAX_SZENEN, WELTEN, freigabe, grad  # noqa: E402
from .ollama import GROSS, antwort, entladen  # noqa: E402


def abschnitte(text: str, anzahl: int) -> list[str]:
    """Den Text in `anzahl` etwa gleich grosse Stuecke teilen.

    Getrennt wird an Absaetzen, und wo ein Absatz allein zu gross ist, an
    Satzenden. Das macht der Python-Code und nicht das Sprachmodell: hier
    darf nichts unter den Tisch fallen, und genau das ist vorher passiert.
    """
    text = (text or "").strip()
    anzahl = max(1, int(anzahl or 1))
    if not text:
        return []
    if anzahl == 1:
        return [text]

    # Erst Absaetze, dann zu grosse Absaetze in Saetze.
    roh = [t.strip() for t in re.split(r"\n\s*\n", text) if t.strip()]
    ziel = max(1, len(text) // anzahl)
    stuecke = []
    for absatz in roh:
        if len(absatz) <= ziel * 1.5:
            stuecke.append(absatz)
            continue
        satz, jetzt = re.split(r"(?<=[.!?])\s+", absatz), ""
        for s in satz:
            if jetzt and len(jetzt) + len(s) > ziel:
                stuecke.append(jetzt.strip())
                jetzt = ""
            jetzt += s + " "
        if jetzt.strip():
            stuecke.append(jetzt.strip())

    # Zusammenlegen, bis es so viele Stuecke sind wie gewuenscht.
    while len(stuecke) > anzahl:
        # Immer die beiden kuerzesten Nachbarn -- so bleiben sie gleich gross.
        paare = [(len(stuecke[i]) + len(stuecke[i + 1]), i)
                 for i in range(len(stuecke) - 1)]
        _, i = min(paare)
        stuecke[i:i + 2] = [stuecke[i] + "\n\n" + stuecke[i + 1]]
    return stuecke


def _umfeld(kurz: str = "", welt: str = "", fiktion=None, stil: str = "",
            alter: str = "") -> str:
    """Die Vorgaben, die fuer jede Szene gelten, als Text fuers Modell."""
    teile = []
    if kurz.strip():
        teile.append(f"Worum es geht: {kurz.strip()}")
    if welt in WELTEN:
        teile.append(WELTEN[welt][1])
    _, satz = grad(fiktion)
    if satz:
        teile.append(satz)
    if freigabe(alter):
        teile.append(freigabe(alter))
    if stil in STYLES:
        teile.append(f"Die ganze Folge ist im Stil: {STYLES[stil][1]}")
    return "\n\n".join(teile)


RAHMEN_SYSTEM = """Du planst eine Bilderfolge zu einer Geschichte.

Du bekommst die Geschichte oder eine Idee dazu. Antworte ausschließlich mit
JSON und genau diesen Schlüsseln:

"titel"  Zwei bis vier Wörter, deutsch.
"kurz"   Drei bis fünf deutsche Sätze: worum es geht, wer vorkommt, wie es
         ausgeht. Kein Vorspann, keine Überschrift.
"anfang" Die ERSTE Szene, eine deutsche Zeile: was auf dem ersten Bild zu
         sehen ist. Ein Augenblick, keine Abfolge.
"ende"   Die LETZTE Szene, eine deutsche Zeile: was auf dem letzten Bild zu
         sehen ist. Sie muss der Schluss sein, auf den alles zuläuft -- kein
         beliebiger später Augenblick.

Anfang und Ende stehen damit fest, bevor die Mitte geschrieben wird. Halte
dich an die Vorlage: erfinde kein anderes Ende, wenn die Geschichte eines
hat."""


def rahmen(text: str, kurz: str = "", welt: str = "", fiktion=None,
           stil: str = "", model: str | None = None, alter: str = "") -> dict:
    """Titel, Kurzfassung, Anfangs- und Schlussszene."""
    if not (text or "").strip():
        return {}
    system = RAHMEN_SYSTEM
    zusatz = _umfeld(kurz, welt, fiktion, stil, alter)
    if zusatz:
        system += "\n\n" + zusatz
    name = model or GROSS
    try:
        roh = antwort({
            "model": name, "format": "json", "keep_alive": "10m",
            "options": {"temperature": 0.6, "num_predict": 700},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": text.strip()[:12000]}],
        }, timeout=600)
    finally:
        entladen(name)
    if not isinstance(roh, dict):
        return {}
    return {k: str(roh.get(k) or "").strip()[:400 if k != "kurz" else 900]
            for k in ("titel", "kurz", "anfang", "ende")}


KAPITEL_SYSTEM = """Du gibst den Abschnitten einer Geschichte Überschriften.

Du bekommst die Abschnitte der Reihe nach. Antworte ausschließlich mit JSON:
{"kapitel": ["…", "…"]} -- genau so viele deutsche Überschriften wie es
Abschnitte gibt, in derselben Reihenfolge, je zwei bis fünf Wörter."""


def kapitel(stuecke: list[str], model: str | None = None) -> list[str]:
    """Je Abschnitt eine Ueberschrift. Fehlt eine, steht dort die Nummer."""
    if not stuecke:
        return []
    inhalt = "\n\n".join(f"Abschnitt {i}:\n{t[:600]}"
                         for i, t in enumerate(stuecke, 1))
    roh = antwort({
        "model": model or GROSS, "format": "json", "keep_alive": "10m",
        "options": {"temperature": 0.4,
                    "num_predict": 200 + 40 * len(stuecke)},
        "messages": [{"role": "system", "content": KAPITEL_SYSTEM},
                     {"role": "user", "content": inhalt}],
    }, timeout=600)
    gegeben = roh.get("kapitel") if isinstance(roh, dict) else None
    raus = [str(t or "").strip()[:60] for t in (gegeben or [])]
    raus = raus[:len(stuecke)]
    return raus + [f"Abschnitt {i}" for i in range(len(raus) + 1, len(stuecke) + 1)]


SZENEN_SYSTEM = """Du machst aus einem Abschnitt einer Geschichte Bildszenen.

Antworte ausschließlich mit JSON: {{"szenen": [ … ]}} -- eine Liste deutscher
Zeilen, GENAU {anzahl} Stück. Jede Zeile sagt, was auf diesem einen Bild zu
sehen ist: ein Augenblick, keine Abfolge, kein "dann" und kein "später".

Regeln:
- Nur dieser Abschnitt. Was davor oder danach geschieht, gehört nicht hierher.
- Der Reihe nach durch den Abschnitt, vom Anfang bis zum Ende.
- Dieselben Figuren und Orte wie in der Vorlage, mit denselben Namen.
- Die Zeilen wiederholen nicht, was schon geschrieben wurde."""


def szenen_aus_abschnitt(abschnitt: str, anzahl: int, kapitel_titel: str = "",
                         kurz: str = "", welt: str = "", fiktion=None,
                         stil: str = "", bisher: str = "", schluss: str = "",
                         model: str | None = None, alter: str = "") -> list[str]:
    """Die Szenen eines Abschnitts. `schluss` setzt das Ende, falls letzter."""
    anzahl = max(1, min(int(anzahl or 1), MAX_SZENEN))
    system = SZENEN_SYSTEM.format(anzahl=anzahl)
    zusatz = _umfeld(kurz, welt, fiktion, stil, alter)
    if zusatz:
        system += "\n\n" + zusatz
    if kapitel_titel.strip():
        system += f"\n\nDieser Abschnitt heißt: {kapitel_titel.strip()}"
    if bisher.strip():
        system += ("\n\nDas wurde für die vorigen Abschnitte schon "
                   f"geschrieben -- wiederhole es nicht:\n{bisher.strip()[:1500]}")
    if schluss.strip():
        system += ("\n\nDas ist der letzte Abschnitt. Die letzte deiner Zeilen "
                   f"muss dieser Schluss sein: {schluss.strip()}")
    roh = antwort({
        "model": model or GROSS, "format": "json", "keep_alive": "10m",
        "options": {"temperature": 0.7,
                    "num_predict": min(4000, 300 + 70 * anzahl)},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": abschnitt.strip()[:6000]}],
    }, timeout=900)
    gegeben = roh.get("szenen") if isinstance(roh, dict) else None
    neu = [str(z or "").strip()[:200] for z in (gegeben or []) if str(z or "").strip()]
    if schluss.strip():
        # Der Schluss steht, auch wenn das Modell ihn vergisst.
        if not neu or neu[-1].lower() != schluss.strip().lower():
            neu = [z for z in neu if z.lower() != schluss.strip().lower()]
            neu = neu[:anzahl - 1] + [schluss.strip()]
    return neu[:anzahl] + [""] * max(0, anzahl - len(neu))
