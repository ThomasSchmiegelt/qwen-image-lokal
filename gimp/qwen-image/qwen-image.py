#!/usr/bin/env python3
"""Qwen-Image 2.1 in GIMP.

Das Plugin rechnet nichts selbst. Es redet ueber HTTP mit dem lokalen Server
aus diesem Projekt (`./start.sh`), schickt ihm die aktuelle Ebene und legt das
Ergebnis als neue Ebene an.

Der Prompt versteht dieselben Kurzbefehle wie die Weboberflaeche -- der Server
wertet sie aus, das Plugin muss die Liste also nicht kennen und kann nicht
veralten. "/remove BG", "/colorize", "/blueprint" und so weiter.

Besteht beim Bearbeiten eine Auswahl, bekommt die neue Ebene eine Ebenenmaske
aus dieser Auswahl. Damit wirkt die Aenderung nur dort, und GIMPs Auswahl- und
Pinselwerkzeuge sind der Maskeneditor -- Qwen-Image 2.1 selbst hat keinen
Masken-Eingang.
"""

import base64
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
from gi.repository import Gimp, GimpUi, Gio, GLib, GObject  # noqa: E402

DEFAULT_URL = os.environ.get("QWEN_URL", "http://127.0.0.1:7860")
POLL_SECONDS = 1.0
TIMEOUT_SECONDS = 1800


def _(message):
    return message


# --- Verkehr mit dem Server ---------------------------------------------
def _get(url, path):
    with urllib.request.urlopen(url.rstrip("/") + path, timeout=30) as response:
        return json.load(response)


def _post(url, path, payload):
    request = urllib.request.Request(
        url.rstrip("/") + path, json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, json.load(response)


def _call(url, path, payload):
    """POST mit lesbaren Fehlern statt roher HTTP-Ausnahmen."""
    try:
        return _post(url, path, payload)[1]
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error).get("error", str(error))
        except Exception:
            detail = str(error)
        raise RuntimeError(detail)
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Kein Kontakt zu {url} – läuft ./start.sh?  ({error.reason})")


def interpret(url, text, has_images):
    """Freitext vom Sprachmodell in Einstellungen uebersetzen lassen.

    Der Server macht die eigentliche Arbeit und prueft die Antwort; hier kommt
    ein fertiger Satz Werte an.
    """
    return _call(url, "/api/chat", {"text": text, "has_images": has_images})


def _submit(url, payload):
    """Auftrag abschicken und bis zum Ende begleiten. Liefert die Dateinamen."""
    _call(url, "/api/generate", payload)

    Gimp.progress_init("Qwen-Image rechnet …")
    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        state = _get(url, "/api/status")
        done, total = len(state["results"]), max(state.get("count") or 1, 1)
        step, steps = state.get("step") or 0, state.get("total") or 1
        Gimp.progress_set_text(state.get("message", ""))
        Gimp.progress_update(min(0.99, (done + step / steps) / total))
        if not state["busy"]:
            Gimp.progress_end()
            if state.get("error"):
                raise RuntimeError(state["error"])
            return state["results"]
        time.sleep(POLL_SECONDS)
    Gimp.progress_end()
    raise RuntimeError("Zeitüberschreitung – der Auftrag läuft noch auf dem Server.")


def _fetch(url, name):
    """Ergebnis herunterladen und als lokale Datei ablegen."""
    handle, path = tempfile.mkstemp(prefix="qwen-", suffix=".png")
    with urllib.request.urlopen(url.rstrip("/") + "/outputs/" + name, timeout=120) as r:
        os.write(handle, r.read())
    os.close(handle)
    return path


# --- Umgang mit dem Bild -------------------------------------------------
def _export(image):
    """Das sichtbare Bild als PNG-Datenurl -- eine flache Kopie, das Original
    bleibt unberuehrt."""
    handle, path = tempfile.mkstemp(prefix="qwen-src-", suffix=".png")
    os.close(handle)
    copy = image.duplicate()
    copy.flatten()
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, copy,
                   Gio.File.new_for_path(path), None)
    copy.delete()
    with open(path, "rb") as fh:
        data = base64.b64encode(fh.read()).decode("ascii")
    os.unlink(path)
    return "data:image/png;base64," + data


