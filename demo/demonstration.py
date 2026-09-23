#!/usr/bin/env python3
"""Vorführung von der Kommandozeile aus.

Dasselbe wie der Reiter „Vorführung" in der Oberfläche, nur ohne Browser. Die
Schritte stehen in webui/demo.py und werden von beiden Wegen benutzt.

    ./qwen_bild/bin/python demo/demonstration.py [--port 7860] [--steps 30]
                                                 [--foto bild.png]
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
import demo  # noqa: E402


def main():
    zerleger = argparse.ArgumentParser()
    zerleger.add_argument("--port", type=int, default=7860)
    zerleger.add_argument("--steps", type=int, default=30)
    zerleger.add_argument("--base", type=int, default=1024)
    zerleger.add_argument("--foto", help="eigenes Bild einer Person statt eines erzeugten")
    zerleger.add_argument("--prompt", default="", help="wer erzeugt werden soll")
    zerleger.add_argument("--ziel", default=demo.HINTERGRUND_ZIEL,
                          help="was in Schritt 4 umgefärbt wird")
    argumente = zerleger.parse_args()

    basis = f"http://127.0.0.1:{argumente.port}"
    auftrag = {"prompt": argumente.prompt, "background_target": argumente.ziel,
               "base": argumente.base, "steps": argumente.steps}
    if argumente.foto:
        with open(argumente.foto, "rb") as fh:
            auftrag["image"] = "data:image/png;base64," + base64.b64encode(fh.read()).decode()

    try:
        urllib.request.urlopen(urllib.request.Request(
            basis + "/api/demo", json.dumps(auftrag).encode(),
            {"Content-Type": "application/json"}), timeout=60)
    except urllib.error.URLError as fehler:
        raise SystemExit(f"Kein Server auf Port {argumente.port} ({fehler.reason}). "
                         "Erst ./start.sh starten.")
    except urllib.error.HTTPError as fehler:
        raise SystemExit(json.load(fehler).get("error", str(fehler)))

    start, letzte = time.time(), None
    while True:
        with urllib.request.urlopen(basis + "/api/status", timeout=30) as antwort:
            stand = json.load(antwort)
        if stand.get("stage") and stand["stage"] != letzte:
            letzte = stand["stage"]
            print(f"  [{round(time.time() - start):>4}s] {letzte}")
        if not stand["busy"]:
            break
        time.sleep(2)

    if stand.get("error"):
        raise SystemExit(f"Fehler: {stand['error']}")
    print(f"\n{len(stand['results'])} Bilder in {round(time.time() - start)}s")
    if stand.get("video"):
        print(f"Video: outputs/{stand['video']}")


if __name__ == "__main__":
    main()
