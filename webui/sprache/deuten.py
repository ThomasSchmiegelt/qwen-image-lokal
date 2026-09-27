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

"prompt"     Die ganze Person auf ENGLISCH, ein Satz: ungefähres Alter,
             Statur, Gesicht, Haarfarbe und Frisur. OHNE Kleidung -- die
             steht für sich. Nennt die Beschreibung einen Charakterzug --
             schüchtern, streng, herzlich, misstrauisch --, setze ihn als
             sichtbares Merkmal um: Haltung, Blick, Zug um den Mund. "streng"
             wird zu "an upright bearing and a level, unsmiling gaze", nicht
             zu "strict".
"gesicht"    Nur das Gesicht, auf ENGLISCH, ein kurzer Satz: Form, Augen,
             Haut, Mund, Brauen, der Ansatz der Haare. Nichts vom Körper,
             nichts von der Kleidung -- dieser Text steht allein im Bild,
             wenn die Kamera dicht an die Augen geht.
"kleidung"   Was die Person üblicherweise trägt, auf ENGLISCH, ein kurzer
             Satz mit Schuhen. Eine Szene darf ihn überschreiben.
"variablen"  Ein Objekt mit genau einer englischen Vorgabe je Lücke,
             als einzelner Text, nicht als Liste. Fällt dir zu einer
             Lücke keine Vorgabe ein, mach dort keine Lücke.

Lücken in geschweiften Klammern sind erlaubt, wo etwas von Bild zu Bild
wechseln darf, etwa {haarfarbe}. Höchstens vier, Namen klein und ohne
Umlaute. Kleidung braucht keine Lücke mehr -- dafür ist "kleidung" da.

Nimm ausschließlich, was in der Anfrage steht, und ergänze nur, was daraus
folgt. Aus dieser Anweisung übernimmst du keine einzige Wendung -- kein
Beispielwort, keine Beispielperson.

Die Form, mit Platzhaltern statt Wörtern:
{"prompt": "<Alter und Statur>, <Haare>, <Haltung oder Blick>",
 "gesicht": "<Gesichtsform> face with <Augen>, <Haut>, <Mund>",
 "kleidung": "<Kleidungsstück> over <Kleidungsstück>, <Schuhe>",
 "variablen": {}}""",

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


# Einzelne Teile einer Person nachschaerfen. Die Felder entstehen zwar schon
# beim "Prompt daraus erzeugen" mit -- aber wer eines davon von Hand
# ueberschreibt, tut das auf Deutsch und will es genauso uebersetzt haben.
TEIL_SYSTEM = {
    "gesicht": """Du schreibst den Bildprompt für das GESICHT einer Person.

Antworte ausschließlich mit JSON: {"text": "…"}.

Eine kurze englische Aufzählung, nur das Gesicht: Form, Augen, Haut, Mund,
Brauen, der Ansatz der Haare. Nichts vom Körper, nichts von der Kleidung,
keine Umgebung -- dieser Text steht allein im Bild, wenn die Kamera dicht an
die Augen geht. Ein Charakterzug wird zu etwas Sichtbarem: "misstrauisch"
zu "narrowed eyes and a set jaw", nicht zu "suspicious".

KEIN vollständiger Satz und KEIN Subjekt: nicht "A man's face has …",
sondern gleich das Gesicht, in der Form
"<shape> face with <eyes>, <skin>, <mouth>" -- die Wörter selbst auf
ENGLISCH.
Der Text wird an die Beschreibung der Person angehängt -- ein zweites
"a man" darin setzt eine zweite Person ins Bild.

Nimm ausschließlich, was in der Anfrage steht. Erfinde keine Merkmale dazu
und übernimm keine aus dieser Anweisung. Die Anfrage ist deutsch, die
Antwort ist englisch -- kein deutsches Wort bleibt stehen.""",

    "kleidung": """Du schreibst den Bildprompt für die KLEIDUNG einer Person.

Antworte ausschließlich mit JSON: {"text": "…"}.

Eine kurze englische Aufzählung, nur was die Person am Leib trägt, von oben
nach unten und mit Schuhen. Stoff und Schnitt gehören dazu, Farbe auch. Kein
Gesicht, kein Körperbau, keine Umgebung, keine Tätigkeit.

