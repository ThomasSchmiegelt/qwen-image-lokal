// Verhalten der Oberflaeche. Der Aufbau steht in index.html, das Aussehen
// in stil.css. Geladen wird die Datei am Ende des Rumpfes -- die Elemente
// sind dann alle vorhanden.
const $ = id => document.getElementById(id);
const RATIOS = {"1:1":1, "4:3":4/3, "3:4":3/4, "3:2":3/2, "2:3":2/3, "16:9":16/9, "9:16":9/16};
const esc = t => String(t).replace(/[<>&"]/g, c => ({"<":"&lt;", ">":"&gt;", "&":"&amp;", '"':"&quot;"}[c]));

const MODES = {
  t2i:    {label: "Erzeugen", refs: 0, sweep: "", count: 1, lock: false,
           ph: 'A neon shop sign that reads "QWEN IMAGE 2.1", rainy night, reflections on wet pavement'},
  edit:   {label: "Bearbeiten", refs: 1, sweep: "", count: 1, lock: false, follow: true,
           ph: "Change the background to a sunset beach",
           hint: refs => `Bis zu ${refs} Bilder. Mehrere werden gemeinsam als Vorlage gelesen.`},
  gruppe: {label: "Gruppenbild erzeugen", refs: 2, sweep: "", count: 1, lock: false, follow: false,
           ph: "standing together in a sunlit park, smiling, casual clothing",
           hint: refs => `Pro Person ein Bild, 2 bis ${refs} Stück. Gesicht gut sichtbar.`},
  person: {label: "Umrundung erzeugen", refs: 1, sweep: "view", count: 10, follow: false, lock: true,
           ph: "standing in a city street, wearing a dark coat",
           hint: () => "Ein Bild der Person. Die Serie fliegt einmal um sie herum."},
  demo: {label: "Ablauf starten", refs: 0, ph: "", hint: () => ""},
  bausteine: {label: "Baustein-Bild erzeugen", refs: 0, ph: "", hint: () => ""},
  szenen: {label: "Szene erzeugen", refs: 0, ph: "", hint: () => ""},
  geschichte: {label: "Geschichte erzeugen", refs: 0, ph: "", hint: () => ""},
  katalog: {label: "Katalog", refs: 0, ph: "", hint: () => ""},
  varianten: {label: "Varianten erzeugen", refs: 1, sweep: "varianten", count: 12,
              follow: true, lock: false,
              ph: "(optional) zusätzliche Angaben, die für jede Variante gelten",
              hint: () => "Das Basisbild. Welche Achsen sich ändern, stellst du unten ein."}
};

let mode = "t2i", refs = [], refPrompts = [], polling = null, maxRefs = 4, templates = {}, refBudget = 2200;
let EFFECTS = [], FORMS = [], PAINTS = [], ACTIONS = [], SUBJECTS = [],
    hasGimp = false, AXIS_OFF = "-";

// ---------- Voreinstellungen laden ----------
fetch("/api/info").then(r => r.json()).then(info => {
  // Das Wichtigste zuerst: bricht weiter unten etwas ab, sind die Grundregler
  // wenigstens gefüllt. Vorher blieb das Seitenverhältnis leer und der Auftrag
  // scheiterte im Server mit einem KeyError auf einem leeren Wert.
  $("aspect").innerHTML = (info.aspects || ["1:1"])
    .map(a => `<option>${a}</option>`).join("");
  maxRefs = info.max_references;
  templates = info.templates;
  refBudget = info.reference_token_budget;
  Object.assign(SWEEP_LEN, {view: info.views.length, style: info.styles.length,
                            light: info.lights.length, camera: info.cameras.length});
  fill("view", info.views); fill("style", info.styles);
  fill("light", info.lights); fill("camera", info.cameras);
  EFFECTS = info.effects; FORMS = info.forms;
  hasGimp = !!(info.gimp && info.gimp.available);
  ABLAEUFE = info.ablaeufe || [];
  $("ablaufWahl").innerHTML = ABLAEUFE.map(
    a => `<option value="${a.key}">${esc(a.label)}</option>`).join("");
  if (ABLAEUFE.length) { $("ablaufWahl").value = ABLAEUFE[0].key; $("ablaufWahl").onchange(); }
  // Ein sehr alter Server meldet gar kein "source" -- dann ist er erst recht
  // veraltet und kann es nur nicht selbst sagen.
  const neustart = " Bitte im Terminal <code>Strg+C</code> und <code>./start.sh</code>.";
  if (!info.source) {
    $("staleBar").style.display = "block";
    $("staleBar").innerHTML = "Dieser Server ist älter als die Oberfläche und kann "
      + "seinen Stand nicht melden. Das gibt widersprüchliches Verhalten." + neustart;
  } else if (info.source.stale) {
    $("staleBar").style.display = "block";
    $("staleBar").innerHTML = "Der Server läuft noch mit älterem Code ("
      + info.source.changed.map(esc).join(", ")
      + " wurde seither geändert). Die Seite hier ist aktuell, der Server nicht —"
      + " das gibt widersprüchliches Verhalten." + neustart;
  }
  if (info.chat && info.chat.available) {
    $("chatBox").style.display = "block";
    $("chat").placeholder = "Sag einfach, was du willst — „10 Drachen als Zeichentrick, hochkant“";
    $("chatNote").textContent = "Freitext, deutsch. " + info.chat.model
      + " übersetzt und stellt die Regler unten ein. Erzeugt wird erst auf deinen Klick.";
  }
  zeigeProjekte(info.projekte, info.projekt);
  BSARTEN = info.bausteinarten || [];
  $("bsArt").innerHTML = BSARTEN.map(
    a => `<option value="${a.key}">${esc(a.label)}</option>`).join("");
  personFelder();
  MIMIKLISTE = info.mimik || [];
  EINSTELLUNGEN = info.einstellungen || [];
  STILLISTE = info.styles || [];
  fill("gsStil", info.styles);
  GEZEICHNET = info.gezeichnet || [];
  fill("gsWelt", info.welten);
  // Gross fuer die schoepferische Arbeit, klein fuer alles andere.
  $("gsModell").innerHTML =
    `<option value="${info.gross}">${esc(info.gross)} (gross, besser)</option>`
    + `<option value="${(info.chat || {}).model || ""}">`
    + `${esc((info.chat || {}).model || "klein")} (klein, schneller)</option>`;
  zeigeSelbstszenen();
  zeigeGrad();
  zeigeBausteine(info.bausteine);
  fill("effect", EFFECTS); fill("form", FORMS);
  AXIS_OFF = info.axis_off || "-";
  // Alle Achsenfelder fuellt subjectChanged() aus info.subjects[].axes --
  // genau der Liste, aus der der Server auch wuerfelt.
  SUBJECTS = info.subjects;
  $("subject").innerHTML = SUBJECTS.map(
    x => `<option value="${x.key}">${esc(x.label)}</option>`).join("");
  subjectChanged();
  $("material").value = AXIS_OFF;   // Werkstoff nur auf Wunsch
  fill("scenario", info.scenarios);
  ACTIONS = info.group_actions;
  $("action").innerHTML = ACTIONS.map(
    a => `<option value="${a.key}">${esc(a.label)}</option>`).join("");
  PAINTS = info.paints;
  paintPreview();
  $("cmdHint").innerHTML = "Direkt tippbar im Prompt: "
    + EFFECTS.map(e => `<code>${esc(e.alias)}</code>`).join(", ")
    + ". Ein getippter Befehl stellt die Regler selbst um.";
  setMode("t2i");
}).catch(fehler => {
  console.error(fehler);
  $("staleBar").style.display = "block";
  $("staleBar").textContent = "Die Oberfläche konnte sich nicht einrichten: "
    + fehler.message + " — läuft der Server mit dem passenden Code?";
});
// Fehlt dem Server ein Feld, soll das auffallen statt die Seite abzuwürgen:
// ein leeres Auswahlfeld liefert sonst "" und der Auftrag scheitert erst
// weit später mit einer unverständlichen Meldung.
function meldeLuecke(id) {
  console.warn("Der Server liefert keine Daten für", id);
  $("staleBar").style.display = "block";
  $("staleBar").textContent = `Der Server liefert keine Daten für „${id}“. `
    + "Wahrscheinlich läuft er mit älterem Code – bitte Strg+C und ./start.sh.";
}

// Achsen im Varianten-Modus kennen drei Zustaende: wuerfeln, unveraendert
// lassen, oder ein fester Wert.
function fillAxis(id, items) {
  if (!Array.isArray(items)) return meldeLuecke(id);
  $(id).innerHTML = '<option value="">würfeln</option>'
    + `<option value="${AXIS_OFF}">unverändert lassen</option>`
    + items.map(i => `<option value="${i.key}">${esc(i.label)}</option>`).join("");
}
function fill(id, items) {
  if (!Array.isArray(items)) return meldeLuecke(id);
  $(id).innerHTML = '<option value="">— automatisch —</option>'
    + items.map(i => `<option value="${i.key}">${esc(i.label)}</option>`).join("");
}

// ---------- Größenanzeige ----------
function dims() {
  const area = $("base").value ** 2, r = RATIOS[$("aspect").value] || 1;
  return [Math.round(Math.sqrt(area * r) / 32) * 32, Math.round(Math.sqrt(area / r) / 32) * 32];
}
// Spiegelt reference_resolution() aus der Engine wider.
function refSize(base, n) {
  if (!n) return base;
  return Math.max(512, Math.min(base, Math.floor(Math.sqrt(refBudget * 1024 / n) / 32) * 32));
}
function refresh() {
  const useRef = refs.length && $("follow").checked && mode !== "t2i";
  $("aspect").disabled = useRef;
  const [w, h] = dims();
  const n = parseInt($("count").value, 10) || 1;
  $("dims").textContent = (useRef ? `Seitenverhältnis folgt der Referenz · ${$("base").value} px Basis` : `${w} × ${h} px`)
    + (n > 1 ? ` · ${n} Bilder` : "") + " · lokal auf der RTX 3090";

  const base = parseInt($("base").value, 10), r = refSize(base, refs.length);
  $("refNote").textContent = refs.length && r < base
    ? `Referenzen werden intern mit ${r} px gelesen, damit die Sequenz ins VRAM passt. `
      + `Die Ausgabe bleibt bei ${base} px.`
    : "";
}
["aspect", "base", "count", "follow"].forEach(id => $(id).addEventListener("change", refresh));

// Bei einem Durchlauf durch eine Tabelle ist deren Laenge die sinnvolle Anzahl.
const SWEEP_LEN = {};
function sweepChanged() {
  const s = $("sweep").value, n = SWEEP_LEN[s];
  if (n) $("count").value = Math.min(n, 20);
  $("seedHint").textContent = $("lockSeed").checked
    ? "Gleicher Seed: Kleidung, Umgebung und Bildaufbau bleiben über die Serie hinweg stabiler."
    : "Aufsteigende Seeds: jedes Bild wird eigenständiger, aber weniger konsistent.";
  refresh();
}
$("sweep").addEventListener("change", sweepChanged);
$("lockSeed").addEventListener("change", sweepChanged);

// Umgebung und Blickwinkel haengen von der Motivart ab.
// Welches Auswahlfeld welche Achse zeigt. Die Namen rechts sind die des
// Servers (variant_axes), links stehen die Felder der Seite.
const ACHSENFELDER = {paint: "paint", palette: "palette", vstyle: "style",
                      scene: "scene", vlight: "light", device: "device",
                      angle: "angle", material: "material",
                      haltung: "haltung", kleidung: "kleidung"};

function subjectChanged() {
  const k = SUBJECTS.find(x => x.key === $("subject").value) || SUBJECTS[0];
  if (!k) return;
  const achsen = k.axes || {};
  Object.keys(ACHSENFELDER).forEach(id => {
    const liste = achsen[ACHSENFELDER[id]];
    const vorher = $(id).value;
    // Nicht jede Motivart kennt jede Achse -- ein gewuerfelter Werkstoff
    // ergibt bei einer Person keinen Sinn, deshalb fehlt er dort.
    if (!Array.isArray(liste)) {
      $(id).innerHTML = `<option value="${AXIS_OFF}">hier nicht vorgesehen</option>`;
      $(id).disabled = true;
      return;
    }
    $(id).disabled = false;
    fillAxis(id, liste);
    // Die bisherige Wahl behalten, wenn es sie hier auch gibt.
    if (vorher === AXIS_OFF || liste.some(i => i.key === vorher)) $(id).value = vorher;
  });
  $("paintTarget").placeholder = "z. B. " + k.target;
  paintPreview();
}
$("subject").addEventListener("change", subjectChanged);

// Zeigt den Satz, den die Farbachse erzeugen wird. Ohne das bleibt unsichtbar,
// dass ein unpassendes Ziel die Achse wirkungslos macht.
function paintPreview() {
  const el = $("paintPreview"), wahl = $("paint").value, ziel = $("paintTarget").value.trim();
  el.className = "hint";
  if (wahl === AXIS_OFF) { el.textContent = "Die Farbe bleibt unverändert."; return; }
  if (!ziel) {
    el.className = "hint warn";
    el.textContent = "Bitte eintragen, wovon die Farbe geändert werden soll — "
      + "sonst bleibt die Farbachse wirkungslos.";
    return;
  }
  const treffer = PAINTS.find(p => p.key === wahl);
  el.textContent = treffer
    ? `Ergibt: „${ziel} is ${treffer.phrase}“`
    : `Pro Bild eine andere Farbe, z. B. „${ziel} is ${(PAINTS[0] || {}).phrase || "red"}“`;
}
$("paint").addEventListener("change", paintPreview);
$("paintTarget").addEventListener("input", paintPreview);

// ---------- Modus ----------
function setMode(next) {
  mode = next;
  const cfg = MODES[next];
  Object.keys(MODES).forEach(m => $("tab-" + m).classList.toggle("on", m === next));
  $("uploadBox").style.display = cfg.refs ? "block" : "none";
  $("followBox").style.display = cfg.refs ? "flex" : "none";
  $("prompt").placeholder = cfg.ph;
  if (!$("go").classList.contains("busy")) $("go").textContent = cfg.label;
  $("ableitenZeile").style.display = cfg.refs ? "block" : "none";
  $("uploadHint").textContent = mode === "gruppe" ? (aktion().hint || "")
                                : (cfg.hint ? cfg.hint(maxRefs) : "");
  if (cfg.sweep !== undefined) $("sweep").value = cfg.sweep;
  if (cfg.count !== undefined) $("count").value = cfg.count;
  if (cfg.follow !== undefined) $("follow").checked = cfg.follow;
  if (cfg.lock !== undefined) $("lockSeed").checked = cfg.lock;
  sweepChanged();

  const tpl = templates[next];
  const istDemo = next === "demo";
  const istBausteine = next === "bausteine";
  const istSzenen = next === "szenen";
  const istGeschichte = next === "geschichte";
  if (istGeschichte) gsHolen();
  const istKatalog = next === "katalog";
  $("katalogBox").style.display = istKatalog ? "block" : "none";
  if (istKatalog) katalogHolen();
  $("szenenBox").style.display = istSzenen ? "block" : "none";
  $("geschichteBox").style.display = istGeschichte ? "block" : "none";
  // Beide Reiter haben eine eigene Bedienung und brauchen die ueblichen
  // Kaesten nicht -- Prompt, Darstellung, Bildgroesse.
  const eigen = istDemo || istBausteine || istSzenen || istGeschichte || istKatalog;
  $("demoBox").style.display = istDemo ? "block" : "none";
  $("bausteinBox").style.display = istBausteine ? "block" : "none";
  // Im Ablauf-Reiter ist das Prompt-Feld ausgeblendet -- dort waere das
  // Ableiten wirkungslos. Der Reiter hat dafuer seine eigene Zeile.
  document.querySelectorAll(".ableiten").forEach(
    el => { el.style.display = eigen ? "none" : "block"; });
  ["boxVorlage", "boxDarstellung", "boxBild", "boxFein", "uploadBox"].forEach(
    id => { if (eigen) $(id).style.display = "none"; });
  $("prompt").parentElement.querySelectorAll("#prompt, #transNote, #tplHint")
    .forEach(el => { el.style.display = eigen ? "none" : ""; });
  document.querySelectorAll("label[for=prompt]").forEach(
    el => el.style.display = eigen ? "none" : "");
  if (!eigen) { $("boxVorlage").style.display = ""; $("boxDarstellung").style.display = "";
                $("boxBild").style.display = ""; $("boxFein").style.display = ""; }
  demoDauer();
  const istVarianten = next === "varianten";
  $("gruppeBox").style.display = next === "gruppe" ? "block" : "none";
  groupSizeSichtbar();
  paintPreview();
  $("variantenBox").style.display = istVarianten ? "block" : "none";
  // Licht und Stil steuern im Varianten-Modus die Achsen, nicht diese Regler.
  [["light", "Licht"], ["style", "Stil"]].forEach(([id, wort]) => {
    $(id).disabled = istVarianten;
    $(id).title = istVarianten
      ? `Im Varianten-Modus zählt die ${wort}-Achse weiter unten` : "";
  });
  $("tplHint").style.display = tpl && next !== "varianten" ? "block" : "none";
  if (tpl) $("tplHint").textContent = "Der Server setzt automatisch davor: „"
    + tpl.replace("{extra}", "…").replace("{n}", refs.length || "N") + "“";
  drawThumbs();
}
Object.keys(MODES).forEach(m => $("tab-" + m).onclick = () => {
  // Ein Effekt, der ein Bild braucht, passt nicht zu Text -> Bild.
  const e = EFFECTS.find(x => x.key === $("effect").value);
  if (m === "t2i" && e && e.needs_image) $("effect").value = "";
  setMode(m);
});

// Effekte und Vorlagen bringen Einstellungen mit. Die werden sichtbar in die
// Regler geschrieben, damit nichts unsichtbar im Hintergrund passiert.
function applyOverrides(o) {
  ["aspect", "style", "light", "camera", "view", "sweep"].forEach(k => {
    if (o[k] !== undefined) $(k).value = o[k];
  });
  if (o.transparent !== undefined) $("transparent").checked = !!o.transparent;
  if (o.lock_seed !== undefined) $("lockSeed").checked = !!o.lock_seed;
  if (o.count !== undefined) $("count").value = o.count;
  // Hochskalieren bringt eine groessere Kantenlaenge mit -- der Regler muss
  // sie zeigen, sonst waere nicht zu sehen, warum es laenger dauert.
  if (o.base !== undefined) $("base").value = o.base;
  refresh();
}
$("effect").onchange = () => {
  const e = EFFECTS.find(x => x.key === $("effect").value);
  if (!e) return;
  if (e.mode) setMode(e.mode);
  else if (e.needs_image && mode === "t2i") setMode("edit");
  applyOverrides(e);
};
$("form").onchange = () => {
  const f = FORMS.find(x => x.key === $("form").value);
  if (f) applyOverrides(f);
};

// Die gewählte Gruppen-Aktion bestimmt, wie viele Bilder nötig sind.
function aktion() {
  return ACTIONS.find(a => a.key === $("action").value) || {min: 2, hint: ""};
}
$("action").addEventListener("change", () => { setMode(mode); refresh(); });
function groupSizeSichtbar() {
  $("groupSizeBox").style.display = $("action").value === "ergaenzen" ? "block" : "none";
}

// ---------- Referenzbilder ----------
$("file").onchange = e => {
  const files = [...e.target.files].slice(0, maxRefs - refs.length);
  let pending = files.length;
  files.forEach(f => {
    const reader = new FileReader();
    reader.onload = () => {
      refs.push(reader.result); refPrompts.push("");
      if (!--pending) { drawThumbs(); setMode(mode); }
    };
    reader.readAsDataURL(f);
  });
  e.target.value = "";
};
function drawThumbs() {
  const kachel = (src, i) =>
    `<div class="thumb"><img src="${src}" alt="Referenz ${i + 1}"><i>${i + 1}</i>`
    + `<b onclick="dropRef(${i})">×</b></div>`;
  const rollen = mode === "gruppe";
  $("thumbs").className = "thumbs" + (rollen ? " rollen" : "");
  $("thumbs").innerHTML = rollen
    ? refs.map((src, i) =>
        `<div class="refrow">${kachel(src, i)}`
        + `<input class="refprompt" data-i="${i}" value="${esc(refPrompts[i] || "")}"`
        + ` placeholder="Wie soll Bild ${i + 1} dargestellt werden? (optional)"></div>`).join("")
    : refs.map(kachel).join("");
  [...document.querySelectorAll(".refprompt")].forEach(el =>
    el.addEventListener("input", () => { refPrompts[el.dataset.i] = el.value; }));
  $("refCount").textContent = refs.length ? `(${refs.length}/${maxRefs})` : "";
  refresh();
}
function dropRef(i) { refs.splice(i, 1); refPrompts.splice(i, 1); drawThumbs(); setMode(mode); }

// ---------- Ablauf ----------
let demoRef = null, ABLAEUFE = [], bloecke = [];

function blockZeichnen() {
  $("bloecke").innerHTML = bloecke.map((b, i) => `
    <div class="block" data-i="${i}">
      <div class="blockkopf">
        <input class="btitel" value="${esc(b.titel || "")}" placeholder="Name des Blocks">
        <a href="#" data-tu="hoch" title="nach oben">&uarr;</a>
        <a href="#" data-tu="runter" title="nach unten">&darr;</a>
        <a href="#" data-tu="weg" title="entfernen">&times;</a>
      </div>
      <div class="row4">
        <input type="number" class="banzahl" min="0" max="40" placeholder="Anzahl"
               title="Wie viele Bilder? Leer = eine je Zeile"
               ${b.art === "gruppe" ? "disabled" : ""}
               value="${b.art === "gruppe" ? "1" : (b.anzahl || "")}">
        <select class="bref">
          <option value="start"${b.referenz !== "letztes" ? " selected" : ""}>vom Startbild</option>
          <option value="letztes"${b.referenz === "letztes" ? " selected" : ""}>vom letzten Bild</option>
        </select>
        <select class="bart">
          <option value="behutsam"${b.art !== "gruppe" && b.vorlage !== "verwandeln" ? " selected" : ""}>behutsam ändern</option>
          <option value="verwandeln"${b.vorlage === "verwandeln" ? " selected" : ""}>verwandeln</option>
          <option value="aktion"${b.vorlage === "aktion" ? " selected" : ""}>Bewegung</option>
          <option value="gruppe"${b.art === "gruppe" ? " selected" : ""}>Gruppenbild</option>
        </select>
        <select class="bseed">
          <option value=""${!b.fest ? " selected" : ""}>eigener Seed</option>
          <option value="1"${b.fest ? " selected" : ""}>Seed wie Start</option>
        </select>
      </div>
      <label>Was bleibt unverändert?</label>
      <input class="bbleibt" value="${esc(b.bleibt || "")}" placeholder="z. B. die Person, ihr Gesicht und ihre Haltung">
      <label>Ein Bild je Zeile &ndash; oder oben eine Anzahl angeben</label>
      <textarea class="bbausteine"${b.art === "gruppe" ? " disabled" : ""}>${esc((b.bausteine || []).join("\n"))}</textarea>
      <div class="check">
        <input type="checkbox" class="bzurueck"${b.zurueck ? " checked" : ""}>
        <label>danach wieder das Startbild zeigen</label>
      </div>
    </div>`).join("");

  $("bloecke").querySelectorAll(".block").forEach(el => {
    const i = +el.dataset.i;
    el.querySelector(".btitel").oninput = e => bloecke[i].titel = e.target.value;
    el.querySelector(".bbleibt").oninput = e => bloecke[i].bleibt = e.target.value;
    el.querySelector(".bbausteine").oninput = e => {
      bloecke[i].bausteine = e.target.value.split("\n").filter(z => z.trim());
      demoDauer();
    };
    el.querySelector(".banzahl").oninput = e => {
      const n = parseInt(e.target.value, 10);
      bloecke[i].anzahl = Number.isFinite(n) && n > 0 ? n : undefined;
      demoDauer();
    };
    el.querySelector(".bref").onchange = e => bloecke[i].referenz = e.target.value;
    el.querySelector(".bseed").onchange = e => bloecke[i].fest = !!e.target.value;
    el.querySelector(".bzurueck").onchange = e => { bloecke[i].zurueck = e.target.checked; demoDauer(); };
    el.querySelector(".bart").onchange = e => {
      const w = e.target.value;
      bloecke[i].art = w === "gruppe" ? "gruppe" : undefined;
      bloecke[i].vorlage = w === "gruppe" ? undefined : w;
      // Ein Gruppenbild ist immer genau ein Bild; eine Anzahl daneben wuerde
      // nur eine Erwartung wecken, die der Server nicht einloest.
      if (w === "gruppe") { bloecke[i].bausteine = [""]; bloecke[i].anzahl = undefined; }
      blockZeichnen(); demoDauer();
    };
    el.querySelectorAll("[data-tu]").forEach(a => a.onclick = ev => {
      ev.preventDefault();
      const tu = a.dataset.tu;
      if (tu === "weg") bloecke.splice(i, 1);
      else {
        const j = tu === "hoch" ? i - 1 : i + 1;
        if (j < 0 || j >= bloecke.length) return;
        [bloecke[i], bloecke[j]] = [bloecke[j], bloecke[i]];
      }
      blockZeichnen(); demoDauer();
    });
  });
}

$("blockNeu").onclick = e => {
  e.preventDefault();
  bloecke.push({titel: "Neuer Block", referenz: "start", vorlage: "verwandeln",
                bleibt: "die Person, ihr Gesicht und ihre Haltung", bausteine: [], zurueck: false});
  blockZeichnen(); demoDauer();
};
$("alsText").onclick = e => {
  e.preventDefault();
  const t = $("ablaufText");
  if (t.style.display === "none") {
    t.value = JSON.stringify(bloecke, null, 1); t.style.display = "block";
  } else {
    try { bloecke = JSON.parse(t.value); blockZeichnen(); demoDauer(); } catch (x) {
      return say("Der Text ist kein gültiges JSON: " + x.message, "err");
    }
    t.style.display = "none";
  }
};
$("ablaufWahl").onchange = () => {
  const a = ABLAEUFE.find(x => x.key === $("ablaufWahl").value);
  if (!a) return;
  bloecke = JSON.parse(JSON.stringify(a.bloecke));
  $("ablaufInfo").textContent = a.label;
  blockZeichnen(); demoDauer();
};
$("demoFile").onchange = e => {
  const f = e.target.files[0];
  if (!f) return;
  const leser = new FileReader();
  leser.onload = () => {
    demoRef = leser.result;
    $("demoPreview").src = demoRef; $("demoPreview").style.display = "block";
    $("demoRefNote").textContent = "Dein Foto wird als Basisbild verwendet. "
      + "Der Text unten beschreibt dann, wer darauf zu sehen ist.";
    $("demoPrompt").disabled = false;
    $("demoPromptLabel").textContent =
      "…kurz beschreiben, wer auf dem Bild ist (leer lassen: der Server liest es selbst)";
    $("demoPrompt").placeholder =
      "z. B. eine Frau Mitte dreißig mit kurzen blonden Haaren, dunkler Jacke";
    $("demoAbleitenZeile").style.display = "block";
    // Gleich beschreiben lassen, statt es erst beim Start zu tun: so steht
    // der Text vor dem Lauf da und laesst sich noch aendern.
    if (!$("demoPrompt").value.trim()) demoBeschreiben();
  };
  leser.readAsDataURL(f);
};
function demoDauer() {
  const n = parseInt($("demoSteps").value, 10) || 24;
  // Dieselbe Regel wie im Server: Anzahl schlaegt die Zahl der Zeilen.
  const proBlock = b => {
    const zeilen = (b.bausteine || []).length;
    if (b.art === "gruppe") return Math.min(zeilen, 1);
    return b.anzahl > 0 && zeilen ? b.anzahl : zeilen;
  };
  const erzeugt = 1 + bloecke.reduce((s, b) => s + proBlock(b), 0);
  const imVideo = erzeugt + bloecke.filter(b => b.zurueck).length;
  // Ein Ladevorgang je Block, der nicht vom Startbild ausgeht, plus einer.
  const laden = 2 + bloecke.filter(b => b.referenz === "letztes" || b.art === "gruppe").length;
  const minuten = Math.round((laden * 60 + erzeugt * (n * 1.5 + 3)) / 60);
  $("demoDauer").textContent = `${erzeugt} Bilder erzeugen, ${imVideo} im Video, `
    + `grob ${minuten} Minuten. Solange ist die Grafikkarte belegt.`;
}
["demoSteps", "demoBase", "demoDuration"].forEach(id => $(id).addEventListener("input", demoDauer));

async function starteDemo() {
  const laeuftSchon = $("go").classList.contains("busy");
  buttonState("busy");
  if (!laeuftSchon) $("stage").dataset.file = "";
  say(laeuftSchon ? "Ablauf wird eingereiht …" : "Vorführung wird vorbereitet …");
  const res = await fetch("/api/demo", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      image: demoRef, prompt: $("demoPrompt").value, bloecke,
      base: parseInt($("demoBase").value, 10),
      steps: parseInt($("demoSteps").value, 10) || 24,
      duration: parseInt($("demoDuration").value, 10) || 20
    })
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    buttonState("idle");
    return say(err.error || "Die Vorführung ließ sich nicht starten.", "err");
  }
  // Der Auftrag laeuft ab hier auf dem Server. Was beim Vorzeichnen
  // schiefgeht, darf die Fortschrittsabfrage nicht mitreissen -- sonst
  // bliebe der Knopf fuer immer auf "laeuft".
  try {
    if (!laeuftSchon) startSlots(1 + bloecke.reduce((s, b) => {
      const zeilen = (b.bausteine || []).length;
      if (b.art === "gruppe") return s + Math.min(zeilen, 1);
      return s + (b.anzahl > 0 && zeilen ? b.anzahl : zeilen);
    }, 0));
  } catch (e) {
    console.error(e);
  }
  poll();
}

