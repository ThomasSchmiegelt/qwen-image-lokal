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

Bis zu zehn Achsen — Farbe, **Farbstimmung**, **Stil**, Umgebung, Licht,
Kameraart, Blickwinkel, Werkstoff (10 Materialien von Aluminium bis Gusseisen)
sowie **Körperhaltung** und **Bekleidung** bei Personen — lassen
sich je einzeln auf **würfeln**, **unverändert lassen** oder einen festen Wert
stellen. Der Werkstoff steht standardmäßig aus und wird bei Personen nie
gewürfelt. So entsteht wahlweise breite Streuung oder eine Serie, in der sich
nur ein einziges Merkmal ändert — oder umgekehrt: Stil fest auf *Comic*, alles
andere gewürfelt, dann bleibt der Zeichenstil und der Rest wechselt.

Die **Farbstimmung** ist etwas anderes als die Farbe: sie färbt das ganze Bild
(knallig, pastell, neon, kitschbunt, metallic, irisierend, monochrom, erdig,
kühl, warm) und braucht kein Ziel. Ohne sie bestimmen Umgebung und Licht die
Palette allein, und die sind erdlastig — daher der frühere Braunstich. Was umgefärbt wird, beschreibst du selbst
(`the vehicle body`, `the person's coat`), ebenso was unverändert bleiben muss.
Neben den Bildern entsteht ein `*.jsonl`-Manifest mit einer Zeile je Variante.

**Serien** mit 1–20 Bildern. Variieren nach Umrundung, Kameraperspektive, Stil
oder Lichtstimmung — der Reihe nach oder gewürfelt. Optional derselbe Seed für
alle Bilder, was Kleidung, Umgebung und Bildaufbau stabil hält.

**Warteschlange.** Aufträge werden eingereiht statt abgewiesen: abschicken,
weiterarbeiten, den nächsten anhängen. Ein einziger Arbeitsfaden nimmt die
Liste der Reihe nach ab — gleichzeitig rechnen kann die eine Grafikkarte
ohnehin nicht. Wartende lassen sich verschieben und einzeln verwerfen, der
laufende wird abgebrochen.

Gleichartige Aufträge, die hintereinander warten, **teilen sich einen
Ladevorgang**. Das lohnt sich: gemessen kostet das Laden rund 70 Sekunden, ein
kleines Bild danach anderthalb. Zwei einzeln eingereihte Aufträge brauchten
144 s, gebündelt 78 s. Gebündelt wird streng nur, was wirklich zusammenpasst —
schlichte Text-zu-Bild-Aufträge ohne Referenzbild, Effekt oder Serienart, bei
gleicher Größe, Schrittzahl und Format.

**Projekte.** Jedes Vorhaben bekommt sein eigenes Verzeichnis unter
`projekte/<name>/`: eigene Bilder, eigene Galerie. Ein Auftrag merkt sich beim
Einreihen, zu welchem Projekt er gehört — wer zwischendurch umschaltet, findet
seine Bilder trotzdem am richtigen Ort. Das Projekt **Allgemein** zeigt weiter
auf das alte `outputs/`, dort liegende Bilder müssen nicht umziehen.

**Video aus ausgewählten Bildern.** In der Galerie „Video zusammenstellen"
anklicken, Bilder in der gewünschten Reihenfolge wählen (sie werden
durchnummeriert), Gesamtdauer eintragen — Standzeit und Überblendung rechnet
der Server daraus aus. Die Bilder gehen nahtlos ineinander über, ohne Schnitt
und ohne Beschriftung.

**Was nicht ins Bild soll.** Das Feld arbeitet als **Torwächter**: die
eingetragenen Begriffe werden aus dem fertigen Prompt gestrichen, bevor
gerechnet wird — „Küche" und „Büro" kommen ohnehin als Wort aus einer
Umgebungsachse oder einem Baustein. Das kostet nichts. Was gestrichen wurde,
steht danach unter dem Feld.

Gestrichen wird so viel wie nötig und so wenig wie möglich: steht der Begriff
vorn im Satzglied, ist er dessen Gegenstand und alles fällt (»in a bright
kitchen« verschwindet ganz). Steht er hinten, ist er Beiwerk und nur der
Nebensatz fällt — »eine Markthalle mit Leuchtreklame« bleibt eine Markthalle. Nur für Dinge, die *nicht* im Prompt stehen
(unscharf, sechs Finger), hilft das Häkchen „auch dem Modell ausreden" — dann
läuft jeder Schritt zweimal und das Bild dauert doppelt so lang.

