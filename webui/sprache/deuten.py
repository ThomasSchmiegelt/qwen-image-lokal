"""Freitext verstehen: aus einem deutschen Satz Prompt und Reglerstellung.

Das Sprachmodell darf nur Werte nennen, die es wirklich gibt -- der Systemtext
wird deshalb aus den echten Katalogen gebaut, und `sanitise` prueft trotzdem
jeden Wert nach. Ein 4B-Modell haelt sich nicht immer an Vorgaben.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kataloge import CAMERAS, EFFECTS, FORMS, LIGHTS, STYLES, VIEWS, overrides  # noqa: E402

from .ollama import MODEL, OLLAMA, THINK, antwort  # noqa: E402

ASPECTS = ["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16"]
RESOLUTIONS = [1024, 1536, 2048]
SWEEPS = ["", "view", "style", "light", "camera", "random"]
MODES = ["t2i", "edit", "gruppe", "person"]


def _names(table):
    return ", ".join(table)



def system_prompt(has_images: int) -> str:
    """Der Systemprompt wird aus den echten Tabellen gebaut, damit er nicht
    veraltet, sobald in den Katalogen etwas dazukommt."""
    situation = (
        f"Der Benutzer hat {has_images} Referenzbild(er) hochgeladen."
        if has_images else
        "Der Benutzer hat kein Referenzbild hochgeladen, es wird also neu erzeugt."
    )
    return f"""Du stellst eine lokale Bildgenerierung ein. {situation}

Das Gespräch geht weiter: Sagt der Benutzer danach "und noch ein Hut dazu"
oder "mach es hochkant", dann ändere die vorige Einstellung an dieser einen
Stelle und gib sie sonst unverändert zurück. Fang nicht von vorn an.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt. Kein Text davor oder danach.

Feld "prompt": die Bildbeschreibung auf ENGLISCH, ausformuliert und bildhaft.
Das Bildmodell versteht Englisch deutlich besser. Uebersetze also, was der
Benutzer will, und ergaenze es um anschauliche Details -- aber erfinde nichts,
was seiner Absicht widerspricht.

Die uebrigen Felder nur setzen, wenn der Benutzer es sagt oder eindeutig meint.
Sonst weglassen. Erlaubte Werte, nichts anderes:

"aspect": {_names(ASPECTS)}   (quer/breit = 16:9 oder 3:2, hochkant = 3:4 oder 9:16)
"count": ganze Zahl 1 bis 20   (wie viele SEPARATE Bilder erzeugt werden.
   Der "prompt" beschreibt immer nur EIN Bild. "zwei Bilder von einem Fahrrad"
   heisst count=2 und ein Fahrrad im Prompt, nicht zwei Fahrraeder.)
"base": {_names(str(r) for r in RESOLUTIONS)}   (Aufloesung, Vorgabe 1024)
"steps": 1 bis 100   (Vorgabe 40)
"style": {_names(STYLES)}
"light": {_names(LIGHTS)}
"camera": {_names(CAMERAS)}
"view": {_names(VIEWS)}   (Blickrichtung auf eine Person)
"form": {_names(FORMS)}   (Bildsorte, z. B. logo bei "Logo", buchumschlag bei "Buchcover")
"effect": {_names(EFFECTS)}   (Bearbeitung eines vorhandenen Bildes)
"sweep": {_names(s or '(leer)' for s in SWEEPS)}   (Serie variieren: view = einmal um
   die Person herum, camera/style/light = diese Liste durchgehen, random = wuerfeln)
"mode": {_names(MODES)}   (t2i = neu erzeugen, edit = vorhandenes Bild aendern,
   gruppe = mehrere Personen in ein Bild, person = dieselbe Person mehrfach)
"transparent": true bei "freigestellt", "transparent", "ohne Hintergrund"
"note": EIN kurzer deutscher Satz, was du verstanden hast.

Der Normalfall ist ein knapper Wunsch ohne Zusatzangaben. Dann stehen nur
"prompt" und "note" im JSON -- kein Stil, kein Licht, keine Kamera, keine
Vorlage. Das erste Beispiel zeigt das.

Jede Beispielantwort ist reines JSON, ohne Kommentar davor oder danach.

