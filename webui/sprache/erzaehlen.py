"""Eine Handlung in Szenen zerlegen.

Das Sprachmodell bekommt den deutschen Handlungstext, die Bausteine des
Projekts mit ihren Kennungen und die erlaubten Werte fuer Mimik und Stil. Es
darf nur aus diesen Listen waehlen -- was es trotzdem erfindet, faellt beim
Nachpruefen heraus. Ein 4B-Modell haelt sich nicht an Vorgaben, es haelt sich
ungefaehr daran.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kataloge import GEZEICHNET, MIMIK, STYLES  # noqa: E402

from .ollama import GROSS, MODEL, antwort, entladen  # noqa: E402

# Wie viele Szenen eine Gliederung hoechstens hat. 24 war zu wenig: wer 30
# will, soll 30 bekommen. Die Zahl begrenzt nur, damit ein verirrtes Modell
# nicht tausend Zeilen schreibt.
MAX_SZENEN = 60


def _system(teile: list[dict], anzahl: int) -> str:
    def zeilen(art):
        passend = [b for b in teile if b.get("art") == art]
        return ("\n".join(f'  {b["id"]} = {b["name"]}' for b in passend)
                or "  (keine)")

    return f"""Du zerlegst eine Handlung in genau {anzahl} Bilder.

Antworte ausschließlich mit JSON: {{"szenen": [ … ]}}. Jede Szene ist ein
Objekt mit genau diesen Schlüsseln:

"titel"      Drei bis fünf Wörter auf Deutsch, nur zur Orientierung.
"person"     Eine Kennung aus der Personenliste, oder "".
"ort"        Eine Kennung aus der Ortsliste, oder "".
"gegenstand" Eine Kennung aus der Gegenstandsliste, oder "".
"handlung"   Was in diesem Bild zu sehen ist, auf ENGLISCH, ein kurzer
             Halbsatz. Keine Namen, keine Vorgeschichte, kein "then" oder
             "later" -- ein Bild zeigt einen Augenblick, keine Abfolge.
"mimik"      Ein Schlüssel aus der Mimikliste, oder "".
"stil"       Ein Schlüssel aus der Stilliste, oder "".

Personen:
{zeilen("person")}

Orte:
{zeilen("ort")}

Gegenstände:
{zeilen("gegenstand")}

Mimik: {", ".join(MIMIK)}

Stil: {", ".join(STYLES)}

Regeln:
- Genau {anzahl} Szenen, in der Reihenfolge der Handlung.
- Nimm nur Kennungen aus den Listen. Passt nichts, schreib "".
- Die Mimik folgt der Handlung: wer etwas verliert, lacht nicht.
- Bleib beim selben Stil, solange die Handlung nicht einen Bruch verlangt."""


def geschichte(text: str, teile: list[dict], anzahl: int = 8,
               model: str | None = None) -> dict:
    """Die Handlung als Liste geprüfter Szenen."""
    anzahl = max(2, min(int(anzahl or 8), MAX_SZENEN))
    erlaubt = {b["id"] for b in teile}
    roh = antwort({
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.4, "num_predict": 1400},
        "messages": [{"role": "system", "content": _system(teile, anzahl)},
                     {"role": "user", "content": text}],
    }, timeout=300)
    if not isinstance(roh, dict) or not isinstance(roh.get("szenen"), list):
        return {"szenen": [], "hinweis": "Das Sprachmodell hat keine Szenen geliefert."}

    def kennung(wert):
        wert = str(wert or "").strip()
        return wert if wert in erlaubt else ""

    def aus(wert, tabelle):
        wert = str(wert or "").strip()
        return wert if wert in tabelle else ""

    szenen = []
    for s in roh["szenen"][:MAX_SZENEN]:
        if not isinstance(s, dict):
            continue
        handlung = str(s.get("handlung") or "").strip()[:220]
        if not handlung:
            continue
        szenen.append({
            "titel": str(s.get("titel") or "").strip()[:60] or f"Bild {len(szenen) + 1}",
            "person": kennung(s.get("person")),
            "ort": kennung(s.get("ort")),
            "gegenstand": kennung(s.get("gegenstand")),
            "handlung": handlung,
            "mimik": aus(s.get("mimik"), MIMIK),
            "stil": aus(s.get("stil"), STYLES),
        })

    hinweis = ""
    if len(szenen) != anzahl:
        hinweis = (f"{len(szenen)} Szenen statt {anzahl} — das Sprachmodell hält "
                   "sich nicht immer an die Zahl. Im Ablauf nachbessern.")
    return {"szenen": szenen, "hinweis": hinweis}



# --- Inhaltsverzeichnis -> Prompts ---------------------------------------
# Der andere Weg: nicht ein Fliesstext, den das Modell zerschneidet, sondern
# eine Gliederung, die der Benutzer selbst geschrieben hat. Je Zeile eine
# Szene, der Ort steht daneben, der Stil gilt fuer die ganze Folge. Das Modell
# hat dann nur noch eine Aufgabe -- aus einer deutschen Zeile ein englisches
# Bild machen -- und die kann es gut.

GLIEDERUNG_SYSTEM = """Du schreibst Bildprompts für eine Bilderfolge.

