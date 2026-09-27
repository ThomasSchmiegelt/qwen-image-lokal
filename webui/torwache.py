"""Der Torwaechter: was nicht ins Bild soll, faellt aus dem Prompt.

Eine eigene Datei, weil zwei Wege ihn brauchen -- der Auftrag mit seinem
Feld "was nicht ins Bild soll" und die Geschichte mit ihrem #-Hinweis je
Szene. Beide sollen denselben Wortlaut streichen, und zwei Kopien davon
liefen frueher oder spaeter auseinander.
"""

import re


def _ausschluesse(text: str) -> list[str]:
    """Die Begriffe aus dem Feld "was nicht ins Bild soll"."""
    return [t.strip().lower() for t in re.split(r"[,;\n]", text or "") if t.strip()]


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