**Bausteine.** Personen, Orte und Gegenstände lassen sich als Prompt mit
Namen und Bild ablegen und immer wieder verwenden. Beschrieben wird auf
Deutsch, das Sprachmodell schreibt daraus den englischen Prompt — und setzt
alles, was sich ändern darf, als Lücke in geschweifte Klammern:

```
a woman in her thirties, slim, short dark hair, wearing {kleidung} and {schuhe}
```

Im Reiter **Zusammenstellen** hakt man Bausteine an, füllt die Lücken und
erzeugt daraus ein Bild. Mehrere Zeilen in einem Lückenfeld ergeben eine ganze
Serie — dieselbe Person in vier Jacken, alle in einem Ladevorgang. Das Ergebnis
lässt sich als **Szene** merken: sie behält ihre Lücken, bekommt das erzeugte
Bild und ist damit wiederholbar.

Leere Lücken hinterlassen keine Bruchstücke: aus `a basket made of {material}`
wird ohne Material `a basket`, nicht `a basket made of ,`.

**Freitext mit Gedächtnis.** Das Gespräch geht weiter: „ein rotes Auto im
Wald" → „mach es hochkant" → „und jetzt als Comic" → „davon bitte sechs
Stück". Jeder Nachsatz ändert genau eine Sache und lässt den Rest stehen; der
Verlauf steht unter dem Feld, „neu anfangen" vergisst ihn.

**Geschichte** in vier Schritten. **Umreißen:** eine Idee genügt — das
Sprachmodell schreibt die Kurzfassung, schlägt den Stil für die ganze Folge
vor und macht einen Vorschlag fürs Inhaltsverzeichnis. Ein **Regler von 0 bis
100 % Fiktion** sagt ihm, wie wirklich es zugehen soll; ohne diese Angabe
biegt es eine Fantasiehandlung so lange zurecht, bis sie alltagstauglich ist.
Gemessen an derselben Idee: bei 0 % sucht eine Frau nachts ein verlegtes Buch,
bei 100 % wandeln sich die Regale, während sie sucht.

**Gliedern:** je Zeile eine Szene, mit `/Name` holst du einen Baustein herein
(`/Anna rennt durch die /Markthalle`). Rechts steht, wie viele Bilder aus
dieser Szene entstehen — mehrere zeigen denselben Augenblick aus wechselndem
Blickwinkel. Gewürfelt wird dabei nur der Blick, nicht Stil, Ort, Kleidung
oder Kameraart: eine gewürfelte Überwachungskamera machte aus einem Manga
mittendrin ein Lichtbild. Bei den elf gezeichneten Stilen steht zusätzlich
ausdrücklich im Prompt, dass kein Foto entstehen soll.

**Schreiben lassen:** die Prompts entstehen der Reihe nach, jede Szene sieht
die vorigen. Dafür ist das große Modell (`qwen3.8:27b-mtp-q4_K_M`, 16,5 GB)
vorgesehen — gemessen rund 30 s zum Laden und dann 7 s je Szene, und es
bleibt zwischen den Szenen geladen. Optional schreibt es auch die Prosa dazu.
Weil es die Grafikkarte belegt, läuft das als Auftrag in der Warteschlange.

**Erzeugen:** in den Ablauf übernehmen und gegenlesen, oder gleich Bilder und
Video.

**Mehrere Geschichten, jede in Bänden.** Eine Geschichte bekommt einen Namen
und die Vorgaben, die für alles gelten: Stil, Welt, Wirklichkeitsgrad,
Sprachmodell. Soll sie weitergehen, hängt *+ Band* einen zweiten Teil an — er
erbt die Vorgaben und kennt die Kurzfassungen der vorigen Bände, knüpft also
an, statt die Figuren neu zu erfinden.

Gespeichert wird als lesbares JSON, eine Datei je Geschichte unter
`projekte/<projekt>/geschichten/<name>.json`: Vorgaben oben, darunter die
Bände mit Idee, Kurzfassung, Inhaltsverzeichnis und Prompts. Damit lässt sich
eine Geschichte auch außerhalb des Programms weiterverarbeiten. Geschrieben
wird verzögert, damit nicht jeder Tastendruck eine Datei anfasst.