// ---------- Start ----------
function say(text, cls = "") { $("status").textContent = text; $("status").className = cls; }

// Der Knopf zeigt den Zustand mit: gelb waehrend der Berechnung, kurz gruen
// wenn fertig, danach wieder normal.
function buttonState(state) {
  const go = $("go");
  go.classList.remove("busy", "done", "ready");
  clearTimeout(buttonState.timer);
  if (state === "busy") {
    // Nicht gesperrt: waehrend etwas rechnet, haengt ein Klick den naechsten
    // Auftrag hinten an. Sonst brauchte man die Warteschlange gar nicht.
    go.disabled = false; go.classList.add("busy");
    go.textContent = "läuft — noch einen einreihen";
    $("stop").style.display = "block";
  } else {
    go.disabled = false; go.textContent = MODES[mode].label;
    $("stop").style.display = "none";
    if (state === "done") {
      go.classList.add("done");
      buttonState.timer = setTimeout(() => go.classList.remove("done"), 2500);
    }
  }
}

async function start() {
  const prompt = $("prompt").value.trim();
  const need = mode === "gruppe" ? aktion().min : MODES[mode].refs;
  // Ein Effekt bringt seine eigene Anweisung mit -- /upscale, /removebg und
  // die uebrigen brauchen kein Wort Eingabe. Der Server sieht das genauso.
  if (!prompt && !templates[mode] && !$("effect").value)
    return say("Bitte einen Prompt eingeben.", "err");
  if (refs.length < need) return say(`Bitte ${need} Referenzbild(er) hochladen.`, "err");
  if (mode === "varianten" && $("paint").value !== AXIS_OFF && !$("paintTarget").value.trim()) {
    paintPreview();
    return say("Die Farbachse braucht ein Ziel — oder stell sie auf „unverändert lassen“.", "err");
  }

  let seed = parseInt($("seed").value, 10);
  if (isNaN(seed) || seed < 0) { seed = Math.floor(Math.random() * 2 ** 31); $("seed").value = seed; }

  const body = {
    mode, prompt, negative_prompt: $("negative").value,
    images: need ? refs : [],
    image_prompts: mode === "gruppe" ? refs.map((_, i) => refPrompts[i] || "") : [],
    aspect: $("aspect").value, base: parseInt($("base").value, 10),
    follow_reference: $("follow").checked,
    steps: parseInt($("steps").value, 10),
    seed, count: parseInt($("count").value, 10) || 1,
    sweep: $("sweep").value, lock_seed: $("lockSeed").checked,
    view: $("view").value, effect: $("effect").value, form: $("form").value,
    keep: $("keep").value, action: $("action").value, scenario: $("scenario").value,
    group_size: parseInt($("groupSize").value, 10) || 2,
    paint: $("paint").value, palette: $("palette").value,
    scene: $("scene").value,
    angle: $("angle").value, device: $("device").value,
    material: $("material").value, subject: $("subject").value,
    haltung: $("haltung").value, kleidung: $("kleidung").value,
    camera: $("camera").value,
    // In den Varianten haben Stil und Licht eigene Achsenfelder, damit sich
    // beide auf "wuerfeln" stellen lassen.
    style: mode === "varianten" ? $("vstyle").value : $("style").value,
    light: mode === "varianten" ? $("vlight").value : $("light").value,
    paint_target: $("paintTarget").value,
    true_cfg_scale: parseFloat($("cfg").value),
    transparent: $("transparent").checked,
    streng: $("streng").checked
  };

  const laeuftSchon = $("go").classList.contains("busy");
  buttonState("busy");
  $("transNote").style.display = "none";
  say(laeuftSchon ? "Wird eingereiht …" : "Auftrag wird gestartet …");
  // Nur wenn nichts laeuft, das Mosaik leeren -- sonst verschwaende man die
  // Anzeige des Auftrags, der gerade rechnet.
  if (!laeuftSchon) { $("stage").dataset.file = ""; paintSeries([], body.count, 1); }

  // Bricht die Verbindung weg, muss der Knopf zurueckspringen -- sonst
  // steht er fuer immer auf "laeuft", ohne dass etwas rechnet.
  const res = await fetch("/api/generate", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
  }).catch(() => null);
  if (!res) {
    buttonState("idle");
    return say("Der Server ist nicht erreichbar.", "err");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({error: res.statusText}));
    buttonState("idle");
    return say(err.error, "err");
  }
  poll();
}
$("go").onclick = () => (mode === "demo" ? starteDemo() : start());
$("stop").onclick = () => {
  // Nur den laufenden Auftrag. Wartende nimmt man einzeln aus der Liste.
  fetch("/api/cancel", {method: "POST"});
  say("Abbruch des laufenden Auftrags angefordert …");
};

