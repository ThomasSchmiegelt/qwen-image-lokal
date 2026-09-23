#!/usr/bin/env python3
"""Einen Ablauf von der Kommandozeile starten.

Dasselbe wie der Reiter „Ablauf" in der Oberfläche, nur ohne Browser.

    ./qwen_bild/bin/python demo/demonstration.py --ablauf reise
    ./qwen_bild/bin/python demo/demonstration.py --foto ich.png --steps 30
    ./qwen_bild/bin/python demo/demonstration.py --datei eigener_ablauf.json
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(WURZEL, "webui"))
import ablauf  # noqa: E402


def main():
    zerleger = argparse.ArgumentParser()
    zerleger.add_argument("--port", type=int, default=7860)
    zerleger.add_argument("--ablauf", default="bogen", choices=sorted(ablauf.ABLAEUFE),
                          help="mitgelieferter Ablauf")
    zerleger.add_argument("--datei", help="eigener Ablauf als JSON-Datei")
    zerleger.add_argument("--steps", type=int, default=24)
    zerleger.add_argument("--base", type=int, default=1024)
    zerleger.add_argument("--dauer", type=float, default=20.0, help="Videolänge in Sekunden")
    zerleger.add_argument("--foto", help="eigenes Startbild statt eines erzeugten")
    zerleger.add_argument("--prompt", default="", help="wer erzeugt werden soll")
    argumente = zerleger.parse_args()

    auftrag = {"prompt": argumente.prompt, "base": argumente.base,
               "steps": argumente.steps, "duration": argumente.dauer}
    if argumente.datei:
        with open(argumente.datei, encoding="utf-8") as fh:
            auftrag["bloecke"] = json.load(fh)
    else:
        auftrag["ablauf"] = argumente.ablauf
    if argumente.foto:
        with open(argumente.foto, "rb") as fh:
            auftrag["image"] = "data:image/png;base64," + base64.b64encode(fh.read()).decode()

    basis = f"http://127.0.0.1:{argumente.port}"
    try:
        urllib.request.urlopen(urllib.request.Request(
            basis + "/api/demo", json.dumps(auftrag).encode(),
            {"Content-Type": "application/json"}), timeout=60)
    except urllib.error.HTTPError as fehler:
        raise SystemExit(json.load(fehler).get("error", str(fehler)))
    except urllib.error.URLError as fehler:
        raise SystemExit(f"Kein Server auf Port {argumente.port} ({fehler.reason}). "
                         "Erst ./start.sh starten.")

    start, letzte = time.time(), None
    while True:
        with urllib.request.urlopen(basis + "/api/status", timeout=30) as antwort:
            stand = json.load(antwort)
        if stand.get("stage") and stand["stage"] != letzte:
            letzte = stand["stage"]
            print(f"  [{round(time.time() - start):>5}s] {letzte}")
        if not stand["busy"]:
            break
        time.sleep(3)

    if stand.get("error"):
        raise SystemExit(f"Fehler: {stand['error']}")
    print(f"\n{len(stand['results'])} Bilder in {round(time.time() - start)}s")
    if stand.get("video"):
        print(f"Video: outputs/{stand['video']}")


if __name__ == "__main__":
    main()