Ein `/Name`, zu dem es noch keinen Baustein gibt, ist eine Arbeitsanweisung
und erscheint im **Katalog unter „Noch anzulegen"**, mit dem Projekt, das ihn
verlangt, und einem Knopf, der ihn gleich anlegt. Sobald er existiert,
verschwindet der Eintrag.

Der alte Weg — Handlung auf Deutsch beschreiben, Bausteine anhaken — das
Sprachmodell zerlegt sie in Bilder und nimmt **Mimik und Stil aus der
Handlung**: wer seinen Korb verliert, schaut erschrocken, wer ihn wiederbekommt,
erleichtert. Heraus kommt kein Sonderformat, sondern die vorhandene
Blockstruktur eines **Ablaufs** — gegenlesen, ändern, starten, oder ohne
Prüfung loslaufen lassen. Hat die Hauptperson ein Bild, wird es zum Startbild,
damit die Folge auf einem Gesicht aufsetzt statt in jedem Bild ein neues zu
erfinden.

**Katalog.** Ein Reiter zeigt alle Bausteine aus allen Projekten auf einer
Seite, nach Art und Text durchsuchbar. Von dort lässt sich eine Person, ein
Ort oder ein Gegenstand in ein anderes Projekt übernehmen — das Bild wandert
als Kopie mit, damit es das Löschen des Ursprungsprojekts überlebt.

**Prompt aus einem Bild.** Der umgekehrte Weg: ein Bild wählen, das
Sprachmodell beschreibt es als Prompt und stellt Stil, Licht und Objektiv
gleich passend ein (gemessen 5–9 s). Im Ablauf-Reiter wird ein hochgeladenes
Startbild sofort kurz beschrieben; der Text lässt sich vor dem Start ändern.

**Voreinstellungen** in `webui/kataloge/`, frei erweiterbar: 22 Stile,
10 Lichtstimmungen, 11 Kameraperspektiven, 10 Blickwinkel, 8 Vorlagen
(Porträt, Logo, Buchumschlag, Verpackung, Icon, Web- und App-Muster) sowie
17 Effekte als Kurzbefehle — `/remove BG`, `/colorize`, `/blueprint`,
`/cad2real` (aus einer CAD-Ansicht ein Produktfoto mit echten Materialien,
Oberflächenspuren und Kontaktschatten, bei unveränderter Geometrie),
`/upscale` (dasselbe Bild in 2048er Kantenlänge, mit ausgezeichneten
Strukturen statt geglätteter Kanten), `/magazine cover`, `/360 View` und
weitere. Kurzbefehle lassen sich direkt in
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
| Vorlage | *behutsam ändern* (bewahrt), *verwandeln* (Stilwechsel) oder *Bewegung* |
| Seed | eigener oder wie das Startbild |
| danach Startbild | blendet das Ausgangsbild wieder ein, ohne es neu zu rechnen |
| Anzahl | wie viele Bilder der Block liefert; mehr als Zeilen heißt, die Zeilen werden der Reihe nach wiederholt |
| was bleibt | die Ausnahme, die stehen bleiben muss |
| Bausteine | ein Bild je Zeile |

Die beiden oberen Felder sind nicht kosmetisch. **Die Prompt-Vorlage:** die
behutsame wiederholt „muss identisch bleiben" mehrfach; ein angehängter
Stilbaustein geht darin unter und das Modell gibt schlicht die Vorlage zurück.
**Der Seed:** ein für alle Bilder gesperrter Seed hält die Bildaufteilung ruhig,
zementiert aber auch die Neigung dieses *einen* Rauschmusters — gemessen wurde
aus „grellem Neon" ein violetter Hauch (Abweichung 42 statt 79).

Sieben Abläufe sind mitgeliefert:

| Ablauf | Bilder | Worum es geht |
|---|---|---|
| **Bogen** | 38 | konservativ über Comic und Neon und zurück |
| **Reise** | 48 | Licht, Perspektive, Person, Schwenk, Bewegung, Hintergrund, Rollen, Szenen bis Cyberpunk, Neonkleidung, Gruppenbild |
| **Klassisch** | 21 | nur Mittel des Fotostudios: Lichtführung, Brennweite, Hintergrund, Schwarzweiß |
| **Zeitreise** | 19 | zwölf Epochen von der Höhle bis in die nahe Zukunft, dazu sechs Aufnahmeverfahren von der Daguerreotypie bis zum Handyfoto |
| **Comicheft** | 16 | zehn Zeichenstile von Ligne claire bis Pop Art, dann immer weiter ins Heft hinein bis zum Rasterpunkt |
| **Neonstadt** | 11 | eine Eskalation, jeder Schritt auf dem vorigen: Neon, Regen, Hologramme, Implantate, Drohnenblick, Glitch — und zurück auf die Straße |
| **Elemente** | 14 | aus Feuer, Wasser, Erde, Luft; dann als Bronze, Marmor, Glas, Holz, Origami, Klemmbaustein; zum Schluss in Bewegung |

