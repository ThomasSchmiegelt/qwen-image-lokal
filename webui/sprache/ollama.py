"""Anbindung an Ollama: Adresse, Modell und der Aufruf selbst.

Alle drei Teile des Pakets sprechen ueber diese Datei mit dem Sprachmodell.
`keep_alive: 0` ist wichtig -- das Sprachmodell gibt die Grafikkarte sofort
wieder frei, sonst fehlt sie dem Bildmodell.
"""

import json
import os
import re
import urllib.error
import urllib.request

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("QWEN_CHAT_MODEL", "qwen3.5:4b")
THINK = re.compile(r"<think>.*?</think>", re.S)


def antwort(body: dict, timeout: int = 180) -> dict | str | None:
    """Schickt eine fertige Anfrage an Ollama und gibt die Antwort zurueck.

    Bei `format: "json"` kommt das ausgepackte Objekt, sonst der Text. Faellt
    etwas aus, kommt None -- wer eine Ausnahme braucht, prueft selbst.
    """
    body = {"stream": False, "think": False, "keep_alive": 0, "model": MODEL, **body}
    anfrage = urllib.request.Request(
        OLLAMA.rstrip("/") + "/api/chat", json.dumps(body).encode("utf-8"),
        {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            inhalt = THINK.sub("", json.load(antwort)["message"]["content"]).strip()
    except Exception:
        return None
    if body.get("format") != "json":
        return inhalt
    try:
        return json.loads(inhalt)
    except json.JSONDecodeError:
        return None


def available(timeout: float = 1.5) -> dict:
    """Ist Ollama erreichbar und liegt das eingestellte Modell vor?"""
    try:
        with urllib.request.urlopen(OLLAMA.rstrip("/") + "/api/tags", timeout=timeout) as r:
            names = {m["name"] for m in json.load(r).get("models", [])}
    except Exception:
        return {"available": False, "model": MODEL, "reason": f"Ollama unter {OLLAMA} nicht erreichbar"}
    if MODEL not in names:
        return {"available": False, "model": MODEL,
                "reason": f"Modell {MODEL} fehlt – `ollama pull {MODEL}`"}
    return {"available": True, "model": MODEL, "reason": ""}