// ---------- Freitexteingabe ----------
// Der Server liefert einen fertigen Satz Einstellungen. Die werden sichtbar in
// die Regler geschrieben, bevor es losgeht -- so ist nachvollziehbar, was das
// Sprachmodell verstanden hat, und korrigierbar, wenn es danebenlag.
function applyPlan(plan) {
  setMode(plan.mode);
  $("prompt").value = plan.prompt || "";
  ["aspect", "style", "light", "camera", "view", "sweep", "effect", "form"].forEach(
    k => { if (plan[k] !== undefined) $(k).value = plan[k]; });
  $("base").value = plan.base;
  $("count").value = plan.count;
  $("steps").value = plan.steps;
  $("transparent").checked = !!plan.transparent;
  $("lockSeed").checked = !!plan.lock_seed;
  refresh();
}

async function sendChat() {
  const text = $("chat").value.trim();
  if (!text) return;
  $("chatGo").disabled = true;
  $("chatNote").className = "hint";
  $("chatNote").textContent = "verstehe …";

  const res = await fetch("/api/chat", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({text, has_images: refs.length})
  }).catch(() => null);
  $("chatGo").disabled = false;

  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    $("chatNote").className = "hint err";
    $("chatNote").textContent = err.error || "Das Sprachmodell antwortet nicht.";
    return;
  }
  const plan = await res.json();
  applyPlan(plan);
  zeigeGespraech(plan.verlauf);
  $("chatNote").textContent = (plan.note || "Verstanden.")
    + ` Einstellungen unten prüfen, dann auf „${MODES[mode].label}“.`;
  $("chat").value = "";
  // Bewusst kein Start: erst Text, dann Prompt, dann prüfen, dann Bild.
  $("go").classList.add("ready");
  setTimeout(() => $("go").classList.remove("ready"), 6000);
}
$("chatGo").onclick = sendChat;

// Der Verlauf steht beim Server; hier wird nur gezeigt, was war. So ist
// nachvollziehbar, worauf sich ein "und jetzt noch einen Hut dazu" bezieht.
function zeigeGespraech(verlauf) {
  if (!Array.isArray(verlauf) || !verlauf.length) {
    $("chatLog").innerHTML = "";
    return;
  }
  $("chatLog").innerHTML = verlauf.map(z => {
    if (z.wer === "user") {
      return `<div class="zug ich"><b>du</b>${esc(z.was)}</div>`;
    }
    let notiz = z.was;
    try { notiz = JSON.parse(z.was).note || z.was; } catch (e) { /* roh zeigen */ }
    return `<div class="zug"><b>verstanden</b>${esc(notiz)}</div>`;
  }).join("")
    + `<p class="hint"><a href="#" onclick="gespraechNeu();return false">`
    + `neu anfangen</a> — vergisst das Bisherige.</p>`;
}

async function gespraechNeu() {
  await fetch("/api/chat", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({neu: true})
  }).catch(() => null);
  $("chatLog").innerHTML = "";
  say("Gespräch zurückgesetzt.", "ok");
}
$("beenden").onclick = e => { e.preventDefault(); programmBeenden(); };
$("ableiten").onclick = e => { e.preventDefault(); promptAusBild(); };
$("ableitenBild").onchange = e => {
  const f = e.target.files[0];
  if (!f) return;
  const leser = new FileReader();
  leser.onload = () => promptAusBild(leser.result);
  leser.readAsDataURL(f);
};
$("demoAbleiten").onclick = e => { e.preventDefault(); demoBeschreiben(); };

// Im Ablauf beschreibt der Text, wen das Modell bewahren soll -- dafuer
// genuegt der kurze Halbsatz, nicht der ganze Bildprompt.
async function demoBeschreiben() {
  if (!demoRef) return say("Erst ein Startbild wählen.", "err");
  say("Das Startbild wird gelesen …");
  const g = await bildLesen("/api/bild-lesen", demoRef);
  if (!g || !g.beschreibung) return;
  $("demoPrompt").value = g.beschreibung;
  $("demoRefNote").textContent = "Im Startbild erkannt: " + g.beschreibung
    + (g.geschlecht !== "unklar" ? ` (${g.geschlecht})` : "");
  say("Beschreibung aus dem Startbild übernommen. Unten änderbar.", "ok");
}

// Rueckwaerts: das hochgeladene Bild ansehen und den Prompt dazu schreiben.
// Lesen darf nur das Sprachmodell, deshalb geht es nicht waehrend eines
// Auftrags -- beide wollen dieselbe Grafikkarte.
// Das Bild einmal ansehen lassen. `pfad` unterscheidet die kurze Fassung
// (wer ist zu sehen) von der langen (der ganze Bildprompt).
async function bildLesen(pfad, bild) {
  const res = await fetch(pfad, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({image: bild})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    say(err.error || "Das Bild ließ sich nicht lesen.", "err");
    return null;
  }
  return res.json();
}

// Der umgekehrte Weg: aus einem Bild den Prompt. Ohne Angabe wird das erste
// Referenzbild genommen, damit man es nicht zweimal hochladen muss.
async function promptAusBild(bild) {
  bild = bild || refs[0];
  if (!bild) return say("Erst ein Bild wählen.", "err");
  say("Das Bild wird gelesen …");
  const g = await bildLesen("/api/bild-prompt", bild);
  if (!g) return;
  $("prompt").value = g.prompt;
  if (g.stil) $("style").value = g.stil;
  if (g.licht) $("light").value = g.licht;
  if (g.kamera) $("camera").value = g.kamera;
  const gesetzt = [["Stil", g.stil], ["Licht", g.licht], ["Objektiv", g.kamera]]
    .filter(x => x[1]).map(x => x[0]).join(", ");
  say("Prompt aus dem Bild abgeleitet"
      + (gesetzt ? ` — ${gesetzt} mitgestellt.` : ".") + " Bitte gegenlesen.", "ok");
}
// Mehrzeilig: Eingabe macht einen Umbruch, abgeschickt wird mit Strg+Eingabe
// oder dem Pfeil daneben.
$("chat").addEventListener("keydown", e => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); sendChat(); }
});