Du bekommst Szene für Szene eine deutsche Zeile und antwortest jedes Mal mit
JSON und genau diesen Schlüsseln:

"prompt"  Was in diesem Bild zu sehen ist, auf ENGLISCH, ein bis zwei Sätze.
          Beschreibe einen Augenblick, keine Abfolge -- kein "then", kein
          "after". Keine Eigennamen: wer gemeint ist, steht schon in der
          Figurenbeschreibung, die separat davorgesetzt wird. Beschreibe
          Haltung, Handlung, Blickrichtung und was im Bild zu sehen ist.
          Nenne den Ort nur, wenn er in der Zeile steht -- sonst wird er
          separat ergänzt.
"mimik"   Ein Schlüssel aus der Liste, oder "".
"kleidung" Nur wenn die Zeile ausdrücklich etwas anderes anzieht als sonst:
          was die Figur in diesem Bild trägt, auf ENGLISCH, ein kurzer Satz.
          Sonst "". Was sie üblicherweise trägt, steht schon woanders --
          schreib es hier nicht noch einmal hin.

Mimik: {mimik}

Die Folge hängt zusammen: du siehst, was du für die vorigen Bilder
geschrieben hast. Halte Kleidung, Tageszeit und Stimmung stimmig, es sei
denn, die Zeile verlangt einen Bruch."""


def gliederung(zeilen: list[str], stil: str = "", welt: str = "",
               kurz: str = "", fiktion=None, model: str | None = None,
               fortschritt=None, hinweise: list[dict] | None = None,
               alter: str = "") -> list[dict]:
    """Aus den Zeilen einer Gliederung die Bildprompts, der Reihe nach.

    Je Zeile ein Aufruf, damit das Modell die vorigen Bilder kennt. Das
    Modell bleibt dabei geladen (`keep_alive`) -- sonst kostete jede Szene
    erneut das Laden von 16,5 GB. Freigegeben wird am Schluss.
    """
    name = model or GROSS
    system = GLIEDERUNG_SYSTEM.format(mimik=", ".join(MIMIK))
    if kurz.strip():
        system += f"\n\nWorum es geht: {kurz.strip()}"
    # Die Weltzuordnung zuerst: ohne sie biegt das Modell eine Fantasiehandlung
    # so lange zurecht, bis sie alltagstauglich wird.
    if welt in WELTEN:
        system += f"\n\n{WELTEN[welt][1]}"
    _, satz = grad(fiktion)
    if satz:
        system += f"\n\n{satz}"
    if freigabe(alter):
        system += f"\n\n{freigabe(alter)}"
    if stil in STYLES:
        system += f"\n\nDie ganze Folge ist im Stil: {STYLES[stil][1]}"
        if stil in GEZEICHNET:
            system += (" Es ist eine Zeichnung, kein Foto -- beschreibe nichts "
                       "Fotografisches wie Objektive, Filmkorn oder Blende.")

    verlauf, szenen = [], []
    try:
        for nr, zeile in enumerate(zeilen, 1):
            text = (zeile or "").strip()
            if not text:
                continue
            if fortschritt:
                fortschritt(nr, len(zeilen))
            # Erwartung und Ausschluss dieser einen Szene. Sie stehen im
            # Auftrag, nicht im Systemprompt: sie gelten nur hier und duerfen
            # die naechste Szene nicht faerben.
            h = (hinweise or [{}] * len(zeilen))[nr - 1] if nr <= len(hinweise or []) else {}
            frage = f"Szene {nr} von {len(zeilen)}: {text}"
            if (h.get("prosa") or "").strip():
                # Der Text der Szene steht vor der Erwartung: er sagt am
                # genauesten, was zu sehen ist.
                frage += ("\nDer Text dieser Szene:\n" + h["prosa"].strip()[:1200]
                          + "\nNimm daraus, was im Bild sichtbar ist -- kein "
                            "Gedanke, kein Gespräch, nur was man sieht.")
            if (h.get("unsichtbar") or "").strip():
                # Wer hinter der Kamera steht, darf im Bild nicht auftauchen
                # -- auch nicht als zweite Gestalt am Rand.
                frage += ("\nNicht im Bild, sondern hinter der Kamera: "
                          + h["unsichtbar"].strip()
                          + ". Diese Figur ist nicht zu sehen; beschreibe nur, "
                            "was sie sieht.")
            if (h.get("erwartung") or "").strip():
                frage += ("\nDas muss in diesem Bild zu sehen sein: "
                          + h["erwartung"].strip())
            if (h.get("ausschluss") or "").strip():
                frage += ("\nDas darf in diesem Bild nicht vorkommen: "
                          + h["ausschluss"].strip()
                          + ". Erwaehne es auch nicht, um es zu verneinen.")
            roh = antwort({
                "model": name,
                "format": "json",
                "keep_alive": "10m",          # zwischen den Szenen geladen lassen
                "options": {"temperature": 0.7, "num_predict": 500},
                "messages": [{"role": "system", "content": system},
                             *verlauf,
                             {"role": "user", "content": frage}],
            }, timeout=600)
            if not isinstance(roh, dict) or not str(roh.get("prompt") or "").strip():
                szenen.append({"nr": nr, "zeile": text, "prompt": "",
                               "mimik": "", "kleidung": ""})
                continue
            prompt = str(roh["prompt"]).strip()[:400]
            mimik = str(roh.get("mimik") or "").strip()
            szenen.append({"nr": nr, "zeile": text, "prompt": prompt,
                           "mimik": mimik if mimik in MIMIK else "",
                           # Zieht die Szene etwas anderes an, gilt das statt
                           # der Vorzugskleidung des Bausteins -- sonst
                           # stuenden Raumanzug und Wollmantel im selben Bild.
                           "kleidung": str(roh.get("kleidung") or "").strip()[:200]})
            verlauf += [{"role": "user", "content": f"Szene {nr}: {text}"},
                        {"role": "assistant", "content": prompt}]
            del verlauf[:-12]
    finally:
        entladen(name)                        # die Karte braucht gleich das Bildmodell
    return szenen


PROSA_SYSTEM = """Du schreibst den Text zu einer Bilderfolge.

