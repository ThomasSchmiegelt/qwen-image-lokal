"""Auftragsabwicklung: was beim Erzeugen eines Bildes oder Ablaufs geschieht.

Der Server nimmt die Anfrage entgegen und beantwortet sie sofort; die Arbeit
laeuft danach in einem eigenen Faden weiter. Hier steht diese Arbeit --
uebersetzen, Groessen bestimmen, die Maschine anwerfen, Bilder ablegen.

Auftraege werden eingereiht statt abgewiesen: `einreihen()` haengt an, ein
einziger Arbeitsfaden nimmt sie der Reihe nach ab. So darf man mehrere
Auftraege hintereinander abschicken, ohne auf das Ende zu warten -- gleichzeitig
rechnen kann die eine Grafikkarte ohnehin nicht.

Was hier oeffentlich heisst, benutzt der Server: `engine`, `current`,
`decode`, `einreihen`, `entfernen`, `uebersicht`, `ziel`.
"""

import base64
import io
import itertools
import json
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime

from PIL import Image, PngImagePlugin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Engine  # noqa: E402
import sprache as chat  # noqa: E402
import ablauf  # noqa: E402
import demo  # noqa: E402
import projekte  # noqa: E402
import bausteine  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Wohin die Bilder gehen, entscheidet das Projekt. Ein Auftrag merkt sich beim
# Einreihen, zu welchem er gehoert -- wer waehrenddessen umschaltet, soll seine
# Bilder nicht ploetzlich woanders wiederfinden.
_projekt_des_laufs = projekte.ALLGEMEIN


def ziel() -> str:
    """Das Bildverzeichnis des gerade laufenden Auftrags."""
    return projekte.bilder(_projekt_des_laufs)


engine = Engine()
# Ergebnisse des laufenden bzw. zuletzt gelaufenen Auftrags.
current = {"files": [], "error": None, "translated": {}, "stage": "",
           "video": None, "gelesen": {}, "nummer": 0, "titel": "", "tor": [], "gliederung": [], "expose": {}}

# Die Warteschlange. Wartende Auftraege halten ihre Referenzbilder als
# Datenzeilen im Speicher -- bei einer Handvoll sind das ein paar Megabyte,
# was in Ordnung ist. Wer hunderte einreiht, sollte sie auf die Platte legen;
# dafuer bekommen hochgeladene Bilder mit den Projekten einen festen Ort.
warteschlange: list[dict] = []
verlauf: list[dict] = []          # die letzten erledigten Auftraege
_wecker = threading.Condition()   # schuetzt beide Listen und weckt den Arbeiter
_zaehler = itertools.count(1)
VERLAUF_LAENGE = 20


def _titel(art: str, params: dict) -> str:
    """Eine Zeile, an der man den Auftrag in der Liste wiedererkennt."""
    if art == "expose":
        return "Geschichte umreissen"
    if art == "prompts":
        return f"Prompts schreiben, {len(params.get('zeilen') or [])} Szenen"
    if art == "demo":
        if params.get("bloecke"):
            return f"Ablauf, {len(params['bloecke'])} Bloecke"
        return f"Ablauf: {params.get('ablauf') or 'reise'}"
    text = (params.get("prompt") or "").strip()
    if text:
        return text[:60] + ("…" if len(text) > 60 else "")
    for feld in ("effect", "form"):
        if params.get(feld):
            return str(params[feld])
    return params.get("mode") or "Auftrag"


def einreihen(art: str, params: dict) -> dict:
    """Haengt einen Auftrag an und weckt den Arbeiter. Antwortet sofort."""
    auftrag = {"nummer": next(_zaehler), "art": art, "params": params,
               "titel": _titel(art, params), "zustand": "wartet",
               "angelegt": time.time(), "bilder": 0, "fehler": None,
               "projekt": projekte.aktiv()}
    with _wecker:
        warteschlange.append(auftrag)
        _wecker.notify()
    return auftrag


