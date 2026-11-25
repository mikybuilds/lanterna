// Lanterna for Chrome: the link between this browser and the Lanterna app on the same computer.
// Lanterna (127.0.0.1 only) sends one command at a time: look at a tab, click, type, fill a form, take a picture of
// it. This script does it and sends back the result. The model and every decision about what needs your OK live
// in Lanterna; this side only does what it is told and shows where it works (the "Lanterna" tab group, an amber
// edge around the page and a Stop button).
"use strict";

const PORTS = [47321, 47322, 47323];
const GROUP_TITLE = "Lanterna";
const GROUP_COLOR = "orange";
const IDLE_DETACH_MS = 90 * 1000;          // the debugger bar goes away a while after the last action
const CMD_TIMEOUT_MS = 45 * 1000;

let ws = null;
let state = { status: "off", ui: "", lang: "en", mode: "semi", words: {}, error: "", port: 0 };
let connecting = false;
let lastTry = 0;

// ---------------------------------------------------------------- small helpers
const sleep = ms => new Promise(r => setTimeout(r, ms));
const store = {
  get: async k => (await chrome.storage.local.get(k))[k],
  set: (k, v) => chrome.storage.local.set({ [k]: v }),
};

function words(key, fallback) {
  return (state.words && state.words[key]) || fallback;
}

function setState(patch) {
  Object.assign(state, patch);
  chrome.runtime.sendMessage({ t: "state", state: publicState() }).catch(() => {});
  chrome.action.setBadgeText({ text: state.status === "ready" ? "" : "!" }).catch(() => {});
  chrome.action.setBadgeBackgroundColor({ color: "#8F5600" }).catch(() => {});
}

function publicState() {
  return { status: state.status, ui: state.ui, lang: state.lang, mode: state.mode, words: state.words, error: state.error };
}

async function hmac(keyB64, text) {
  const raw = Uint8Array.from(atob(keyB64), c => c.charCodeAt(0));
  const key = await crypto.subtle.importKey("raw", raw, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(text));
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}

function nonce() {
  const a = new Uint8Array(16);
  crypto.getRandomValues(a);
  return btoa(String.fromCharCode(...a));
}

// ---------------------------------------------------------------- the link to Lanterna
async function connect(force = false) {
  if (connecting || ws && ws.readyState <= 1) return;
  if (!force && Date.now() - lastTry < 4000) return;
  connecting = true;
  lastTry = Date.now();
  try {
    for (const port of PORTS) {
      const ok = await tryPort(port);
      if (ok) return;
    }
    setState({ status: "off", ui: "" });
  } finally {
    connecting = false;
  }
}

function tryPort(port) {
  return new Promise(resolve => {
    let done = false;
    const finish = ok => { if (!done) { done = true; resolve(ok); } };
    let sock;
    try {
      sock = new WebSocket(`ws://127.0.0.1:${port}/ext`);
    } catch (e) {
      return finish(false);
    }
    const timer = setTimeout(() => { try { sock.close(); } catch (e) {} finish(false); }, 2500);
    const mine = nonce();
    sock.onopen = async () => {
      const key = (await store.get("key")) || "";
      sock.send(JSON.stringify({ t: "hello", v: chrome.runtime.getManifest().version, browser: navigator.userAgent,
        key: key ? "yes" : "", nonce: mine }));
    };
    sock.onmessage = async ev => {
      let m;
      try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m.t === "welcome") {
        let key = (await store.get("key")) || "";
        if (m.error === "paired") {
          // Lanterna is connected to another copy of this extension: the user lets a new one in (Settings → Chrome)
          clearTimeout(timer);
          try { sock.close(); } catch (e) {}
          setState({ status: "pair", ui: "", port });
          return finish(true);
        }
        if (key) {
          // Lanterna proves it is the one we were connected to before
          if (!m.proof || m.proof !== await hmac(key, mine)) {
            clearTimeout(timer);
            setState({ status: "reset", ui: "", port });
            ws = sock;
            return finish(true);
          }
        } else if (m.key) {
          key = m.key;
          await store.set("key", key);
        }
        if (!key || !m.challenge) {
          clearTimeout(timer);
          try { sock.close(); } catch (e) {}
          return finish(false);
        }
        // and this side proves it too; Lanterna sends its window and commands only after that
        ws = sock;
        sock.send(JSON.stringify({ t: "auth", mac: await hmac(key, m.challenge) }));
        return;
      }
      if (m.t === "ready") {
        clearTimeout(timer);
        setState({ status: "ready", ui: m.ui || "", lang: m.lang || "en", mode: m.mode || "semi", words: m.words || {}, port, error: "" });
        return finish(true);
      }
      handle(m);
    };
    sock.onerror = () => { clearTimeout(timer); finish(false); };
    sock.onclose = () => {
      clearTimeout(timer);
      if (ws === sock) {
        ws = null;
        setState({ status: "off", ui: "" });
        hideAll();
      }
      finish(false);
    };
  });
}

function send(m) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify(m));
}

// a fresh key when the user agrees (Lanterna on this computer was set up again)
async function pairAgain() {
  await chrome.storage.local.remove("key");
  if (ws) try { ws.close(); } catch (e) {}
  ws = null;
  await connect(true);
}