Du bekommst die Szenen als nummerierte Liste. Antworte mit JSON:

{"absaetze": [{"nr": 1, "text": "…"}, {"nr": 2, "text": "…"}]}

Zu JEDER Szene ein Eintrag, mit ihrer Nummer und einem deutschen Absatz von
zwei bis vier Sätzen, erzählend. Überspringe keine Nummer, auch wenn zwei
Szenen einander ähneln. Kein Vorspann, keine Überschriften, keine Nummern im
Text selbst."""


# Wie viele Szenen in einen Prosa-Aufruf gehen. Achtzehn Absaetze passten
# nicht in eine Antwort: sie brach ab, und hinten fehlte die Prosa ganz.
JE_PROSA = 6


def prosa(szenen: list[dict], model: str | None = None,
          kurz: str = "", welt: str = "", fiktion=None, alter: str = "",
          figuren: str = "", erzaehler: str = "",
          fortschritt=None) -> list[str]:
    """Zu jeder Szene ein Absatz Prosa -- aus der Gliederung, nicht erfunden.

    In Haeppchen zu sechs Szenen, weil eine einzige Antwort fuer zwanzig
    Absaetze abbricht. Jedes Haeppchen sieht den letzten Absatz des vorigen,
    damit der Text nicht bei jedem Schnitt neu anfaengt.
    """
    if not szenen:
        return []
    name = model or GROSS
    system = PROSA_SYSTEM
    if kurz.strip():
        system += f"\n\nWorum es geht: {kurz.strip()}"
    if welt in WELTEN:
        system += f"\n\n{WELTEN[welt][1]}"
    _, satz = grad(fiktion)
    if satz:
        system += f"\n\n{satz}"
    if freigabe(alter):
        system += f"\n\n{freigabe(alter)}"
    if erzaehler.strip():
        # Wer schreibt. Steht vor der Besetzung: die Stimme bestimmt, wie
        # ueber die Figuren geredet wird, nicht umgekehrt.
        system += f"\n\n{erzaehler.strip()}"
    if figuren.strip():
        # Wer vorkommt und was er ist. Ohne das schreibt das Modell ueber
        # eine Androidin, als waere sie ein Mensch -- im Bild sieht man die
        # Naht am Kiefer, im Text steht nichts davon.
        system += ("\n\nWer und was darin vorkommt:\n" + figuren.strip()
                   + "\n\nHalte dich daran. Ist eine Figur kein Mensch, "
                     "schreibe sie auch nicht wie einen.")

    raus = []
    try:
        for anfang in range(0, len(szenen), JE_PROSA):
            teil = szenen[anfang:anfang + JE_PROSA]
            if fortschritt:
                fortschritt(anfang, len(szenen))
            frage = "\n".join(
                f"{s.get('nr', anfang + i + 1)}. {s.get('zeile') or s.get('prompt')}"
                for i, s in enumerate(teil))
            if raus and raus[-1]:
                frage = ("Der vorige Absatz endete so:\n" + raus[-1][-400:]
                         + "\n\nSchreibe daran anschliessend:\n" + frage)
            # Ueber die Nummer zuordnen, nicht ueber die Reihenfolge. Das
            # Modell ueberspringt Szenen, die einander aehneln -- positionell
            # zugeordnet verrutschte danach die ganze Folge, und Absatz zwei
            # erzaehlte von Szene drei.
            nummern = [int(s.get("nr") or 0) for s in teil]
            gefunden = _absaetze(system, frage, len(teil), name)
            fehlt = [n for n in nummern if not gefunden.get(n)]
            if fehlt:
                # Ein zweiter Anlauf, nur fuer die fehlenden.
                nach = "\n".join(
                    f"{s.get('nr')}. {s.get('zeile') or s.get('prompt')}"
                    for s in teil if int(s.get("nr") or 0) in fehlt)
                gefunden.update({k: v for k, v in
                                 _absaetze(system, nach, len(fehlt), name).items()
                                 if v})
            raus += [gefunden.get(n, "") for n in nummern]
    finally:
        entladen(name)
    return raus[:len(szenen)]


def _absaetze(system: str, frage: str, wieviel: int, model: str) -> dict:
    """Ein Aufruf, Ergebnis als {Szenennummer: Absatz}."""
    roh = antwort({
        "model": model,
        "format": "json",
        "keep_alive": "10m",
        "options": {"temperature": 0.8, "num_predict": 300 + 260 * wieviel},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": frage}],
    }, timeout=900)
    raus = {}
    for e in (roh.get("absaetze") if isinstance(roh, dict) else None) or []:
        if not isinstance(e, dict):
            continue
        try:
            nr = int(e.get("nr") or 0)
        except (TypeError, ValueError):
            continue
        text = str(e.get("text") or "").strip()[:900]
        if nr and text:
            raus[nr] = text
    return raus



# --- Expose --------------------------------------------------------------
# Vor der ersten Szene: worum geht es, in welchem Stil, und spielt das in der
# wirklichen Welt oder einer erfundenen? Das Letzte ist kein Beiwerk. Ein
# Modell, dem niemand sagt, dass Drachen vorkommen duerfen, versucht die
# Handlung zurechtzubiegen, bis sie plausibel wird.

WELTEN = {
    "wirklich": ("Wirklichkeit",
                 "Die Geschichte spielt in der wirklichen Welt. Alles muss "
                 "physikalisch moeglich und alltaeglich glaubhaft sein."),
    "fantasie": ("Fantasie",
                 "Die Geschichte spielt in einer erfundenen Welt. Magie, "
                 "Fabelwesen und unmoegliche Orte sind ausdruecklich erlaubt "
                 "und sollen nicht wegerklaert werden."),
    "scifi":    ("Zukunft",
                 "Die Geschichte spielt in der Zukunft. Technik darf weit "
                 "ueber das Heutige hinausgehen, soll aber in sich stimmig "
                 "bleiben."),
    "maerchen": ("Märchen",
                 "Die Geschichte ist ein Maerchen. Sprechende Tiere, Zauber "
                 "und Wunder gehoeren dazu; Logik tritt hinter das Bild."),
}

# Wie wirklich soll es sein? Ein Regler von 0 bis 10 statt einer Ja-Nein-
# Frage: das Spannende liegt oft dazwischen -- eine Welt, die fast die unsere
# ist, in der aber eine Sache nicht stimmt und niemand sich daran stoert.
GRADE = (
    (1,  ["wirklich"],
     "Nichts Uebernatuerliches. Alles muss physikalisch moeglich und "
     "alltaeglich glaubhaft sein."),
    (3,  ["wirklich"],
     "Die wirkliche Welt, aber am Rand ein Hauch von Unwirklichem -- nie "
     "erklaert, nie ausgesprochen."),
    (5,  ["wirklich", "scifi"],
     "Die Grenze zum Unmoeglichen ist durchlaessig: einzelne Dinge duerfen "
     "nicht stimmen, ohne dass jemand darueber staunt."),
    (7,  ["scifi", "fantasie"],
     "Eine erfundene Welt mit eigenen Regeln. Sie darf weit von der unseren "
     "abweichen, muss aber in sich folgerichtig bleiben."),
    (9,  ["fantasie", "maerchen"],
     "Magie und Fabelwesen gehoeren dazu und werden nicht wegerklaert."),
    (10, ["maerchen"],
     "Maerchenlogik: Wunder brauchen keine Begruendung, das Bild geht vor "
     "der Erklaerung."),
)


# Altersfreigabe. Kein Schutzmechanismus -- ein Sprachmodell laesst sich
# nicht mit einer Zahl sperren -- sondern ein Regler wie der
# Wirklichkeitsgrad: er sagt einmal, was gezeigt werden darf, statt dass man
# es in jede Szene schreibt. Bei hoher Fiktion driftet das Modell sonst von
# allein ins Drastische.
FREIGABEN = {
    "alle": ("Für alle",
             "Die Bilder sind für kleine Kinder gedacht: nichts Bedrohliches, "
             "keine Gewalt, keine Verletzungen, keine Waffen, kein Blut, "
             "keine Angstbilder, keine Nacktheit."),
    "ab6": ("Ab 6",
            "Spannung ja, Schrecken nein: keine Gewalt, keine Verletzungen, "
            "kein Blut, keine bedrohlichen Fratzen, keine Nacktheit."),
    "ab12": ("Ab 12",
             "Gefahr und Konflikt dürfen vorkommen, auch Waffen und Kämpfe, "
             "aber nicht ausgemalt: kein Blut, keine Wunden, keine Leichen, "
             "keine Nacktheit."),
    "ab16": ("Ab 16",
             "Gewalt und ihre Folgen dürfen gezeigt werden, ohne darin zu "
             "schwelgen. Keine Nacktheit, nichts Sexuelles."),
    "ab18": ("Ab 18", ""),
}


def freigabe(schluessel) -> str:
    """Der Satz zur Altersfreigabe fuers Sprachmodell, oder leer."""
    eintrag = FREIGABEN.get(str(schluessel or ""))
    return eintrag[1] if eintrag else ""


# Wer die Prosa schreibt. Nicht der Stil des Bildes, sondern die Stimme des
# Textes: dieselbe Szene klingt anders, je nachdem wer sie erzaehlt. "{wer}"
# wird durch den Namen der Figur ersetzt, wenn eine gewaehlt ist.
ERZAEHLER = {
    "neutral": ("Neutral erzählt", ""),
    "protagonist": (
        "Eine Figur der Geschichte",
        "Erzählt wird in der Ich-Form von {wer}. Alles steht in dieser Sicht: "
        "Was {wer} nicht sieht, nicht hört und nicht weiß, kommt im Text nicht "
        "vor. Auch das Urteil über die anderen ist ihres."),
    "zeuge": (
        "Eine Nebenfigur, die dabei war",
        "Erzählt wird in der Ich-Form von jemandem, der dabeistand, aber nicht "
        "im Mittelpunkt: einem Nachbarn, einem Kollegen, einem Kind. Er "
        "berichtet, was er gesehen hat, und versteht nicht alles davon."),
    "zukunft": (
        "Jemand aus der Zukunft, im Rückblick",
        "Geschrieben von jemandem, der lange nach diesen Ereignissen lebt und "
        "zurückblickt. Vergangenheitsform, und ab und zu ein Satz aus dem "
        "Abstand -- was daraus geworden ist, was man damals noch nicht wusste. "
        "Aber keine Erklärung, die die Szene selbst auflöst."),
    "chronist": (
        "Ein Chronist, nüchtern",
        "Ein Chronist berichtet: Vergangenheitsform, knapp, in der Reihenfolge "
        "der Ereignisse, ohne Innensicht und ohne Ausschmückung. Was niemand "
        "sehen konnte, steht nicht da."),
    "maerchen": (
        "Ein Märchenerzähler",
        "Erzählt wie ein Märchen: einfache Sätze, feste Wendungen, "
        "Wiederholungen, und der Erzähler wendet sich gelegentlich an den, "
        "der zuhört."),
    "eigen": ("Nur die eigene Beschreibung", ""),
}


def erzaehlerstimme(schluessel, wer: str = "", eigen: str = "") -> str:
    """Der Satz zur Erzaehlstimme fuers Sprachmodell, oder leer.

    `wer` ist der Name der Figur, aus deren Sicht erzaehlt wird; `eigen` eine
    frei geschriebene Beschreibung des Autors, die immer dazukommt. Fehlt
    beides, erzaehlt niemand Bestimmtes -- so wie bisher.
    """
    eintrag = ERZAEHLER.get(str(schluessel or ""))
    text = (eintrag[1] if eintrag else "").replace(
        "{wer}", (wer or "").strip() or "der Hauptfigur")
    eigen = (eigen or "").strip()
    if eigen:
        text = (text + "\n\n" if text else "") + f"Wer das schreibt: {eigen}"
    return text


def grad(fiktion) -> tuple[list[str], str]:
    """Aus dem Regler die erlaubten Welten und den Satz fuer das Modell.

    Nimmt auch True/False -- der Regler ersetzte einen Haken, und alte
    Aufrufe sollen nicht brechen.
    """
    if fiktion is None:
        return list(WELTEN), ""
    if fiktion is True:
        fiktion = 9
    elif fiktion is False:
        fiktion = 0
    try:
        wert = max(0, min(int(fiktion), 10))
    except (TypeError, ValueError):
        return list(WELTEN), ""
    for grenze, welten, satz in GRADE:
        if wert <= grenze:
            return welten, satz
    return list(WELTEN), ""


EXPOSE_SYSTEM = """Du planst eine Bilderfolge.

