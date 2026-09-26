"""Auftragsabwicklung: was beim Erzeugen eines Bildes oder Ablaufs geschieht.

Der Server nimmt die Anfrage entgegen und beantwortet sie sofort; die Arbeit
laeuft danach in einem eigenen Faden weiter. Hier steht diese Arbeit --
uebersetzen, Groessen bestimmen, die Maschine anwerfen, Bilder ablegen.

Was hier oeffentlich heisst, benutzt der Server: `engine`, `current`,
`OUTPUTS`, `decode`, `run_job`, `run_demo`.
"""

import json
import os
import sys
import traceback
from datetime import datetime

from PIL import Image, PngImagePlugin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Engine  # noqa: E402
import sprache as chat  # noqa: E402
import ablauf  # noqa: E402
import demo  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUTS = os.path.join(ROOT, "outputs")
os.makedirs(OUTPUTS, exist_ok=True)


engine = Engine()
# Ergebnisse des laufenden bzw. zuletzt gelaufenen Auftrags.
current = {"files": [], "error": None, "translated": {}, "stage": "",
           "video": None, "gelesen": {}}


def decode(data_url: str) -> Image.Image:
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
                "form", "paint", "palette", "scene", "angle", "device",
                "scenario", "material"):
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
        palette=params.get("palette") or None,
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


def run_job(params: dict) -> None:
    try:
        current["translated"] = _translate_inputs(params)
        refs = [decode(d) for d in (params.get("images") or []) if d]
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


def run_demo(params: dict) -> None:
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
            basis_bild = decode(params["image"]).convert("RGBA")
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

        # Erst das Startbild ansehen, dann den Ablauf bauen. Zweierlei kommt
        # dabei heraus: manche Schritte passen nicht zu jedem Bild (ein Bart
        # bei einer Frau), und die Beschreibung der Person schaerft danach
        # jede Bewahrungsklausel.
        current["stage"] = "Startbild wird gelesen"
        with open(os.path.join(OUTPUTS, basis_datei), "rb") as fh:
            gelesen = chat.bild_lesen(fh.read())
        current["gelesen"] = gelesen

        # Zu einem hochgeladenen Bild darf man selbst sagen, was darauf zu
        # sehen ist. Das schlaegt die maschinelle Lesung: wer sein eigenes
        # Foto beschreibt, trifft es genauer als ein Blick des Modells.
        eigene = (eigenes["prompt"] or "").strip() if params.get("image") else ""
        if eigene:
            gelesen = dict(gelesen, beschreibung=eigene)
            current["gelesen"] = gelesen

        bloecke = params.get("bloecke")
        if not bloecke:
            name = params.get("ablauf") or "reise"
            eintrag = ablauf.ABLAEUFE.get(name) or ablauf.ABLAEUFE["reise"]
            bloecke = eintrag["bauen"](kulisse, gelesen["geschlecht"] == "frau")
        # Auch ein selbst zusammengestellter Ablauf profitiert davon.
        bloecke = ablauf.mit_beschreibung(bloecke, gelesen["beschreibung"])
        gesamt = ablauf.zu_erzeugen(bloecke)

        # --- Bloecke abarbeiten -------------------------------------------
        je_block: dict[int, list[str]] = {}
        letztes = basis_datei
        zaehler = 1
        for art, buendel in _bloecke_gruppieren(bloecke):
            pruefe()
            namen = [b["titel"] for b in buendel]
            current["stage"] = (f"{', '.join(namen)} · "
                                f"{zaehler + 1}–{zaehler + sum(len(ablauf.bausteine_von(b)) for b in buendel)}"
                                f"/{gesamt}")
            gesammelt.clear()

            if art == "gruppe":
                # Der Gruppen-Pfad, nicht der Bearbeiten-Pfad: letzterer
                # verschmilzt zwei Ansichten derselben Person zu einer. Der
                # Baustein des Blocks geht als Zusatz in die Anweisung und
                # stellt klar, dass zwei Figuren gemeint sind.
                engine.run_series(**_series_kwargs(
                    {"mode": "gruppe", "action": "zusammen",
                     "prompt": ablauf.gruppen_prompt(buendel[0]),
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

            erwartet = sum(len(ablauf.bausteine_von(b)) for b in buendel)
            if len(gesammelt) < erwartet:
                pruefe()
                raise RuntimeError(f"nur {len(gesammelt)} von {erwartet} Bildern")

            rest = iter(gesammelt)
            for block in buendel:
                je_block[id(block)] = [next(rest) for _ in ablauf.bausteine_von(block)]
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
