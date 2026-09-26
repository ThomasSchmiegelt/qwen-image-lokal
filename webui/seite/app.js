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
                      angle: "angle", material: "material"};

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
  $("demoBox").style.display = istDemo ? "block" : "none";
  ["boxVorlage", "boxDarstellung", "boxBild", "boxFein", "uploadBox"].forEach(
    id => { if (istDemo) $(id).style.display = "none"; });
  $("prompt").parentElement.querySelectorAll("#prompt, #transNote, #tplHint")
    .forEach(el => { el.style.display = istDemo ? "none" : ""; });
  document.querySelectorAll("label[for=prompt]").forEach(
    el => el.style.display = istDemo ? "none" : "");
  if (!istDemo) { $("boxVorlage").style.display = ""; $("boxDarstellung").style.display = "";
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
  buttonState("busy");
  $("stage").dataset.file = "";
  say("Vorführung wird vorbereitet …");
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
    startSlots(1 + bloecke.reduce((s, b) => {
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
    go.disabled = true; go.classList.add("busy"); go.textContent = "läuft …";
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
    camera: $("camera").value,
    // In den Varianten haben Stil und Licht eigene Achsenfelder, damit sich
    // beide auf "wuerfeln" stellen lassen.
    style: mode === "varianten" ? $("vstyle").value : $("style").value,
    light: mode === "varianten" ? $("vlight").value : $("light").value,
    paint_target: $("paintTarget").value,
    true_cfg_scale: parseFloat($("cfg").value),
    transparent: $("transparent").checked
  };

  buttonState("busy");
  $("stage").dataset.file = "";
  $("transNote").style.display = "none";
  say("Auftrag wird gestartet …");
  paintSeries([], body.count, 1);

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
$("stop").onclick = () => { fetch("/api/cancel", {method: "POST"}); say("Abbruch angefordert …"); };

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
  $("chatNote").textContent = (plan.note || "Verstanden.")
    + ` Einstellungen unten prüfen, dann auf „${MODES[mode].label}“.`;
  $("chat").value = "";
  // Bewusst kein Start: erst Text, dann Prompt, dann prüfen, dann Bild.
  $("go").classList.add("ready");
  setTimeout(() => $("go").classList.remove("ready"), 6000);
}
$("chatGo").onclick = sendChat;
$("beenden").onclick = e => { e.preventDefault(); programmBeenden(); };
$("ableiten").onclick = e => { e.preventDefault(); promptAusBild(); };

// Rueckwaerts: das hochgeladene Bild ansehen und den Prompt dazu schreiben.
// Lesen darf nur das Sprachmodell, deshalb geht es nicht waehrend eines
// Auftrags -- beide wollen dieselbe Grafikkarte.
async function promptAusBild() {
  if (!refs.length) return say("Erst ein Referenzbild hochladen.", "err");
  say("Das Bild wird gelesen …");
  const res = await fetch("/api/bild-prompt", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({image: refs[0]})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Das Bild liess sich nicht lesen.", "err");
  }
  const g = await res.json();
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

// ---------- Fortschritt ----------
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
      const perImage = s.total ? s.step / s.total : 0;
      $("fill").style.width =
        (100 * (done + (s.busy ? perImage : 0)) / Math.max(s.count, 1)) + "%";
      paintSeries(s.results || [], s.count, s.image);
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
    + (m.prompt ? `<div style="margin-top:7px"><code>${esc(m.prompt)}</code></div>` : "");
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

async function loadGallery() {
  const antwort = await fetch("/api/gallery").then(r => r.json()).catch(() => null);
  if (!antwort) return;
  $("gallery").innerHTML = antwort.files.map(f =>
    `<figure class="kachel"><img src="/outputs/${f}" title="${f}" alt="${f}"
       onclick="show('${f}')"><b onclick="loeschen('${f}')" title="Löschen">×</b></figure>`
  ).join("");
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
  if (!confirm("Das Programm beenden? Ein laufender Auftrag wird abgebrochen.")) return;
  await fetch("/api/shutdown", {method: "POST"}).catch(() => null);
  document.body.innerHTML = "<main><section class=\"panel\"><h1>Beendet</h1>"
    + "<p>Der Server ist angehalten, die Grafikkarte ist frei. "
    + "Zum Weitermachen im Terminal wieder <code>./start.sh</code> starten.</p>"
    + "</section></main>";
}

fetch("/api/status").then(r => r.json()).then(s => {
  if (s.busy) { buttonState("busy"); poll(); }
});
loadGallery();
