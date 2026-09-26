"""Geschichten in Baenden: mehrere Erzaehlungen je Projekt, fortsetzbar.

Eine **Geschichte** hat einen Namen und die globalen Vorgaben, die fuer alles
gelten: Stil, Welt, Wirklichkeitsgrad, Sprachmodell. Sie besteht aus
**Baenden**. Jeder Band hat seine eigene Idee, sein Inhaltsverzeichnis und
seine Prompts -- aber er erbt die Vorgaben und weiss, was vorher geschah.

    projekte/<projekt>/geschichten/<schluessel>.json

Warum nicht ein Band je Datei: die Vorgaben gehoeren der Geschichte, nicht
dem Band. Sie zweimal zu halten hiesse, sie frueher oder spaeter zweimal zu
aendern.
"""

import json
import os
import time

import projekte

# Was zur Geschichte gehoert und fuer jeden Band gilt.
GLOBAL = ("stil", "welt", "fiktion", "modell")
# Was je Band eigen ist.
BAND = ("idee", "kurz", "titel", "zeilen", "prompts")


def _ordner(projekt: str) -> str:
    pfad = os.path.join(projekte.ordner(projekt), "geschichten")
    os.makedirs(pfad, exist_ok=True)
    return pfad


def _datei(projekt: str, schluessel: str) -> str:
    return os.path.join(_ordner(projekt), f"{schluessel}.json")


def liste(projekt: str) -> list[dict]:
    """Alle Geschichten eines Projekts, zuletzt geaenderte zuerst."""
    raus = []
    for name in os.listdir(_ordner(projekt)):
        if not name.endswith(".json"):
            continue
        g = lesen(projekt, name[:-5])
        if g:
            raus.append({"schluessel": g["schluessel"], "name": g["name"],
                         "baende": len(g.get("baende") or []),
                         "geaendert": g.get("geaendert", "")})
    return sorted(raus, key=lambda x: x["geaendert"], reverse=True)


def lesen(projekt: str, schluessel: str) -> dict:
    if not projekte.SCHLUESSEL.fullmatch(schluessel or ""):
        return {}
    try:
        with open(_datei(projekt, schluessel), encoding="utf-8") as fh:
            daten = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return daten if isinstance(daten, dict) else {}


def _schreiben(projekt: str, g: dict) -> dict:
    g["geaendert"] = time.strftime("%Y-%m-%d %H:%M")
    with open(_datei(projekt, g["schluessel"]), "w", encoding="utf-8") as fh:
        json.dump(g, fh, ensure_ascii=False, indent=2)
    return g


def anlegen(projekt: str, name: str, globale: dict | None = None) -> dict:
    """Eine neue Geschichte mit erstem, noch leerem Band."""
    basis = projekte._schluessel(name)
    schluessel, n = basis, 2
    while os.path.isfile(_datei(projekt, schluessel)):
        schluessel, n = f"{basis}-{n}", n + 1
    g = {"schluessel": schluessel, "name": (name or "").strip() or schluessel,
         **{k: (globale or {}).get(k) for k in GLOBAL},
         "baende": [{"nr": 1, **{k: None for k in BAND}}]}
    return _schreiben(projekt, g)


def speichern(projekt: str, schluessel: str, daten: dict) -> dict:
    """Vorgaben und einen Band ablegen.

    `daten["band"]` ist die Nummer; fehlt sie, gilt der letzte. Nur bekannte
    Felder wandern in die Datei -- was die Seite sonst mitschickt, nicht.
    """
    g = lesen(projekt, schluessel)
    if not g:
        return {}
    for k in GLOBAL:
        if k in daten:
            g[k] = daten[k]
    if daten.get("name"):
        g["name"] = str(daten["name"]).strip()[:60]

    baende = g.setdefault("baende", [{"nr": 1}])
    nr = int(daten.get("band") or baende[-1].get("nr", 1))
    band = next((b for b in baende if b.get("nr") == nr), None)
    if band is None:
        band = {"nr": nr}
        baende.append(band)
    for k in BAND:
        if k in daten:
            band[k] = daten[k]
    return _schreiben(projekt, g)


def band_anlegen(projekt: str, schluessel: str) -> dict:
    """Den naechsten Band anhaengen. Die Vorgaben gelten weiter."""
    g = lesen(projekt, schluessel)
    if not g:
        return {}
    baende = g.setdefault("baende", [])
    nr = (max((b.get("nr", 0) for b in baende), default=0)) + 1
    baende.append({"nr": nr, **{k: None for k in BAND}})
    return _schreiben(projekt, g)


def loeschen(projekt: str, schluessel: str) -> bool:
    if not projekte.SCHLUESSEL.fullmatch(schluessel or ""):
        return False
    try:
        os.remove(_datei(projekt, schluessel))
        return True
    except OSError:
        return False


def vorgeschichte(g: dict, bis_nr: int) -> str:
    """Was in den Baenden davor geschah, als Text fuers Sprachmodell.

    Ohne das faengt Band 2 bei null an und erfindet die Figuren neu. Genommen
    wird die Kurzfassung je Band; die Gliederung waere zu lang und die
    Prompts sind englisch.
    """
    stuecke = []
    for b in g.get("baende") or []:
        if b.get("nr", 0) >= bis_nr:
            continue
        kurz = (b.get("kurz") or "").strip()
        if kurz:
            stuecke.append(f"Band {b['nr']}: {kurz}")
    return "\n\n".join(stuecke)