async function handle(m) {
  if (m.t === "cmd") {
    let out;
    try {
      if (state.status !== "ready") throw new Error("not paired");
      out = { t: "res", id: m.id, ok: true, data: await withTimeout(run(m.cmd, m.args || {}), CMD_TIMEOUT_MS) };
    } catch (e) {
      out = { t: "res", id: m.id, ok: false, error: String(e && e.message || e) };
    }
    send(out);
  } else if (m.t === "set") {
    setState({ lang: m.lang || state.lang, mode: m.mode || state.mode, words: m.words || state.words, ui: m.ui || state.ui });
  } else if (m.t === "pong") {
    // alive
  }
}

function withTimeout(p, ms) {
  return Promise.race([p, new Promise((_, no) => setTimeout(() => no(new Error("timed out")), ms))]);
}

// keep the link alive (an open WebSocket that talks keeps this service worker running), and try again now and then
setInterval(() => { if (ws && ws.readyState === 1) send({ t: "ping" }); }, 20000);
chrome.alarms.create("lanterna-link", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(a => { if (a.name === "lanterna-link") connect(); });
chrome.runtime.onStartup.addListener(() => connect(true));
chrome.runtime.onInstalled.addListener(async () => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "ask-page", title: chrome.i18n.getMessage("ask_page"), contexts: ["page"] });
    chrome.contextMenus.create({ id: "ask-selection", title: chrome.i18n.getMessage("ask_selection"), contexts: ["selection"] });
    chrome.contextMenus.create({ id: "ask-link", title: chrome.i18n.getMessage("ask_link"), contexts: ["link"] });
  });
  connect(true);
});
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
connect(true);

// ---------------------------------------------------------------- the side panel and the page's Stop button
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.t === "panel_hello") {
    connect(true).then(() => reply(publicState()));
    return true;
  }
  if (msg.t === "panel_state") { reply(publicState()); return false; }
  if (msg.t === "pair_again") { pairAgain().then(() => reply(publicState())); return true; }
  if (msg.t === "stop") { send({ t: "event", what: "stop", tab: sender.tab && sender.tab.id }); hideAll(); return false; }
  if (msg.t === "record_step") { recordStep(sender, msg.step); return false; }
  if (msg.t === "record_stop") {
    // Lanterna takes the steps with its record_stop command; without Lanterna there is nobody to give them to
    if (ws && state.status === "ready") send({ t: "event", what: "record_stop" }); else stopRecording();
    return false;
  }
  if (msg.t === "panel_open") { send({ t: "event", what: "panel", open: true }); return false; }
  return false;
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  try { await chrome.sidePanel.open({ windowId: tab.windowId }); } catch (e) {}
  const ask = info.menuItemId === "ask-selection" ? { kind: "selection", text: info.selectionText || "" }
    : info.menuItemId === "ask-link" ? { kind: "link", url: info.linkUrl || "" } : { kind: "page" };
  await chrome.storage.session.set({ ask: { ...ask, tab: tab.id, title: tab.title, page: tab.url, at: Date.now() } });
  chrome.runtime.sendMessage({ t: "ask", ask }).catch(() => {});
  send({ t: "event", what: "ask", ask: { ...ask, title: tab.title, page: tab.url } });
});

// the tab the user looks at: Lanterna's side panel shows it, and "this page" means it
async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab ? tabInfo(tab) : null;
}
chrome.tabs.onActivated.addListener(async () => send({ t: "event", what: "tab", tab: await activeTab() }));
chrome.tabs.onUpdated.addListener(async (id, ch, tab) => {
  if (ch.status === "complete" && tab.active) send({ t: "event", what: "tab", tab: tabInfo(tab) });
});

// ---------------------------------------------------------------- tabs, the "Lanterna" group
let groupId = null;

function tabInfo(t) {
  return { id: t.id, title: t.title || "", url: t.url || t.pendingUrl || "", active: !!t.active,
    lanterna: groupId != null && t.groupId === groupId, window: t.windowId, loading: t.status === "loading" };
}

async function findGroup(windowId) {
  if (groupId != null) {
    try { const g = await chrome.tabGroups.get(groupId); if (g && g.windowId === windowId) return groupId; } catch (e) {}
  }
  const gs = await chrome.tabGroups.query({ title: GROUP_TITLE, windowId });
  groupId = gs.length ? gs[0].id : null;
  return groupId;
}

async function joinGroup(tabId) {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (tab.groupId !== -1 && tab.groupId !== await findGroup(tab.windowId)) return;   // the user's own group: leave it
    const g = await findGroup(tab.windowId);
    if (g != null) await chrome.tabs.group({ tabIds: [tabId], groupId: g });
    else {
      groupId = await chrome.tabs.group({ tabIds: [tabId], createProperties: { windowId: tab.windowId } });
      await chrome.tabGroups.update(groupId, { title: GROUP_TITLE, color: GROUP_COLOR });
    }
  } catch (e) { /* a tab of an app window or a pinned tab can't be grouped: the edge still shows */ }
}

async function pickTab(id) {
  if (id != null && id !== "" && id !== "active") {
    try { return await chrome.tabs.get(+id); } catch (e) { throw new Error(`no tab ${id}: call browser_tabs for the tabs there are now`); }
  }
  const [t] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!t) throw new Error("no tab is open");
  return t;
}

function hostOf(url) {
  try { return new URL(url).hostname; } catch (e) { return ""; }
}

function okUrl(url) {
  const u = new URL(url);
  if (!/^https?:$/.test(u.protocol)) throw new Error("only http and https addresses can be opened");
  return u.href;
}