def entfernen(nummer: int) -> bool:
    """Nimmt einen wartenden Auftrag wieder heraus. Der laufende bleibt --
    den stoppt `engine.cancel()`, weil er schon Rechenzeit verbraucht hat."""
    with _wecker:
        for i, a in enumerate(warteschlange):
            if a["nummer"] == nummer:
                del warteschlange[i]
                return True
    return False


def verschieben(nummer: int, richtung: int) -> bool:
    """Einen wartenden Auftrag eine Stelle nach vorn oder hinten."""
    with _wecker:
        for i, a in enumerate(warteschlange):
            if a["nummer"] != nummer:
                continue
            ziel = i + richtung
            if not 0 <= ziel < len(warteschlange):
                return False
            warteschlange[i], warteschlange[ziel] = warteschlange[ziel], warteschlange[i]
            return True
    return False


def leeren() -> int:
    """Alle wartenden Auftraege verwerfen. Der laufende bleibt unberuehrt."""
    with _wecker:
        anzahl = len(warteschlange)
        warteschlange.clear()
        return anzahl


def _kurz(auftrag: dict) -> dict:
    """Was die Oberflaeche ueber einen Auftrag wissen muss -- ohne die
    Referenzbilder, die als Datenzeilen im Auftrag stecken."""
    return {k: auftrag[k] for k in
            ("nummer", "art", "titel", "zustand", "angelegt", "bilder",
             "fehler", "projekt")}


def uebersicht() -> dict:
    with _wecker:
        return {"wartend": [_kurz(a) for a in warteschlange],
                "verlauf": [_kurz(a) for a in reversed(verlauf)]}


# Die Achsen, die `plan()` in den Prompt einbaut. Eine Liste, damit sie beim
# Buendeln und beim Einzellauf garantiert dieselbe ist.
ACHSEN = ("view", "style", "light", "camera", "paint", "palette", "scene",
          "angle", "device", "scenario", "material", "haltung", "kleidung")

# Alles, was beim Buendeln uebereinstimmen muss: was die Maschine einmal
# einstellt und nicht je Bild wechseln kann.
GLEICH = ("aspect", "base", "steps", "true_cfg_scale", "negative_prompt")


def _buendelbar(a: dict, b: dict) -> bool:
    """Duerfen diese beiden Auftraege einen Ladevorgang teilen?

    Gemessen kostet ein Ladevorgang rund 68 Sekunden, das Rechnen eines
    kleinen Bildes anderthalb. Wer drei Bilder einzeln einreiht, wartet also
    dreimal auf dasselbe Modell. Zusammen geht das in einem Durchgang.

    Streng gefasst: nur schlichte Text-zu-Bild-Auftraege ohne Referenzbild,
    Effekt, Vorlage oder Serienart. Bei denen ist der fertige Prompt genau
    das, was `plan()` daraus macht -- bei allem anderen baut `run_series` den
    Text noch um, und die Abkuerzung ueber `prompts=` ginge daneben.
    """
    if a["art"] != "generate" or b["art"] != "generate":
        return False
    if a.get("projekt") != b.get("projekt"):
        return False
    pa, pb = a.get("params") or {}, b.get("params") or {}
    for p in (pa, pb):
        if (p.get("mode") or "t2i") != "t2i":
            return False
        if p.get("images") or p.get("effect") or p.get("form"):
            return False
        if p.get("sweep") or p.get("prompts") or p.get("transparent"):
            return False
        if int(p.get("count", 1) or 1) != 1:
            return False
    return all(str(pa.get(k, "")) == str(pb.get(k, "")) for k in GLEICH)


def _fertiger_prompt(params: dict) -> tuple[str, int]:
    """Prompt und Seed eines Auftrags, so wie `plan()` sie bauen wuerde.

    Ueber `plan()` statt von Hand: die Achsenliste waechst, und zwei Stellen,
    die denselben Text bauen, laufen frueher oder spaeter auseinander.
    """
    seed = int(params.get("seed", 42))
    auftragsliste = Engine.plan(
        params.get("prompt", ""), 1, seed, None,
        subject=params.get("subject") or "fahrzeug",
        paint_target=params.get("paint_target") or "",
        **{k: params.get(k) or None for k in ACHSEN})
    return auftragsliste[0]["prompt"], auftragsliste[0]["seed"]