Beispiele:
"ein Apfel auf einem Tisch" ->
{{"prompt":"a single ripe red apple resting on a wooden table","note":"Ein Apfel auf einem Tisch."}}
"mach mir 10 Drachen als Zeichentrick, hochkant" ->
{{"prompt":"A friendly dragon with large wings perched on a rock, bold outlines, flat bright colours","count":10,"style":"zeichentrick","aspect":"3:4","note":"10 Zeichentrick-Drachen im Hochformat."}}
"ein Logo fuer eine Baeckerei, freigestellt" ->
{{"prompt":"a family bakery, a wheat sheaf and a bread loaf","form":"logo","transparent":true,"note":"Ein freigestelltes Baeckerei-Logo."}}
"zeig die Person von allen Seiten" ->
{{"prompt":"standing in the same place","mode":"person","sweep":"view","count":10,"note":"Eine Umrundung der Person in 10 Ansichten."}}
"mach aus den beiden ein Gruppenfoto im Park" ->
{{"prompt":"standing together in a sunlit park, smiling","mode":"gruppe","note":"Ein Gruppenfoto der beiden im Park."}}
"zwei Bilder von einem gelben Fahrrad im Wald" ->
{{"prompt":"a yellow bicycle leaning against a tree in a misty forest","count":2,"note":"Zwei Varianten eines gelben Fahrrads im Wald."}}
"faerb das alte Foto ein" ->
{{"prompt":"","effect":"colorize","mode":"edit","note":"Das alte Foto wird eingefaerbt."}}

"transparent" nur bei ausdruecklichem Wunsch nach Freistellung. Im Zweifel
lieber ein Feld weglassen als raten."""


def ask(text: str, has_images: int = 0, model: str | None = None,
        verlauf: list[dict] | None = None) -> dict:
    """Fragt Ollama. Wirft RuntimeError mit einer lesbaren Meldung.

    `verlauf` sind die bisherigen Wechsel des Gespraechs, als Wechselfolge
    von Benutzer- und Modellbeitraegen. Damit versteht "und jetzt noch einen
    Hut dazu", worauf es sich bezieht -- ohne Verlauf faengt jeder Satz bei
    null an.
    """
    body = {
        "model": model or MODEL,
        # Nur "json", kein JSON-Schema: ein Schema erzwingt zwar gueltige
        # Syntax, aber die grammatikgebundene Ausgabe kostet hier spuerbar
        # Verstaendnis -- gemessen 14 statt 22 Treffern, weil ausdrueckliche
        # Wuensche wie "quer" oder "freigestellt" unter den Tisch fielen.
        # Geprueft wird die Antwort ohnehin in sanitise().
        "format": "json",
        "stream": False,
        "think": False,          # Qwen3 denkt sonst laut, das kostet nur Zeit
        "keep_alive": 0,         # sofort entladen -- die GPU braucht gleich das Bildmodell
        "options": {"temperature": 0.2, "num_predict": 700},
        "messages": [
            {"role": "system", "content": system_prompt(has_images)},
            *(verlauf or []),
            {"role": "user", "content": text},
        ],
    }
    request = urllib.request.Request(
        OLLAMA.rstrip("/") + "/api/chat", json.dumps(body).encode("utf-8"),
        {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            answer = json.load(response)["message"]["content"]
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"Ollama meldet {error.code}: {detail}")
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Kein Kontakt zu Ollama unter {OLLAMA} ({error.reason}). "
            "Laeuft der Dienst?")

    try:
        return json.loads(THINK.sub("", answer).strip())
    except json.JSONDecodeError:
        raise RuntimeError("Das Sprachmodell hat kein verwertbares JSON geliefert.")


def _clamp(value, low, high, fallback):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return fallback


def sanitise(raw: dict, has_images: int) -> dict:
    """Nur bekannte Felder mit bekannten Werten. Alles andere fliegt raus."""
    if not isinstance(raw, dict):
        raise RuntimeError("Unerwartete Antwort des Sprachmodells.")

    def pick(key, table):
        value = raw.get(key)
        return value if isinstance(value, str) and value in table else ""

    out = {
        "prompt": str(raw.get("prompt") or "").strip(),
        "aspect": raw.get("aspect") if raw.get("aspect") in ASPECTS else "1:1",
        "base": raw.get("base") if raw.get("base") in RESOLUTIONS else 1024,
        "count": _clamp(raw.get("count", 1), 1, 20, 1),
        "steps": _clamp(raw.get("steps", 40), 1, 100, 40),
        "style": pick("style", STYLES),
        "light": pick("light", LIGHTS),
        "camera": pick("camera", CAMERAS),
        "view": pick("view", VIEWS),
        "form": pick("form", FORMS),
        "effect": pick("effect", EFFECTS),
        "sweep": raw.get("sweep") if raw.get("sweep") in SWEEPS else "",
        "transparent": bool(raw.get("transparent")),
        "note": str(raw.get("note") or "").strip()[:200],
    }

    # Effekte, die ein Bild brauchen, sind ohne Referenz sinnlos.
    if out["effect"] and EFFECTS[out["effect"]].get("needs_image") and not has_images:
        out["effect"] = ""

    # Bei einem reinen Effektbefehl ("faerb das ein") traegt die Anweisung des
    # Effekts den Auftrag, eine eigene Bildbeschreibung braucht es dann nicht.
    if not out["prompt"] and not out["effect"] and not out["form"]:
        raise RuntimeError("Das Sprachmodell hat keine Bildbeschreibung geliefert.")

    # Der Modus haengt vor allem daran, wie viele Bilder daliegen -- das weiss
    # der Server sicherer als das Sprachmodell.
    mode = raw.get("mode") if raw.get("mode") in MODES else None
    if not has_images:
        mode = "t2i"
    elif mode in (None, "t2i"):
        mode = "gruppe" if has_images >= 2 else "edit"
    elif mode == "gruppe" and has_images < 2:
        mode = "edit"
    out["mode"] = mode

    # Was der Effekt oder die Vorlage mitbringt, gilt nur fuer Felder, die das
    # Sprachmodell offengelassen hat -- ein ausgesprochener Wunsch geht vor.
    for key in ("effect", "form"):
        source = EFFECTS if key == "effect" else FORMS
        if out[key]:
            for field, value in overrides(source[out[key]]).items():
                if field in out and not out[field] and not raw.get(field):
                    out[field] = value

    # Der Umrundungs-Modus ohne Umrundung waere ein einzelnes Bild von vorn.
    # Wenn das Sprachmodell den Modus erkannt, die Serienart aber vergessen hat,
    # ist die Absicht trotzdem eindeutig.
    if out["mode"] == "person" and not out["sweep"]:
        out["sweep"] = "view"

    # Eine Liste durchzugehen ergibt nur mit genug Bildern Sinn.
    tables = {"view": VIEWS, "style": STYLES, "light": LIGHTS, "camera": CAMERAS}
    if out["sweep"] in tables and out["count"] == 1:
        out["count"] = min(len(tables[out["sweep"]]), 20)

    out["lock_seed"] = out["sweep"] == "view"
    return out


def interpret(text: str, has_images: int = 0, model: str | None = None,
              verlauf: list[dict] | None = None) -> dict:
    return sanitise(ask(text, has_images, model, verlauf), has_images)


# --- Bausteine -----------------------------------------------------------
BAUSTEIN_SYSTEM = {
    "person": """Du schreibst den Bildprompt für eine Person, die immer wieder