Der Benutzer nennt eine Idee. Antworte ausschließlich mit JSON und genau
diesen Schlüsseln:

"kurz"    Drei bis fünf deutsche Sätze: worum es geht, wer vorkommt, wie es
          ausgeht. Kein Vorspann, keine Überschrift.
"welt"    Einer dieser Schlüssel: {welten}
          Wähle ehrlich. Kommen Drachen oder Magie vor, ist es "fantasie",
          auch wenn die Idee nüchtern klingt.
"stil"    Ein Schlüssel aus der Stilliste, der zur Geschichte passt und für
          ALLE Bilder gelten soll: {stile}
"titel"   Zwei bis vier Wörter, deutsch.
"szenen"  Vorschlag für die Gliederung: eine Liste deutscher Zeilen, je eine
          Szene, {anzahl}. Eine Zeile sagt, was in diesem einen
          Bild zu sehen ist."""


ERGAENZEN_SYSTEM = """Du setzt ein Inhaltsverzeichnis fort.

Der Benutzer hat eine Bilderfolge begonnen und braucht noch weitere Szenen.
Du bekommst die vorhandenen Zeilen und die Zahl der fehlenden.

Antworte ausschließlich mit JSON: {{"szenen": [ … ]}} -- eine Liste deutscher
Zeilen, GENAU {fehlt} Stück, nicht mehr und nicht weniger. Jede Zeile sagt,
was in diesem einen Bild zu sehen ist.