async function waitLoaded(tabId, ms = 20000) {
  const end = Date.now() + ms;
  await sleep(150);
  while (Date.now() < end) {
    let t;
    try { t = await chrome.tabs.get(tabId); } catch (e) { return null; }
    if (t.status === "complete") { await sleep(250); return t; }
    await sleep(200);
  }
  return chrome.tabs.get(tabId).catch(() => null);
}

// ---------------------------------------------------------------- the page script and frames
async function inject(tabId) {
  await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, files: ["page.js"] }).catch(() => {});
}

// Chrome's own pages, other extensions' pages and the Web Store are closed to every extension; local files only
// with «Allow access to file URLs». Said in words, so the model doesn't take the page for an empty one.
function pageError(e) {
  const m = String((e && e.message) || e);
  if (/^Cannot access contents of url "file:/i.test(m))
    return new Error("Lanterna can't read files opened in Chrome unless «Allow access to file URLs» is on in its extension's details (chrome://extensions). Ask the user, or read the file with Lanterna's own file tools.");
  if (/chrome:\/\/|chrome-extension:\/\/|edge:\/\/|extensions gallery|cannot be scripted|Cannot access contents of url "(about|view-source|devtools|chrome)/i.test(m))
    return new Error("This tab shows a page no extension may read or change (one of Chrome's own pages, another extension's page, or the Chrome Web Store). Open a normal site, or ask the user to do this step.");
  return e instanceof Error ? e : new Error(m);
}

async function inPage(tabId, fn, args = [], frameId = 0) {
  let r;
  try {
    await chrome.scripting.executeScript({ target: { tabId, frameIds: [frameId] }, files: ["page.js"] });
    [r] = await chrome.scripting.executeScript({ target: { tabId, frameIds: [frameId] }, func: fn, args });
  } catch (e) {
    throw pageError(e);
  }
  if (r && r.error) throw new Error(r.error.message || String(r.error));
  return r ? r.result : null;
}

async function inFrames(tabId, fn, args = []) {
  await inject(tabId);
  let res;
  try {             // frames Lanterna may not touch are left out; the page itself closed is an error
    res = await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, func: fn, args });
  } catch (e) {
    throw pageError(e);
  }
  return res.filter(r => r && r.result);
}

// the field with the cursor, in whatever frame it is: Lanterna never types into a password or card field
async function secretFocus(tabId) {
  const res = await inFrames(tabId, () => globalThis.__lanternaPage ? globalThis.__lanternaPage.focused() : null);
  const top = res.find(r => r.frameId === 0);
  if (res.some(r => r.result && r.result.secret)) throw new Error("secret");
  return top ? top.result : null;
}

// a ref of a frame other than the top page is written "<frame>:eN"
function splitRef(ref) {
  const m = /^(?:(\d+):)?(e\d+)$/.exec(String(ref || "").trim());
  if (!m) throw new Error(`"${ref}" is not an element name: use one like e12 from browser_read or browser_find`);
  return { frame: m[1] ? +m[1] : 0, ref: m[2] };
}

// ---------------------------------------------------------------- real input (the debugger), console and network
const attached = new Map();      // tabId → { console: [], network: Map, lastUse, timer }

async function attach(tabId) {
  let a = attached.get(tabId);
  if (!a) {
    await chrome.debugger.attach({ tabId }, "1.3");
    a = { console: [], network: new Map(), order: [], lastUse: Date.now(), timer: null };
    attached.set(tabId, a);
    await cdp(tabId, "Runtime.enable").catch(() => {});
    await cdp(tabId, "Log.enable").catch(() => {});
    await cdp(tabId, "Network.enable", { maxPostDataSize: 0 }).catch(() => {});
    await cdp(tabId, "Page.enable").catch(() => {});
  }
  a.lastUse = Date.now();
  clearTimeout(a.timer);
  a.timer = setTimeout(() => detach(tabId), IDLE_DETACH_MS);
  return a;
}

async function detach(tabId) {
  const a = attached.get(tabId);
  if (!a) return;
  if (Date.now() - a.lastUse < IDLE_DETACH_MS - 1000) return;
  attached.delete(tabId);
  await chrome.debugger.detach({ tabId }).catch(() => {});
}

function cdp(tabId, method, params = {}) {
  const p = chrome.debugger.sendCommand({ tabId }, method, params);
  if (!method.startsWith("Input.")) return p;
  // a click or a key waits until Chrome draws the page: never, in a minimized window
  return withTimeout(p, 8000).catch(e => {
    throw /timed out/.test(String(e && e.message)) ? new Error("Chrome didn't take Lanterna's click or key: its window may be minimized. Ask the user to bring Chrome's window up, then try again.") : e;
  });
}

// trusted input (the debugger's clicks and keys) reaches only a tab Chrome draws: the one in front of its window
async function front(t) {
  if (t.active) return t;
  await chrome.tabs.update(t.id, { active: true });
  await sleep(250);
  return chrome.tabs.get(t.id);
}

chrome.debugger.onDetach.addListener((src, reason) => {
  if (src.tabId != null) attached.delete(src.tabId);
  if (reason === "canceled_by_user") send({ t: "event", what: "stop", reason: "debugger", tab: src.tabId });
});