verwendet werden soll.

Antworte ausschließlich mit JSON und genau diesen Schlüsseln:

"prompt"     Die Beschreibung auf ENGLISCH, ein Satz. Unveränderliches gehört
             in den Text: ungefähres Alter, Statur, Gesicht, Haarfarbe und
             Frisur. Nennt die Beschreibung einen Charakterzug -- schüchtern,
             streng, herzlich, misstrauisch --, setze ihn als sichtbares
             Merkmal um: Haltung, Blick, Zug um den Mund. "streng" wird zu
             "an upright bearing and a level, unsmiling gaze", nicht zu
             "strict". Alles, was sich von Bild zu Bild ändern darf -- vor allem
             Kleidung und Schuhe -- setzt du als Lücke in geschweifte Klammern,
             zum Beispiel {kleidung} oder {schuhe}. Höchstens vier Lücken,
             Namen klein und ohne Umlaute.
"variablen"  Ein Objekt mit genau einer englischen Vorgabe je Lücke,
             als einzelner Text, nicht als Liste. Fällt dir zu einer
             Lücke keine Vorgabe ein, mach dort keine Lücke.

Beispiel: {"prompt": "a woman in her thirties, slim, high cheekbones, short
dark hair, wearing {kleidung} and {schuhe}", "variablen": {"kleidung": "a red
wool coat", "schuhe": "brown leather boots"}}""",

    "ort": """Du schreibst den Bildprompt für einen Ort, der immer wieder
verwendet werden soll.

Antworte ausschließlich mit JSON und genau diesen Schlüsseln:

"prompt"     Die Beschreibung auf ENGLISCH, ein Satz, beginnend mit einer
             Ortsangabe wie "in", "on" oder "at". Was den Ort ausmacht, gehört
             in den Text. Wechselndes wie Tageszeit oder Wetter setzt du als
             Lücke in geschweifte Klammern, etwa {tageszeit} oder {wetter}.
             Höchstens drei Lücken, Namen klein und ohne Umlaute.
"variablen"  Ein Objekt mit genau einer englischen Vorgabe je Lücke,
             als einzelner Text, nicht als Liste. Fällt dir zu einer
             Lücke keine Vorgabe ein, mach dort keine Lücke.""",

    "gegenstand": """Du schreibst den Bildprompt für einen Gegenstand, der
immer wieder verwendet werden soll.

Antworte ausschließlich mit JSON und genau diesen Schlüsseln:

"prompt"     Die Beschreibung auf ENGLISCH, ein Satz. Form, Material und
             Merkmale gehören in den Text. Wechselndes wie Farbe oder Zustand
             setzt du als Lücke in geschweifte Klammern, etwa {farbe}.
             Höchstens drei Lücken, Namen klein und ohne Umlaute.
"variablen"  Ein Objekt mit genau einer englischen Vorgabe je Lücke,
             als einzelner Text, nicht als Liste. Fällt dir zu einer
             Lücke keine Vorgabe ein, mach dort keine Lücke.""",
}