Beginne mit dem ersten Kleidungsstück. KEIN Subjekt, kein vollständiger
Satz, und die Person kommt darin nicht vor: nicht "a woman … wearing …",
sondern gleich die Form
"<garment> over <garment>, <shoes>" -- die Wörter selbst auf ENGLISCH.
Der Text wird an die Beschreibung der Person angehängt -- steht sie ein
zweites Mal darin, setzt das eine zweite Person ins Bild.

Nimm ausschließlich die Kleidungsstücke aus der Anfrage. Erfinde keine dazu
und übernimm keine aus dieser Anweisung. Die Anfrage ist deutsch, die
Antwort ist englisch -- kein deutsches Wort bleibt stehen.""",
}


def teil_prompt(feld: str, text: str, person: str = "",
                model: str | None = None) -> str:
    """Aus einer deutschen Angabe den Prompt fuer Gesicht oder Kleidung.

    `person` ist der allgemeine Prompt und dient als Umfeld: eine Jacke fuer
    eine Bergsteigerin sieht anders aus als eine fuer eine Beamtin.
    """
    system = TEIL_SYSTEM.get(feld)
    if not system or not (text or "").strip():
        return ""
    if person.strip():
        system += f"\n\nDie Person: {person.strip()}"
    roh = antwort({
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.3, "num_predict": 300},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": text}],
    })
    if not isinstance(roh, dict):
        return ""
    fertig = str(roh.get("text") or "").strip()[:400].rstrip(".")
    # Trotz aller Ansage kommt manchmal ein ganzer Satz zurueck. Das Subjekt
    # davor faellt weg, sonst steht eine zweite Person im Prompt.
    if feld == "kleidung":
        # "... wearing a red coat" -> "a red coat". Alles vor dem Tragen ist
        # die Person, und die steht schon im allgemeinen Prompt.
        fertig = re.sub(r"^.{0,90}?\b(?:wearing|wears|dressed in|clad in)\s+",
                        "", fertig, flags=re.I)
    fertig = re.sub(r"^(?:an?|the)\s+\w+(?:'s)?\s+(?:face\s+)?"
                    r"(?:is|has)\s+", "", fertig, flags=re.I)
    return fertig[:1].lower() + fertig[1:] if fertig else ""


MAX_ZEILEN = 24

RATEN_SYSTEM = """Du ordnest Namen aus einer Geschichte ein.

Du bekommst das Inhaltsverzeichnis einer Bilderfolge und eine Liste von
Namen, die darin mit einem Schrägstrich erwähnt werden. Zu jedem Namen sagst
du, was er ist und wie er aussehen könnte.

Antworte ausschließlich mit JSON: {"teile": [ … ]}. Jeder Eintrag hat genau
diese Schlüssel:

"name"         Der Name, unverändert aus der Liste.
"art"          "person", "ort" oder "gegenstand". Was in der Geschichte
               handelt, ist eine Person; wo sie sich aufhält, ein Ort; was
               sie benutzt oder trägt, ein Gegenstand.
"beschreibung" Ein Satz auf DEUTSCH, wie das aussieht. Halte dich an das,
               was das Inhaltsverzeichnis hergibt, und erfinde den Rest
               plausibel dazu -- es ist ein Vorschlag, den der Benutzer
               danach ändert. Keine Handlung, nur Aussehen."""


def bausteine_raten(namen: list[str], umfeld: str = "",
                    model: str | None = None) -> list[dict]:
    """Zu unbekannten /Namen Art und eine deutsche Beschreibung vorschlagen.

    Ein Aufruf fuer alle Namen: sie gehoeren zu derselben Geschichte, und
    einzeln gefragt erfindet das Modell zu jedem eine eigene Welt.
    """
    namen = [n for n in namen if (n or "").strip()][:12]
    if not namen:
        return []
    frage = "Namen: " + ", ".join(namen)
    if umfeld.strip():
        frage = f"Inhaltsverzeichnis:\n{umfeld.strip()[:2000]}\n\n{frage}"
    roh = antwort({
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.5, "num_predict": 900},
        "messages": [{"role": "system", "content": RATEN_SYSTEM},
                     {"role": "user", "content": frage}],
    }, timeout=300)
    gegeben = roh.get("teile") if isinstance(roh, dict) else None
    nach_name = {}
    for e in gegeben or []:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name") or "").strip()
        art = str(e.get("art") or "").strip().lower()
        if name:
            nach_name[name.lower()] = {
                "art": art if art in ("person", "ort", "gegenstand") else "",
                "beschreibung": str(e.get("beschreibung") or "").strip()[:400]}
    # Jeder gefragte Name kommt zurueck, auch wenn das Modell ihn ausliess --
    # sonst fehlt am Ende ein Baustein, ohne dass jemand es merkt.
    raus = []
    for n in namen:
        e = nach_name.get(n.lower()) or {}
        raus.append({"name": n, "art": e.get("art") or "person",
                     "beschreibung": e.get("beschreibung") or ""})
    return raus


EMPFEHLEN_SYSTEM = """Du sagst, welche Bausteine eine Bilderfolge braucht.

