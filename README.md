# Qwen-Image 2.1 — lokale Weboberfläche und GIMP-Anbindung

Text zu Bild, Bildbearbeitung, Gruppenbilder und Serien mit
[Qwen-Image 2.1](https://huggingface.co/Qwen/Qwen-Image-2.1) — vollständig auf
dem eigenen Rechner, ohne Cloud. Dazu eine Freitexteingabe auf Deutsch und ein
GIMP-Plugin.

Entwickelt und gemessen auf einer **RTX 3090 (24 GB) mit 31 GB Arbeitsspeicher**.

## Warum zwei Phasen

Qwen-Image 2.1 wiegt in bfloat16 rund **33 GB**: Text-Encoder ~17,5 GB,
Transformer ~14,2 GB, VAE ~1,4 GB. Auf dieser Maschine passt weder alles
zusammen in die GPU noch alles zusammen in den Hauptspeicher —
`enable_model_cpu_offload()` aus den offiziellen Beispielen läuft deshalb in
den Swap oder scheitert.

Stattdessen wird jeder Auftrag zweistufig abgearbeitet, mit einer Leerung der
GPU dazwischen:

1. **Text-Encoder** auf die GPU, alle Prompts der Serie einbetten, freigeben.
2. **Transformer + VAE** auf die GPU, alle Bilder entrauschen und dekodieren.

So liegen nie mehr als ~17,5 GB gleichzeitig auf der Karte. Eine ganze Serie
teilt sich die beiden Ladevorgänge: das erste Bild kostet gut anderthalb
Minuten, jedes weitere nur noch die reine Rechenzeit.

Gemessen bei 1024 px und 30 Schritten: **erstes Bild ~100 s, jedes weitere
~25 s.** Zehn Varianten dauern also rund fünf statt siebzehn Minuten.

## Installation

```bash
git clone <dieses-repository> qwen_image
cd qwen_image
python3 -m venv qwen_bild
./qwen_bild/bin/pip install -r requirements.txt
```

Qwen-Image 2.1 braucht `diffusers` von `main`; die Version in `requirements.txt`
ist auf den geprüften Stand festgenagelt. Beim ersten Start lädt das Modell
rund 31 GB in den Hugging-Face-Cache.

## Starten

```bash
./start.sh              # http://127.0.0.1:7860
./start.sh 8080         # anderer Port
QWEN_HOST=0.0.0.0 ./start.sh   # auch vom Handy im selben Netz erreichbar
```

Immer nur **eine** Instanz gleichzeitig — zwei Prozesse, die je 17 GB auf die
Karte laden, werfen sich gegenseitig heraus.

## Was die Oberfläche kann

**Vier Betriebsarten:** Text zu Bild · Bearbeiten (1–4 Referenzbilder) ·
Gruppenbild (2–4 Personen in ein gemeinsames Foto) · Umrundung (eine Person
aus wechselnden Blickwinkeln).

**Serien** mit 1–20 Bildern. Variieren nach Umrundung, Kameraperspektive, Stil
oder Lichtstimmung — der Reihe nach oder gewürfelt. Optional derselbe Seed für
alle Bilder, was Kleidung, Umgebung und Bildaufbau stabil hält.

**Voreinstellungen** in `webui/presets.py`, frei erweiterbar: 17 Stile,
10 Lichtstimmungen, 11 Kameraperspektiven, 10 Blickwinkel, 8 Vorlagen
(Porträt, Logo, Buchumschlag, Verpackung, Icon, Web- und App-Muster) sowie
15 Effekte als Kurzbefehle — `/remove BG`, `/colorize`, `/blueprint`,
`/magazine cover`, `/360 View` und weitere. Kurzbefehle lassen sich direkt in
das Prompt-Feld tippen und stellen die Regler selbst um.

**Freitexteingabe:** Ein Satz auf Deutsch, ein lokales Sprachmodell über
[Ollama](https://ollama.com) übersetzt und stellt ein. Der eigentliche Gewinn
ist die Übersetzung — Qwen-Image folgt englischen Bildbeschreibungen deutlich
besser. Alles Verstandene landet sichtbar in den Reglern, bevor es losgeht.

Das Sprachmodell wird nach jeder Anfrage sofort wieder entladen
(`keep_alive: 0`), damit die GPU frei für das Bildmodell bleibt.

## GIMP-Plugin

```bash
./gimp/install.sh   # GIMP danach neu starten
```

Menü **Filter › Qwen**: *Text zu Bild*, *Bild bearbeiten*,
*Hintergrund entfernen*. Das Plugin rechnet nichts selbst, es redet über HTTP
mit dem laufenden Server.

**Die GIMP-Auswahl ist die Maske.** Besteht beim Bearbeiten eine Auswahl,
bekommt die Ergebnisebene automatisch eine Ebenenmaske daraus — die Änderung
wirkt nur dort. Qwen-Image 2.1 selbst hat keinen Masken-Eingang; GIMPs
Auswahl- und Pinselwerkzeuge übernehmen diese Rolle. Auswahl vorher ausblenden,
sonst gibt es eine harte Kante.

GIMP 3.2 benutzt `~/.config/GIMP/3.2/plug-ins/`, auch als Snap-Paket. Das
Verzeichnis `~/snap/gimp/*/.config/GIMP/3.0/` ist ein Überbleibsel und wird
nicht gelesen.

## Einstellungen über Umgebungsvariablen

| Variable | Vorgabe | Wirkung |
|---|---|---|
| `QWEN_HOST` | `127.0.0.1` | Bindeadresse des Servers |
| `QWEN_PORT` | `7860` | Port |
| `QWEN_IMAGE_REPO` | `Qwen/Qwen-Image-2.1` | Modell |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama für die Freitexteingabe |
| `QWEN_CHAT_MODEL` | `qwen3.5:4b` | Sprachmodell für die Deutung |
| `QWEN_URL` | `http://127.0.0.1:7860` | Server, den das GIMP-Plugin anspricht |

## Bekannte Grenzen

**`/expand` ist kein pixelgenaues Outpainting.** Qwen-Image 2.1 hat weder einen
Masken-Eingang noch einen Outpainting-Prior: einen freigelassenen Rand füllt es
nicht auf, einen unscharf vorgefüllten übernimmt es unscharf. Umgesetzt ist
deshalb der Weg, der zum Modell passt — die Szene wird im neuen Format neu
gezeichnet. Person, Kleidung, Umgebung und Licht bleiben erhalten, die Mitte
ist danach aber nicht pixelgleich.

**`/restore` ist nur ein Prompt.** Ein Diffusionsmodell erfindet Details, statt
sie wiederherzustellen. Für echtes Restaurieren gehört ein eigenes Modell her.

**Das Sprachmodell rät mit.** Kleine Modelle setzen gern Stil oder Licht, nach
denen niemand gefragt hat. Deswegen landet alles sichtbar in den Reglern. Aus
einem Vergleich von vier Modellen auf einem Testsatz aus zehn Anfragen:

| Modell | Testsatz (22 Punkte) | Erfundene Felder bei knappen Wünschen |
|---|---|---|
| `qwen3.5:4b` | 22/22 | 0 |
| `ministral-3:3b` | 21/22 | 0 |
| `qwen3.5:2b` | 22/22 | 0 |
| `granite4.2:3b` | 16/22 | 9 |

Ein JSON-Schema statt `format: "json"` erzwingt zwar gültige Syntax, kostet
aber spürbar Verständnis — gemessen 14 statt 22 Treffern, weil ausdrückliche
Wünsche wie „quer" oder „freigestellt" unter den Tisch fielen. Die Antwort wird
stattdessen serverseitig gegen die echten Tabellen geprüft.

**Mehrere Referenzbilder kosten Sequenzlänge.** Vier Referenzen bei voller
Auflösung sprengen den Speicher. Die Referenzauflösung wird deshalb automatisch
gesenkt (1–2 Bilder 1024 px, 3 Bilder 864 px, 4 Bilder 736 px), die
Ausgabegröße bleibt unberührt. VRAM-Spitze bei vier Personen: 19,9 GB.

## Aufbau

```
start.sh              Server starten, Browser öffnen
webui/server.py       HTTP-Server, nur Standardbibliothek
webui/engine.py       zweiphasige Pipeline
webui/presets.py      Stile, Lichter, Kameras, Blickwinkel, Vorlagen, Effekte
webui/chat.py         Freitext über Ollama deuten und prüfen
webui/index.html      Oberfläche
gimp/qwen-image/      GIMP-3-Plugin
gimp/install.sh       Plugin verknüpfen
```

## Lizenz

PolyForm Noncommercial 1.0.0 mit einer zusätzlichen Einschränkung für
militärische Nutzung und Waffen — siehe [LICENSE](LICENSE). Das ist **keine**
Open-Source-Lizenz.

Die Lizenz gilt für den Code in diesem Repository. **Qwen-Image 2.1 selbst
steht unter seiner eigenen Lizenz** und wird hier nicht mitgeliefert, sondern
beim ersten Start heruntergeladen.