def _abarbeiten(auftrag: dict, weitere: list[dict] | None = None) -> None:
    """Einen Auftrag ausfuehren. Nur der Arbeiter ruft das auf."""
    global _projekt_des_laufs
    engine.lock.acquire()
    try:
        _projekt_des_laufs = auftrag.get("projekt") or projekte.ALLGEMEIN
        alle = [auftrag] + (weitere or [])
        for a in alle:
            a["zustand"] = "laeuft"
        engine.aborted = False
        titel = (auftrag["titel"] if len(alle) == 1
                 else f"{len(alle)} Auftraege zusammen")
        current.update(files=[], error=None, translated={}, video=None,
                       gelesen={}, tor=[], gliederung=[], expose={}, stage="wird vorbereitet",
                       nummer=auftrag["nummer"], titel=titel)
        if len(alle) == 1:
            laeufe = {"demo": run_demo, "prompts": run_prompts,
                      "expose": run_expose}
            laeufe.get(auftrag["art"], run_job)(auftrag["params"])
        else:
            # Ein Ladevorgang fuer alle: die fertigen Prompts gehen als Liste
            # an run_series, genau wie bei einem Ablauf.
            fertig = [_fertiger_prompt(a["params"]) for a in alle]
            gemeinsam = dict(auftrag["params"])
            gemeinsam["prompts"] = [t for t, _ in fertig]
            gemeinsam["seeds"] = [sd for _, sd in fertig]
            run_job(gemeinsam)
    finally:
        alle = [auftrag] + (weitere or [])
        zustand = ("fehler" if current["error"]
                   else "abgebrochen" if engine.aborted else "fertig")
        for i, a in enumerate(alle):
            # Im Buendel gehoert jedem Auftrag genau ein Bild, in der
            # Reihenfolge der Prompts. Allein bekommt er alle.
            eigene = (current["files"] if len(alle) == 1
                      else current["files"][i:i + 1])
            kennung = (a.get("params") or {}).get("baustein")
            if kennung and eigene:
                bausteine.bild_setzen(a.get("projekt") or projekte.ALLGEMEIN,
                                      str(kennung), eigene[0])
            a["bilder"] = len(eigene)
            a["fehler"] = current["error"]
            a["zustand"] = zustand
            # Die Vorgaben samt Referenzbildern werden nicht aufgehoben.
            a.pop("params", None)
        with _wecker:
            verlauf.extend(alle)
            del verlauf[:-VERLAUF_LAENGE]
        engine.lock.release()


def _arbeiter() -> None:
    while True:
        with _wecker:
            while not warteschlange:
                _wecker.wait()
            auftrag = warteschlange.pop(0)
            # Was gleich dahinter steht und dazu passt, laeuft mit -- das
            # spart je Auftrag einen vollstaendigen Ladevorgang.
            weitere = []
            while warteschlange and _buendelbar(auftrag, warteschlange[0]):
                weitere.append(warteschlange.pop(0))
        try:
            _abarbeiten(auftrag, weitere)
        except Exception:                      # darf den Faden nie beenden
            traceback.print_exc()


threading.Thread(target=_arbeiter, daemon=True, name="auftraege").start()


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
                "scenario", "material", "haltung", "kleidung"):
        if meta.get(key) is not None:
            info.add_text(f"qwen_{key}", str(meta[key]))
    image.save(os.path.join(ziel(), name), pnginfo=info)
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


def _cfg_fuer(params: dict) -> float:
    """Der CFG-Wert fuer diesen Auftrag.

    Ein negativer Prompt wirkt nur oberhalb von 1 (engine.py:
    `true_cfg_scale > 1`), und dort laeuft jeder Schritt zweimal -- das Bild
    dauert also rund doppelt so lang. Angehoben wird deshalb nur auf
    ausdruecklichen Wunsch ("streng"). Steht nichts im Feld, kostet es
    ohnehin nichts: der negative Zweig faellt ganz weg.
    """
    wert = float(params.get("true_cfg_scale", 1.0) or 1.0)
    if (wert <= 1.0 and params.get("streng")
            and (params.get("negative_prompt") or "").strip()):
        return 2.5
    return wert