def baustein_prompt(text: str, art: str = "person",
                    model: str | None = None) -> dict:
    """Aus einer deutschen Beschreibung einen Baustein-Prompt mit Luecken.

    Die Luecken sind der eigentliche Zweck: dieselbe Person soll spaeter vier
    Jacken durchprobieren koennen, ohne dass man den Prompt neu schreibt. Was
    zurueckkommt, wird nicht blind geglaubt -- die Luecken im Text sind
    massgeblich, nicht die Liste des Modells.
    """
    system = BAUSTEIN_SYSTEM.get(art) or BAUSTEIN_SYSTEM["person"]
    roh = antwort({
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": 400},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": text}],
    })
    if not isinstance(roh, dict):
        return {"prompt": "", "variablen": {}}
    prompt = str(roh.get("prompt") or "").strip()[:600]
    gegeben = roh.get("variablen") if isinstance(roh.get("variablen"), dict) else {}
    # Nur Luecken, die wirklich im Text stehen.
    offen = re.findall(r"\{([a-zA-Z][a-zA-Z0-9_]{0,29})\}", prompt)

    def vorgabe(wert):
        # Mal kommt eine Liste von Moeglichkeiten statt einer Vorgabe zurueck.
        # Dann ist die erste gemeint; stumpf in Text verwandelt staende sonst
        # "['morning', 'afternoon']" im Prompt.
        if isinstance(wert, list):
            wert = wert[0] if wert else ""
        return str(wert or "").strip()[:120]

    return {"prompt": prompt,
            "variablen": {k: vorgabe(gegeben.get(k)) for k in dict.fromkeys(offen)}}


LUECKEN_SYSTEM = """Du füllst eine Lücke in einem Bildprompt mit Vorschlägen.

Antworte ausschließlich mit JSON: {"werte": ["…", "…"]}.

Jeder Wert ist ein kurzes englisches Satzstück, das genau an die Stelle der
Lücke passt — so, dass der Satz danach richtig klingt. Keine Nummern, keine
Erklärungen, keine Wiederholungen. Die Vorschläge sollen sich deutlich
voneinander unterscheiden, nicht nur in der Farbe."""


def luecken_vorschlaege(name: str, umfeld: str, anzahl: int = 10,
                        model: str | None = None) -> list[str]:
    """Vorschlaege fuer eine Luecke -- "hose" ergibt zehn verschiedene Hosen.

    `umfeld` ist der Prompt, in dem die Luecke steht. Ohne ihn schlaegt das
    Modell Hosen vor, die nicht zur Person passen.
    """
    anzahl = max(1, min(int(anzahl or 10), 30))
    roh = antwort({
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.8, "num_predict": 600},
        "messages": [
            {"role": "system", "content": LUECKEN_SYSTEM},
            {"role": "user", "content":
                f"Lücke: {{{name}}}\nSatz: {umfeld}\n"
                f"Gib genau {anzahl} Vorschläge."},
        ],
    })
    if not isinstance(roh, dict) or not isinstance(roh.get("werte"), list):
        return []
    gesehen, raus = set(), []
    for w in roh["werte"]:
        text = str(w or "").strip().strip(",.").strip()[:120]
        if text and text.lower() not in gesehen:
            gesehen.add(text.lower())
            raus.append(text)
    return raus[:anzahl]
