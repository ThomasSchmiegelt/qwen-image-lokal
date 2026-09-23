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

**Fünf Betriebsarten:** Text zu Bild · Bearbeiten (1–4 Referenzbilder) ·
Gruppe · Umrundung (eine Person aus wechselnden Blickwinkeln) · Varianten.

**Gruppe** kennt drei Aufgaben: *aus Einzelbildern zusammenstellen* (je ein
Bild pro Person), *Person ergänzen* (erstes Bild ist das Gruppenfoto, danach
je ein Bild pro Person, die dazu soll) und *Person entfernen* (beschreiben,
wer verschwinden soll — „die mittlere Person"). **Jedes Referenzbild bekommt
auf Wunsch einen eigenen Text**, der sagt, wie diese Person darzustellen ist —
„ein mittelalterlicher Ritter", „eine Astronautin im Raumanzug". Beim Ergänzen
gibst du an, wie
viele Personen schon auf dem Gruppenfoto sind: das Modell kann nicht zählen,
und ohne feste Zielzahl stellt es wahllos Leute dazu.

Dazu **Inszenierungen** — 12 Vorlagen für das Aussehen der Gruppe, von
leuchtenden Geistern über Fantasy-Gefährten und Tafelrunde bis Detektive und
Familienporträt. Sie beschreiben den Look ausformuliert statt einen Filmtitel
zu nennen; das trifft das Modell zuverlässiger.

**Varianten** vervielfachen ein Basisbild, etwa für Trainingsdaten. Zuerst die
**Motivart** wählen — Fahrzeug, Gegenstand oder Person: davon hängt ab, welche
Umgebungen und Blickwinkel angeboten werden. „Auf Stoßstangenhöhe von hinten"
passt zu einem Auto und zu nichts sonst, ein Gegenstand will „auf der Werkbank"
und „freigestellt mit Schlagschatten".

Sechs Achsen — Farbe, Umgebung, Licht, Kameraart, Blickwinkel und Werkstoff
(10 Materialien von Aluminium bis Gusseisen) — lassen sich je einzeln auf
**würfeln**, **unverändert lassen** oder einen festen Wert stellen. Der
Werkstoff steht standardmäßig aus und wird bei Personen nie gewürfelt.
So entsteht wahlweise breite Streuung oder eine Serie, in der sich nur ein
einziges Merkmal ändert. Was umgefärbt wird, beschreibst du selbst
(`the vehicle body`, `the person's coat`), ebenso was unverändert bleiben muss.
Neben den Bildern entsteht ein `*.jsonl`-Manifest mit einer Zeile je Variante.

**Serien** mit 1–20 Bildern. Variieren nach Umrundung, Kameraperspektive, Stil
oder Lichtstimmung — der Reihe nach oder gewürfelt. Optional derselbe Seed für
alle Bilder, was Kleidung, Umgebung und Bildaufbau stabil hält.

**Voreinstellungen** in `webui/presets.py`, frei erweiterbar: 17 Stile,
10 Lichtstimmungen, 11 Kameraperspektiven, 10 Blickwinkel, 8 Vorlagen
(Porträt, Logo, Buchumschlag, Verpackung, Icon, Web- und App-Muster) sowie
16 Effekte als Kurzbefehle — `/remove BG`, `/colorize`, `/blueprint`,
`/cad2real` (aus einer CAD-Ansicht ein Produktfoto mit echten Materialien,
Oberflächenspuren und Kontaktschatten, bei unveränderter Geometrie),
`/magazine cover`, `/360 View` und weitere. Kurzbefehle lassen sich direkt in
das Prompt-Feld tippen und stellen die Regler selbst um.

**Deutsch überall.** Prompt, „was unverändert bleiben muss", „was umgefärbt
wird" und der negative Prompt dürfen deutsch sein. Der Server erkennt das und
übersetzt vor dem Auftrag ins Englische, weil Qwen-Image dem deutlich besser
folgt. Kostet rund vier Sekunden und gilt auch für das GIMP-Plugin. Englische
Eingaben laufen unangetastet durch. Ist Ollama nicht erreichbar, läuft der
Auftrag mit dem Originaltext weiter statt zu scheitern. Was übersetzt wurde,
zeigt die Oberfläche unter dem Prompt-Feld an.

**Freitexteingabe:** Ein Satz auf Deutsch, ein lokales Sprachmodell über
[Ollama](https://ollama.com) übersetzt und stellt ein. Der eigentliche Gewinn
ist die Übersetzung — Qwen-Image folgt englischen Bildbeschreibungen deutlich
besser. Alles Verstandene landet sichtbar in den Reglern, bevor es losgeht.

Die Deutung erzeugt noch kein Bild: erst Text, dann Prompt und Einstellungen,
dann prüfen, dann selbst auf Erzeugen klicken.

Das Sprachmodell wird nach jeder Anfrage sofort wieder entladen
(`keep_alive: 0`), damit die GPU frei für das Bildmodell bleibt.

## Abläufe

Der Reiter **Ablauf** erzeugt eine Bildfolge und schneidet daraus ein Video
ohne Beschriftung, bei dem die Bilder ineinander blenden. Eine Folge ist eine
**Datenstruktur aus Blöcken**, kein fest verdrahteter Code — jeder Block sagt:

| Feld | Bedeutung |
|---|---|
| Referenz | vom Startbild oder vom letzten Bild des vorigen Blocks |
| Vorlage | *behutsam ändern* (bewahrt) oder *verwandeln* (Stilwechsel) |
| Seed | eigener oder wie das Startbild |
| danach Startbild | blendet das Ausgangsbild wieder ein, ohne es neu zu rechnen |
| was bleibt | die Ausnahme, die stehen bleiben muss |
| Bausteine | ein Bild je Zeile |

Die beiden oberen Felder sind nicht kosmetisch. **Die Prompt-Vorlage:** die
behutsame wiederholt „muss identisch bleiben" mehrfach; ein angehängter
Stilbaustein geht darin unter und das Modell gibt schlicht die Vorlage zurück.
**Der Seed:** ein für alle Bilder gesperrter Seed hält die Bildaufteilung ruhig,
zementiert aber auch die Neigung dieses *einen* Rauschmusters — gemessen wurde
aus „grellem Neon" ein violetter Hauch (Abweichung 42 statt 79).

Zwei Abläufe sind mitgeliefert: **Bogen** (38 Bilder, konservativ über Comic
und Neon und zurück) und **Reise** (43 Bilder: Beleuchtung, Kameraperspektiven,
Person, Kameraschwenk, Hintergründe, Rollen, Szenen bis in den Cyberpunk — und
dort bleibend für Neonkleidung, zum Schluss ein Gruppenbild aus letzter Ansicht
und Startbild).

Im Editor lassen sich Blöcke hinzufügen, verschieben, löschen und über **als
Text** als JSON sichern und zurückspielen. Die Kommandozeile nimmt so eine
Datei:

```bash
./qwen_bild/bin/python demo/demonstration.py --ablauf reise
./qwen_bild/bin/python demo/demonstration.py --datei eigener_ablauf.json --foto ich.png
```

**Zur Laufzeit:** aufeinanderfolgende Blöcke, die vom Startbild ausgehen, laufen
als *eine* Serie. Bei der Reise sind das 36 Bilder in einem Ladevorgang; nur die
Blöcke, die auf dem letzten Bild aufsetzen, brauchen einen eigenen. 43 Bilder
kosten so rund 29 Minuten statt über einer Stunde.

Die **Kulisse** hinter der Person — Auto, Raumschiff, Fangemeinde, Pferd,
Bagger, Bücherwand und weitere — wird ohne Angabe aus dem Seed abgeleitet und
wechselt damit von Lauf zu Lauf, bleibt aber reproduzierbar.

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

In der Weboberfläche gibt es unter jedem angezeigten Bild **In GIMP öffnen** —
das startet GIMP auf dem Rechner, auf dem der Server läuft, mit genau diesem
Bild. Weil das ein Programm startet, nimmt der Server diesen Aufruf nur von
`127.0.0.1` an; vom Handy aus bleibt er verwehrt, auch bei `QWEN_HOST=0.0.0.0`.

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
| `QWEN_GIMP` | `gimp` | Befehl für „In GIMP öffnen" |

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

**Der Blickwinkel ändert sich bei Varianten nur wenig.** Qwen-Image 2.1
hält sich eng an die Bildaufteilung der Vorlage. Lack, Umgebung und Licht
wechseln zuverlässig, „bodennah" oder „Nahaufnahme" verschieben den Ausschnitt
dagegen nur leicht. Für echte Perspektivvielfalt braucht es Aufnahmen aus
verschiedenen Winkeln als Basis.

**Farbe und Werkstoff zugleich ist mehrdeutig.** Wer beide Achsen gleichzeitig
würfelt, bekommt womöglich ein gelbes Teil neben einem zweiten aus Carbon. Eins
von beidem wählen, das andere auf „unverändert lassen".

**Rollen je Bild greifen, aber nicht immer vollständig.** Der Ritter kam mit
Rüstung und Jeans. Je knapper und konkreter der Rollentext, desto besser.

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
webui/demo.py         Schritte der Vorführung und der Videobau
demo/demonstration.py dieselbe Vorführung von der Kommandozeile
webui/index.html      Oberfläche
gimp/qwen-image/      GIMP-3-Plugin
gimp/install.sh       Plugin verknüpfen
```

## Lizenz

Der **Code in diesem Repository** steht unter [MIT](LICENSE).

### Das Modell hat eine andere Lizenz — und die ist strenger

Dieses Repository enthält keine Modellgewichte. Qwen-Image 2.1 wird beim
ersten Start von Hugging Face geladen, und dabei akzeptierst du dessen eigene
Lizenz:

> **Qwen-Image 2.1 steht unter der [Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)
> und darf nur für Forschung und Evaluierung genutzt werden.**
> Für kommerzielle Nutzung ist eine gesonderte Lizenz von Hangzhou Tongyi
> Laboratory nötig (`model-business@notice.qwencloud.com`).

Das gilt unabhängig von der MIT-Lizenz dieses Codes. MIT erlaubt dir alles mit
*diesen Dateien* — es verschafft dir keinerlei Rechte am Modell.

Beachtenswert: Qwen-Image 1.0 und Qwen-Image-Edit stehen noch unter Apache 2.0.
Erst mit 2.1 wurde auf die Research License gewechselt.

Zwei Pflichten aus dieser Lizenz betreffen typische Nutzung dieses Werkzeugs:

- **Trainierst du mit den erzeugten Bildern ein Modell und gibst es weiter**,
  musst du gut sichtbar „Built with Qwen" angeben (Abschnitt 4b). Das betrifft
  den Varianten-Modus unmittelbar.
- **„Qwen" darf nicht der primäre Name** eines abgeleiteten Produkts sein;
  beschreibende Verwendung ist erlaubt (Abschnitt 4c).

Qwen is licensed under the Qwen RESEARCH LICENSE AGREEMENT, Copyright (c) 2026
Hangzhou Tongyi Laboratory Technology Co., Ltd. All Rights Reserved.

### Die Sprachmodelle ebenfalls

Die Freitextdeutung und die Übersetzung laufen über Ollama. Welches Modell du
dort einsetzt, bestimmst du selbst — dessen Lizenz gilt dann für dich, nicht
die dieses Repositories.

*Dies ist eine Zusammenfassung nach bestem Wissen, keine Rechtsberatung.*