def _insert(image, path, label, fit):
    """Ergebnis als neue Ebene einhaengen.

    `fit` skaliert die Ebene auf die Leinwandgroesse. Beim Bearbeiten ist das
    noetig, weil das Modell auf sein eigenes Raster rundet und die Ebene sonst
    um ein paar Pixel gegen das Original verschoben liegt.
    """
    layer = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, image,
                                 Gio.File.new_for_path(path))
    layer.set_name(label)
    image.insert_layer(layer, None, 0)
    if fit:
        layer.scale(image.get_width(), image.get_height(), False)
        layer.set_offsets(0, 0)
    else:
        layer.set_offsets((image.get_width() - layer.get_width()) // 2,
                          (image.get_height() - layer.get_height()) // 2)
    return layer


def _apply_selection_mask(image, layer):
    """Auswahl als Ebenenmaske -- die Aenderung wirkt nur innerhalb."""
    if Gimp.Selection.is_empty(image):
        return False
    layer.add_mask(layer.create_mask(Gimp.AddMaskType.SELECTION))
    return True


# Was das Sprachmodell bestimmen darf. Schritte, Auflösung und Seed bleiben
# beim Dialog -- die stellt man bewusst ein, nicht nebenbei im Satz.
PLAN_KEYS = ("prompt", "aspect", "count", "style", "light", "camera", "view",
             "effect", "form", "sweep", "lock_seed", "transparent")


def _merge_plan(payload, plan):
    for key in PLAN_KEYS:
        if key in plan:
            payload[key] = plan[key]
    return payload


def _fail(procedure, message):
    Gimp.message(message)
    return procedure.new_return_values(
        Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(message))


def _dialog(procedure, config, run_mode, key):
    if run_mode != Gimp.RunMode.INTERACTIVE:
        return True
    GimpUi.init(key)
    dialog = GimpUi.ProcedureDialog(procedure=procedure, config=config)
    dialog.fill(None)
    ok = dialog.run()
    dialog.destroy()
    return ok


# --- Die drei Menuepunkte ------------------------------------------------
def run_generate(procedure, run_mode, image, drawables, config, data):
    if not _dialog(procedure, config, run_mode, "qwen-generate"):
        return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

    payload = {
        "mode": "t2i",
        "prompt": config.get_property("prompt"),
        "aspect": config.get_property("aspect"),
        "base": int(config.get_property("resolution")),
        "steps": config.get_property("steps"),
        "seed": config.get_property("seed"),
        "count": config.get_property("count"),
        "images": [],
    }
    url = config.get_property("server")

    image.undo_group_start()
    try:
        if config.get_property("interpret"):
            plan = interpret(url, payload["prompt"], 0)
            _merge_plan(payload, plan)
            Gimp.message("Qwen: " + (plan.get("note") or "verstanden"))
        names = _submit(url, payload)
        for index, name in enumerate(names, start=1):
            path = _fetch(url, name)
            _insert(image, path, f"Qwen {index}", fit=False)
            os.unlink(path)
    except RuntimeError as error:
        image.undo_group_end()
        return _fail(procedure, str(error))
    image.undo_group_end()
    Gimp.displays_flush()
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


def _edit(procedure, run_mode, image, config, prompt, label, use_chat=False):
    url = config.get_property("server")
    payload = {
        "mode": "edit",
        "prompt": prompt,
        "images": [_export(image)],
        "base": int(config.get_property("resolution")),
        "follow_reference": True,
        "steps": config.get_property("steps"),
        "seed": config.get_property("seed"),
        "count": 1,
    }

    image.undo_group_start()
    try:
        if use_chat and prompt.strip():
            plan = interpret(url, prompt, 1)
            _merge_plan(payload, plan)
            payload["mode"] = "edit"
            Gimp.message("Qwen: " + (plan.get("note") or "verstanden"))
        names = _submit(url, payload)
        if not names:
            raise RuntimeError("Der Server hat kein Bild geliefert.")
        path = _fetch(url, names[0])
        layer = _insert(image, path, label, fit=True)
        os.unlink(path)
        masked = _apply_selection_mask(image, layer)
    except RuntimeError as error:
        image.undo_group_end()
        return _fail(procedure, str(error))
    image.undo_group_end()
    Gimp.displays_flush()
    if masked:
        Gimp.message("Die neue Ebene ist auf die Auswahl maskiert.")
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


def run_edit(procedure, run_mode, image, drawables, config, data):
    if not _dialog(procedure, config, run_mode, "qwen-edit"):
        return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
    return _edit(procedure, run_mode, image, config,
                 config.get_property("prompt"), "Qwen Bearbeitung",
                 use_chat=config.get_property("interpret"))


def run_remove_bg(procedure, run_mode, image, drawables, config, data):
    if not _dialog(procedure, config, run_mode, "qwen-remove-bg"):
        return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
    return _edit(procedure, run_mode, image, config, "/remove BG", "Qwen freigestellt")


# --- Registrierung -------------------------------------------------------
ASPECTS = ["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16"]
RESOLUTIONS = [("1024", "1024 px (schnell)"), ("1536", "1536 px"), ("2048", "2048 px (langsam)")]


def _choice(pairs):
    choice = Gimp.Choice.new()
    for index, (nick, label) in enumerate(pairs):
        choice.add(nick, index, label, "")
    return choice


def _add_interpret_argument(procedure):
    procedure.add_boolean_argument(
        "interpret", _("Freitext deuten"),
        _("Den Text erst von einem Sprachmodell übersetzen und auswerten lassen. "
          "Braucht ein laufendes Ollama. Deutsch geht dann, und Angaben wie "
          "„hochkant“ oder „als Zeichentrick“ werden umgesetzt."),
        False, GObject.ParamFlags.READWRITE)


def _common_arguments(procedure, with_aspect):
    procedure.add_string_argument(
        "server", _("Server"), _("Adresse des lokalen Qwen-Image-Servers"),
        DEFAULT_URL, GObject.ParamFlags.READWRITE)
    if with_aspect:
        procedure.add_choice_argument(
            "aspect", _("Seitenverhältnis"), _("Seitenverhältnis des neuen Bildes"),
            _choice([(a, a) for a in ASPECTS]), "1:1", GObject.ParamFlags.READWRITE)
    procedure.add_choice_argument(
        "resolution", _("Auflösung"), _("Längere Kante in Pixeln"),
        _choice(RESOLUTIONS), "1024", GObject.ParamFlags.READWRITE)
    procedure.add_int_argument(
        "steps", _("Schritte"), _("Mehr Schritte, mehr Details, mehr Zeit"),
        1, 100, 40, GObject.ParamFlags.READWRITE)
    procedure.add_int_argument(
        "seed", _("Seed"), _("Gleicher Seed, gleiches Ergebnis"),
        0, 2147483647, 42, GObject.ParamFlags.READWRITE)


class QwenImage(Gimp.PlugIn):
    def do_set_i18n(self, procname):
        # Kein Uebersetzungskatalog dabei; die Texte stehen direkt im Code.
        return False

    def do_query_procedures(self):
        return ["qwen-generate", "qwen-edit", "qwen-remove-bg"]

    def do_create_procedure(self, name):
        handler = {"qwen-generate": run_generate,
                   "qwen-edit": run_edit,
                   "qwen-remove-bg": run_remove_bg}[name]
        procedure = Gimp.ImageProcedure.new(
            self, name, Gimp.PDBProcType.PLUGIN, handler, None)
        procedure.set_image_types("*")
        procedure.set_attribution("Qwen-Image WebUI", "Qwen-Image WebUI", "2026")

        if name == "qwen-generate":
            procedure.set_menu_label(_("_Text zu Bild …"))
            procedure.set_documentation(
                _("Bild aus einer Beschreibung erzeugen"),
                _("Erzeugt ein Bild aus einem Prompt und legt es als neue Ebene an."),
                name)
            procedure.add_string_argument(
                "prompt", _("Prompt"), _("Was soll zu sehen sein?"),
                "", GObject.ParamFlags.READWRITE)
            _add_interpret_argument(procedure)
            _common_arguments(procedure, with_aspect=True)
            procedure.add_int_argument(
                "count", _("Anzahl Bilder"), _("Jedes Bild wird eine eigene Ebene"),
                1, 20, 1, GObject.ParamFlags.READWRITE)

        elif name == "qwen-edit":
            procedure.set_menu_label(_("_Bild bearbeiten …"))
            procedure.set_documentation(
                _("Das sichtbare Bild nach Anweisung ändern"),
                _("Schickt das sichtbare Bild an den Server. Kurzbefehle wie "
                  "/remove BG oder /colorize funktionieren im Prompt. Besteht eine "
                  "Auswahl, wirkt die Änderung nur dort."),
                name)
            procedure.add_string_argument(
                "prompt", _("Anweisung"),
                _("z. B. „Hintergrund durch einen Sonnenuntergang ersetzen“ "
                  "oder ein Kurzbefehl wie /colorize"),
                "", GObject.ParamFlags.READWRITE)
            _add_interpret_argument(procedure)
            _common_arguments(procedure, with_aspect=False)

        else:
            procedure.set_menu_label(_("_Hintergrund entfernen"))
            procedure.set_documentation(
                _("Motiv freistellen"),
                _("Entfernt den Hintergrund und legt das Motiv mit Transparenz "
                  "als neue Ebene an."),
                name)
            _common_arguments(procedure, with_aspect=False)

        # Erst nach set_menu_label -- sonst lehnt GIMP den Menuepfad ab.
        procedure.add_menu_path("<Image>/Filters/Qwen")
        return procedure


Gimp.main(QwenImage.__gtype__, sys.argv)