// ---------- Bausteine ----------
// Personen, Orte und Gegenstaende zum Wiederverwenden. Was sich aendern darf,
// steht als Luecke in geschweiften Klammern und wird beim Benutzen gefuellt.
let BAUSTEINE = [], BSARTEN = [], MIMIKLISTE = [], STILLISTE = [],
    EINSTELLUNGEN = [], GEZEICHNET = [];
const LUECKE = /\{([a-zA-Z][a-zA-Z0-9_]{0,29})\}/g;

function luecken(text) {
  return [...new Set([...(text || "").matchAll(LUECKE)].map(m => m[1]))];
}

function zeigeBausteine(liste) {
  if (!Array.isArray(liste)) return;
  BAUSTEINE = liste;
  const label = k => (BSARTEN.find(a => a.key === k) || {}).label || k;
  $("bausteinListe").innerHTML = liste.length
    ? liste.map(b => `<div class="baustein">
        ${b.bild ? `<img src="/outputs/${b.bild}" alt="${esc(b.name)}"
             onclick="show('${b.bild}')">` : `<span class="ohnebild">?</span>`}
        <div class="bstext"><b>${esc(b.name)}</b>
          <span class="art">${esc(label(b.art))}</span><br>
          <code>${esc(b.prompt)}</code></div>
        <span class="knopf" onclick="bausteinLaden('${b.id}')" title="bearbeiten">✎</span>
        <span class="knopf" onclick="bausteinWeg('${b.id}')" title="löschen">×</span>
      </div>`).join("")
    : `<p class="hint">Noch keine Bausteine in diesem Projekt.</p>`;
  zeigeWahl();
  zeigeSelbstszenen();
}

// Zu jeder Luecke ein Feld. `mehrzeilig` erlaubt eine Werteliste -- daraus
// wird spaeter eine Serie mit einem Bild je Zeile.
function luckenFelder(wohin, text, vorgaben, mehrzeilig) {
  const namen = luecken(text);
  $(wohin).innerHTML = namen.map(n => `
    <label for="${wohin}-${n}">${esc(n)}</label>
    ${mehrzeilig
      ? `<textarea id="${wohin}-${n}" class="lueckenfeld" data-l="${n}"
           style="min-height:40px">${esc((vorgaben || {})[n] || "")}</textarea>
         <p class="hint"><a href="#" onclick="luckenVorschlaege('${n}');return false">
           10 Vorschläge</a> — eine Zeile je Bild.</p>`
      : `<input id="${wohin}-${n}" class="lueckenfeld" data-l="${n}"
           value="${esc((vorgaben || {})[n] || "")}">`}`).join("");
  return namen;
}

function lueckenWerte(wohin) {
  const werte = {};
  $(wohin).querySelectorAll(".lueckenfeld").forEach(
    el => werte[el.dataset.l] = el.value);
  return werte;
}

async function bausteinRuf(rumpf) {
  const res = await fetch("/api/baustein", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(rumpf)
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    say(err.error || "Das hat nicht geklappt.", "err");
    return null;
  }
  return res.json();
}

async function bausteineHolen() {
  const info = await fetch("/api/info").then(r => r.json()).catch(() => null);
  if (info) zeigeBausteine(info.bausteine);
}

$("bsErzeugen").onclick = async e => {
  e.preventDefault();
  const text = $("bsText").value.trim();
  if (!text) return say("Erst auf Deutsch beschreiben.", "err");
  say("Der Prompt wird geschrieben …");
  const g = await bausteinRuf({tu: "prompt", text, art: $("bsArt").value});
  if (!g) return;
  $("bsPrompt").value = g.prompt;
  $("bsGesicht").value = g.gesicht || "";
  $("bsKleidung").value = g.kleidung || "";
  luckenFelder("bsVariablen", g.prompt, g.variablen, false);
  say(`Prompt erzeugt, ${luecken(g.prompt).length} Lücke(n). Bitte gegenlesen.`, "ok");
};

// Gesicht und Kleidung einzeln schreiben lassen. Beide Felder entstehen
// schon beim "Prompt daraus erzeugen" mit -- das hier ist fuer danach: eine
// Kleidung, die man auf Deutsch hineingetippt hat, kommt englisch zurueck.
async function teilSchreiben(feld, id) {
  const eigen = $(id).value.trim();
  const text = eigen || $("bsText").value.trim();
  if (!text) return say("Erst beschreiben — im Feld oder oben auf Deutsch.", "err");
  say("Der Prompt wird geschrieben …");
  const g = await bausteinRuf({tu: "teilprompt", feld, text,
                               person: $("bsPrompt").value});
  if (!g) return;
  $(id).value = g.text;
  say("Geschrieben. Bitte gegenlesen.", "ok");
}

$("bsGesichtNeu").onclick = e => {
  e.preventDefault();
  teilSchreiben("gesicht", "bsGesicht");
};

$("bsKleidungNeu").onclick = e => {
  e.preventDefault();
  teilSchreiben("kleidung", "bsKleidung");
};

$("bsPrompt").addEventListener("input", () => {
  luckenFelder("bsVariablen", $("bsPrompt").value, lueckenWerte("bsVariablen"), false);
});

function bausteinAusFeldern() {
  return {id: $("bsPrompt").dataset.id || "", art: $("bsArt").value,
          name: $("bsName").value, prompt: $("bsPrompt").value,
          gesicht: $("bsGesicht").value, kleidung: $("bsKleidung").value,
          variablen: lueckenWerte("bsVariablen")};
}

// Gesicht und Kleidung gibt es nur bei Personen. Ein Ort hat kein Gesicht,
// und ein leeres Feld, das nie etwas tut, verwirrt nur.
function personFelder() {
  $("bsPersonBox").style.display =
    $("bsArt").value === "person" ? "block" : "none";
}
$("bsArt").addEventListener("change", personFelder);

$("bsSpeichern").onclick = async e => {
  e.preventDefault();
  if (!$("bsPrompt").value.trim()) return say("Kein Prompt.", "err");
  const b = await bausteinRuf({tu: "speichern", baustein: bausteinAusFeldern()});
  if (!b) return;
  await bausteineHolen();
  say(`„${b.name}“ gespeichert.`, "ok");
  bausteinLeeren();
};

$("bsBild").onclick = async e => {
  e.preventDefault();
  if (!$("bsPrompt").value.trim()) return say("Kein Prompt.", "err");
  const b = await bausteinRuf({tu: "speichern", baustein: bausteinAusFeldern()});
  if (!b) return;
  await bausteineHolen();
  // Mit den Vorgaben gefuellt -- das Bild soll den Baustein zeigen, wie er
  // gemeint ist, nicht mit offenen Luecken.
  const g = await bausteinRuf({tu: "zusammensetzen", ids: [b.id],
                               werte: b.variablen, freistellen: true});
  if (!g) return;
  await einreihenEinfach({prompt: g.prompt, baustein: b.id, aspect: "3:4"});
  // Aufraeumen nicht vergessen: bleibt die Kennung stehen, ueberschreibt der
  // naechste Baustein diesen hier. Genau das ist passiert.
  bausteinLeeren();
  say(`„${b.name}“ gespeichert, Bild dazu eingereiht.`, "ok");
};

$("bsLeeren").onclick = e => { e.preventDefault(); bausteinLeeren(); };

function bausteinLeeren() {
  ["bsName", "bsText", "bsPrompt", "bsGesicht", "bsKleidung"]
    .forEach(id => $(id).value = "");
  personFelder();
  $("bsPrompt").dataset.id = "";
  $("bsVariablen").innerHTML = "";
  bausteinKopf();
}

// Ob gerade ein neuer Baustein entsteht oder ein vorhandener geaendert wird,
// muss man sehen koennen -- sonst ueberschreibt man aus Versehen.
function bausteinKopf() {
  const id = $("bsPrompt").dataset.id;
  const b = id && BAUSTEINE.find(x => x.id === id);
  $("bsKopf").innerHTML = b
    ? `Ändert „${esc(b.name)}“ <a href="#" onclick="bausteinLeeren();return false"
         style="font-size:11.5px">stattdessen neu anlegen</a>`
    : "Neu anlegen";
}

function bausteinLaden(id) {
  const b = BAUSTEINE.find(x => x.id === id);
  if (!b) return;
  $("bsArt").value = b.art;
  $("bsName").value = b.name;
  $("bsPrompt").value = b.prompt;
  $("bsGesicht").value = b.gesicht || "";
  $("bsKleidung").value = b.kleidung || "";
  $("bsPrompt").dataset.id = b.id;
  personFelder();
  luckenFelder("bsVariablen", b.prompt, b.variablen, false);
  bausteinKopf();
  say(`„${b.name}“ geladen. Ändern und speichern.`);
}

async function bausteinWeg(id) {
  const b = BAUSTEINE.find(x => x.id === id);
  if (!confirm(`„${b ? b.name : id}“ löschen?`)) return;
  if (!await bausteinRuf({tu: "loeschen", id})) return;
  await bausteineHolen();
  say("Baustein gelöscht.", "ok");
}

// --- Zusammensetzen ---
function zeigeWahl() {
  $("bsWahl").innerHTML = BAUSTEINE.length
    ? BAUSTEINE.map(b => `<label class="wahl"><input type="checkbox"
        class="bswahl" value="${b.id}"> ${esc(b.name)}</label>`).join("")
    : "";
  $("bsWahl").querySelectorAll(".bswahl").forEach(
    el => el.onchange = wahlGeaendert);
  wahlGeaendert();
}

function gewaehlte() {
  const ids = [...$("bsWahl").querySelectorAll(".bswahl:checked")].map(el => el.value);
  return BAUSTEINE.filter(b => ids.includes(b.id));
}

function wahlGeaendert() {
  const teile = gewaehlte();
  const text = teile.map(b => b.prompt).join(" ");
  const vorgaben = {};
  teile.forEach(b => Object.assign(vorgaben, b.variablen || {}));
  luckenFelder("bsFelder", text, {...vorgaben, ...lueckenWerte("bsFelder")}, true);
  $("bsFelder").querySelectorAll(".lueckenfeld").forEach(
    el => el.addEventListener("input", vorschau));
  vorschau();
}

// Eine Luecke mit mehreren Zeilen ergibt eine Serie: ein Bild je Zeile.
function serienWerte() {
  const werte = lueckenWerte("bsFelder");
  let laenge = 1;
  Object.values(werte).forEach(v => {
    const zeilen = String(v).split("\n").filter(z => z.trim());
    if (zeilen.length > laenge) laenge = zeilen.length;
  });
  const reihe = [];
  for (let i = 0; i < laenge; i++) {
    const eins = {};
    Object.entries(werte).forEach(([k, v]) => {
      const zeilen = String(v).split("\n").filter(z => z.trim());
      eins[k] = zeilen.length ? zeilen[Math.min(i, zeilen.length - 1)].trim() : "";
    });
    reihe.push(eins);
  }
  return reihe;
}

// Zehn verschiedene Hosen fuer die Luecke {hose}: das Sprachmodell kennt
// den Satz, in dem sie steht, und schlaegt Passendes vor.
async function luckenVorschlaege(name) {
  const teile = gewaehlte();
  const umfeld = teile.map(b => b.prompt).join(" ");
  say(`Vorschläge für „${name}“ …`);
  const g = await bausteinRuf({tu: "vorschlaege", luecke: name,
                               umfeld, anzahl: 10});
  if (!g) return;
  const feld = $("bsFelder-" + name);
  if (feld) {
    feld.value = g.werte.join("\n");
    feld.dispatchEvent(new Event("input"));
  }
  say(`${g.werte.length} Vorschläge eingesetzt — Zeilen ändern oder löschen.`, "ok");
}

async function vorschau() {
  const teile = gewaehlte();
  if (!teile.length) { $("bsVorschau").value = ""; return; }
  const reihe = serienWerte();
  const g = await bausteinRuf({tu: "zusammensetzen",
                               ids: teile.map(b => b.id), werte: reihe[0]});
  if (!g) return;
  // Den reinen Prompt getrennt aufheben -- ihn spaeter aus der Anzeige
  // zurueckzuschneiden waere bruechig.
  $("bsVorschau").dataset.prompt = g.prompt;
  $("bsVorschau").value = reihe.length > 1
    ? `${g.prompt}\n\n… und ${reihe.length - 1} weitere daraus`
    : g.prompt;
}

$("bsUebernehmen").onclick = e => {
  e.preventDefault();
  const text = $("bsVorschau").dataset.prompt || "";
  if (!text.trim()) return say("Erst Bausteine anhaken.", "err");
  setMode("t2i");
  $("prompt").value = text;
  say("In den Prompt übernommen.", "ok");
};