def _ausschluesse(text: str) -> list[str]:
    """Die Begriffe aus dem Feld "was nicht ins Bild soll"."""
    return [t.strip().lower() for t in re.split(r"[,;\n]", text or "") if t.strip()]


def _durchs_tor(prompt: str, params: dict) -> str:
    """Einen einzelnen Prompt durch den Torwaechter schicken und mitschreiben,
    was dabei herausfiel."""
    sauber, weg = torwaechter(prompt, params.get("negative_prompt") or "")
    if weg:
        current["tor"] = list(current["tor"]) + weg
    return sauber


def torwaechter(prompt: str, ausschluss: str) -> tuple[str, list[str]]:
    """Streicht ausgeschlossene Begriffe aus dem fertigen Prompt.

    Der billige Weg: "Kueche" und "Buero" stehen als Wort im Prompt -- meist
    aus einer Umgebungsachse oder einem Baustein. Sie dort zu entfernen
    kostet nichts, waehrend es dem Modell auszureden die Rechenzeit
    verdoppelt. Entfernt wird das ganze Aufzaehlungsglied, in dem der Begriff
    steht, sonst bliebe ein Satzbruchstueck zurueck.

    Gibt den bereinigten Prompt und die tatsaechlich entfernten Stuecke
    zurueck -- stillschweigend soll das nicht geschehen.
    """
    begriffe = _ausschluesse(ausschluss)
    if not begriffe or not prompt:
        return prompt, []
    behalten, entfernt = [], []
    for glied in prompt.split(","):
        treffer = next((b for b in begriffe if b in glied.lower()), None)
        if not treffer:
            behalten.append(glied)
            continue
        # Steht der Begriff nicht gleich vorn, ist er ein Beiwerk: dann faellt
        # nur der Nebensatz, nicht das ganze Glied. "eine Markthalle mit
        # Leuchtreklame" ohne Leuchtreklame soll eine Markthalle bleiben --
        # beim ersten Versuch war sie mit verschwunden.
        teile = re.split(r"(\s+(?:with|and|featuring|including|under)\s+)", glied)
        wenn_vorn = treffer in teile[0].lower()
        if wenn_vorn or len(teile) == 1:
            entfernt.append(f"{glied.strip()} (wegen „{treffer}“)")
            continue
        rest, weg = [teile[0]], []
        for i in range(1, len(teile), 2):
            trenner, stueck = teile[i], teile[i + 1] if i + 1 < len(teile) else ""
            if treffer in stueck.lower():
                weg.append(stueck.strip())
            else:
                rest += [trenner, stueck]
        behalten.append("".join(rest))
        entfernt.append(f"{' / '.join(weg)} (wegen „{treffer}“)")
    sauber = ",".join(behalten).strip().strip(",").strip()
    return (sauber or prompt), entfernt


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
        true_cfg_scale=_cfg_fuer(params),
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

        manifest = os.path.join(ziel(), f"{stamp}_{kind}.jsonl") if kind == "varianten" else None

        def on_image(meta, image):
            name = _save(meta, image, stamp, kind)
            current["files"].append(name)
            if manifest:
                # Eine Zeile je Bild: was variiert wurde, direkt neben der Datei.
                # Damit laesst sich der Satz spaeter filtern oder ausbalancieren.
                row = {"file": name, **{k: v for k, v in meta.items() if k != "index"}}
                with open(manifest, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        # `prompts` kommt von einer Serie ueber eine Variable oder aus einem
        # Buendel: dieselbe Person in vier Jacken, ein Ladevorgang fuer alle.
        fertige = [p for p in (params.get("prompts") or []) if str(p).strip()]
        if not fertige:
            # Ohne fertige Liste baut plan() den Prompt -- damit der
            # Torwaechter auch dort greift, wird er hier einmal gebaut.
            fertige = [_fertiger_prompt(params)[0]] if params.get("prompt") else []
            if fertige and int(params.get("count", 1) or 1) != 1:
                fertige = []          # Serien baut plan() selbst

        ausschluss = params.get("negative_prompt") or ""
        gestrichen = []
        if fertige and ausschluss.strip():
            geprueft = []
            for text in fertige:
                sauber, weg = torwaechter(text, ausschluss)
                geprueft.append(sauber)
                gestrichen += weg
            fertige = geprueft
        current["tor"] = gestrichen

        engine.run_series(**_series_kwargs(params, refs, kind, on_image),
                          **({"prompts": fertige} if fertige else {}))
        done = len(current["files"])
        engine.note("idle", f"fertig: {done} Bild(er)" if done else "abgebrochen")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        engine.note("error", current["error"])
    # Die Sperre haelt und loest der Arbeiter -- siehe _abarbeiten().


def run_expose(params: dict) -> None:
    """Die Geschichte umreissen: Kurzfassung, Welt, Stil, Szenenvorschlag.

    Steht vor allem anderen, weil hier der globale Stil und die Frage
    Wirklichkeit oder Erfindung entschieden werden -- beides gilt danach fuer
    jede Szene.
    """
    try:
        current["stage"] = "Grosses Sprachmodell wird geladen"
        erg = chat.expose(params.get("idee") or "",
                          fiktion=params.get("fiktion"),
                          vorher=params.get("vorher") or "",
                          model=params.get("modell") or None)
        current["expose"] = erg
        current["stage"] = ""
        engine.note("idle", "Geschichte umrissen" if erg["kurz"]
                    else "Das Sprachmodell hat nichts geliefert")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        engine.note("error", current["error"])


def run_prompts(params: dict) -> None:
    """Aus der Gliederung die Bildprompts schreiben, der Reihe nach.

    Laeuft als Auftrag und nicht als Direktaufruf, weil das grosse Modell die
    Grafikkarte belegt: nur so wartet ein Bildauftrag daneben, statt sich mit
    ihm um den Speicher zu streiten. Der Fortschritt landet in `stage`, damit
    die Seite ihn zeigen kann -- bei 16,5 GB und mehreren Szenen dauert es.
    """
    try:
        zeilen = [z.get("text") or "" for z in (params.get("zeilen") or [])]
        current["stage"] = "Grosses Sprachmodell wird geladen"

        def fortschritt(nr, gesamt):
            current["stage"] = f"Prompt {nr} von {gesamt}"

        szenen = chat.gliederung(zeilen, stil=params.get("stil") or "",
                                 welt=params.get("welt") or "",
                                 kurz=params.get("kurz") or "",
                                 fiktion=params.get("fiktion"),
                                 model=params.get("modell") or None,
                                 fortschritt=fortschritt)
        if params.get("prosa"):
            current["stage"] = "Text wird geschrieben"
            absaetze = chat.prosa(szenen, model=params.get("modell") or None)
            for i, s in enumerate(szenen):
                s["prosa"] = absaetze[i] if i < len(absaetze) else ""
        current["gliederung"] = szenen
        current["stage"] = ""
        geschrieben = sum(1 for s in szenen if s.get("prompt"))
        engine.note("idle", f"{geschrieben} von {len(zeilen)} Prompts geschrieben")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        engine.note("error", current["error"])


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
            bild = Image.open(os.path.join(ziel(), datei))
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
        with open(os.path.join(ziel(), basis_datei), "rb") as fh:
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
                    # Der Torwaechter gilt auch hier: ein Ablauf soll
                    # ausgeschlossene Dinge genauso wenig zeigen.
                    prompts=[_durchs_tor(s["prompt"], params) for s in schritte],
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
            video_ziel = os.path.join(ziel(), f"{stamp}_demonstration.mp4")
            demo.baue_video([os.path.join(ziel(), n) for n in reihenfolge], video_ziel,
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
    # Die Sperre haelt und loest der Arbeiter -- siehe _abarbeiten().
