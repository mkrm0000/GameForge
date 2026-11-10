const $ = s => document.querySelector(s);
const say = (s, m) => { $(s).textContent = m; };
const h = (tag, text, cls) => {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
};
const post = (path, body) => fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

async function errorText(r) {
  const d = (await r.json().catch(() => ({}))).detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map(x => `${x.loc.slice(1).join(".")}: ${x.msg}`).join("; ");
  return r.statusText || `HTTP ${r.status}`;
}

async function api(path, body) {
  const r = body === undefined ? await fetch(path) : await post(path, body);
  if (!r.ok) throw new Error(await errorText(r));
  return r.json();
}

const ACTIONS = ["#generate", "#regen", "#accept", "#edit", "#apply-patch", "#test", "#save"].map($);

async function run(status, msg, fn) {
  ACTIONS.forEach(b => { b.disabled = true; });
  say(status, msg);
  try {
    say(status, (await fn()) || "");
  } catch (e) {
    say(status, "Error: " + e.message);
  } finally {
    ACTIONS.forEach(b => { b.disabled = false; });
  }
}

function chips(box, opts, selected, multi, onChange) {
  box.replaceChildren(...opts.map(o => {
    const b = h("button", o);
    b.type = "button";
    b.setAttribute("aria-pressed", selected.includes(o));
    b.onclick = () => {
      if (multi) b.setAttribute("aria-pressed", b.getAttribute("aria-pressed") !== "true");
      else box.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b));
      if (onChange) onChange();
    };
    return b;
  }));
}
const picked = box => [...box.querySelectorAll("[aria-pressed=true]")].map(b => b.textContent);

const GUIDES = {
  dimension: { label: "Dimension", opts: ["2D", "2.5D", "3D"], def: ["2D"] },
  art_style: { label: "Art style", opts: ["Pixel", "Cartoonish", "Low-poly", "Minimalist", "Realistic"], def: ["Pixel"] },
  platform: { label: "Platform", opts: ["PC", "Mobile", "Both"], def: ["PC"] },
  perspective: { label: "Perspective", opts: ["Top-down", "Side-scroller", "Isometric", "First-person", "Third-person"], def: ["Top-down"] },
  controls: { label: "Controls", opts: ["Keyboard", "Mouse", "Touch"], def: ["Keyboard"], multi: true },
  genre: { label: "Genre", opts: ["Auto", "Action", "Puzzle", "Platformer", "Shooter", "RPG", "Arcade", "Horror-survival", "Strategy"], def: ["Auto"] },
  renderer: { label: "Renderer", opts: ["Canvas 2D", "Three.js", "DOM+CSS"], def: ["Canvas 2D"] },
  length: { label: "Length", opts: ["Short demo", "Full playable loop"], def: ["Short demo"] },
};

const SETTINGS = {
  audio: { label: "Audio", opts: ["Music only", "SFX only", "Both", "None"], def: "SFX only" },
  progression: { label: "Progression", opts: ["Endless", "Single level", "Multi-level (3-5)"], def: "Single level" },
  difficulty: { label: "Difficulty", opts: ["Easy", "Normal", "Hard"], def: "Normal" },
  session: { label: "Session length", opts: ["~1 min", "~5 min", "~15 min"], def: "~5 min" },
  performance: { label: "Performance", opts: ["Low-end friendly", "Standard", "High"], def: "Standard" },
  palette: { label: "Palette/theme", opts: ["Auto", "Dark", "Bright", "Retro", "Pastel"], def: "Auto" },
};

for (const [k, g] of Object.entries(GUIDES)) {
  const box = h("div", undefined, "chips");
  box.id = "g-" + k;
  chips(box, g.opts, g.def, g.multi);
  const row = h("div", undefined, "row");
  row.append(h("span", g.label, "label"), box);
  $("#guides").append(row);
}

for (const [k, s] of Object.entries(SETTINGS)) {
  const sel = h("select");
  sel.id = "s-" + k;
  s.opts.forEach(o => sel.append(new Option(o)));
  sel.value = s.def;
  const lab = h("label", s.label + " ");
  lab.append(sel);
  $("#settings").append(lab);
}