$("bsSerie").onclick = async e => {
  e.preventDefault();
  const teile = gewaehlte();
  if (!teile.length) return say("Erst Bausteine anhaken.", "err");
  const ids = teile.map(b => b.id);
  const reihe = serienWerte();
  const prompts = [];
  let vorlage = "";
  for (const werte of reihe) {
    const g = await bausteinRuf({tu: "zusammensetzen", ids, werte});
    if (!g) return;
    prompts.push(g.prompt);
    vorlage = g.vorlage;
  }
  // Die Szene behaelt ihre Luecken und die zuletzt benutzten Werte -- so
  // laesst sie sich spaeter wiederholen und weiter abwandeln.
  const name = $("szName").value.trim();
  let merken = null;
  if (name) {
    merken = await bausteinRuf({tu: "speichern", baustein: {
      art: "szene", name, prompt: vorlage, variablen: reihe[0]}});
    if (merken) await bausteineHolen();
  }
  await einreihenEinfach({
    prompt: prompts[0], prompts, aspect: $("szFormat").value,
    ...(merken ? {baustein: merken.id} : {})});
  say(`${prompts.length} Bild(er) eingereiht`
      + (merken ? `, als Szene „${name}“ gemerkt.` : "."), "ok");
};

// Einen schlichten Auftrag einreihen, ohne die Regler der anderen Reiter.
async function einreihenEinfach(zusatz) {
  const rumpf = {mode: "t2i", aspect: "3:2", base: parseInt($("base").value, 10) || 1024,
                 steps: parseInt($("steps").value, 10) || 24, count: 1,
                 seed: parseInt($("seed").value, 10) || 42, ...zusatz};
  const res = await fetch("/api/generate", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(rumpf)
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Einreihen ging nicht.", "err");
  }
  buttonState("busy");
  poll();
}

// ---------- Geschichte ----------
// Drei Schritte: umreissen, gliedern, schreiben lassen. Der Stil und die
// Frage Wirklichkeit oder Erfindung stehen ganz vorn, weil beides fuer jede
// Szene gilt -- und weil ein Modell, dem niemand sagt, dass Drachen erlaubt
// sind, die Handlung so lange zurechtbiegt, bis sie alltagstauglich wird.
let GESCHICHTE = null, gsZeilen = [{text: "", bilder: 1}], gsLetzteNr = 0;

// Die Kameraeinstellung steht als \Name in der Zeile -- aber niemand soll
// sie dort suchen muessen. Jede Szene traegt deshalb ein Auswahlfeld, das
// zeigt, was gesetzt ist, und daneben das Feld fuer die Klammer.
const EINST_MUSTER =
  /\\([A-Za-zÄÖÜäöüß0-9][\wÄÖÜäöüß-]{0,29})(?:\(([^)]{1,120})\))?/;

function einstellungBekannt(name) {
  const klein = (name || "").toLowerCase();
  return EINSTELLUNGEN.some(x => x.key === klein)
      || GEMERKTE.some(x => (x.name || "").toLowerCase() === klein);
}

// Was in dieser Zeile an Kamera steht: {key, angabe, treffer} oder null.
function einstellungInZeile(text) {
  const m = EINST_MUSTER.exec(text || "");
  if (!m || !einstellungBekannt(m[1])) return null;
  return {key: m[1].toLowerCase(), angabe: m[2] || "", treffer: m[0]};
}

function einstellungEintrag(key) {
  return EINSTELLUNGEN.find(x => x.key === key) || null;
}

// Einstellung und Klammer einer Szene neu setzen. Der Text bleibt, was er
// ist -- getauscht wird nur das \Wort.
function einstellungSchreiben(i, key, angabe) {
  const z = gsZeilen[i];
  const alt = einstellungInZeile(z.text);
  let text = alt ? z.text.replace(alt.treffer, "").replace(/\s{2,}/g, " ").trim()
                 : z.text;
  if (key) {
    const klammer = (angabe || "").trim() ? `(${angabe.trim()})` : "";
    text = (`\\${key}${klammer} ` + text).trim();
  }
  z.text = text;
  zeigeSelbstszenen();
  gsMerken();
}

function zeigeSelbstszenen() {
  $("gsSelbst").innerHTML = gsZeilen.map((z, i) => {
    const e = einstellungInZeile(z.text);
    const fest = e ? einstellungEintrag(e.key) : null;
    const luecke = fest ? fest.luecke : "";
    const wahl = [`<option value="">— ohne Kamera —</option>`]
      .concat(EINSTELLUNGEN.map(x =>
        `<option value="${x.key}"${e && e.key === x.key ? " selected" : ""}>${
          esc(x.label)}${x.paar ? " (2 Bilder)" : ""}</option>`))
      .concat(GEMERKTE.map(x =>
        `<option value="${esc(x.name)}"${
          e && e.key === (x.name || "").toLowerCase() ? " selected" : ""
        }>gemerkt: ${esc(x.name)}</option>`))
      .join("");
    return `
    <div class="selbstszene${e ? " mitkamera" : ""}">
      <div class="szkopf"><span class="nr">${i + 1}</span>
        <textarea class="gszeile" data-i="${i}" rows="2"
          placeholder="was in diesem Bild zu sehen ist">${esc(z.text)}</textarea>
      </div>
      <div class="szleiste">
        <select class="gseinst" data-i="${i}" title="Kameraeinstellung">${wahl}</select>
        ${luecke ? `<input class="gsangabe" data-i="${i}"
            placeholder="${esc(luecke === "hoehe" ? "Höhe, z. B. fünf Meter"
                                                  : "was sich spiegelt")}"
            value="${esc(e.angabe)}">` : ""}
        <span class="fuell"></span>
        <input type="number" class="gsbilder" data-i="${i}" min="1" max="20"
          title="wie viele Bilder aus dieser Szene" value="${z.bilder || 1}">
        <span class="knopf" onclick="gsSchieben(${i}, -1)" title="nach oben">▲</span>
        <span class="knopf" onclick="gsSchieben(${i}, 1)" title="nach unten">▼</span>
        <span class="knopf" onclick="gsZeileWeg(${i})" title="entfernen">×</span>
      </div>
      ${vorschlagZeile(z, i)}
    </div>`;
  }).join("")
    + (BAUSTEINE.length
        ? `<p class="hint">Bausteine: ` + BAUSTEINE.map(x =>
            `<a href="#" onclick="gsEinfuegen('/', '${esc(x.name)}');return false">/${esc(x.name)}</a>`
          ).join(" · ") + `</p>`
        : "")
    + (EINSTELLUNGEN.length
        ? `<p class="hint">Kamera: ` + EINSTELLUNGEN.map(x =>
            `<a href="#" onclick="gsEinfuegen('\\\\', '${x.key}');return false"
               title="${esc(x.label)}">\\${x.key}</a>${x.paar ? " (2 Bilder)" : ""}`
          ).join(" · ") + `</p>`
        : "")
    // Was sich einmal bewaehrt hat, steht neben den festen Einstellungen:
    // ein gemerkter Prompt wird genauso gerufen.
    + (GEMERKTE.length
        ? `<p class="hint">Gemerkt: ` + GEMERKTE.map(x =>
            `<a href="#" onclick="gsEinfuegen('\\', '${esc(x.name)}');return false"
               title="${esc(x.prompt.slice(0, 160))}">\\${esc(x.name)}</a>`
          ).join(" · ") + `</p>`
        : "");
  $("gsSelbst").querySelectorAll(".gszeile").forEach(el => {
    el.oninput = () => { gsZeilen[+el.dataset.i].text = el.value; mitwachsen(el); };
    el.onfocus = () => gsLetzteNr = +el.dataset.i;
    mitwachsen(el);
  });
  $("gsSelbst").querySelectorAll(".gsbilder").forEach(el => {
    el.oninput = () => {
      gsZeilen[+el.dataset.i].bilder = Math.max(1, parseInt(el.value, 10) || 1);
      gsSumme();
    };
  });
  $("gsSelbst").querySelectorAll(".gseinst").forEach(el => {
    el.onchange = () => {
      const i = +el.dataset.i;
      const alt = einstellungInZeile(gsZeilen[i].text);
      einstellungSchreiben(i, el.value, alt ? alt.angabe : "");
    };
  });
  $("gsSelbst").querySelectorAll(".gsangabe").forEach(el => {
    // Erst beim Verlassen schreiben: bei jedem Tastendruck neu zu zeichnen
    // naehme dem Feld den Fokus.
    el.onchange = () => {
      const i = +el.dataset.i;
      const alt = einstellungInZeile(gsZeilen[i].text);
      if (alt) einstellungSchreiben(i, alt.key, el.value);
    };
  });
  gsSumme();
  gsMerken();
}

// Ein Feld waechst mit dem Text, schrumpft aber nie unter das, was man ihm
// von Hand gegeben hat: wer es groesser gezogen hat, will es so behalten.
function mitwachsen(el) {
  // Die jetzige Hoehe zuerst merken: hat der Benutzer das Feld von Hand
  // groesser gezogen, soll das Tippen es nicht wieder zusammenziehen.
  const jetzt = el.offsetHeight;
  el.style.height = "auto";
  el.style.height = Math.max(el.scrollHeight, jetzt, 46) + "px";
}

function gsSumme() {
  const n = gsZeilen.reduce((s, z) => s + (z.bilder || 1), 0);
  $("gsSumme").textContent = `${gsZeilen.filter(z => z.text.trim()).length} Szenen, `
    + `${n} Bild(er)`;
}

// Einen Baustein oder eine Kameraeinstellung in die zuletzt angeklickte
// Zeile schreiben. `zeichen` ist / oder der Rueckwaertsschraegstrich.
function gsEinfuegen(zeichen, name) {
  const i = Math.min(gsLetzteNr, gsZeilen.length - 1);
  gsZeilen[i].text = (gsZeilen[i].text + " " + zeichen + name).trim();
  zeigeSelbstszenen();
  gsMerken();
}

// Die Vorschlaege einer Szene: anklicken schreibt /Name in die Zeile. Was
// schon drinsteht, ist abgehakt. Sie haengen an der Szene selbst, ziehen
// also beim Umsortieren mit und stehen nach dem Speichern wieder da.
function vorschlagZeile(z, i) {
  const liste = z.vorschlag || [];
  if (!liste.length) return "";
  const drin = n => new RegExp("/" + n.replace(/[.*+?^${}()|[\]\\-]/g, "\\$&")
                               + "\\b", "i").test(z.text);
  const offen = liste.filter(t => !drin(t.name));
  return `<div class="szvorschlag">
    ${liste.map(t => `<span class="chip ${t.da ? "hat" : "neu"}${
        drin(t.name) ? " drin" : ""}" title="${
        t.art}${t.da ? ", gibt es schon" : ", noch anzulegen"}"
      onclick="vorschlagNehmen(${i}, '${esc(t.name)}')">${
        drin(t.name) ? "✓ " : ""}${esc(t.name)}</span>`).join("")}
    ${offen.length > 1
      ? `<a href="#" onclick="vorschlagAlle(${i});return false">alle</a>` : ""}
  </div>`;
}

function vorschlagNehmen(i, name) {
  const z = gsZeilen[i];
  const muster = new RegExp("/" + name.replace(/[.*+?^${}()|[\]\\-]/g, "\\$&")
                            + "\\b", "i");
  if (muster.test(z.text)) return;            // steht schon drin
  z.text = (z.text.trim() + " /" + name).trim();
  zeigeSelbstszenen();
  gsMerken();
}

function vorschlagAlle(i) {
  (gsZeilen[i].vorschlag || []).forEach(t => {
    const muster = new RegExp("/" + t.name.replace(/[.*+?^${}()|[\]\\-]/g, "\\$&")
                              + "\\b", "i");
    if (!muster.test(gsZeilen[i].text)) {
      gsZeilen[i].text = (gsZeilen[i].text.trim() + " /" + t.name).trim();
    }
  });
  zeigeSelbstszenen();
  gsMerken();
}

// Die Reihenfolge aendern. Eine Szene an die falsche Stelle zu schreiben
// passiert staendig; sie dafuer zweimal abzutippen ist zu viel verlangt.
function gsSchieben(i, wohin) {
  const ziel = i + wohin;
  if (ziel < 0 || ziel >= gsZeilen.length) return;
  const [weg] = gsZeilen.splice(i, 1);
  gsZeilen.splice(ziel, 0, weg);
  gsLetzteNr = ziel;
  zeigeSelbstszenen();
  gsMerken();
}

function gsZeileWeg(i) {
  gsZeilen.splice(i, 1);
  if (!gsZeilen.length) gsZeilen = [{text: "", bilder: 1}];
  zeigeSelbstszenen();
}

// Je Szene vorschlagen, welche Bausteine sie braucht. Zwei Schritte statt
// einem: erst sehen, was gemeint ist, dann entscheiden, was hineinkommt.
$("gsEmpfehlen").onclick = async e => {
  e.preventDefault();
  if (!gsZeilen.some(z => z.text.trim()))
    return say("Erst das Inhaltsverzeichnis füllen.", "err");
  say("Die Bausteine werden vorgeschlagen …");
  const g = await bausteinRuf({tu: "empfehlen", zeilen: gsZeilen});
  if (!g) return;
  gsZeilen.forEach(z => delete z.vorschlag);
  let n = 0;
  (g.empfehlungen || []).forEach(e2 => {
    const z = gsZeilen[e2.nr - 1];
    if (!z || !e2.teile.length) return;
    z.vorschlag = e2.teile;
    n += e2.teile.length;
  });
  zeigeSelbstszenen();
  gsMerken();
  say(n ? `${n} Vorschläge — anklicken übernimmt sie in die Szene.`
        : "Keine Bausteine erkannt.", n ? "ok" : "err");
};

