let after = 0, timer = null, depth = 0, lastErr = "", chain = Promise.resolve();
const box = $("#console-log");

function addEvent(e) {
  const row = h("div", undefined, "ev " + e.kind);
  const meta = [e.t, e.kind, e.model, e.ms != null && e.ms + " ms", e.tokens != null && e.tokens + " tok", e.finish && e.finish !== "stop" && e.finish].filter(Boolean).join(" | ");
  row.append(h("div", meta, "meta"));
  if (e.text.length > 200 || e.text.includes("\n")) {
    const d = h("details");
    d.append(h("summary", e.text.slice(0, 120).replace(/\s+/g, " ") + "... (" + e.text.length + " chars)"), h("pre", e.text));
    row.append(d);
  } else if (e.text) {
    row.append(h("div", e.text));
  }
  box.append(row);
}

async function load() {
  try {
    const r = await api("/api/events?after=" + after);
    lastErr = "";
    if (r.last < after) {
      after = 0;
      box.replaceChildren();
    }
    const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
    r.events.forEach(e => {
      addEvent(e);
      after = e.id;
    });
    if (r.events.length && stick) box.scrollTop = box.scrollHeight;
  } catch (e) {
    if (e.message !== lastErr) {
      lastErr = e.message;
      addEvent({ t: new Date().toLocaleTimeString(), kind: "error", text: "Console feed failed: " + e.message });
    }
  }
}

const fetchEvents = () => (chain = chain.then(load));

function watch(on) {
  depth += on ? 1 : -1;
  if (on && depth === 1) {
    fetchEvents();
    timer = setInterval(fetchEvents, 1000);
  } else if (!on && depth === 0) {
    clearInterval(timer);
    fetchEvents();
  }
}

const plainRun = run;
run = async (...args) => {
  watch(true);
  try {
    return await plainRun(...args);
  } finally {
    watch(false);
  }
};

$("#console-clear").onclick = () => box.replaceChildren();
fetchEvents();