Der Ablauf **passt sich dem Startbild an**. Bevor die Blöcke gebaut werden,
beschreibt dasselbe Sprachmodell das Bild — Geschlecht, ungefähres Alter,
Haare, auffällige Kleidung, Umgebung. Daraus folgt zweierlei:

- Ist eine Frau zu sehen, wird aus dem Bart-Schritt ein Haarfarben-Schritt.
  Bei unklarem Befund bleibt es beim Regelfall, statt zu raten.
- Die Beschreibung wandert in jede Bewahrungsklausel. „Die Person muss gleich
  bleiben" trifft das Modell besser, wenn dort steht, *wen* es gleich lassen
  soll — also „die Person (eine Frau Mitte zwanzig mit langen braunen Haaren,
  schwarzes Oberteil)". Was erkannt wurde, steht unter dem hochgeladenen Bild.

Jede Anweisung endet mit einem Hinweis zu den **Zähnen**. Diffusionsmodelle
verzeichnen sie notorisch — zu viele, verschmiert, doppelte Reihen. Der kurze
Zusatz („gleichmäßig, richtig geformt, die richtige Anzahl, nicht verschmiert
oder verdoppelt") hilft spürbar.

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

**`/upscale` rechnet nicht hoch, es zeichnet neu.** Einen Skalierer bringt
Qwen-Image 2.1 nicht mit. Der Effekt gibt das Bild deshalb mit 2048er
Kantenlänge neu aus — das Seitenverhältnis kommt aus der Vorlage, die mit
1472 px gelesen wird. Es entstehen echte Strukturen statt weichgezeichneter
Kanten, das Ergebnis ist dafür nicht pixelgleich: kleine Details können
anders ausfallen als im Original. Für Beweisfotos ist das nichts, für ein
altes Handybild, das groß gedruckt werden soll, sehr wohl.

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

## Prüfen

```bash
./qwen_bild/bin/python webui/pruefung.py        # Server auf 7860 muss laufen
```

Vergleicht die Oberfläche mit dem laufenden Server: liest die Seite nur Felder,
die `/api/info` auch liefert, existiert jedes angesprochene Element, sind die
Klammern im Skript geschlossen, läuft der Server mit dem Code von der Platte.

Anlass war ein echter Fehler: ein Feld wurde aus `/api/info` entfernt, die
beiden Aufrufe in der Seite blieben stehen. Der TypeError brach die gesamte
Einrichtung ab, das Seitenverhältnis-Feld blieb leer — und der Auftrag
scheiterte erst viel später im Server mit `KeyError: ''`.

## Aufbau

```
start.sh              Server starten, Browser öffnen
webui/server.py       HTTP-Server, nur Routen und Start
webui/auftraege.py    Warteschlange und Abwicklung eines Auftrags
webui/projekte.py     getrennte Ablagen, Projektverzeichnisse
webui/bausteine.py    Personen, Orte, Gegenstände und Szenen mit Lücken
webui/geschichte.py   Szenen einer Handlung zu Ablaufblöcken
webui/engine.py       zweiphasige Pipeline
webui/kataloge/       Voreinstellungen: anmutung.py (Stil, Licht, Kamera,
                      Farbe), motiv.py (Umgebung, Blickwinkel, Werkstoff),
                      vorlage.py (Prompt-Vorlagen, Effekte, Gruppen)
webui/sprache/        Ollama: deuten.py (Freitext), uebersetzen.py,
                      sehen.py (Bilder lesen), erzaehlen.py (Handlung in
                      Szenen), ollama.py (der Aufruf)
webui/ablauf.py       Abläufe als Blöcke, mitgelieferte Folgen
webui/demo.py         Startbild-Vorgabe und Videobau
webui/pruefung.py     Oberfläche gegen den Server prüfen
demo/demonstration.py dieselbe Vorführung von der Kommandozeile
webui/seite/          Oberfläche: index.html (Aufbau), stil.css (Aussehen),
                      app.js (Verhalten)
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