// Alles, was die Geschichte mit /Name verlangt und noch nicht gibt, gleich
// anlegen -- mit geratener Art und geschriebenem Prompt. Ein Vorschlag zum
// Abaendern ist mehr wert als ein leeres Feld.
$("gsFehlend").onclick = async e => {
  e.preventDefault();
  const zeilen = gsZeilen.filter(z => z.text.trim());
  if (!zeilen.length) return say("Erst das Inhaltsverzeichnis füllen.", "err");
  say("Die fehlenden Bausteine werden geschrieben …");
  const g = await bausteinRuf({tu: "vorschlagen", zeilen});
  if (!g) return;
  if (!g.neu.length) return say(g.hinweis || "Nichts anzulegen.", "ok");
  await bausteineHolen();
  zeigeSelbstszenen();
  say(`${g.neu.length} Baustein(e) angelegt: `
      + g.neu.map(b => b.name).join(", ")
      + " — im Reiter Bausteine gegenlesen und ändern.", "ok");
};

// Regler und Einordnung halten sich stimmig: der Regler sagt, wie weit weg
// von der Wirklichkeit, das Feld sagt wohin.
const GRADTEXT = [
  "ganz die wirkliche Welt — nichts Übernatürliches",
  "ganz die wirkliche Welt — nichts Übernatürliches",
  "wirklich, mit einem Hauch von Unwirklichem am Rand",
  "wirklich, mit einem Hauch von Unwirklichem am Rand",
  "die Grenze zum Unmöglichen ist durchlässig",
  "die Grenze zum Unmöglichen ist durchlässig",
  "erfundene Welt mit eigenen, folgerichtigen Regeln",
  "erfundene Welt mit eigenen, folgerichtigen Regeln",
  "Magie und Fabelwesen gehören dazu",
  "Magie und Fabelwesen gehören dazu",
  "Märchenlogik — Wunder brauchen keine Begründung",
];

function zeigeGrad() {
  const n = +$("gsFiktion").value;
  $("gsFiktionText").textContent = `${n * 10} % Fiktion — ${GRADTEXT[n]}`;
  const passend = n <= 3 ? "wirklich" : n <= 5 ? "scifi"
                : n <= 7 ? "fantasie" : n <= 9 ? "fantasie" : "maerchen";
  if ($("gsWelt").value === "wirklich" || n <= 3) $("gsWelt").value = passend;
  stilHinweis();
}

// Je unwirklicher die Geschichte, desto besser fahren Anime, Comic und Manga:
// ein Foto muss glaubhaft sein, eine Zeichnung darf alles. Gesagt wird es nur
// -- gewaehlt wird der Stil weiter von Hand.
function stilHinweis() {
  const hoch = +$("gsFiktion").value >= 7;
  const stil = $("gsStil").value;
  const gezeichnet = !stil || GEZEICHNET.includes(stil);
  $("gsStilHinweis").textContent = hoch && !gezeichnet
    ? "Bei so viel Fiktion sind Anime, Comic und Manga klar im Vorteil — "
      + "ein Foto muss glaubhaft aussehen, eine Zeichnung darf alles."
    : "";
}
$("gsStil").addEventListener("change", stilHinweis);

$("gsFiktion").addEventListener("input", zeigeGrad);

// Mehrere Geschichten je Projekt, jede in Baenden. Die Vorgaben -- Stil,
// Welt, Wirklichkeitsgrad, Modell -- gehoeren der Geschichte und gelten fuer
// alle Baende; Idee, Gliederung und Prompts gehoeren dem Band.
let gsSpeicherUhr = null, GSAKTUELL = null, gsBandNr = 1;

async function gsRuf(rumpf) {
  const res = await fetch("/api/geschichten", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(rumpf)
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    say(err.error || "Das hat nicht geklappt.", "err");
    return null;
  }
  return res.json();
}

function gsStand() {
  return {band: gsBandNr,
          stil: $("gsStil").value, welt: $("gsWelt").value,
          fiktion: +$("gsFiktion").value, modell: $("gsModell").value,
          idee: $("gsIdee").value, kurz: $("gsKurz").value,
          zeilen: gsZeilen,
          prompts: (GESCHICHTE && GESCHICHTE.prompts) || []};
}

function gsMerken() {
  if (!GSAKTUELL) return;
  clearTimeout(gsSpeicherUhr);
  $("gsStand").textContent = "· ungespeichert";
  gsSpeicherUhr = setTimeout(gsJetztSpeichern, 1200);
}

// Von Hand speichern. Die Nebenbei-Sicherung laeuft weiter -- aber wer eine
// Stunde an einem Inhaltsverzeichnis sitzt, will einmal selbst den Knopf
// druecken und schwarz auf weiss lesen, dass es liegt.
async function gsJetztSpeichern() {
  if (!GSAKTUELL) {
    say("Erst eine Geschichte anlegen.", "err");
    return false;
  }
  clearTimeout(gsSpeicherUhr);
  const g = await gsRuf({tu: "speichern", schluessel: GSAKTUELL, stand: gsStand()});
  if (!g) { $("gsStand").textContent = "· nicht gespeichert"; return false; }
  const uhr = new Date().toLocaleTimeString("de-DE",
    {hour: "2-digit", minute: "2-digit", second: "2-digit"});
  $("gsStand").textContent = `· gespeichert ${uhr}`;
  return true;
}

$("gsSpeichern").onclick = async e => {
  e.preventDefault();
  if (await gsJetztSpeichern()) say("Geschichte gespeichert.", "ok");
};

async function gsListe(waehle) {
  const g = await gsRuf({tu: "liste"});
  if (!g) return;
  $("gsWahl").innerHTML = g.geschichten.length
    ? g.geschichten.map(x =>
        `<option value="${x.schluessel}">${esc(x.name)} (${x.baende} Bd.)</option>`).join("")
    : `<option value="">— noch keine —</option>`;
  const ziel = waehle || (g.geschichten[0] || {}).schluessel || "";
  if (ziel) { $("gsWahl").value = ziel; await gsOeffnen(ziel); }
  else { GSAKTUELL = null; $("gsBand").innerHTML = ""; }
}

async function gsOeffnen(schluessel, nr) {
  const g = await gsRuf({tu: "lesen", schluessel});
  if (!g) return;
  GSAKTUELL = schluessel;
  const baende = g.baende || [];
  $("gsBand").innerHTML = baende.map(b =>
    `<option value="${b.nr}">Band ${b.nr}</option>`).join("");
  gsBandNr = nr || baende[baende.length - 1].nr;
  $("gsBand").value = gsBandNr;
  // Vorgaben der Geschichte
  if (g.stil) $("gsStil").value = g.stil;
  if (g.welt) $("gsWelt").value = g.welt;
  if (g.modell) $("gsModell").value = g.modell;
  if (g.fiktion !== null && g.fiktion !== undefined) $("gsFiktion").value = g.fiktion;
  zeigeGrad();
  // Inhalt des Bandes
  const band = baende.find(x => x.nr === gsBandNr) || {};
  $("gsIdee").value = band.idee || "";
  $("gsKurz").value = band.kurz || "";
  gsZeilen = (band.zeilen && band.zeilen.length)
    ? band.zeilen : [{text: "", bilder: 1}];
  zeigeSelbstszenen();
  GESCHICHTE = null;
  $("gsSzenen").innerHTML = "";
  $("gsKnoepfe").style.display = "none";
  if (band.prompts && band.prompts.length) zeigeGliederung(band.prompts);
  say(`„${g.name}“, Band ${gsBandNr} geladen.`);
}

$("gsWahl").onchange = () => gsOeffnen($("gsWahl").value);
$("gsBand").onchange = () => gsOeffnen(GSAKTUELL, +$("gsBand").value);

$("gsNeu").onclick = async e => {
  e.preventDefault();
  const name = prompt("Wie soll die Geschichte heißen?");
  if (!name) return;
  const g = await gsRuf({tu: "anlegen", name, globale: {
    stil: $("gsStil").value, welt: $("gsWelt").value,
    fiktion: +$("gsFiktion").value, modell: $("gsModell").value}});
  if (!g) return;
  await gsListe(g.schluessel);
  say(`„${g.name}“ angelegt — Band 1 ist leer.`, "ok");
};

$("gsBandNeu").onclick = async e => {
  e.preventDefault();
  if (!GSAKTUELL) return say("Erst eine Geschichte anlegen.", "err");
  const g = await gsRuf({tu: "band", schluessel: GSAKTUELL});
  if (!g) return;
  const neu = g.baende[g.baende.length - 1].nr;
  await gsListe(GSAKTUELL);
  await gsOeffnen(GSAKTUELL, neu);
  say(`Band ${neu} angelegt. Die Vorgaben gelten weiter, die Vorgeschichte `
      + "kennt das Sprachmodell beim Umreißen.", "ok");
};

$("gsWeg").onclick = async e => {
  e.preventDefault();
  if (!GSAKTUELL) return;
  const name = $("gsWahl").selectedOptions[0].textContent;
  if (!confirm(`„${name}“ mit allen Bänden löschen?`)) return;
  if (!await gsRuf({tu: "loeschen", schluessel: GSAKTUELL})) return;
  GSAKTUELL = null;
  await gsListe();
  say("Geschichte gelöscht.", "ok");
};

async function gsHolen() {
  if (!GSAKTUELL) await gsListe();
}

["gsIdee", "gsKurz", "gsStil", "gsWelt", "gsFiktion", "gsModell"].forEach(
  id => $(id).addEventListener("input", gsMerken));

$("gsPlus").onclick = e => {
  e.preventDefault();
  gsZeilen.push({text: "", bilder: 1});
  zeigeSelbstszenen();
};

// --- Schritt 1: umreissen ---
$("gsUmreissen").onclick = async e => {
  e.preventDefault();
  const idee = $("gsIdee").value.trim();
  if (!idee) return say("Erst eine Idee eintippen.", "err");
  const res = await fetch("/api/expose", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({idee, fiktion: +$("gsFiktion").value,
                          anzahl: parseInt($("gsAnzahl").value, 10) || 0,
                          modell: $("gsModell").value,
                          schluessel: GSAKTUELL, band: gsBandNr})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Das ließ sich nicht umreißen.", "err");
  }
  buttonState("busy");
  poll();
  say("Die Geschichte wird umrissen …");
};

function zeigeExpose(e) {
  if (!e || !e.kurz || e.kurz === $("gsKurz").value) return;
  $("gsKurz").value = e.kurz;
  if (e.stil) $("gsStil").value = e.stil;
  if (e.welt) {
    $("gsWelt").value = e.welt;
    // Den Regler nur nachziehen, wenn er noch auf Anschlag steht -- eine
    // bewusst gewaehlte Zwischenstellung soll nicht ueberschrieben werden.
    const jetzt = +$("gsFiktion").value;
    if (jetzt === 0 || jetzt === 10) {
      $("gsFiktion").value = {wirklich: 0, scifi: 6, fantasie: 8, maerchen: 10}[e.welt] ?? jetzt;
      zeigeGrad();
    }
  }
  if (e.szenen && e.szenen.length) {
    gsZeilen = e.szenen.map(t => ({text: t, bilder: 1}));
    zeigeSelbstszenen();
  }
  say(`„${e.titel || "Geschichte"}“ umrissen — Stil und Welt sind gesetzt, `
      + "das Inhaltsverzeichnis ist ein Vorschlag.", "ok");
}

// --- Schritt 3: Prompts schreiben lassen ---
$("gsErzeugen").onclick = async e => {
  e.preventDefault();
  const zeilen = gsZeilen.filter(z => z.text.trim());
  if (!zeilen.length) return say("Erst das Inhaltsverzeichnis füllen.", "err");
  const res = await fetch("/api/gliederung", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({zeilen, stil: $("gsStil").value, welt: $("gsWelt").value,
                          kurz: $("gsKurz").value, fiktion: +$("gsFiktion").value,
                          modell: $("gsModell").value,
                          schluessel: GSAKTUELL, band: gsBandNr,
                          prosa: $("gsProsa").checked})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Die Prompts ließen sich nicht schreiben.", "err");
  }
  buttonState("busy");
  poll();
  say("Die Prompts werden geschrieben …");
};

async function zeigeGliederung(prompts) {
  if (!prompts || !prompts.length) return;
  if (GESCHICHTE && GESCHICHTE.prompts
      && GESCHICHTE.prompts.length === prompts.length
      && GESCHICHTE.prompts[0].prompt === prompts[0].prompt) return;
  const zeilen = gsZeilen.filter(z => z.text.trim());
  const g = await fetch("/api/szenen", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({zeilen, prompts, stil: $("gsStil").value})
  }).then(r => r.json()).catch(() => null);
  if (!g) return;
  GESCHICHTE = {...g, prompts};
  gsMerken();
  const name = (liste, k) => (liste.find(x => x.key === k) || {}).label || "";
  $("gsSzenen").innerHTML = prompts.map((p, i) => `
    <div class="szene"><span class="nr">${i + 1}</span>
      <div class="sztext"><b>${esc(p.zeile)}</b>
        ${p.mimik ? `<span class="art">${esc(name(MIMIKLISTE, p.mimik))}</span>` : ""}
        <br><code>${esc(p.prompt)}</code>
        ${p.prosa ? `<br><i>${esc(p.prosa)}</i>` : ""}</div>
    </div>`).join("");
  $("gsHinweis").textContent = `${g.bilder} Bild(er) entstehen daraus.`;
  $("gsKnoepfe").style.display = "block";
}

