const LOCAL = ["ollama", "lmstudio", "llamacpp", "vllm"];
const OTHER = ["openai", "anthropic", "gemini", "deepseek", "groq", "mistral", "custom"];
const FAMILIES = { claude: "anthropic/", gemini: "google/", chatgpt: "openai/", deepseek: "deepseek/" };
let presets = {}, orModels = null, family = "claude";

const hosted = () => ["openrouter", "free"].includes($("#source").value);

function layout() {
  const s = $("#source").value;
  $("#families").hidden = s !== "openrouter";
  $("#provider-row").hidden = hosted();
  $("#provider").replaceChildren(...(s === "local" ? LOCAL : s === "other" ? OTHER : []).map(n => new Option(n)));
}

function syncUrl() {
  const url = hosted() ? presets.openrouter : presets[$("#provider").value];
  if (url) $("#base_url").value = url;
}

async function fillModels(reset) {
  const dl = $("#models");
  dl.replaceChildren();
  if (!hosted()) return;
  try {
    orModels ||= await api("/api/openrouter-models");
    const list = $("#source").value === "free" ? orModels.free : orModels[family];
    dl.replaceChildren(...list.map(m => new Option(m)));
    if (reset && !list.includes($("#model").value)) $("#model").value = list[0] || "";
  } catch (e) {
    say("#model-status", "Error: " + e.message);
  }
}

const cfgBody = () => ({
  provider: hosted() ? "openrouter" : $("#provider").value,
  base_url: $("#base_url").value.trim(),
  api_key: $("#api_key").value,
  model: $("#model").value.trim(),
  temperature: +$("#temperature").value,
  max_tokens: +$("#max_tokens").value,
});

$("#source").onchange = () => {
  layout();
  syncUrl();
  if (!hosted()) $("#model").value = "";
  fillModels(true);
};
$("#provider").onchange = syncUrl;

$("#test").onclick = () => run("#model-status", "Testing...", async () => {
  const r = await api("/api/test-model", cfgBody());
  return r.ok ? "Connected" + (r.reply ? ": " + r.reply : "") : "Failed: " + r.error;
});

$("#save").onclick = () => run("#model-status", "Saving...", async () => {
  $("#api_key").value = (await api("/api/config", cfgBody())).api_key;
  return "Saved";
});

(async () => {
  try {
    let cfg;
    [presets, cfg] = await Promise.all([api("/api/presets"), api("/api/config")]);
    const free = cfg.model.endsWith(":free") || cfg.model === "openrouter/free";
    $("#source").value = cfg.base_url === presets.openrouter ? (free ? "free" : "openrouter") : LOCAL.includes(cfg.provider) ? "local" : "other";
    family = Object.keys(FAMILIES).find(k => cfg.model.startsWith(FAMILIES[k])) || "claude";
    chips($("#families"), Object.keys(FAMILIES), [family], false, () => {
      family = picked($("#families"))[0];
      fillModels(true);
    });
    layout();
    if ([...$("#provider").options].some(o => o.value === cfg.provider)) $("#provider").value = cfg.provider;
    for (const k of ["base_url", "api_key", "model", "temperature", "max_tokens"]) $("#" + k).value = cfg[k];
    fillModels(false);
  } catch (e) {
    say("#model-status", "Error: " + e.message);
  }
})();