Du bekommst ein Inhaltsverzeichnis, Zeile für Zeile eine Szene, und eine
Liste der Bausteine, die es schon gibt. Für jede Szene nennst du, wer darin
vorkommt, wo sie spielt und welcher Gegenstand darin wichtig ist.

Antworte ausschließlich mit JSON: {"szenen": [ … ]}. Ein Eintrag je Szene:

"nr"    Die Nummer der Szene, bei 1 beginnend.
"teile" Eine Liste. Jeder Eintrag hat "name" und "art"
        ("person", "ort" oder "gegenstand").

Regeln:
- Gibt es einen passenden Baustein schon, nimm seinen Namen BUCHSTABENGETREU.
  Dieselbe Figur soll nicht zweimal unter zwei Namen entstehen.
- Sonst ein kurzer, sprechender Name, deutsch, ein Wort oder zwei ohne
  Leerzeichen dazwischen -- er wird später mit einem Schrägstrich getippt.
- Höchstens ein Ort und höchstens ein Gegenstand je Szene, Personen bis zu
  drei. Was im Bild nicht zu sehen ist, gehört nicht dazu.
- Eine Szene ohne erkennbaren Baustein bekommt eine leere Liste."""


def bausteine_empfehlen(zeilen: list[str], vorhanden: list[dict],
                        model: str | None = None) -> list[dict]:
    """Je Szene vorschlagen, welche Bausteine gebraucht werden.

    Ein Aufruf fuer die ganze Gliederung: nur so kann das Modell dieselbe
    Person in Szene eins und Szene sieben wiedererkennen.
    """
    zeilen = [(z or "").strip() for z in zeilen][:MAX_ZEILEN]
    if not any(zeilen):
        return []
    liste = "\n".join(f'  {b.get("name")} ({b.get("art")})'
                       for b in vorhanden if b.get("name")) or "  (keine)"
    inhalt = "\n".join(f"{i}. {z}" for i, z in enumerate(zeilen, 1) if z)
    frage = f"Vorhandene Bausteine:\n{liste}\n\nInhaltsverzeichnis:\n{inhalt}"
    roh = antwort({
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.3, "num_predict": 1200},
        "messages": [{"role": "system", "content": EMPFEHLEN_SYSTEM},
                     {"role": "user", "content": frage}],
    }, timeout=300)
    gegeben = roh.get("szenen") if isinstance(roh, dict) else None
    raus = []
    for e in gegeben or []:
        if not isinstance(e, dict):
            continue
        try:
            nr = int(e.get("nr") or 0)
        except (TypeError, ValueError):
            continue
        if not 1 <= nr <= len(zeilen):
            continue
        teile, gesehen = [], set()
        for t in (e.get("teile") or [])[:5]:
            if not isinstance(t, dict):
                continue
            name = str(t.get("name") or "").strip()[:40]
            art = str(t.get("art") or "").strip().lower()
            # Ein Name mit Leerzeichen liesse sich nicht mit /Name tippen.
            name = re.sub(r"\s+", "-", name)
            if not name or art not in ("person", "ort", "gegenstand"):
                continue
            if name.lower() in gesehen:
                continue
            gesehen.add(name.lower())
            teile.append({"name": name, "art": art})
        raus.append({"nr": nr, "teile": teile})
    return raus


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
    prompt = str(roh.get("prompt") or "").strip()[:600].rstrip(".")
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

    erg = {"prompt": prompt,
           "variablen": {k: vorgabe(gegeben.get(k)) for k in dict.fromkeys(offen)}}
    # Nur bei Personen: das Gesicht fuer die Grossaufnahme, die Kleidung zum
    # Ueberschreiben durch die Szene. Fehlen sie, bleiben die Felder leer --
    # dann gilt eben der allgemeine Prompt.
    if art == "person":
        for feld in ("gesicht", "kleidung"):
            erg[feld] = str(roh.get(feld) or "").strip()[:400]
    return erg


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