// --- Schritt 4: in den Ablauf oder gleich erzeugen ---
async function geschichteInAblauf() {
  if (!GESCHICHTE) return false;
  bloecke = JSON.parse(JSON.stringify(GESCHICHTE.bloecke));
  if (GESCHICHTE.startbild) {
    const antwort = await fetch("/outputs/" + GESCHICHTE.startbild).catch(() => null);
    if (antwort && antwort.ok) {
      const blob = await antwort.blob();
      demoRef = await new Promise(fertig => {
        const leser = new FileReader();
        leser.onload = () => fertig(leser.result);
        leser.readAsDataURL(blob);
      });
      $("demoPreview").src = demoRef;
      $("demoPreview").style.display = "block";
      $("demoRefNote").textContent = "Startbild aus dem Baustein übernommen.";
    }
  }
  return true;
}

$("gsUebernehmen").onclick = async e => {
  e.preventDefault();
  if (!await geschichteInAblauf()) return;
  setMode("demo");
  blockZeichnen();
  demoDauer();
  say("In den Ablauf übernommen. Dort prüfen und starten.", "ok");
};

$("gsSofort").onclick = async e => {
  e.preventDefault();
  if (!await geschichteInAblauf()) return;
  blockZeichnen();
  await starteDemo();
};

// ---------- Katalog ----------
// Alle Bausteine aus allen Projekten. Die Bibliothek waechst ueber ein
// Projekt hinaus: wer eine Person einmal beschrieben hat, will sie im
// naechsten Vorhaben wiedersehen, ohne sie neu zu bauen.
let KATALOG = [], KATPROJEKTE = [], KATFEHLT = [];

async function katalogHolen() {
  const g = await bausteinRuf({tu: "katalog"});
  if (!g) return;
  KATALOG = g.bausteine;
  KATPROJEKTE = g.projekte;
  KATFEHLT = g.fehlend || [];
  if ($("katArt").options.length <= 1) {
    $("katArt").innerHTML = '<option value="">alle</option>'
      + BSARTEN.map(a => `<option value="${a.key}">${esc(a.label)}</option>`).join("");
  }
  katalogZeigen();
}

function katalogZeigen() {
  const art = $("katArt").value;
  const suche = $("katSuche").value.trim().toLowerCase();
  const passt = b => (!art || b.art === art)
    && (!suche || (b.name + " " + b.prompt).toLowerCase().includes(suche));
  const gefunden = KATALOG.filter(passt);
  $("katZahl").textContent = gefunden.length === 1
    ? "1 Baustein" : `${gefunden.length} Bausteine`;

  const label = k => (BSARTEN.find(a => a.key === k) || {}).label || k;
  const nach = KATPROJEKTE.map(p => p.key);
  $("katListe").innerHTML = KATPROJEKTE.map(p => {
    const eigene = gefunden.filter(b => b.projekt === p.key);
    if (!eigene.length) return "";
    return `<div class="katgruppe"><h3>${esc(p.label)}</h3>` + eigene.map(b => {
      const ziele = nach.filter(k => k !== b.projekt);
      return `<div class="baustein katzeile">
        ${b.bild ? `<img src="/bilder/${b.projekt}/${b.bild}" alt="${esc(b.name)}">`
                 : `<span class="ohnebild">?</span>`}
        <div class="bstext"><b>${esc(b.name)}</b>
          <span class="art">${esc(label(b.art))}</span><br>
          <code>${esc(b.prompt)}</code></div>
        ${ziele.length ? `<select onchange="katalogKopieren('${b.projekt}','${b.id}',this)">
            <option value="">kopieren nach …</option>
            ${ziele.map(k => `<option value="${k}">${esc(
                (KATPROJEKTE.find(x => x.key === k) || {}).label || k)}</option>`).join("")}
          </select>` : ""}
      </div>`;
    }).join("") + "</div>";
  }).join("") || `<p class="hint">Noch keine Bausteine — im Reiter
      <b>Bausteine</b> legst du welche an.</p>`;

  // Was eine Geschichte mit /Name verlangt, aber noch nicht gibt.
  const offen = KATFEHLT.filter(f => !suche
    || f.name.toLowerCase().includes(suche));
  $("katListe").innerHTML += offen.length
    ? `<div class="katgruppe"><h3>Noch anzulegen</h3>` + offen.map(f =>
        `<div class="baustein katzeile"><span class="ohnebild">!</span>
          <div class="bstext"><b>${esc(f.name)}</b>
            <span class="art">in „${esc(f.projektname)}“ verlangt</span><br>
            <code>mit /${esc(f.name)} in der Geschichte erwähnt, aber nicht angelegt</code></div>
          <span class="knopf" onclick="bausteinAnlegen('${esc(f.name)}')"
            title="jetzt anlegen">+</span>
        </div>`).join("") + "</div>"
    : "";
}

// Aus dem Katalog heraus einen fehlenden Baustein anlegen.
function bausteinAnlegen(name) {
  setMode("bausteine");
  bausteinLeeren();
  $("bsName").value = name;
  $("bsText").focus();
  say(`„${name}“ beschreiben und Prompt erzeugen lassen.`);
}

async function katalogKopieren(von, id, feld) {
  const nach = feld.value;
  feld.value = "";
  if (!nach) return;
  const b = await bausteinRuf({tu: "kopieren", von, nach, id});
  if (!b) return;
  await katalogHolen();
  await bausteineHolen();
  const ziel = (KATPROJEKTE.find(x => x.key === nach) || {}).label || nach;
  say(`„${b.name}“ nach „${ziel}“ kopiert.`, "ok");
}

$("katArt").onchange = katalogZeigen;
$("katSuche").addEventListener("input", katalogZeigen);

// ---------- Projekte ----------
// Ein Projekt bestimmt, wohin neue Bilder gehen und welche die Galerie zeigt.
// "Allgemein" ist das alte outputs/ -- die Bilder von frueher bleiben dort.
function zeigeProjekte(liste, aktiv) {
  if (!Array.isArray(liste)) return meldeLuecke("projekt");
  $("projekt").innerHTML = liste.map(x =>
    `<option value="${x.key}"${x.key === aktiv ? " selected" : ""}>`
    + `${esc(x.label)} (${x.bilder})</option>`).join("");
  const eigenes = aktiv !== "allgemein";
  $("projektUm").style.display = eigenes ? "inline" : "none";
  $("projektWeg").style.display = eigenes ? "inline" : "none";
}

async function projektTun(rumpf) {
  const res = await fetch("/api/projekt", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(rumpf)
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    say(err.error || "Das hat nicht geklappt.", "err");
    return null;
  }
  const info = await fetch("/api/info").then(r => r.json()).catch(() => null);
  if (info) { zeigeProjekte(info.projekte, info.projekt); zeigeBausteine(info.bausteine); }
  loadGallery();
  return res.json();
}

$("projekt").onchange = async () => {
  await projektTun({tu: "waehlen", key: $("projekt").value});
  say(`Projekt gewechselt: ${$("projekt").selectedOptions[0].textContent}`, "ok");
};

$("projektNeu").onclick = async e => {
  e.preventDefault();
  const name = prompt("Wie soll das Projekt heißen?");
  if (!name) return;
  await projektTun({tu: "anlegen", name});
  say(`Projekt „${name}“ angelegt und ausgewählt.`, "ok");
};

$("projektUm").onclick = async e => {
  e.preventDefault();
  const alt = $("projekt").selectedOptions[0].textContent.replace(/ \(\d+\)$/, "");
  const name = prompt("Neuer Name:", alt);
  if (!name) return;
  await projektTun({tu: "umbenennen", key: $("projekt").value, name});
};

$("projektWeg").onclick = async e => {
  e.preventDefault();
  const wahl = $("projekt").selectedOptions[0];
  if (!confirm(`„${wahl.textContent}“ mit allen Bildern endgültig löschen?`)) return;
  const erg = await projektTun({tu: "loeschen", key: $("projekt").value});
  if (erg) say("Projekt gelöscht.", "ok");
};

// ---------- Fortschritt ----------
// Welcher Auftrag gerade laeuft -- am Wechsel erkennt die Seite, dass der
// vorige fertig ist.
let laufendeNummer = 0;

// Versehentlich zugemacht: der Server laeuft weiter, die Arbeit geht also
// nicht verloren -- nur zusehen kann man dann nicht mehr. Deshalb nachfragen,
// solange etwas laeuft oder wartet.
let laufendeArbeit = false, wartendeAnzahl = 0, beendetGewollt = false;
window.addEventListener("beforeunload", e => {
  if (beendetGewollt || (!laufendeArbeit && !wartendeAnzahl)) return;
  e.preventDefault();
  e.returnValue = "";
});

function poll() {
  clearInterval(polling);
  polling = setInterval(async () => {
    const s = await fetch("/api/status").then(r => r.json()).catch(() => null);
    if (!s) return;

    const done = (s.results || []).length;
    // Anzeigen duerfen scheitern, ohne die Abfrage mitzureissen: sonst
    // bleibt der Knopf stehen, obwohl der Auftrag laengst fertig ist.
    try {
      zeigeUebersetzung(s.translated);
      zeigeGelesen(s.gelesen);
      // Was der Torwaechter gestrichen hat, soll man sehen.
      $("torNote").textContent = (s.tor || []).length
        ? "Aus dem Prompt gestrichen: " + s.tor.join(" · ") : "";
      const perImage = s.total ? s.step / s.total : 0;
      $("fill").style.width =
        (100 * (done + (s.busy ? perImage : 0)) / Math.max(s.count, 1)) + "%";
      paintSeries(s.results || [], s.count, s.image);
      zeigeWarteschlange(s);
      zeigeExpose(s.expose);
      zeigeGliederung(s.gliederung);
      laufendeArbeit = !!(s.busy && s.titel);
      wartendeAnzahl = (s.wartend || []).length;
      // Wechselt der laufende Auftrag, ist der vorige fertig -- seine Bilder
      // sollen dann sofort in der Galerie stehen, nicht erst ganz am Ende.
      if (s.nummer && s.nummer !== laufendeNummer) {
        if (laufendeNummer) loadGallery();
        laufendeNummer = s.nummer;
      }
    } catch (e) {
      console.error(e);
    }

    if (s.busy) return say((s.stage ? s.stage + " · " : "") + s.message
                          + " · " + fmt(s.elapsed));

    clearInterval(polling);
    if (s.error) { buttonState("idle"); $("fill").style.width = "0"; return say(s.error, "err"); }
    buttonState(done ? "done" : "idle");
    if (s.video) zeigeVideo(s.video);
    if (done) say(`${s.message} in ${fmt(s.elapsed)}`, "ok");
    else { $("fill").style.width = "0"; say(s.message); }
    loadGallery();
  }, 900);
}
// Der laufende Auftrag und die wartenden darunter. Wartende lassen sich
// verschieben und herausnehmen; der laufende nur abbrechen, er hat schon
// Rechenzeit verbraucht.
function zeigeWarteschlange(s) {
  const zeilen = [];
  if (s.busy && s.titel) {
    zeilen.push(`<div class="zeile laeuft"><span class="nr">#${s.nummer}</span>`
      + `<span class="was">${esc(s.titel)}</span><span>läuft</span></div>`);
  }
  (s.wartend || []).forEach((a, i, alle) => {
    zeilen.push(`<div class="zeile"><span class="nr">#${a.nummer}</span>`
      + `<span class="was">${esc(a.titel)}</span>`
      + (i > 0 ? `<span class="knopf" onclick="auftragSchieben(${a.nummer},'hoch')" title="nach vorn">↑</span>` : "")
      + (i < alle.length - 1 ? `<span class="knopf" onclick="auftragSchieben(${a.nummer},'runter')" title="nach hinten">↓</span>` : "")
      + `<span class="knopf" onclick="auftragWeg(${a.nummer})" title="entfernen">×</span></div>`);
  });
  (s.verlauf || []).slice(0, 3).forEach(a => {
    const wie = a.zustand === "fertig" ? `${a.bilder} Bild(er)` : a.zustand;
    zeilen.push(`<div class="zeile fertig"><span class="nr">#${a.nummer}</span>`
      + `<span class="was">${esc(a.titel)}</span><span>${wie}</span></div>`);
  });
  if ((s.wartend || []).length > 1) {
    zeilen.push(`<p class="hint"><a href="#" onclick="listeLeeren();return false">`
      + `Warteliste leeren</a> — der laufende Auftrag bleibt.</p>`);
  }
  $("warteschlange").innerHTML = zeilen.join("");
}

async function auftragWeg(nummer) {
  await fetch("/api/cancel", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({nummer})}).catch(() => null);
}

async function auftragSchieben(nummer, richtung) {
  await fetch("/api/verschieben", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({nummer, richtung})}).catch(() => null);
}

async function listeLeeren() {
  if (!confirm("Alle wartenden Aufträge verwerfen?")) return;
  await fetch("/api/cancel", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({alles: true})}).catch(() => null);
}

const fmt = sec => sec < 90 ? `${Math.round(sec)}s` : `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, "0")} min`;

// Was der Server im Startbild erkannt hat. Die Beschreibung landet in den
// Bewahrungsklauseln, deshalb soll sichtbar sein, was dort gelesen wurde.
function zeigeGelesen(g) {
  if (!g || !g.beschreibung) return;
  $("demoRefNote").textContent = "Im Startbild erkannt: " + g.beschreibung
    + (g.geschlecht && g.geschlecht !== "unklar" ? ` (${g.geschlecht})` : "");
}

// Was der Server vor dem Auftrag übersetzt hat — damit nachvollziehbar ist,
// was das Bildmodell tatsächlich gelesen hat.
const FELDNAME = {prompt: "Prompt", keep: "Unverändert", paint_target: "Umgefärbt",
                  negative_prompt: "Negativ"};