Regeln:
- Die vorhandenen Zeilen wiederholst du nicht. Du schreibst nur die neuen.
- Sie schliessen an die letzte vorhandene an und fuehren die Handlung weiter.
- Dieselben Figuren und Orte wie bisher, mit denselben Namen.
- Eine Zeile, ein Augenblick. Keine Abfolge in einer Zeile."""


def szenen_ergaenzen(zeilen: list[str], fehlt: int, kurz: str = "",
                     welt: str = "", fiktion=None, stil: str = "",
                     model: str | None = None) -> list[str]:
    """Die fehlenden Zeilen eines Inhaltsverzeichnisses nachschreiben.

    Gedacht fuer den Fall, dass das Umreissen zu wenige geliefert hat oder
    die Geschichte laenger werden soll als geplant.
    """
    fehlt = max(1, min(int(fehlt or 0), MAX_SZENEN))
    da = [(z or "").strip() for z in zeilen if (z or "").strip()]
    name = model or GROSS
    system = ERGAENZEN_SYSTEM.format(fehlt=fehlt)
    if kurz.strip():
        system += f"\n\nWorum es geht: {kurz.strip()}"
    if welt in WELTEN:
        system += f"\n\n{WELTEN[welt][1]}"
    _, satz = grad(fiktion)
    if satz:
        system += f"\n\n{satz}"
    if stil in STYLES:
        system += f"\n\nDie ganze Folge ist im Stil: {STYLES[stil][1]}"
    inhalt = "\n".join(f"{i}. {z}" for i, z in enumerate(da, 1)) or "(noch nichts)"
    try:
        roh = antwort({
            "model": name, "format": "json", "keep_alive": "10m",
            "options": {"temperature": 0.8,
                        "num_predict": min(4000, 400 + 60 * fehlt)},
            "messages": [{"role": "system", "content": system},
                         {"role": "user",
                          "content": f"Bisher:\n{inhalt}\n\n"
                                     f"Schreibe die {fehlt} fehlenden Szenen."}],
        }, timeout=600)
    finally:
        entladen(name)
    if not isinstance(roh, dict):
        return []
    neu = [str(z or "").strip()[:200] for z in (roh.get("szenen") or [])
           if str(z or "").strip()]
    # Was schon dasteht, faellt heraus: das Modell wiederholt gern die letzte.
    vorhanden = {z.lower() for z in da}
    neu = [z for z in neu if z.lower() not in vorhanden]
    return neu[:fehlt] + [""] * max(0, fehlt - len(neu))


def expose(idee: str, fiktion=None, vorher: str = "",
           model: str | None = None, anzahl: int = 0, alter: str = "") -> dict:
    """Aus einer Idee die Kurzbeschreibung samt Stil und Weltzuordnung.

    `fiktion` ist der Regler des Benutzers, 0 bis 10, und schlaegt das
    Urteil des Modells. None laesst es selbst entscheiden. `anzahl` ist die
    gewuenschte Zahl der Szenen; 0 laesst das Modell entscheiden.
    """
    leer = {"kurz": "", "welt": "wirklich", "stil": "", "titel": "", "szenen": []}
    if not (idee or "").strip():
        return leer
    name = model or GROSS
    erlaubt, satz = grad(fiktion)
    try:
        wunsch = max(0, min(int(anzahl or 0), MAX_SZENEN))
    except (TypeError, ValueError):
        wunsch = 0
    system = EXPOSE_SYSTEM.format(
        welten=", ".join(f'"{k}" ({WELTEN[k][0]})' for k in erlaubt),
        stile=", ".join(STYLES),
        anzahl=(f"GENAU {wunsch} Stück -- nicht mehr und nicht weniger"
                if wunsch else "fünf bis zehn Stück"))
    if satz:
        system += f"\n\nDer Benutzer hat den Wirklichkeitsgrad vorgegeben: {satz}"
    if freigabe(alter):
        system += f"\n\n{freigabe(alter)}"
    # Je unwirklicher, desto eher gezeichnet. Ein Foto muss glaubhaft sein --
    # eine fliegende Stadt im Fotostil sieht nach Montage aus, dieselbe Stadt
    # als Anime nach Absicht.
    try:
        stufe = int(fiktion)
    except (TypeError, ValueError):
        stufe = -1
    if stufe >= 7:
        system += ("\n\nSo weit weg von der Wirklichkeit sind gezeichnete "
                   "Stile klar im Vorteil. Waehle einen davon: "
                   + ", ".join(sorted(GEZEICHNET)) + ".")
    # Ein Folgeband faengt nicht bei null an. Ohne die Vorgeschichte erfindet
    # das Modell die Figuren neu und widerspricht dem, was schon geschehen ist.
    if vorher.strip():
        system += ("\n\nDas ist die Fortsetzung. Bisher geschah:\n"
                   + vorher.strip()
                   + "\n\nKnuepfe daran an, wiederhole es nicht.")
    try:
        roh = antwort({
            "model": name, "format": "json", "keep_alive": "10m",
            # Der Platz muss mit der Zahl der Szenen wachsen. Mit festen 900
            # Tokens brach die Antwort bei etwa 22 Zeilen ab -- gemessen an
            # einer Bitte um 30. Abgeschnittenes JSON ergibt weniger Szenen,
            # ohne dass jemand es merkt.
            "options": {"temperature": 0.8,
                        "num_predict": min(4000, 900 + 60 * wunsch)},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": idee}],
        }, timeout=600)
    finally:
        entladen(name)
    if not isinstance(roh, dict):
        return leer
    welt = str(roh.get("welt") or "").strip()
    if welt not in erlaubt:
        welt = erlaubt[0]
    stil = str(roh.get("stil") or "").strip()
    szenen = [str(z or "").strip()[:200] for z in (roh.get("szenen") or [])
              if str(z or "").strip()]
    # Ein kleines Modell trifft die Zahl nicht immer. Zu viele werden
    # abgeschnitten, zu wenige mit leeren Zeilen aufgefuellt -- lieber eine
    # leere Zeile zum Selberschreiben als eine fehlende Szene.
    if wunsch:
        szenen = szenen[:wunsch] + [""] * max(0, wunsch - len(szenen))
    return {
        "kurz": str(roh.get("kurz") or "").strip()[:900],
        "welt": welt,
        "stil": stil if stil in STYLES else "",
        "titel": str(roh.get("titel") or "").strip()[:60],
        "szenen": szenen[:MAX_SZENEN],
    }
