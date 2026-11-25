"use strict";
// The side panel: Lanterna's own chat (from the app on this computer) when it runs, a short note when it doesn't.
const $ = id => document.getElementById(id);
const msg = (k, ...a) => chrome.i18n.getMessage(k, a) || k;
const frame = $("ui");
let shownUi = "";

function render(s) {
  if (s && s.status === "ready" && s.ui) {
    $("off").hidden = true;
    frame.hidden = false;
    if (shownUi !== s.ui) { shownUi = s.ui; frame.src = s.ui; }
    return;
  }
  frame.hidden = true;
  shownUi = "";
  frame.removeAttribute("src");
  $("off").hidden = false;
  const reset = s && s.status === "reset", pair = s && s.status === "pair";
  $("h").textContent = msg(reset ? "reset_title" : pair ? "pair_title" : "off_title");
  $("p").textContent = msg(reset ? "reset_text" : pair ? "pair_text" : "off_text");
  $("go").textContent = msg(reset ? "connect" : "retry");
  $("more").textContent = msg("what");
  $("more").hidden = reset || pair;
  $("go").onclick = () => chrome.runtime.sendMessage({ t: reset ? "pair_again" : "panel_hello" }).then(render).catch(() => {});
}

chrome.runtime.onMessage.addListener(m => {
  if (m.t === "state") render(m.state);
  if (m.t === "ask") forwardAsk(m.ask);
});

// "Ask Lanterna about this" from the page's menu: the chat box gets the question
async function forwardAsk(ask) {
  if (!ask) return;
  for (let i = 0; i < 40 && (frame.hidden || !frame.contentWindow); i++) await new Promise(r => setTimeout(r, 250));
  if (frame.contentWindow && shownUi) frame.contentWindow.postMessage({ lanterna: "ask", ask }, new URL(shownUi).origin);
}

frame.addEventListener("load", async () => {
  const { ask } = await chrome.storage.session.get("ask");
  if (ask && Date.now() - ask.at < 15000) {
    await chrome.storage.session.remove("ask");
    forwardAsk(ask);
  }
});

chrome.runtime.sendMessage({ t: "panel_hello" }).then(render).catch(() => render(null));
chrome.runtime.sendMessage({ t: "panel_open" }).catch(() => {});
setInterval(() => { if (!$("off").hidden) chrome.runtime.sendMessage({ t: "panel_hello" }).then(render).catch(() => {}); }, 4000);
