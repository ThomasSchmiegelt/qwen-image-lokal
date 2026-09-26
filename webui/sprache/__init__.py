"""Das Sprachmodell: verstehen, uebersetzen, sehen.

    ollama        Adresse, Modell, der Aufruf selbst
    deuten        Freitext -> Prompt und Reglerstellung
    uebersetzen   Deutsch -> Englisch, nur wo noetig
    sehen         Bilder beschreiben und rueckwaerts den Prompt schreiben

Der Server spricht nur mit diesem Paket, nicht mit den einzelnen Dateien.
"""

from .deuten import (
    MODES, ask, baustein_prompt, interpret, luecken_vorschlaege, sanitise,
    system_prompt,
)
from .erzaehlen import WELTEN, expose, geschichte, gliederung, prosa
from .ollama import GROSS, MODEL, OLLAMA, available, entladen
from .sehen import bild_frage, bild_lesen, bild_zu_prompt, ist_weiblich
from .uebersetzen import looks_german, translate

__all__ = [
    "GROSS", "MODEL", "MODES", "OLLAMA", "WELTEN", "entladen", "expose", "ask", "available", "baustein_prompt",
    "bild_frage", "bild_lesen",
    "bild_zu_prompt", "geschichte", "gliederung", "interpret",
    "ist_weiblich",
    "luecken_vorschlaege", "prosa",
    "looks_german", "sanitise",
    "system_prompt", "translate",
]
