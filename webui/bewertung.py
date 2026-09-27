"""Bilder benoten -- und aus den guten benannte Prompts machen.

Je Projekt eine Datei:

    projekte/<projekt>/bewertung.json

Sie ist bewusst schlicht und lesbar gehalten, denn sie geht aus dem Programm
heraus und wieder hinein: der Benutzer benotet die Bilder, reicht die Datei
weiter und bekommt sie mit Verbesserungen zurueck.

    {
      "bilder": {
        "20260927-...png": {"note": 5, "notiz": "so soll es aussehen",
                            "name": "augen-makro", "nr": 1,
                            "prompt": "extreme macro close-up ...",
                            "geaendert": "2026-09-27 14:12"}
      },
      "verbesserungen": [
        {"was": "scheibe", "text": "Die Scheibe spiegelt zu stark.",
         "wann": "2026-09-27 14:20"}
      ]
    }

Ein Bild mit Namen ist mehr als eine Note: sein Prompt laesst sich in einer
Szene mit \\Name wieder aufrufen. Deshalb wird der Prompt hier mitgeschrieben
und nicht jedes Mal aus dem PNG gelesen -- das Bild darf geloescht werden,
der gute Prompt soll bleiben.
"""

import json
import os
import re
import time

import projekte

# Wie ein Name aussehen darf. Er wird in einer Szene hinter dem \\ getippt,
# also keine Leerzeichen und nichts, was die Zeile zerschiesst.
NAME = re.compile(r"[A-Za-z0-9ÄÖÜäöüß_-]{2,30}")


def _datei(projekt: str) -> str:
    return os.path.join(projekte.ordner(projekt), "bewertung.json")


def lesen(projekt: str) -> dict:
    try:
        with open(_datei(projekt), encoding="utf-8") as fh:
            daten = json.load(fh)
    except (OSError, json.JSONDecodeError):
        daten = {}
    if not isinstance(daten, dict):
        daten = {}
    daten.setdefault("bilder", {})
    daten.setdefault("verbesserungen", [])
    if not isinstance(daten["bilder"], dict):
        daten["bilder"] = {}
    if not isinstance(daten["verbesserungen"], list):
        daten["verbesserungen"] = []
    return daten


def _schreiben(projekt: str, daten: dict) -> dict:
    with open(_datei(projekt), "w", encoding="utf-8") as fh:
        json.dump(daten, fh, ensure_ascii=False, indent=2, sort_keys=True)
    return daten


def _naechste_nr(daten: dict) -> int:
    belegt = {e.get("nr") for e in daten["bilder"].values() if e.get("nr")}
    nr = 1
    while nr in belegt:
        nr += 1
    return nr


def setzen(projekt: str, datei: str, note=None, notiz=None, name=None,
           prompt: str = "") -> dict:
    """Note, Notiz und Namen eines Bildes ablegen. Zurueck kommt der Eintrag.

    Was nicht mitgeschickt wird, bleibt stehen -- die Seite schickt beim
    Sternklicken nur die Note und soll damit keine Notiz loeschen.
    """
    if not datei:
        return {}
    daten = lesen(projekt)
    eintrag = daten["bilder"].get(datei) or {}
    if note is not None:
        try:
            eintrag["note"] = max(0, min(int(note), 5))
        except (TypeError, ValueError):
            pass
    if notiz is not None:
        eintrag["notiz"] = str(notiz).strip()[:500]
    if prompt:
        eintrag["prompt"] = str(prompt).strip()[:1200]
    if name is not None:
        sauber = str(name).strip()
        if sauber and NAME.fullmatch(sauber):
            eintrag["name"] = sauber
            # Die Nummer ist der zweite Weg zum Prompt: \\7 statt \\augen-makro.
            # Einmal vergeben, bleibt sie -- sonst zeigt eine notierte Nummer
            # spaeter auf ein anderes Bild.
            eintrag.setdefault("nr", _naechste_nr(daten))
        elif not sauber:
            eintrag.pop("name", None)
            eintrag.pop("nr", None)
    eintrag["geaendert"] = time.strftime("%Y-%m-%d %H:%M")
    # Eine Null ohne alles ist keine Bewertung, sondern das Loeschen einer.
    if not eintrag.get("note") and not eintrag.get("notiz") \
            and not eintrag.get("name"):
        daten["bilder"].pop(datei, None)
        _schreiben(projekt, daten)
        return {}
    daten["bilder"][datei] = eintrag
    _schreiben(projekt, daten)
    return eintrag


def loeschen(projekt: str, datei: str) -> bool:
    """Die Bewertung eines Bildes entfernen -- etwa mit dem Bild selbst."""
    daten = lesen(projekt)
    if datei not in daten["bilder"]:
        return False
    del daten["bilder"][datei]
    _schreiben(projekt, daten)
    return True


def verbessern(projekt: str, was: str, text: str) -> dict:
    """Einen Verbesserungshinweis anhaengen, ohne die Noten anzuruehren."""
    text = str(text or "").strip()[:1000]
    if not text:
        return {}
    daten = lesen(projekt)
    eintrag = {"was": str(was or "").strip()[:60], "text": text,
               "wann": time.strftime("%Y-%m-%d %H:%M")}
    daten["verbesserungen"].append(eintrag)
    _schreiben(projekt, daten)
    return eintrag


def gemerkte(projekt: str) -> list[dict]:
    """Die benannten Prompts, nach Nummer. Das ist, was \\Name erreicht."""
    raus = []
    for datei, e in lesen(projekt)["bilder"].items():
        if e.get("name") and (e.get("prompt") or "").strip():
            raus.append({"nr": e.get("nr") or 0, "name": e["name"],
                         "prompt": e["prompt"], "note": e.get("note") or 0,
                         "bild": datei})
    return sorted(raus, key=lambda x: x["nr"])


def nach_namen(projekt: str) -> dict:
    """Die gemerkten Prompts unter Name *und* Nummer erreichbar."""
    tabelle = {}
    for e in gemerkte(projekt):
        tabelle[e["name"].lower()] = e["prompt"]
        if e["nr"]:
            tabelle[str(e["nr"])] = e["prompt"]
    return tabelle