chrome.debugger.onEvent.addListener((src, method, p) => {
  const a = attached.get(src.tabId);
  if (!a) return;
  if (method === "Runtime.consoleAPICalled") {
    const text = (p.args || []).map(x => x.value !== undefined ? (typeof x.value === "string" ? x.value : JSON.stringify(x.value)) : x.description || x.type).join(" ");
    a.console.push({ level: p.type, text: text.slice(0, 2000), at: p.timestamp });
  } else if (method === "Runtime.exceptionThrown") {
    const d = p.exceptionDetails || {};
    a.console.push({ level: "error", text: ((d.exception && d.exception.description) || d.text || "exception").slice(0, 2000), at: p.timestamp });
  } else if (method === "Log.entryAdded") {
    a.console.push({ level: p.entry.level, text: `${p.entry.text || ""} ${p.entry.url || ""}`.slice(0, 2000), at: p.entry.timestamp });
  } else if (method === "Network.requestWillBeSent") {
    a.network.set(p.requestId, { id: p.requestId, url: p.request.url, method: p.request.method, type: p.type || "", status: 0 });
    a.order.push(p.requestId);
  } else if (method === "Network.responseReceived") {
    const r = a.network.get(p.requestId);
    if (r) { r.status = p.response.status; r.mime = p.response.mimeType; }
  } else if (method === "Network.loadingFailed") {
    const r = a.network.get(p.requestId);
    if (r) r.failed = p.errorText;
  }
  if (a.console.length > 300) a.console.splice(0, a.console.length - 300);
  if (a.order.length > 400) {
    for (const id of a.order.splice(0, a.order.length - 400)) a.network.delete(id);
  }
});

const KEYS = {
  enter: ["Enter", "Enter", 13, "\r"], tab: ["Tab", "Tab", 9], escape: ["Escape", "Escape", 27], esc: ["Escape", "Escape", 27],
  backspace: ["Backspace", "Backspace", 8], delete: ["Delete", "Delete", 46], space: [" ", "Space", 32, " "],
  arrowup: ["ArrowUp", "ArrowUp", 38], arrowdown: ["ArrowDown", "ArrowDown", 40], arrowleft: ["ArrowLeft", "ArrowLeft", 37],
  arrowright: ["ArrowRight", "ArrowRight", 39], up: ["ArrowUp", "ArrowUp", 38], down: ["ArrowDown", "ArrowDown", 40],
  left: ["ArrowLeft", "ArrowLeft", 37], right: ["ArrowRight", "ArrowRight", 39], home: ["Home", "Home", 36], end: ["End", "End", 35],
  pageup: ["PageUp", "PageUp", 33], pagedown: ["PageDown", "PageDown", 34],
  f5: ["F5", "F5", 116],
};

function parseKey(s) {
  const parts = String(s).split("+").map(x => x.trim()).filter(Boolean);
  let mods = 0;
  let key = parts.pop() || "";
  for (const p of parts) {
    const l = p.toLowerCase();
    if (l === "alt") mods |= 1; else if (l === "ctrl" || l === "control") mods |= 2;
    else if (l === "meta" || l === "cmd" || l === "win") mods |= 4; else if (l === "shift") mods |= 8;
  }
  const k = KEYS[key.toLowerCase()];
  if (k) return { key: k[0], code: k[1], vk: k[2], text: mods & ~8 ? "" : k[3] || "", mods };
  if (key.length === 1) {
    const up = key.toUpperCase();
    const code = /[A-Z]/.test(up) ? "Key" + up : /[0-9]/.test(key) ? "Digit" + key : "";
    return { key, code, vk: up.charCodeAt(0), text: mods & ~8 ? "" : key, mods };
  }
  throw new Error(`unknown key "${key}"`);
}

async function pressKey(tabId, s) {
  const k = parseKey(s);
  const base = { modifiers: k.mods, key: k.key, code: k.code, windowsVirtualKeyCode: k.vk, nativeVirtualKeyCode: k.vk };
  await cdp(tabId, "Input.dispatchKeyEvent", { type: k.text ? "keyDown" : "rawKeyDown", text: k.text || undefined, unmodifiedText: k.text || undefined, ...base });
  await cdp(tabId, "Input.dispatchKeyEvent", { type: "keyUp", ...base });
}

async function mouse(tabId, type, x, y, extra = {}) {
  await cdp(tabId, "Input.dispatchMouseEvent", { type, x, y, button: extra.button || "none", clickCount: extra.clickCount || 0,
    modifiers: extra.modifiers || 0, deltaX: extra.deltaX || 0, deltaY: extra.deltaY || 0, buttons: extra.buttons || 0 });
}

async function clickAt(tabId, x, y, button = "left", count = 1) {
  await mouse(tabId, "mouseMoved", x, y);
  for (let i = 1; i <= count; i++) {
    await mouse(tabId, "mousePressed", x, y, { button, clickCount: i, buttons: button === "right" ? 2 : 1 });
    await mouse(tabId, "mouseReleased", x, y, { button, clickCount: i });
  }
}

// ---------------------------------------------------------------- showing where Lanterna works
const lit = new Set();
let hideTimer = null;

async function show(tabId) {
  lit.add(tabId);
  clearTimeout(hideTimer);
  hideTimer = setTimeout(hideAll, 20000);
  await joinGroup(tabId);
  chrome.action.setBadgeText({ tabId, text: "●" }).catch(() => {});
  chrome.action.setBadgeBackgroundColor({ tabId, color: "#F5B544" }).catch(() => {});
  await inPage(tabId, (w) => globalThis.__lanternaPage.overlay(true, w), [{
    text: words("working", "Lanterna is working in this tab"), stop: words("stop", "Stop") }]).catch(() => {});
}

