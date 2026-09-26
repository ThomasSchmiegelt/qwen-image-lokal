"""Kleiner HTTP-Server fuer die Qwen-Image-2.1 Oberflaeche (nur Standardbibliothek).

Start:  ./start.sh          bzw.  ./qwen_bild/bin/python webui/server.py
Dann:   http://127.0.0.1:7860
"""

import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import (  # noqa: E402
    ASPECT_RATIOS, MAX_REFERENCES, REFERENCE_TOKEN_BUDGET, dimensions_for,
)
# Die eigentliche Arbeit steht in auftraege.py -- hier nur Routen und Start.
from auftraege import (  # noqa: E402
    current, decode, einreihen, engine, entfernen, leeren, uebersicht,
    verschieben,
)
import projekte  # noqa: E402
import bausteine  # noqa: E402
import geschichte  # noqa: E402
import sprache as chat  # noqa: E402
import ablauf  # noqa: E402
import demo  # noqa: E402
from kataloge import (  # noqa: E402
    AXIS_OFF, EFFECTS, GROUP_ACTIONS, MIMIK, PAINT_TARGET, catalog, overrides,
    parse_command,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SEITE = os.path.join(HERE, "seite")
HOST = os.environ.get("QWEN_HOST", "127.0.0.1")
PORT = int(os.environ.get("QWEN_PORT", "7860"))
SAFE_NAME = re.compile(r"[\w.\-]+\.(png|jsonl|mp4)")
# Fester Befehl, keine Shell: der Aufruf kann nur eine Datei aus outputs/ oeffnen.
GIMP_CMD = os.environ.get("QWEN_GIMP", "gimp")



def _source_state() -> dict[str, str]:
    """Pruefsummen der Python-Dateien, die der Server beim Start geladen hat."""
    state = {}
    # Auch die Unterverzeichnisse: seit der Aufteilung liegen Kataloge und
    # Sprachanbindung in eigenen Paketen, und eine Aenderung dort faellt sonst
    # durch -- der Server liefe mit altem Code, ohne es zu melden.
    for wurzel, ordner, dateien in os.walk(HERE):
        ordner[:] = [o for o in ordner if o != "__pycache__"]
        for name in sorted(dateien):
            if not name.endswith(".py"):
                continue
            pfad = os.path.join(wurzel, name)
            with open(pfad, "rb") as fh:
                schluessel = os.path.relpath(pfad, HERE)
                state[schluessel] = hashlib.sha256(fh.read()).hexdigest()[:12]
    return state


# Beim Start festgehalten. Python laedt Module genau einmal -- wer danach eine
# Datei aendert, sieht die Aenderung erst nach einem Neustart. Das ist schon
# mehrfach fuer einen Programmfehler gehalten worden, deshalb meldet es der
# Server jetzt von sich aus.
SOURCE_AT_START = _source_state()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # ruhiger Log
        if "/api/status" not in (self.path or ""):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- Helfer -----------------------------------------------------------
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj))

    def _nur_hier(self) -> bool:
        """Kommt die Anfrage vom Rechner des Servers selbst?

        Bei QWEN_HOST=0.0.0.0 haengt die Oberflaeche im Netz. Was dort etwas
        anrichtet -- GIMP starten, Bilder loeschen, den Server abschalten --
        bleibt deshalb dem eigenen Rechner vorbehalten.
        """
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def _bild_aus_anfrage(self):
        """Das Bild aus dem Anfragerumpf, als PNG-Bytes fuers Sprachmodell.

        Gibt bei einem Fehler stattdessen (Code, Meldung) zurueck -- der
        Aufrufer erkennt das am Tupel. Das Sprachmodell darf nicht waehrend
        eines Auftrags laufen, beide wollen dieselbe Grafikkarte.
        """
        if engine.lock.locked():
            return 409, {"error": "Es laeuft gerade ein Auftrag"}
        params = self._body()
        if params is None:
            return 400, {"error": "ungueltiges JSON"}
        if not params.get("image"):
            return 400, {"error": "Kein Bild"}
        try:
            roh = decode(params["image"])
        except Exception as exc:
            return 400, {"error": f"Bild nicht lesbar: {exc}"}
        puffer = io.BytesIO()
        roh.convert("RGB").save(puffer, format="PNG")
        return puffer.getvalue()

    def _body(self):
        """Der JSON-Rumpf der Anfrage, oder None wenn er nicht lesbar ist."""
        length = int(self.headers.get("Content-Length", 0))
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return None

    def _output_path(self, name):
        """Pfad in outputs/ -- oder None, wenn der Name nicht sauber ist."""
        if not SAFE_NAME.fullmatch(name):
            return None
        path = os.path.join(projekte.bilder(projekte.aktiv()), name)
        return path if os.path.isfile(path) else None

    # -- Routen -----------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path

        if path in ("/", "/index.html"):
            with open(os.path.join(SEITE, "index.html"), "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")

        if path.startswith("/seite/"):
            # Aufbau, Aussehen und Verhalten der Oberflaeche liegen getrennt.
            # Nur schlichte Namen, keine Verzeichniswechsel.
            name = path[len("/seite/"):]
            if not re.fullmatch(r"[\w.\-]+\.(css|js)", name):
                return self._json(404, {"error": "not found"})
            datei = os.path.join(SEITE, name)
            if not os.path.isfile(datei):
                return self._json(404, {"error": "not found"})
            art = "text/css" if name.endswith(".css") else "text/javascript"
            with open(datei, "rb") as fh:
                return self._send(200, fh.read(), f"{art}; charset=utf-8")

        if path == "/api/status":
            status = engine.snapshot()
            status["results"] = list(current["files"])
            status["error"] = current["error"]
            status["translated"] = dict(current["translated"])
            status["stage"] = current["stage"]
            status["video"] = current["video"]
            status["gelesen"] = dict(current["gelesen"])
            status["tor"] = list(current["tor"])
            status["nummer"] = current["nummer"]
            status["titel"] = current["titel"]
            status.update(uebersicht())
            status["projekt"] = projekte.aktiv()
            status["bausteine"] = bausteine.liste(projekte.aktiv())
            # Solange noch etwas wartet, ist die Oberflaeche nicht fertig --
            # sonst hoerte sie nach dem ersten Auftrag auf nachzufragen.
            status["busy"] = status["busy"] or bool(status["wartend"])
            return self._json(200, status)

        if path == "/api/info":
            info = catalog()
            info["aspects"] = list(ASPECT_RATIOS)
            info["sizes"] = {a: dimensions_for(a, 1024) for a in ASPECT_RATIOS}
            info["max_references"] = MAX_REFERENCES
            info["reference_token_budget"] = REFERENCE_TOKEN_BUDGET
            info["chat"] = chat.available()
            info["axis_off"] = AXIS_OFF
            info["paint_target"] = PAINT_TARGET
            info["gimp"] = {"available": bool(shutil.which(GIMP_CMD)), "command": GIMP_CMD}
            now = _source_state()
            changed = sorted(k for k in set(now) | set(SOURCE_AT_START)
                             if now.get(k) != SOURCE_AT_START.get(k))
            info["source"] = {"stale": bool(changed), "changed": changed}
            info["projekte"] = projekte.liste()
            info["bausteine"] = bausteine.liste(projekte.aktiv())
            info["bausteinarten"] = [{"key": k, "label": v}
                                     for k, v in bausteine.ARTEN.items()]
            info["mimik"] = [{"key": k, "label": v[0]} for k, v in MIMIK.items()]
            info["projekt"] = projekte.aktiv()
            info["demo"] = demo.available()
            info["kulissen"] = [{"key": k, "label": v[0]}
                                for k, v in demo.KULISSEN.items()]
            info["ablaeufe"] = [
                {"key": k, "label": v["label"],
                 "bilder": ablauf.anzahl_bilder(v["bauen"]("auto", None)),
                 "erzeugt": ablauf.zu_erzeugen(v["bauen"]("auto", None)),
                 "bloecke": v["bauen"]("auto", None)}
                for k, v in ablauf.ABLAEUFE.items()]
            return self._json(200, info)

        if path == "/api/gallery":
            files = sorted(
                (f for f in os.listdir(projekte.bilder(projekte.aktiv()))
                 if f.endswith(".png")), reverse=True
            )
            return self._json(200, {"files": files[:120]})

        if path == "/api/meta":
            name = (parse_qs(url.query).get("file") or [""])[0]
            target = self._output_path(name)
            if not target:
                return self._json(404, {"error": "not found"})
            with Image.open(target) as im:
                meta = {k[5:]: v for k, v in im.text.items() if k.startswith("qwen_")}
                meta["size"] = list(im.size)
            return self._json(200, meta)

        if path == "/api/zip":
            names = (parse_qs(url.query).get("files") or [""])[0].split(",")
            paths = [(n, self._output_path(n)) for n in names if n]
            paths = [(n, p) for n, p in paths if p]
            if not paths:
                return self._json(404, {"error": "keine Bilder"})
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
                for name, target in paths:
                    zf.write(target, name)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="qwen-serie.zip"')
            self.send_header("Content-Length", str(buf.tell()))
            self.end_headers()
            return self.wfile.write(buf.getvalue())

        if path.startswith("/outputs/"):
            target = self._output_path(os.path.basename(path))
            if not target:
                return self._json(404, {"error": "not found"})
            ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
            with open(target, "rb") as fh:
                return self._send(200, fh.read(), ctype)

        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/cancel":
            # Ohne Angabe: den laufenden Auftrag stoppen. Mit "nummer": einen
            # wartenden aus der Liste nehmen. Mit "alles": die Liste leeren,
            # der laufende bleibt.
            params = self._body() or {}
            if params.get("alles"):
                return self._json(200, {"ok": True, "entfernt": leeren()})
            if params.get("nummer"):
                weg = entfernen(int(params["nummer"]))
                return self._json(200 if weg else 404, {"ok": weg})
            engine.cancel()
            return self._json(200, {"ok": True})

        if path == "/api/verschieben":
            params = self._body() or {}
            weg = verschieben(int(params.get("nummer") or 0),
                              -1 if params.get("richtung") == "hoch" else 1)
            return self._json(200 if weg else 404, {"ok": weg})

        if path == "/api/video":
            # Aus ausgewaehlten Bildern ein Video mit weichen Uebergaengen.
            # Die Standzeit ergibt sich aus der Wunschlaenge -- mehr muss man
            # nicht angeben.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            namen = [os.path.basename(str(n)) for n in (params.get("files") or [])]
            pfade = [p for p in (self._output_path(n) for n in namen) if p]
            if len(pfade) < 2:
                return self._json(400, {"error": "Mindestens zwei Bilder auswaehlen"})
            if not demo.available()["video"]:
                return self._json(501, {"error": "ffmpeg fehlt"})
            dauer = max(2.0, min(float(params.get("duration") or 20), 600.0))
            ziel = os.path.join(projekte.bilder(projekte.aktiv()),
                                datetime.now().strftime("%Y%m%d-%H%M%S") + "_film.mp4")
            try:
                demo.baue_video(pfade, ziel, gesamtdauer=dauer)
            except Exception as exc:
                return self._json(500, {"error": f"ffmpeg scheiterte: {exc}"})
            return self._json(200, {"ok": True, "video": os.path.basename(ziel),
                                    "bilder": len(pfade), "dauer": dauer})

        if path == "/api/geschichte":
            # Handlung -> Szenen -> Bloecke, wie der Ablauf-Reiter sie kennt.
            # Erzeugt wird hier noch nichts; das entscheidet die Oberflaeche.
            if engine.lock.locked():
                return self._json(409, {"error": "Es laeuft gerade ein Auftrag"})
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            text = (params.get("text") or "").strip()
            if not text:
                return self._json(400, {"error": "Keine Handlung"})
            projekt = projekte.aktiv()
            alle = {b["id"]: b for b in bausteine.liste(projekt)}
            gewaehlt = [alle[k] for k in (params.get("ids") or []) if k in alle]
            if not gewaehlt:
                return self._json(400, {"error":
                    "Erst Bausteine anhaken, die vorkommen sollen"})
            erg = chat.geschichte(text, gewaehlt, int(params.get("anzahl") or 8))
            if not erg["szenen"]:
                return self._json(502, {"error": erg["hinweis"]})
            return self._json(200, {
                "szenen": erg["szenen"],
                "hinweis": erg["hinweis"],
                "bloecke": geschichte.zu_bloecken(erg["szenen"], gewaehlt),
                "startbild": geschichte.startbild(erg["szenen"], gewaehlt)})

        if path == "/api/baustein":
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            projekt = projekte.aktiv()
            was = params.get("tu")

            if was == "speichern":
                return self._json(200, bausteine.speichern(projekt, params.get("baustein") or {}))
            if was == "loeschen":
                gut = bausteine.loeschen(projekt, str(params.get("id") or ""))
                return self._json(200 if gut else 404, {"ok": gut})
            if was == "prompt":
                # Deutsche Beschreibung -> englischer Prompt mit Luecken.
                if engine.lock.locked():
                    return self._json(409, {"error": "Es laeuft gerade ein Auftrag"})
                text = (params.get("text") or "").strip()
                if not text:
                    return self._json(400, {"error": "Keine Beschreibung"})
                erg = chat.baustein_prompt(text, str(params.get("art") or "person"))
                if not erg["prompt"]:
                    return self._json(502, {"error":
                        "Das Sprachmodell hat keinen Prompt geliefert."})
                return self._json(200, erg)
            if was == "zusammensetzen":
                alle = {b["id"]: b for b in bausteine.liste(projekt)}
                teile = [alle[k] for k in (params.get("ids") or []) if k in alle]
                return self._json(200, {
                    "prompt": bausteine.zusammensetzen(teile, params.get("werte") or {}),
                    # Dieselbe Mischung mit offenen Luecken -- so wird sie als
                    # Szene gespeichert und bleibt wiederverwendbar.
                    "vorlage": bausteine.vorlage(teile)})
            return self._json(400, {"error": "unbekannte Aktion"})

        if path == "/api/projekt":
            # Anlegen, wechseln, umbenennen, loeschen. Alles am eigenen
            # Rechner: ein Projekt zu loeschen nimmt Bilder mit.
            if not self._nur_hier():
                return self._json(403, {"error": "Nur vom Rechner des Servers aus"})
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            was = params.get("tu")
            schluessel = str(params.get("key") or "")
            if was == "anlegen":
                neu_p = projekte.anlegen(str(params.get("name") or ""))
                return self._json(200, {"ok": True, "projekt": neu_p,
                                        "aktiv": projekte.aktiv()})
            if was == "waehlen":
                gut = projekte.waehlen(schluessel)
                return self._json(200 if gut else 404,
                                  {"ok": gut, "aktiv": projekte.aktiv()})
            if was == "umbenennen":
                gut = projekte.umbenennen(schluessel, str(params.get("name") or ""))
                return self._json(200 if gut else 404, {"ok": gut})
            if was == "loeschen":
                # Ein laufender Auftrag schreibt womoeglich gerade dorthin.
                if engine.lock.locked():
                    return self._json(409, {"error":
                        "Erst abwarten: es laeuft ein Auftrag"})
                gut = projekte.loeschen(schluessel)
                return self._json(200 if gut else 404,
                                  {"ok": gut, "aktiv": projekte.aktiv()})
            return self._json(400, {"error": "unbekannte Aktion"})

        if path == "/api/bild-lesen":
            # Die kurze Fassung: wer ist zu sehen. Fuer den Ablauf-Reiter, wo
            # die Beschreibung in die Bewahrungsklauseln wandert und nicht als
            # ganzer Bildprompt gebraucht wird.
            bild = self._bild_aus_anfrage()
            if isinstance(bild, tuple):
                return self._json(*bild)
            return self._json(200, chat.bild_lesen(bild))

        if path == "/api/bild-prompt":
            # Rueckwaerts: aus einem mitgebrachten Bild den Prompt schreiben.
            # Wie beim Chat nicht waehrend eines Auftrags -- Ollama und das
            # Bildmodell wuerden sich um die Grafikkarte streiten.
            bild = self._bild_aus_anfrage()
            if isinstance(bild, tuple):
                return self._json(*bild)
            ergebnis = chat.bild_zu_prompt(bild)
            if not ergebnis["prompt"]:
                return self._json(502, {"error":
                    "Das Sprachmodell hat keinen Prompt geliefert."})
            return self._json(200, ergebnis)

        if path == "/api/delete":
            # Loescht eine Datei auf dem Rechner des Servers -- wie beim
            # GIMP-Aufruf nur von dort aus erlaubt.
            if not self._nur_hier():
                return self._json(403, {"error": "Nur vom Rechner des Servers aus"})
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            ziel = self._output_path(os.path.basename(params.get("file") or ""))
            if not ziel:
                return self._json(404, {"error": "Bild nicht gefunden"})
            try:
                os.remove(ziel)
            except OSError as exc:
                return self._json(500, {"error": f"liess sich nicht loeschen: {exc}"})
            return self._json(200, {"ok": True, "file": os.path.basename(ziel)})

        if path == "/api/shutdown":
            if not self._nur_hier():
                return self._json(403, {"error": "Nur vom Rechner des Servers aus"})
            # Erst antworten, dann abschalten: sonst sieht die Seite nur einen
            # abgebrochenen Aufruf und meldet einen Fehler.
            self._json(200, {"ok": True})
            engine.cancel()
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return None

        if path == "/api/open-in-gimp":
            # Startet ein Programm auf dem Rechner des Servers. Deshalb nur von
            # dort aus erreichbar -- bei QWEN_HOST=0.0.0.0 koennte sonst jeder
            # im Netz GIMP-Fenster aufpoppen lassen.
            if self.client_address[0] not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
                return self._json(403, {"error": "Nur vom Rechner des Servers aus"})
            length = int(self.headers.get("Content-Length", 0))
            try:
                params = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as exc:
                return self._json(400, {"error": f"ungueltiges JSON: {exc}"})
            target = self._output_path(os.path.basename(params.get("file") or ""))
            if not target:
                return self._json(404, {"error": "Bild nicht gefunden"})
            if not shutil.which(GIMP_CMD):
                return self._json(501, {"error": f"{GIMP_CMD} ist nicht installiert"})
            if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                return self._json(501, {"error":
                    "Der Server sieht keine Anzeige. start.sh aus einer Desktop-Sitzung starten."})
            try:
                subprocess.Popen(
                    [GIMP_CMD, target], start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError as exc:
                return self._json(500, {"error": f"GIMP liess sich nicht starten: {exc}"})
            return self._json(200, {"ok": True})

        if path == "/api/demo":
            length = int(self.headers.get("Content-Length", 0))
            try:
                params = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as exc:
                return self._json(400, {"error": f"ungueltiges JSON: {exc}"})
            auftrag = einreihen("demo", params)
            return self._json(202, {"ok": True, "nummer": auftrag["nummer"]})

        if path == "/api/chat":
            length = int(self.headers.get("Content-Length", 0))
            try:
                params = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as exc:
                return self._json(400, {"error": f"ungueltiges JSON: {exc}"})
            text = (params.get("text") or "").strip()
            if not text:
                return self._json(400, {"error": "Kein Text"})
            # Das Sprachmodell belegt selbst GPU-Speicher; solange das Bildmodell
            # rechnet, ist daneben kein Platz.
            if engine.lock.locked():
                return self._json(409, {"error": "Es laeuft gerade ein Auftrag"})
            try:
                return self._json(200, chat.interpret(
                    text, int(params.get("has_images") or 0)))
            except RuntimeError as exc:
                return self._json(502, {"error": str(exc)})

        if path != "/api/generate":
            return self._json(404, {"error": "not found"})

        length = int(self.headers.get("Content-Length", 0))
        try:
            params = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            return self._json(400, {"error": f"ungueltiges JSON: {exc}"})

        refs = params.get("images") or []

        # Getippter Kurzbefehl: Er ist die ausdrueckliche Absicht, seine
        # Einstellungen setzen sich deshalb gegen die Regler durch. Wird ein
        # Effekt dagegen im Menue gewaehlt, hat die Oberflaeche die Regler
        # bereits sichtbar umgestellt.
        typed, rest = parse_command(params.get("prompt", ""))
        if typed:
            params["prompt"] = rest
            params["effect"] = typed
            params.update(overrides(EFFECTS[typed]))

        spec = EFFECTS.get(params.get("effect") or "", {})
        mode = params.get("mode") or "t2i"
        has_text = bool(params.get("prompt", "").strip())
        if not has_text and not spec and not params.get("form") \
                and mode not in ("gruppe", "person", "varianten"):
            return self._json(400, {"error": "Prompt ist leer"})
        if spec.get("needs_image") and not refs:
            return self._json(400, {
                "error": f"„{spec['label']}\u201c braucht ein Bild \u2013 bitte eines hochladen"})
        if len(refs) > MAX_REFERENCES:
            return self._json(400, {"error": f"Hoechstens {MAX_REFERENCES} Referenzbilder"})
        if mode in ("edit", "person", "varianten") and not refs:
            return self._json(400, {"error": "Bitte ein Referenzbild hochladen"})
        if mode == "gruppe":
            act = GROUP_ACTIONS.get(params.get("action") or "zusammen") or GROUP_ACTIONS["zusammen"]
            if len(refs) < act["min"]:
                return self._json(400, {"error":
                    f"„{act['label']}“ braucht mindestens {act['min']} Referenzbild(er)"})
            if params.get("action") == "entfernen" and not has_text:
                return self._json(400, {"error": "Bitte beschreiben, wer entfernt werden soll"})

        auftrag = einreihen("generate", params)
        return self._json(202, {"ok": True, "nummer": auftrag["nummer"]})


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Qwen-Image WebUI laeuft auf http://{HOST}:{PORT}  (Strg+C zum Beenden)")
    print(f"Bilder landen in {projekte.bilder(projekte.aktiv())}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbeendet")
    else:
        # serve_forever() kehrt nur zurueck, wenn /api/shutdown es angehalten hat.
        print("ueber die Oberflaeche beendet")
    server.server_close()


if __name__ == "__main__":
    main()
