"""Das Sprachmodell: verstehen, uebersetzen, sehen.

    ollama        Adresse, Modell, der Aufruf selbst
    deuten        Freitext -> Prompt und Reglerstellung
    uebersetzen   Deutsch -> Englisch, nur wo noetig
    sehen         Bilder beschreiben und rueckwaerts den Prompt schreiben

Der Server spricht nur mit diesem Paket, nicht mit den einzelnen Dateien.
"""

from .deuten import MODES, ask, interpret, sanitise, system_prompt
from .ollama import MODEL, OLLAMA, available
from .sehen import bild_frage, bild_lesen, bild_zu_prompt, ist_weiblich
from .uebersetzen import looks_german, translate

__all__ = [
    "MODEL", "MODES", "OLLAMA", "ask", "available", "bild_frage", "bild_lesen",
    "bild_zu_prompt", "interpret", "ist_weiblich", "looks_german", "sanitise",
    "system_prompt", "translate",
]
