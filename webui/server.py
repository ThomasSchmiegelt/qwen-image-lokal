"""Kleiner HTTP-Server fuer die Qwen-Image-2.1 Oberflaeche (nur Standardbibliothek).

Start:  ./start.sh          bzw.  ./qwen_bild/bin/python webui/server.py
Dann:   http://127.0.0.1:7860
"""

import base64
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
import traceback
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PIL import Image, PngImagePlugin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import (  # noqa: E402
    ASPECT_RATIOS, MAX_REFERENCES, REFERENCE_TOKEN_BUDGET, Engine, dimensions_for,
)
import chat  # noqa: E402
import ablauf  # noqa: E402
import demo  # noqa: E402
from presets import (  # noqa: E402
    AXIS_OFF, EFFECTS, GROUP_ACTIONS, PAINT_TARGET, catalog, overrides, parse_command,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTPUTS = os.path.join(ROOT, "outputs")
HOST = os.environ.get("QWEN_HOST", "127.0.0.1")
PORT = int(os.environ.get("QWEN_PORT", "7860"))
SAFE_NAME = re.compile(r"[\w.\-]+\.(png|jsonl|mp4)")
# Fester Befehl, keine Shell: der Aufruf kann nur eine Datei aus outputs/ oeffnen.
GIMP_CMD = os.environ.get("QWEN_GIMP", "gimp")

os.makedirs(OUTPUTS, exist_ok=True)


def _source_state() -> dict[str, str]:
    """Pruefsummen der Python-Dateien, die der Server beim Start geladen hat."""
    state = {}
    for name in sorted(os.listdir(HERE)):
        if name.endswith(".py"):
            with open(os.path.join(HERE, name), "rb") as fh:
                state[name] = hashlib.sha256(fh.read()).hexdigest()[:12]
    return state


# Beim Start festgehalten. Python laedt Module genau einmal -- wer danach eine
# Datei aendert, sieht die Aenderung erst nach einem Neustart. Das ist schon
# mehrfach fuer einen Programmfehler gehalten worden, deshalb meldet es der
# Server jetzt von sich aus.
SOURCE_AT_START = _source_state()

engine = Engine()
# Ergebnisse des laufenden bzw. zuletzt gelaufenen Auftrags.
current = {"files": [], "error": None, "translated": {}, "stage": "", "video": None}


def _decode(data_url: str) -> Image.Image:
    raw = base64.b64decode(data_url.split(",", 1)[-1])
    img = Image.open(io.BytesIO(raw))
    img.load()
    return img


def _save(meta: dict, image: Image.Image, stamp: str, kind: str,
          nummer: int | None = None) -> str:
    """Legt das Bild ab und schreibt Prompt/Seed als PNG-Textfelder mit hinein.

    `meta["index"]` zaehlt je Serienaufruf ab 1. Wer mehrere Serien unter
    demselben Zeitstempel ablegt, muss die Nummer deshalb selbst vergeben --
    sonst ueberschreiben sich die Dateien gegenseitig.
    """
    name = f"{stamp}_{kind}_{(nummer if nummer is not None else meta['index']):02d}_seed{meta['seed']}.png"
    info = PngImagePlugin.PngInfo()
    for key in ("prompt", "seed", "view", "style", "light", "camera", "effect",
                "form", "paint", "scene", "angle", "device", "scenario", "material"):
        if meta.get(key) is not None:
            info.add_text(f"qwen_{key}", str(meta[key]))
    image.save(os.path.join(OUTPUTS, name), pnginfo=info)
    return name


# Freitextfelder, die im Prompt landen und deshalb englisch sein sollten.
TRANSLATABLE = ("prompt", "keep", "paint_target", "negative_prompt")


def _translate_inputs(params: dict) -> dict:
    """Deutsche Eingaben vor dem Auftrag ins Englische bringen.

    Faellt Ollama aus, bleibt alles wie eingegeben -- lieber ein Bild aus
    deutschem Prompt als gar keines.
    """
    quelle = {k: params.get(k) or "" for k in TRANSLATABLE}
    # Die Rollentexte der einzelnen Referenzbilder sind ebenfalls Freitext.
    rollen = list(params.get("image_prompts") or [])
    for i, text in enumerate(rollen):
        quelle[f"bild{i + 1}"] = text or ""

    engine.note("loading", "Eingaben werden übersetzt …")
    fertig = chat.translate(quelle)

    for i in range(len(rollen)):
        neu = fertig.get(f"bild{i + 1}")
        if neu:
            rollen[i] = neu
    if rollen:
        params["image_prompts"] = rollen
    params.update({k: v for k, v in fertig.items() if k in TRANSLATABLE})
    return fertig


def _series_kwargs(params: dict, refs: list, kind: str, on_image) -> dict:
    """Uebersetzt einen Parametersatz der Schnittstelle in Engine-Argumente.

    Auftrag und Vorfuehrung teilen sich diese Abbildung -- die Vorfuehrung soll
    ausdruecklich denselben Weg nehmen wie ein normaler Auftrag.
    """
    return dict(
        prompt=params.get("prompt", ""),
        negative_prompt=params.get("negative_prompt", ""),
        images=refs,
        mode=kind,
        aspect=params.get("aspect", "1:1"),
        base=int(params.get("base", 1024)),
        follow_reference=bool(params.get("follow_reference", True)),
        steps=int(params.get("steps", 40)),
        seed=int(params.get("seed", 42)),
        true_cfg_scale=float(params.get("true_cfg_scale", 1.0)),
        transparent=bool(params.get("transparent", False)),
        effect=params.get("effect") or None,
        form=params.get("form") or None,
        keep=params.get("keep") or "The main subject",
        paint=params.get("paint") or None,
        scene=params.get("scene") or None,
        angle=params.get("angle") or None,
        device=params.get("device") or None,
        paint_target=params.get("paint_target") or "",
        scenario=params.get("scenario") or None,
        material=params.get("material") or None,
        subject=params.get("subject") or "fahrzeug",
        image_prompts=params.get("image_prompts") or [],
        action=params.get("action") or "zusammen",
        group_size=int(params.get("group_size") or 2),
        count=int(params.get("count", 1)),
        sweep=params.get("sweep") or None,
        lock_seed=bool(params.get("lock_seed", False)),
        view=params.get("view") or None,
        style=params.get("style") or None,
        light=params.get("light") or None,
        camera=params.get("camera") or None,
        on_image=on_image,
    )


def _run_job(params: dict) -> None:
    try:
        current["translated"] = _translate_inputs(params)
        refs = [_decode(d) for d in (params.get("images") or []) if d]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        kind = params.get("mode") or ("edit" if refs else "t2i")

        manifest = os.path.join(OUTPUTS, f"{stamp}_{kind}.jsonl") if kind == "varianten" else None

        def on_image(meta, image):
            name = _save(meta, image, stamp, kind)
            current["files"].append(name)
            if manifest:
                # Eine Zeile je Bild: was variiert wurde, direkt neben der Datei.
                # Damit laesst sich der Satz spaeter filtern oder ausbalancieren.
                row = {"file": name, **{k: v for k, v in meta.items() if k != "index"}}
                with open(manifest, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        engine.run_series(**_series_kwargs(params, refs, kind, on_image))
        done = len(current["files"])
        engine.note("idle", f"fertig: {done} Bild(er)" if done else "abgebrochen")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        engine.note("error", current["error"])
    finally:
        engine.lock.release()


class Abgebrochen(Exception):
    """Der Benutzer hat die Vorfuehrung gestoppt."""


def _bloecke_gruppieren(bloecke: list[dict]) -> list[tuple[str, list[dict]]]:
    """Faellige Ladevorgaenge buendeln.

    Aufeinanderfolgende Bloecke, die auf dem Startbild aufsetzen, laufen als
    eine Serie -- ein Ladevorgang statt einer je Bild. Ein Block, der auf dem
    vorigen Bild aufsetzt, braucht zwangslaeufig einen eigenen.
    """
    gebuendelt: list[tuple[str, list[dict]]] = []
    for block in bloecke:
        art = "gruppe" if block.get("art") == "gruppe" else block.get("referenz", "start")
        if gebuendelt and gebuendelt[-1][0] == "start" == art:
            gebuendelt[-1][1].append(block)
        else:
            gebuendelt.append((art, [block]))
    return gebuendelt


def _run_demo(params: dict) -> None:
    """Arbeitet einen Ablauf ab und baut daraus ein Video."""
    try:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        fest = {"base": int(params.get("base", 1024)),
                "steps": int(params.get("steps", 24)), "true_cfg_scale": 1.0}
        seed = int(params.get("seed") or 3100)

        # Was hinter der Person steht. Ohne Angabe eine aus dem Seed
        # abgeleitete -- so wechselt die Kulisse von Lauf zu Lauf.
        kulisse = demo.kulisse_waehlen(params.get("kulisse") or "", seed)

        eigenes = {"prompt": params.get("prompt") or ""}
        if eigenes["prompt"].strip():
            engine.note("loading", "Eingaben werden übersetzt …")
            current["translated"] = chat.translate(eigenes)
            eigenes.update(current["translated"])

        gesammelt: list[str] = []

        def sammler(meta, image):
            name = _save(meta, image, stamp, "demo", nummer=len(current["files"]) + 1)
            current["files"].append(name)
            gesammelt.append(name)

        def pruefe():
            if engine.aborted:
                raise Abgebrochen()

        def laden(datei):
            bild = Image.open(os.path.join(OUTPUTS, datei))
            bild.load()
            return bild

        # --- Startbild ---------------------------------------------------
        pruefe()
        current["stage"] = "Startbild"
        if params.get("image"):
            basis_bild = _decode(params["image"]).convert("RGBA")
            basis_datei = _save({"index": 1, "seed": seed, "prompt": "hochgeladenes Startbild"},
                                basis_bild, stamp, "demo", nummer=1)
            current["files"].append(basis_datei)
        else:
            engine.run_series(**_series_kwargs(
                {"mode": "t2i",
                 "prompt": eigenes["prompt"] or demo.basis_prompt(kulisse),
                 "aspect": "3:2", "seed": seed, "count": 1, **fest}, [], "t2i", sammler))
            if not gesammelt:
                pruefe()
                raise RuntimeError("Das Startbild konnte nicht erzeugt werden")
            basis_datei = gesammelt[-1]
            basis_bild = laden(basis_datei)

        # Der Ablauf wird erst jetzt gebaut: manche Schritte passen nicht zu
        # jedem Startbild. Ein Bart-Schritt ergibt bei einer Frau keinen Sinn.
        bloecke = params.get("bloecke")
        if not bloecke:
            with open(os.path.join(OUTPUTS, basis_datei), "rb") as fh:
                weiblich = chat.ist_weiblich(fh.read())
            name = params.get("ablauf") or "reise"
            eintrag = ablauf.ABLAEUFE.get(name) or ablauf.ABLAEUFE["reise"]
            bloecke = eintrag["bauen"](kulisse, weiblich)
        gesamt = ablauf.zu_erzeugen(bloecke)

        # --- Bloecke abarbeiten -------------------------------------------
        je_block: dict[int, list[str]] = {}
        letztes = basis_datei
        zaehler = 1
        for art, buendel in _bloecke_gruppieren(bloecke):
            pruefe()
            namen = [b["titel"] for b in buendel]
            current["stage"] = (f"{', '.join(namen)} · "
                                f"{zaehler + 1}–{zaehler + sum(len(b['bausteine']) for b in buendel)}"
                                f"/{gesamt}")
            gesammelt.clear()

            if art == "gruppe":
                # Der Gruppen-Pfad, nicht der Bearbeiten-Pfad: letzterer
                # verschmilzt zwei Ansichten derselben Person zu einer. Der
                # Baustein des Blocks geht als Zusatz in die Anweisung und
                # stellt klar, dass zwei Figuren gemeint sind.
                engine.run_series(**_series_kwargs(
                    {"mode": "gruppe", "action": "zusammen",
                     "prompt": buendel[0]["bausteine"][0],
                     "aspect": "3:2", "follow_reference": False, "seed": seed,
                     "count": 1, **fest},
                    [laden(letztes), basis_bild], "gruppe", sammler))
            else:
                vorlage = basis_bild if art == "start" else laden(letztes)
                schritte = [s for b in buendel
                            for s in ablauf.schritte([b])]
                engine.run_series(
                    **_series_kwargs(
                        {"mode": "edit", "prompt": "", "seed": seed,
                         "follow_reference": True, **fest}, [vorlage], "edit", sammler),
                    prompts=[s["prompt"] for s in schritte],
                    seeds=[seed if s["fest"] else seed + zaehler + i
                           for i, s in enumerate(schritte)])

            erwartet = sum(len(b["bausteine"]) for b in buendel)
            if len(gesammelt) < erwartet:
                pruefe()
                raise RuntimeError(f"nur {len(gesammelt)} von {erwartet} Bildern")

            rest = iter(gesammelt)
            for block in buendel:
                je_block[id(block)] = [next(rest) for _ in block["bausteine"]]
            letztes = gesammelt[-1]
            zaehler += erwartet

        # --- Reihenfolge fuers Video ---------------------------------------
        reihenfolge = [basis_datei]
        for block in bloecke:
            reihenfolge += je_block.get(id(block), [])
            if block.get("zurueck"):
                reihenfolge.append(basis_datei)

        if demo.available()["video"]:
            pruefe()
            current["stage"] = "Video wird gebaut"
            video_ziel = os.path.join(OUTPUTS, f"{stamp}_demonstration.mp4")
            demo.baue_video([os.path.join(OUTPUTS, n) for n in reihenfolge], video_ziel,
                            gesamtdauer=float(params.get("duration") or 20.0))
            current["video"] = os.path.basename(video_ziel)

        current["stage"] = ""
        engine.note("idle", f"Ablauf fertig: {len(reihenfolge)} Bilder im Video")
    except Abgebrochen:
        current["stage"] = ""
        engine.note("idle", f"abgebrochen nach {len(current['files'])} Bild(ern)")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        engine.note("error", current["error"])
    finally:
        engine.lock.release()


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

    def _output_path(self, name):
        """Pfad in outputs/ -- oder None, wenn der Name nicht sauber ist."""
        if not SAFE_NAME.fullmatch(name):
            return None
        path = os.path.join(OUTPUTS, name)
        return path if os.path.isfile(path) else None

    # -- Routen -----------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path

        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")

        if path == "/api/status":
            status = engine.snapshot()
            status["results"] = list(current["files"])
            status["error"] = current["error"]
            status["translated"] = dict(current["translated"])
            status["stage"] = current["stage"]
            status["video"] = current["video"]
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
                (f for f in os.listdir(OUTPUTS) if f.endswith(".png")), reverse=True
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
            engine.cancel()
            return self._json(200, {"ok": True})

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
            if not engine.lock.acquire(blocking=False):
                return self._json(409, {"error": "Es laeuft bereits ein Auftrag"})
            engine.aborted = False
            current["files"] = []
            current["error"] = None
            current["translated"] = {}
            current["stage"] = "wird vorbereitet"
            current["video"] = None
            threading.Thread(target=_run_demo, args=(params,), daemon=True).start()
            return self._json(202, {"ok": True})

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

        if not engine.lock.acquire(blocking=False):
            return self._json(409, {"error": "Es laeuft bereits ein Auftrag"})

        engine.aborted = False
        current["files"] = []
        current["error"] = None
        current["translated"] = {}
        current["stage"] = ""
        current["video"] = None
        threading.Thread(target=_run_job, args=(params,), daemon=True).start()
        return self._json(202, {"ok": True})


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Qwen-Image WebUI laeuft auf http://{HOST}:{PORT}  (Strg+C zum Beenden)")
    print(f"Bilder landen in {OUTPUTS}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbeendet")


if __name__ == "__main__":
    main()
