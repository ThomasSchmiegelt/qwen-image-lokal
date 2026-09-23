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
    with open(os.path.join(HERE, "index.html"), encoding="utf-8") as fh:
        text = fh.read()
    return text, re.search(r"<script>(.*)</script>", text, re.S).group(1)


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


def pruefe_felder(skript: str, info: dict) -> list[str]:
    gelesen = sorted(set(re.findall(r"\binfo\.(\w+)", skript)))
    fehlend = [k for k in gelesen if k not in info]
    return [f"die Seite liest info.{k}, der Server liefert es nicht" for k in fehlend]


def main() -> int:
    zerleger = argparse.ArgumentParser()
    zerleger.add_argument("--port", type=int, default=7860)
    argumente = zerleger.parse_args()

    text, skript = seite()
    fehler = pruefe_elemente(text, skript)

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
    print(f"in Ordnung: {geprueft} Elemente, {felder} Serverfelder, Klammern geschlossen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
