#!/usr/bin/env python3
"""Prüft die Oberfläche gegen den laufenden Server.

Die Seite und der Server entwickeln sich getrennt: das Skript vergleicht, ob
die Oberfläche nur Felder liest, die der Server auch liefert, ob jedes
angesprochene Element existiert und ob das Skript syntaktisch geschlossen ist.

Anlass war ein echter Fehler: ein Feld wurde aus `/api/info` entfernt, die
beiden Aufrufe in der Seite blieben stehen. Der dabei geworfene TypeError
brach die gesamte Einrichtung ab, das Seitenverhältnis-Feld blieb leer, und
der Auftrag scheiterte erst im Server mit einem unverständlichen KeyError.

    ./qwen_bild/bin/python webui/pruefung.py [--port 7860]
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def seite() -> tuple[str, str]:
    """Aufbau und Verhalten der Oberflaeche.

    Beides liegt seit der Aufteilung in eigenen Dateien: `seite/index.html`
    traegt die Elemente, `seite/app.js` das Skript. Geprueft wird weiter im
    Zusammenhang -- gerade die Frage, ob jedes angesprochene Element auch
    existiert, laesst sich nur ueber beide hinweg beantworten.
    """
    ordner = os.path.join(HERE, "seite")
    with open(os.path.join(ordner, "index.html"), encoding="utf-8") as fh:
        text = fh.read()
    with open(os.path.join(ordner, "app.js"), encoding="utf-8") as fh:
        skript = fh.read()
    return text, skript


def pruefe_elemente(text: str, skript: str) -> list[str]:
    fehler = []
    kennungen = re.findall(r'\bid="([^"]+)"', text)
    doppelt = {k for k in kennungen if kennungen.count(k) > 1}
    if doppelt:
        fehler.append(f"doppelte Element-Kennungen: {sorted(doppelt)}")
    fehlend = sorted(set(re.findall(r'\$\("([^"]+)"\)', skript)) - set(kennungen))
    if fehlend:
        fehler.append(f"angesprochen, aber nicht vorhanden: {fehlend}")
    for auf, zu in (("(", ")"), ("{", "}"), ("[", "]")):
        if skript.count(auf) != skript.count(zu):
            fehler.append(f"Klammern {auf}{zu} unausgeglichen: "
                          f"{skript.count(auf)} zu {skript.count(zu)}")
    return fehler


# Alles, was der Browser selbst mitbringt, plus die Schlüsselwörter, die vor
# einer Klammer stehen dürfen. Was ein Aufruf weder hier noch im Skript
# findet, gibt es schlicht nicht.
BEKANNT = {
    "if", "for", "while", "switch", "catch", "return", "typeof", "function",
    "async", "await", "new", "else", "do", "try", "in", "of", "delete", "void",
    "fetch", "setTimeout", "clearTimeout", "setInterval", "clearInterval",
    "parseInt", "parseFloat", "isNaN", "encodeURIComponent", "decodeURIComponent",
    "String", "Number", "Boolean", "Array", "Object", "JSON", "Math", "Promise",
    "Error", "Set", "Map", "Date", "RegExp", "alert", "confirm", "console",
    "FileReader", "Blob", "URL", "FormData", "Image", "atob", "btoa",
}

# Zeichenketten und Kommentare enthalten deutschen Fließtext -- "das ist (so)"
# sähe sonst aus wie ein Aufruf von ist().
def _nur_code(skript: str) -> str:
    ohne = re.sub(r"/\*.*?\*/", " ", skript, flags=re.S)
    ohne = re.sub(r"(?<![:\w])//[^\n]*", " ", ohne)
    for muster in (r"`(?:[^`\\]|\\.)*`", r"'(?:[^'\\\n]|\\.)*'", r'"(?:[^"\\\n]|\\.)*"'):
        ohne = re.sub(muster, '""', ohne)
    return ohne


def pruefe_aufrufe(skript: str) -> list[str]:
    """Ruft die Seite eine Funktion auf, die es nicht gibt?

    Anlass war ein echter Fehler: `startSlots` wurde aufgerufen, aber nie
    geschrieben. Der ReferenceError brach `starteDemo` genau vor der
    Fortschrittsabfrage ab -- der Auftrag lief, die Seite erfuhr nie davon,
    und der Startknopf blieb für immer auf "läuft".
    """
    code = _nur_code(skript)
    bekannt = set(BEKANNT)
    bekannt |= set(re.findall(r"\bfunction\s+([\w$]+)", code))
    bekannt |= set(re.findall(r"\b(?:const|let|var)\s+([\w$]+)", code))
    # Mehrfachzuweisungen in einer Zeile: let a = 1, b = 2, c = null
    for zeile in re.findall(r"\b(?:const|let|var)\s+([^;\n]+)", code):
        bekannt |= set(re.findall(r"([\w$]+)\s*=", zeile))
    # Benannte Argumente von Pfeilfunktionen
    bekannt |= set(re.findall(r"\(([\w$]+)\)\s*=>", code))
    bekannt |= set(re.findall(r"\b([\w$]+)\s*=>", code))

    return [f"die Seite ruft {name}() auf, geschrieben ist es nirgends"
            for name in sorted(set(re.findall(r"(?<![.\w$])([a-zA-Z_$][\w$]*)\s*\(", code)))
            if name not in bekannt]


def pruefe_felder(skript: str, info: dict) -> list[str]:
    gelesen = sorted(set(re.findall(r"\binfo\.(\w+)", skript)))
    fehlend = [k for k in gelesen if k not in info]
    return [f"die Seite liest info.{k}, der Server liefert es nicht" for k in fehlend]


def main() -> int:
    zerleger = argparse.ArgumentParser()
    zerleger.add_argument("--port", type=int, default=7860)
    argumente = zerleger.parse_args()

    text, skript = seite()
    fehler = pruefe_elemente(text, skript) + pruefe_aufrufe(skript)

    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{argumente.port}/api/info", timeout=20) as antwort:
            info = json.load(antwort)
    except urllib.error.URLError as ausnahme:
        print(f"Kein Server auf Port {argumente.port} ({ausnahme.reason}) – "
              "nur die Seite selbst geprüft.")
        info = None
    else:
        fehler += pruefe_felder(skript, info)
        if info.get("source", {}).get("stale"):
            fehler.append("der Server läuft mit älterem Code als die Dateien auf "
                          f"der Platte: {info['source']['changed']}")

    if fehler:
        print("Beanstandungen:")
        for eintrag in fehler:
            print(f"  - {eintrag}")
        return 1

    geprueft = len(set(re.findall(r'\$\("([^"]+)"\)', skript)))
    felder = len(set(re.findall(r"\binfo\.(\w+)", skript))) if info else 0
    aufrufe = len(set(re.findall(r"(?<![.\w$])([a-zA-Z_$][\w$]*)\s*\(", _nur_code(skript))))
    print(f"in Ordnung: {geprueft} Elemente, {felder} Serverfelder, "
          f"{aufrufe} Aufrufe, Klammern geschlossen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