let audioPrev = SETTINGS.audio.def;
$("#prototype").onchange = e => {
  const a = $("#s-audio");
  if (e.target.checked) audioPrev = a.value;
  a.value = e.target.checked ? "None" : audioPrev;
  a.disabled = e.target.checked;
};

function payload(slug) {
  const guides = {};
  for (const k in GUIDES) {
    const v = picked($("#g-" + k));
    guides[k] = GUIDES[k].multi ? (v.length ? v : ["Keyboard"]) : v[0];
  }
  const settings = { prototype: $("#prototype").checked };
  for (const k in SETTINGS) settings[k] = $("#s-" + k).value;
  return { idea: $("#idea").value.trim(), notes: $("#notes").value.trim(), guides, settings, slug };
}

let slug = null, current = null, editing = false;

function renderDesign(d) {
  const box = $("#design");
  box.replaceChildren(h("h3", d.title), h("p", d.pitch));
  const field = (k, v) => {
    const p = h("p");
    p.append(h("strong", k + ": "), v);
    box.append(p);
  };
  const list = (k, items) => {
    const ul = h("ul");
    items.forEach(i => ul.append(h("li", i)));
    box.append(h("h4", k), ul);
  };
  field("Genre", d.genre);
  field("Core loop", d.core_loop);
  field("Controls", d.controls);
  list("Entities", d.entities);
  list("Mechanics", d.mechanics);
  field("Win/lose", d.win_lose);
  list("Assets", d.assets.map(a => `${a.name} (${a.type}): ${a.description}`));
  field("Audio plan", d.audio_plan);
  list("Files", d.file_tree);
  field("Notes", d.impl_notes);
}

function show(d) {
  current = d;
  editing = false;
  $("#design-edit").hidden = true;
  $("#design").hidden = false;
  $("#edit").textContent = "Edit";
  renderDesign(d);
  $("#review").hidden = false;
  $("#result").hidden = true;
}

const gen = reuse => run(reuse ? "#review-status" : "#status", "Generating design...", async () => {
  const p = payload(reuse ? slug : undefined);
  if (!p.idea) {
    $("#idea").focus();
    throw new Error("Enter an idea first");
  }
  const r = await api("/api/design", p);
  slug = r.slug;
  show(r.design);
});
$("#generate").onclick = () => gen(false);
$("#regen").onclick = () => gen(true);

$("#edit").onclick = () => {
  try {
    if (editing) {
      current = JSON.parse($("#design-edit").value);
      renderDesign(current);
    } else {
      $("#design-edit").value = JSON.stringify(current, null, 2);
    }
  } catch (e) {
    return say("#review-status", "Invalid design: " + e.message);
  }
  editing = !editing;
  say("#review-status", "");
  $("#design-edit").hidden = !editing;
  $("#design").hidden = editing;
  $("#edit").textContent = editing ? "Preview" : "Edit";
};

const log = m => { $("#log").textContent += m + "\n"; };

async function build() {
  const r = await post("/api/build", { slug });
  if (!r.ok) throw new Error(await errorText(r));
  const reader = r.body.getReader(), dec = new TextDecoder();
  let buf = "", finished = false;
  const handle = m => {
    if (m.log) log(m.log);
    if (m.error) {
      log("Error: " + m.error);
      finished = true;
    }
    if (m.done) {
      finished = true;
      $("#play").href = m.play_url;
      $("#play").hidden = false;
      $("#patch").hidden = false;
    }
  };
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n");
    buf = parts.pop();
    parts.filter(Boolean).forEach(p => handle(JSON.parse(p)));
  }
  if (!finished) log("Build stream ended unexpectedly");
}

$("#accept").onclick = () => run("#review-status", "Accepting and building...", async () => {
  const design = editing ? JSON.parse($("#design-edit").value) : current;
  await api("/api/accept", { slug, design });
  current = design;
  $("#result").hidden = false;
  $("#log").textContent = "";
  $("#play").hidden = true;
  $("#patch").hidden = true;
  await build();
});

$("#apply-patch").onclick = () => run("#patch-status", "Patching...", async () => {
  const files = $("#patch-files").value.split(",").map(s => s.trim()).filter(Boolean);
  const r = await api("/api/patch", { slug, instruction: $("#patch-instruction").value.trim(), files });
  log("Patched: " + (r.updated.join(", ") || "nothing changed"));
});