function zeigeUebersetzung(t) {
  const el = $("transNote");
  if (!t || !Object.keys(t).length) { el.style.display = "none"; return; }
  el.style.display = "block";
  el.innerHTML = "Ins Englische übersetzt — "
    + Object.entries(t).map(([k, v]) => `<b>${FELDNAME[k] || k}:</b> ${esc(v)}`).join(" · ");
}

// ---------- Mosaik der Serie ----------
let seriesFiles = [];

// Leere Plaetze fuer einen angekuendigten Ablauf: so ist von Anfang an zu
// sehen, wie viele Bilder noch kommen.
function startSlots(anzahl) { paintSeries([], anzahl, 1); }
function paintSeries(files, count, active) {
  const cells = [];
  for (let i = 0; i < Math.max(count, files.length); i++) {
    const f = files[i];
    cells.push(f
      ? `<figure class="tile">
           <img src="/outputs/${f}" alt="${f}" onclick="show('${f}')"
                onload="this.closest('.tile').querySelector('.px').textContent=this.naturalWidth+'×'+this.naturalHeight">
           <figcaption><span class="px"></span><span class="cam" id="cam-${i}"></span>
             <a href="/outputs/${f}" download title="Herunterladen">&darr;</a></figcaption>
         </figure>`
      : `<div class="slot${i === active - 1 ? " now" : ""}">${i === active - 1 ? "…" : ""}</div>`);
  }
  const html = cells.join("");
  if ($("series").innerHTML === html) return;
  $("series").innerHTML = html;
  seriesFiles = files;
  $("seriesHead").style.display = files.length > 1 ? "flex" : "none";
  $("zip").href = "/api/zip?files=" + encodeURIComponent(files.join(","));
  files.forEach((f, i) => fetch("/api/meta?file=" + encodeURIComponent(f))
    .then(r => r.json()).then(m => {
      const el = $("cam-" + i);
      if (el) el.textContent = [m.paint, m.scene].filter(Boolean).join(" · ")
                              || m.view || m.camera || m.style || "";
    }).catch(() => {}));
  if (files.length && !$("stage").dataset.file) show(files[0]);
}

function zeigeVideo(datei) {
  $("stage").dataset.file = "";
  $("stage").innerHTML = `<video src="/outputs/${datei}" controls autoplay muted loop`
    + ` style="max-width:100%;max-height:68vh;border-radius:6px"></video>`;
  $("meta").innerHTML = `<div><a href="/outputs/${datei}" download>${esc(datei)}</a>`
    + ` · Video der Vorführung</div>`;
}

// ---------- Große Anzeige ----------
async function show(file) {
  $("stage").dataset.file = file;
  $("stage").innerHTML = `<img src="/outputs/${file}" alt="Erzeugtes Bild">`;
  [...document.querySelectorAll(".grid img, .tile img")].forEach(
    img => img.classList.toggle("sel", img.alt === file));
  const m = await fetch("/api/meta?file=" + encodeURIComponent(file)).then(r => r.json()).catch(() => ({}));
  const tags = ["scenario", "paint", "material", "scene", "angle", "device", "effect", "form",
                "view", "style", "light", "camera"].filter(k => m[k]).map(k => `<span>${esc(m[k])}</span>`).join("");
  $("meta").innerHTML =
    `<div><a href="/outputs/${file}" download>${esc(file)}</a>`
    + (m.size ? ` · ${m.size[0]} × ${m.size[1]} px` : "")
    + (m.seed ? ` · Seed ${esc(m.seed)}` : "")
    + (hasGimp ? ` · <a href="#" onclick="openInGimp('${file}');return false">In GIMP öffnen</a>` : "")
    + `</div>`
    + (tags ? `<div class="tags">${tags}</div>` : "")
    + (m.prompt ? `<div style="margin-top:7px"><code>${esc(m.prompt)}</code></div>` : "")
    + sterneZeigen(file);
}

// Öffnet das Bild in GIMP auf dem Rechner, auf dem der Server läuft.
async function openInGimp(file) {
  say("GIMP wird gestartet …");
  const res = await fetch("/api/open-in-gimp", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({file})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "GIMP ließ sich nicht starten.", "err");
  }
  say("In GIMP geöffnet. Der erste Start dauert einen Moment.", "ok");
}

// ---------- Video aus ausgewaehlten Bildern ----------
// Die Reihenfolge ist die der Auswahl, nicht die der Galerie -- so laesst
// sich die Abfolge bestimmen, ohne etwas zu verschieben.
let filmModus = false, filmWahl = [];

function filmUmschalten(an) {
  filmModus = an;
  filmWahl = [];
  $("filmLeiste").style.display = an ? "flex" : "none";
  $("gallery").classList.toggle("waehlen", an);
  filmZeigen();
  loadGallery();
}

function filmZeigen() {
  $("filmZahl").textContent = filmWahl.length === 1
    ? "1 Bild gewählt" : `${filmWahl.length} Bilder gewählt`;
  $("gallery").querySelectorAll(".kachel").forEach(el => {
    const platz = filmWahl.indexOf(el.dataset.f);
    const alt = el.querySelector(".nr");
    if (alt) alt.remove();
    if (platz >= 0) {
      const marke = document.createElement("span");
      marke.className = "nr";
      marke.textContent = platz + 1;
      el.appendChild(marke);
    }
  });
}

function filmWaehlen(datei) {
  const platz = filmWahl.indexOf(datei);
  if (platz >= 0) filmWahl.splice(platz, 1);
  else filmWahl.push(datei);
  filmZeigen();
}

$("filmAn").onclick = e => { e.preventDefault(); filmUmschalten(true); };
$("filmAus").onclick = e => { e.preventDefault(); filmUmschalten(false); };

$("filmBauen").onclick = async e => {
  e.preventDefault();
  if (filmWahl.length < 2) return say("Mindestens zwei Bilder wählen.", "err");
  const dauer = parseFloat($("filmDauer").value) || 20;
  say(`Video aus ${filmWahl.length} Bildern wird gebaut …`);
  const res = await fetch("/api/video", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({files: filmWahl, duration: dauer})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Das Video ließ sich nicht bauen.", "err");
  }
  const g = await res.json();
  filmUmschalten(false);
  zeigeVideo(g.video);
  say(`Video fertig: ${g.bilder} Bilder in ${g.dauer} s.`, "ok");
};

async function loadGallery() {
  const antwort = await fetch("/api/gallery").then(r => r.json()).catch(() => null);
  if (!antwort) return;
  await notenHolen();
  $("gallery").innerHTML = antwort.files.map(f => {
    const n = (NOTEN[f] || {}).note || 0;
    return `<figure class="kachel" data-f="${f}"><img src="/outputs/${f}" title="${f}"
       alt="${f}" onclick="${filmModus ? `filmWaehlen('${f}')` : `show('${f}')`}">`
      + (filmModus ? "" : `<b onclick="loeschen('${f}')" title="Löschen">×</b>`)
      + (n ? `<span class="note">${"★".repeat(n)}</span>` : "")
      + `</figure>`;
  }).join("");
  if (filmModus) filmZeigen();
}

// ---------- Noten ----------
// Bewertet wird, damit gute Prompts wiederkommen: ein Bild mit Namen laesst
// sich in einer Szene mit \Name wieder aufrufen. Alles liegt im Projekt in
// bewertung.json -- lesbar, zum Weiterreichen.
let NOTEN = {}, GEMERKTE = [];

async function notenHolen() {
  const b = await fetch("/api/bewertung").then(r => r.json()).catch(() => null);
  if (!b) return;
  NOTEN = b.bilder || {};
  GEMERKTE = b.gemerkte || [];
}

function sterneZeigen(datei) {
  const e = NOTEN[datei] || {};
  const n = e.note || 0;
  return `<div class="noten">
    <div class="sterne">${[1, 2, 3, 4, 5].map(i =>
      `<span class="${i <= n ? "voll" : ""}" title="${i} von 5"
         onclick="benoten('${datei}', ${i === n ? 0 : i})">★</span>`).join("")}</div>
    <input class="name" placeholder="Prompt merken als …"
      value="${esc(e.name || "")}" onchange="merken('${datei}', this.value)">
    ${e.nr ? `<span class="nr">\\${esc(e.name)} oder \\${e.nr}</span>` : ""}
    <input class="notiz" placeholder="Was daran gut oder schlecht ist"
      value="${esc(e.notiz || "")}" onchange="notieren('${datei}', this.value)">
  </div>`;
}

async function notenRuf(daten) {
  const res = await fetch("/api/bewertung", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(daten)
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    say(err.error || "Die Bewertung ließ sich nicht speichern.", "err");
    return null;
  }
  return res.json();
}

async function benoten(datei, note) {
  const e = await notenRuf({file: datei, note});
  if (e === null) return;
  NOTEN[datei] = e;
  if ($("stage").dataset.file === datei) show(datei);
  loadGallery();
}

async function merken(datei, name) {
  const e = await notenRuf({file: datei, name});
  if (e === null) return;
  NOTEN[datei] = e;
  await notenHolen();
  zeigeSelbstszenen();             // die Liste unter den Szenen waechst mit
  if (e.name) {
    say(`Gemerkt. In einer Szene mit \\${e.name} oder \\${e.nr} aufrufbar.`, "ok");
  } else {
    say("Der Name ist weg, der Prompt damit auch.", "ok");
  }
  if ($("stage").dataset.file === datei) show(datei);
}

async function notieren(datei, notiz) {
  const e = await notenRuf({file: datei, notiz});
  if (e !== null) NOTEN[datei] = e;
}

// Endgueltig, ohne Papierkorb -- deshalb die Rueckfrage.
async function loeschen(datei) {
  if (!confirm(`„${datei}“ wirklich löschen?`)) return;
  const res = await fetch("/api/delete", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({file: datei})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Löschen ist fehlgeschlagen.", "err");
  }
  if ($("stage").dataset.file === datei) {
    $("stage").dataset.file = "";
    $("stage").innerHTML = "<p>Bild gelöscht.</p>";
    $("meta").innerHTML = "";
  }
  say(`${datei} gelöscht.`, "ok");
  loadGallery();
}

// Haelt den Server an. Danach ist die Seite tot -- das muss sie auch sagen.
async function programmBeenden() {
  const offen = (laufendeArbeit ? 1 : 0) + wartendeAnzahl;
  const frage = offen
    ? `Es ${offen === 1 ? "ist noch ein Auftrag" : `sind noch ${offen} Aufträge`} `
      + "offen. Trotzdem beenden?"
    : "Das Programm beenden?";
  if (!confirm(frage)) return;
  beendetGewollt = true;                 // die Warnung beim Schliessen aus
  await fetch("/api/shutdown", {method: "POST"}).catch(() => null);
  // Den Reiter schliessen darf nur, wer ihn selbst geoeffnet hat. start.sh
  // oeffnet ihn ueber den Browser, also schlaegt das meistens fehl -- dann
  // bleibt die Abschiedsseite stehen.
  document.body.innerHTML = "<main><section class=\"panel\"><h1>Beendet</h1>"
    + "<p>Der Server ist angehalten, die Grafikkarte ist frei. "
    + "Dieser Reiter kann zu. Zum Weitermachen im Terminal wieder "
    + "<code>./start.sh</code> starten.</p></section></main>";
  window.close();
}


// ---------- Splitter zwischen den beiden Spalten ----------
// Die Breite steckt in --links auf <main> und bleibt im Browser stehen.
// Sie gehoert dem Bildschirm, nicht dem Projekt, deshalb localStorage und
// nicht der Server.
const SPLIT_STD = 430, SPLIT_MIN = 320;

function splitSetzen(px) {
  const platz = document.querySelector("main").clientWidth;
  // Rechts muessen mindestens 300 px bleiben, sonst ist die Galerie ein
  // Streifen und man kommt nicht mehr zurueck.
  const max = Math.max(SPLIT_MIN, platz - 320);
  const breit = Math.round(Math.min(Math.max(px, SPLIT_MIN), max));
  document.querySelector("main").style.setProperty("--links", breit + "px");
  try { localStorage.setItem("splitter", breit); } catch (e) { /* egal */ }
}

(function splitterAufbauen() {
  const griff = $("splitter");
  if (!griff) return;
  try {
    const gemerkt = parseInt(localStorage.getItem("splitter"), 10);
    if (gemerkt > 0) splitSetzen(gemerkt);
  } catch (e) { /* ohne Speicher eben die Vorgabe */ }

  let zieht = false;
  griff.addEventListener("pointerdown", e => {
    zieht = true;
    griff.setPointerCapture(e.pointerId);
    griff.classList.add("zieht");
    document.body.classList.add("zieht");
    e.preventDefault();
  });
  griff.addEventListener("pointermove", e => {
    if (!zieht) return;
    const links = document.querySelector("main").getBoundingClientRect().left;
    splitSetzen(e.clientX - links);
  });
  const fertig = e => {
    if (!zieht) return;
    zieht = false;
    try { griff.releasePointerCapture(e.pointerId); } catch (err) { /* egal */ }
    griff.classList.remove("zieht");
    document.body.classList.remove("zieht");
  };
  griff.addEventListener("pointerup", fertig);
  griff.addEventListener("pointercancel", fertig);
  griff.addEventListener("dblclick", () => splitSetzen(SPLIT_STD));
})();


fetch("/api/status").then(r => r.json()).then(s => {
  if (s.busy) { buttonState("busy"); poll(); }
});
loadGallery();