async function hideAll() {
  clearTimeout(hideTimer);
  for (const id of [...lit]) {
    lit.delete(id);
    chrome.action.setBadgeText({ tabId: id, text: "" }).catch(() => {});
    if (recording && recording.tab === id) continue;
    inPage(id, () => globalThis.__lanternaPage.overlay(false)).catch(() => {});
  }
}

// ---------------------------------------------------------------- downloads Lanterna started by a click
let acting = 0;              // when Lanterna last acted: a download right after it is held until Lanterna says
const lately = [];           // …and named in the click's answer, so the model knows the file came
const held = new Set();      // the ones waiting for Lanterna's answer (the user's card, or a quiet OK)
chrome.downloads.onCreated.addListener(async item => {
  if (Date.now() - acting > 4000 || !ws) return;
  lately.push({ id: item.id, at: Date.now(), url: item.finalUrl || item.url || "" });
  if (lately.length > 20) lately.shift();
  if (state.mode === "full") return;
  held.add(item.id);
  try { await chrome.downloads.pause(item.id); } catch (e) { held.delete(item.id); return; }
  send({ t: "event", what: "download", item: { id: item.id, url: item.finalUrl || item.url, name: item.filename || "", size: item.totalBytes || 0 } });
});

async function downloadsSince(since) {
  const out = [];
  const start = Date.now();             // a small file is done in a moment: then the model can say it came
  for (const d of lately.filter(x => x.at >= since)) {
    let it;
    for (;;) {                          // (one held for the user's card waits less: the card can take minutes)
      [it] = await chrome.downloads.search({ id: d.id }).catch(() => []);
      const waiting = held.has(d.id);   // (a small file can be whole while it waits: the card still decides)
      if (!it || Date.now() - start > (waiting ? 1000 : 2500) || (!waiting && it.state !== "in_progress")) break;
      await sleep(250);
    }
    let name = ((it && it.filename) || "").split(/[\\/]/).pop();
    if (!name) { try { name = decodeURIComponent(new URL(d.url).pathname.split("/").pop()); } catch (e) { name = ""; } }
    out.push({ name: name || "file", state: held.has(d.id) ? "held" : it ? it.state : "in_progress" });
  }
  return out;
}

// ---------------------------------------------------------------- recording the user's steps
let recording = null;        // { tab, steps: [] }

async function startRecording(tabId) {
  recording = { tab: tabId, steps: [], started: Date.now() };
  const t = await chrome.tabs.get(tabId);
  recording.steps.push({ kind: "open", url: t.url, title: t.title });
  await inPage(tabId, () => globalThis.__lanternaPage.recStart());
  await inPage(tabId, (w) => globalThis.__lanternaPage.overlay(true, w), [{
    text: words("recording", "Lanterna is recording your steps"), stop: words("stop_recording", "Stop recording"), rec: true }]);
}

function recordStep(sender, step) {
  if (!recording || !sender.tab || sender.tab.id !== recording.tab) return;
  const last = recording.steps[recording.steps.length - 1];
  if (last && last.kind === step.kind && last.name === step.name && step.kind === "input") last.value = step.value;
  else recording.steps.push(step);
  if (recording.steps.length > 200) recording.steps.shift();
}

chrome.webNavigation.onCommitted.addListener(async d => {
  if (!recording || d.tabId !== recording.tab || d.frameId !== 0) return;
  // an address typed or picked from bookmarks is a step; a page a click opened follows from that click
  if (d.transitionType === "typed" || d.transitionType === "auto_bookmark" || d.transitionType === "generated") {
    recording.steps.push({ kind: "open", url: d.url });
  }
  await sleep(600);
  await inPage(d.tabId, () => globalThis.__lanternaPage.recStart()).catch(() => {});
  await inPage(d.tabId, (w) => globalThis.__lanternaPage.overlay(true, w), [{
    text: words("recording", "Lanterna is recording your steps"), stop: words("stop_recording", "Stop recording"), rec: true }]).catch(() => {});
});

async function stopRecording() {
  if (!recording) return { steps: [] };
  const r = recording;
  recording = null;
  await inPage(r.tab, () => { globalThis.__lanternaPage.recStop(); globalThis.__lanternaPage.overlay(false); }).catch(() => {});
  return { steps: r.steps, tab: r.tab };
}

