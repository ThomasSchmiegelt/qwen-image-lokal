"""Kleiner HTTP-Server fuer die Qwen-Image-2.1 Oberflaeche (nur Standardbibliothek).

Start:  ./start.sh          bzw.  ./qwen_bild/bin/python webui/server.py
Dann:   http://127.0.0.1:7860
"""

import base64
import io
import json
import mimetypes
import os
import re
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
from presets import EFFECTS, catalog, overrides, parse_command  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTPUTS = os.path.join(ROOT, "outputs")
HOST = os.environ.get("QWEN_HOST", "127.0.0.1")
PORT = int(os.environ.get("QWEN_PORT", "7860"))
SAFE_NAME = re.compile(r"[\w.\-]+\.png")

os.makedirs(OUTPUTS, exist_ok=True)

engine = Engine()
# Ergebnisse des laufenden bzw. zuletzt gelaufenen Auftrags.
current = {"files": [], "error": None}


def _decode(data_url: str) -> Image.Image:
    raw = base64.b64decode(data_url.split(",", 1)[-1])
    img = Image.open(io.BytesIO(raw))
    img.load()
    return img


def _save(meta: dict, image: Image.Image, stamp: str, kind: str) -> str:
    """Legt das Bild ab und schreibt Prompt/Seed als PNG-Textfelder mit hinein."""
    name = f"{stamp}_{kind}_{meta['index']:02d}_seed{meta['seed']}.png"
    info = PngImagePlugin.PngInfo()
    for key in ("prompt", "seed", "view", "style", "light", "camera", "effect", "form"):
        if meta.get(key) is not None:
            info.add_text(f"qwen_{key}", str(meta[key]))
    image.save(os.path.join(OUTPUTS, name), pnginfo=info)
    return name


def _run_job(params: dict) -> None:
    try:
        refs = [_decode(d) for d in (params.get("images") or []) if d]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        kind = params.get("mode") or ("edit" if refs else "t2i")

        def on_image(meta, image):
            current["files"].append(_save(meta, image, stamp, kind))

        engine.run_series(
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
            count=int(params.get("count", 1)),
            sweep=params.get("sweep") or None,
            lock_seed=bool(params.get("lock_seed", False)),
            view=params.get("view") or None,
            style=params.get("style") or None,
            light=params.get("light") or None,
            camera=params.get("camera") or None,
            on_image=on_image,
        )
        done = len(current["files"])
        engine.note("idle", f"fertig: {done} Bild(er)" if done else "abgebrochen")
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
            return self._json(200, status)

        if path == "/api/info":
            info = catalog()
            info["aspects"] = list(ASPECT_RATIOS)
            info["sizes"] = {a: dimensions_for(a, 1024) for a in ASPECT_RATIOS}
            info["max_references"] = MAX_REFERENCES
            info["reference_token_budget"] = REFERENCE_TOKEN_BUDGET
            info["chat"] = chat.available()
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
        if not has_text and not spec and not params.get("form") and mode not in ("gruppe", "person"):
            return self._json(400, {"error": "Prompt ist leer"})
        if spec.get("needs_image") and not refs:
            return self._json(400, {
                "error": f"„{spec['label']}\u201c braucht ein Bild \u2013 bitte eines hochladen"})
        if len(refs) > MAX_REFERENCES:
            return self._json(400, {"error": f"Hoechstens {MAX_REFERENCES} Referenzbilder"})
        if mode in ("edit", "person") and not refs:
            return self._json(400, {"error": "Bitte ein Referenzbild hochladen"})
        if mode == "gruppe" and len(refs) < 2:
            return self._json(400, {"error": "Fuer ein Gruppenbild mindestens zwei Personen hochladen"})

        if not engine.lock.acquire(blocking=False):
            return self._json(409, {"error": "Es laeuft bereits ein Auftrag"})

        current["files"] = []
        current["error"] = None
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