// ---------------------------------------------------------------- the commands
async function run(cmd, a) {
  switch (cmd) {
    case "status": return { version: chrome.runtime.getManifest().version, tab: await activeTab() };

    case "tabs": {
      const tabs = await chrome.tabs.query({});
      const win = (await chrome.windows.getLastFocused().catch(() => null)) || {};
      for (const t of tabs) if (t.groupId !== -1 && groupId == null) await findGroup(t.windowId);
      return { tabs: tabs.filter(t => t.windowId === win.id || t.groupId === groupId).slice(0, 40).map(tabInfo), window: win.id };
    }

    case "open": {
      const url = okUrl(a.url);
      const win = await chrome.windows.getLastFocused({ windowTypes: ["normal"] }).catch(() => null);
      const t = await chrome.tabs.create({ url, active: a.active !== false, windowId: win ? win.id : undefined });
      await joinGroup(t.id);
      const done = await waitLoaded(t.id);
      await show(t.id);
      return tabInfo(done || t);
    }

    case "go": {
      const t = await pickTab(a.tab);
      acting = Date.now();
      if (a.to === "back") await chrome.tabs.goBack(t.id);
      else if (a.to === "forward") await chrome.tabs.goForward(t.id);
      else if (a.to === "reload") await chrome.tabs.reload(t.id);
      else await chrome.tabs.update(t.id, { url: okUrl(a.to) });
      const done = await waitLoaded(t.id);
      await show(t.id);
      return tabInfo(done || t);
    }

    case "switch": {
      const t = await pickTab(a.tab);
      await chrome.tabs.update(t.id, { active: true });
      await chrome.windows.update(t.windowId, { focused: true }).catch(() => {});
      return tabInfo(await chrome.tabs.get(t.id));
    }

    case "close": {
      const t = await pickTab(a.tab);
      await chrome.tabs.remove(t.id);
      return { closed: t.id };
    }

    case "info": {
      const t = await pickTab(a.tab);
      return tabInfo(t);
    }

    case "snapshot": {
      const t = await pickTab(a.tab);
      const res = await inFrames(t.id, (o) => globalThis.__lanternaPage ? globalThis.__lanternaPage.snapshot(o) : null, [{ max: a.max, all: a.all }]);
      const top = res.find(r => r.frameId === 0);
      if (!top) throw new Error("this page can't be read (a browser page, the web store, or it is still loading)");
      const frames = res.filter(r => r.frameId !== 0 && r.result.lines.length > 1).slice(0, 6).map(r => ({
        frame: r.frameId, url: r.result.url, lines: r.result.lines.map(l => l.replace(/\[(e\d+)\]/g, `[${r.frameId}:$1]`)) }));
      if (a.show !== false) await show(t.id);
      return { tab: tabInfo(t), ...top.result, frames };
    }

    case "text": {
      const t = await pickTab(a.tab);
      const res = await inFrames(t.id, (o) => globalThis.__lanternaPage ? globalThis.__lanternaPage.text(o) : null, [{ max: a.max }]);
      const top = res.find(r => r.frameId === 0);
      if (!top) throw new Error("this page can't be read");
      const frames = res.filter(r => r.frameId !== 0 && r.result.text.length > 200).slice(0, 4).map(r => ({ frame: r.frameId, url: r.result.url, text: r.result.text.slice(0, 6000) }));
      return { tab: tabInfo(t), ...top.result, frames };
    }

    case "find": {
      const t = await pickTab(a.tab);
      const res = await inFrames(t.id, (q) => globalThis.__lanternaPage ? globalThis.__lanternaPage.find(q) : null, [a.query]);
      const hits = [];
      for (const r of res) for (const h of r.result.hits) hits.push(r.frameId ? h.replace(/\[(e\d+)\]/, `[${r.frameId}:$1]`) : h);
      return { tab: tabInfo(t), hits: hits.slice(0, 25) };
    }

    case "inspect": {
      const t = await pickTab(a.tab);
      const site = hostOf(t.url);
      if (a.focused) {
        const f = await inPage(t.id, () => globalThis.__lanternaPage.focused());
        return { ...(f || {}), frame: 0, tab: t.id, site, url: t.url };
      }
      if (a.ref) {
        const { frame, ref } = splitRef(a.ref);
        const i = await inPage(t.id, (r) => globalThis.__lanternaPage.inspect({ ref: r }), [ref], frame);
        if (i && i.error) throw new Error(`element ${a.ref} is not on the page any more: call browser_read again`);
        return { ...i, frame, tab: t.id, site };
      }
      const i = await inPage(t.id, (x, y) => globalThis.__lanternaPage.inspect({ x, y }), [+a.x, +a.y]);
      return { ...i, frame: 0, tab: t.id, site };
    }

    case "click": {
      const t = await front(await pickTab(a.tab));
      await show(t.id);
      acting = Date.now();
      const since = acting;
      const button = a.button || "left", count = Math.max(1, Math.min(3, +a.count || 1));
      if (a.ref) {
        const { frame, ref } = splitRef(a.ref);
        if (frame) return { ...(await inPage(t.id, (r) => globalThis.__lanternaPage.clickDom(r), [ref], frame)), how: "page" };
        const i = await inPage(t.id, (r) => globalThis.__lanternaPage.reveal(r), [ref]);
        if (!i || i.error) throw new Error(`element ${a.ref} is not on the page any more: call browser_read again`);
        await attach(t.id);
        await clickAt(t.id, i.x, i.y, button, count);
      } else {
        await attach(t.id);
        await clickAt(t.id, +a.x, +a.y, button, count);
      }
      await sleep(400);
      const after = await waitLoaded(t.id, 8000);
      return { tab: tabInfo(after || t), downloads: await downloadsSince(since) };
    }

    case "hover": {
      const t = await front(await pickTab(a.tab));
      await show(t.id);
      let x = +a.x, y = +a.y;
      if (a.ref) {
        const { ref } = splitRef(a.ref);
        const i = await inPage(t.id, (r) => globalThis.__lanternaPage.reveal(r), [ref]);
        if (!i || i.error) throw new Error(`element ${a.ref} is not on the page any more`);
        x = i.x; y = i.y;
      }
      await attach(t.id);
      await mouse(t.id, "mouseMoved", x, y);
      await sleep(300);
      return { ok: true };
    }

    case "drag": {
      const t = await front(await pickTab(a.tab));
      await show(t.id);
      await attach(t.id);
      const pos = async (ref, x, y) => {
        if (!ref) return [+x, +y];
        const i = await inPage(t.id, (r) => globalThis.__lanternaPage.reveal(r), [splitRef(ref).ref]);
        if (!i || i.error) throw new Error(`element ${ref} is not on the page any more`);
        return [i.x, i.y];
      };
      const [x1, y1] = await pos(a.ref, a.x, a.y);
      const [x2, y2] = await pos(a.to_ref, a.to_x, a.to_y);
      acting = Date.now();
      await mouse(t.id, "mouseMoved", x1, y1);
      await mouse(t.id, "mousePressed", x1, y1, { button: "left", clickCount: 1, buttons: 1 });
      for (let i = 1; i <= 8; i++) await mouse(t.id, "mouseMoved", x1 + (x2 - x1) * i / 8, y1 + (y2 - y1) * i / 8, { buttons: 1 });
      await mouse(t.id, "mouseReleased", x2, y2, { button: "left", clickCount: 1 });
      return { ok: true };
    }

    case "type": {
      const t = await front(await pickTab(a.tab));
      await show(t.id);
      acting = Date.now();
      if (a.ref) {
        const { frame, ref } = splitRef(a.ref);
        if (frame) return await inPage(t.id, (r, v, c) => globalThis.__lanternaPage.typeDom(r, v, c), [ref, String(a.text), !!a.clear], frame);
        const i = await inPage(t.id, (r) => globalThis.__lanternaPage.reveal(r), [ref]);
        if (!i || i.error) throw new Error(`element ${a.ref} is not on the page any more: call browser_read again`);
        if (i.secret) throw new Error("secret");
        await attach(t.id);
        await clickAt(t.id, i.x, i.y);
      } else {
        await attach(t.id);
      }
      const f = await secretFocus(t.id);
      if (a.clear) { await pressKey(t.id, "ctrl+a"); await pressKey(t.id, "Delete"); }
      await cdp(t.id, "Input.insertText", { text: String(a.text) });
      if (a.enter) { await pressKey(t.id, "Enter"); await sleep(500); await waitLoaded(t.id, 8000); }
      return { ok: true, field: f };
    }

    case "key": {
      const t = await front(await pickTab(a.tab));
      await show(t.id);
      await attach(t.id);
      acting = Date.now();
      if (a.ref) {
        const { frame, ref } = splitRef(a.ref);
        const i = await inPage(t.id, (r) => globalThis.__lanternaPage.focusRef(r), [ref], frame);
        if (!i || i.error) throw new Error(`element ${a.ref} is not on the page any more: call browser_read again`);
      }
      const typing = String(a.keys || "").split(/\s+/).some(k => !/^(shift\+)?(tab|escape|esc|arrow\w+|up|down|left|right|pageup|pagedown|home|end)$/i.test(k));
      if (typing) await secretFocus(t.id);
      const list = String(a.keys || "").split(/\s+/).filter(Boolean).slice(0, 30);
      const n = Math.max(1, Math.min(50, +a.repeat || 1));
      for (let i = 0; i < n; i++) for (const k of list) await pressKey(t.id, k);
      await sleep(300);
      return { ok: true };
    }

    case "scroll": {
      const t = await front(await pickTab(a.tab));
      await show(t.id);
      if (a.ref) {
        const { frame, ref } = splitRef(a.ref);
        return await inPage(t.id, (r) => globalThis.__lanternaPage.reveal(r), [ref], frame);
      }
      await attach(t.id);
      const amount = Math.max(1, Math.min(10, +a.amount || 3)) * 120;
      const dir = a.direction || "down";
      const [w, h] = await inPage(t.id, () => [innerWidth, innerHeight]);
      const x = a.x != null ? +a.x : w / 2, y = a.y != null ? +a.y : h / 2;
      await mouse(t.id, "mouseWheel", x, y, { deltaX: dir === "left" ? -amount : dir === "right" ? amount : 0, deltaY: dir === "up" ? -amount : dir === "down" ? amount : 0 });
      await sleep(350);
      return { ok: true };
    }

    case "fill": {
      const t = await pickTab(a.tab);
      await show(t.id);
      acting = Date.now();
      const out = [];
      for (const f of (a.fields || []).slice(0, 40)) {
        const { frame, ref } = splitRef(f.ref);
        out.push({ ref: f.ref, ...(await inPage(t.id, (r, v) => globalThis.__lanternaPage.fill(r, v), [ref, f.value], frame)) });
      }
      return { fields: out };
    }

    case "screenshot": {
      const t = await pickTab(a.tab);
      if (!t.active) { await chrome.tabs.update(t.id, { active: true }); await sleep(400); }
      await attach(t.id);
      const m = await cdp(t.id, "Page.getLayoutMetrics");
      const vp = m.cssVisualViewport || m.visualViewport;
      const width = vp.clientWidth, height = vp.clientHeight;
      let clip = { x: vp.pageX, y: vp.pageY, width, height };
      let scale = Math.min(1, 1280 / width);
      if (a.region) {
        const [x0, y0, x1, y1] = a.region.map(Number);
        clip = { x: vp.pageX + x0, y: vp.pageY + y0, width: Math.max(8, x1 - x0), height: Math.max(8, y1 - y0) };
        scale = Math.min(3, 1000 / clip.width);
      }
      const veil = (hide) => inPage(t.id, (h) => globalThis.__lanternaPage.veil(h), [hide]).catch(() => {});
      await veil(true);                         // the model sees the page, not Lanterna's frame and bar over it
      let shot;
      try {
        shot = await cdp(t.id, "Page.captureScreenshot", { format: "jpeg", quality: 70, clip: { ...clip, scale } });
      } finally {
        await veil(false);
      }
      return { tab: tabInfo(t), image: "data:image/jpeg;base64," + shot.data, width: Math.round(clip.width * scale), height: Math.round(clip.height * scale), scale, view: [width, height] };
    }

    case "js": {
      const t = await pickTab(a.tab);
      await show(t.id);
      await attach(t.id);
      acting = Date.now();
      const r = await cdp(t.id, "Runtime.evaluate", { expression: String(a.code), awaitPromise: true, returnByValue: true, replMode: true, timeout: 15000, userGesture: true });
      if (r.exceptionDetails) {
        const d = r.exceptionDetails;
        return { error: ((d.exception && d.exception.description) || d.text || "error").slice(0, 1500) };
      }
      const v = r.result;
      let text;
      if (v.type === "undefined") text = "undefined";
      else if (v.value !== undefined) text = typeof v.value === "string" ? v.value : JSON.stringify(v.value, null, 1);
      else text = v.description || v.type;
      return { value: String(text) };
    }

    case "console": {
      const t = await pickTab(a.tab);
      const at = await attach(t.id);
      let list = at.console.slice();
      if (a.pattern) { const re = new RegExp(a.pattern, "i"); list = list.filter(x => re.test(x.text)); }
      if (a.errors) list = list.filter(x => /error|warn/i.test(x.level));
      if (a.clear) at.console.length = 0;
      return { tab: tabInfo(t), messages: list.slice(-(+a.limit || 60)) };
    }

    case "network": {
      const t = await pickTab(a.tab);
      const at = await attach(t.id);
      if (a.id) {
        const body = await cdp(t.id, "Network.getResponseBody", { requestId: a.id }).catch(e => ({ body: "", error: String(e.message || e) }));
        return { body: (body.base64Encoded ? "(binary)" : body.body || "").slice(0, 20000), error: body.error || "" };
      }
      let list = at.order.map(id => at.network.get(id)).filter(Boolean);
      if (a.pattern) list = list.filter(x => x.url.includes(a.pattern));
      if (a.clear) { at.order.length = 0; at.network.clear(); }
      return { tab: tabInfo(t), requests: list.slice(-(+a.limit || 60)) };
    }

    case "resize": {
      const t = await pickTab(a.tab);
      await chrome.windows.update(t.windowId, { width: Math.max(400, +a.width), height: Math.max(300, +a.height), state: "normal" });
      return { ok: true };
    }

    case "upload": {
      const t = await pickTab(a.tab);
      await show(t.id);
      const { frame, ref } = splitRef(a.ref);
      if (frame) throw new Error("files can be given only to a field of the page itself, not of a frame inside it");
      const mark = "lt" + Math.random().toString(36).slice(2);
      // the page script marks the field for a moment, so the debugger can find the same element
      const ok = await inPage(t.id, (r, m) => globalThis.__lanternaPage.mark(r, m), [ref, mark]);
      if (!ok) throw new Error("this element doesn't take files: use a file field (file input) from browser_read");
      await attach(t.id);
      const doc = await cdp(t.id, "DOM.getDocument", { depth: 0 });
      const q = await cdp(t.id, "DOM.querySelector", { nodeId: doc.root.nodeId, selector: `[data-lanterna-mark="${mark}"]` });
      if (!q.nodeId) throw new Error("the file field wasn't found");
      await cdp(t.id, "DOM.setFileInputFiles", { nodeId: q.nodeId, files: a.files });
      await inPage(t.id, (m) => { const el = document.querySelector(`[data-lanterna-mark="${m}"]`); if (el) el.removeAttribute("data-lanterna-mark"); }, [mark]);
      return { ok: true };
    }

    case "wait": {
      await sleep(Math.max(100, Math.min(10000, (+a.seconds || 1) * 1000)));
      const t = await pickTab(a.tab).catch(() => null);
      return t ? { tab: tabInfo(t) } : { ok: true };
    }

    case "selection": {
      const t = await pickTab(a.tab);
      return await inPage(t.id, () => globalThis.__lanternaPage.selection());
    }

    case "download": {
      const id = +a.id;
      held.delete(id);
      if (a.allow) { await chrome.downloads.resume(id).catch(() => {}); return { ok: true }; }
      const [it] = await chrome.downloads.search({ id }).catch(() => []);
      if (it && it.state === "complete") {
        // a small file can be whole before Lanterna holds it: the user said no, so it doesn't stay
        await chrome.downloads.removeFile(id).catch(() => {});
        await chrome.downloads.erase({ id }).catch(() => {});
        return { ok: true, removed: true };
      }
      await chrome.downloads.cancel(id).catch(() => {});
      return { ok: true };
    }

    case "idle": { await hideAll(); return { ok: true }; }

    case "record_start": {
      const t = await pickTab(a.tab);
      await startRecording(t.id);
      return { ok: true, tab: tabInfo(t) };
    }

    case "record_stop": return await stopRecording();

    case "reload_extension": { setTimeout(() => chrome.runtime.reload(), 300); return { ok: true }; }

    default: throw new Error(`unknown command ${cmd}`);
  }
}
