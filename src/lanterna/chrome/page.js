// Lanterna in a web page: reads it for the model (elements get short names like e12), finds things, fills
// forms, shows that Lanterna works in this tab, and records the user's steps. It runs in the extension's own
// isolated world, so the page can't call it. Nothing here sends anything anywhere: the background script asks
// for one result at a time and gives it to Lanterna on this computer.
(() => {
  // a tab keeps this script after the extension reloads (Lanterna updated it): a newer one takes over
  const V = chrome.runtime.getManifest().version;
  const before = globalThis.__lanternaPage;
  if (before && before.v === V) return;
  if (before) {
    try { before.recStop(); } catch (e) { /* the old one may not reach the extension any more */ }
    document.querySelectorAll("lanterna-indicator").forEach(x => x.remove());
  }

  const MAX_NODES = 6000;
  const refs = new Map();              // "e12" → WeakRef(element)
  const known = new WeakMap();         // element → "e12": the same element keeps its name between looks
  let next = 1;

  const INTERACTIVE_ROLES = new Set(["button", "link", "checkbox", "radio", "tab", "menuitem", "menuitemcheckbox",
    "menuitemradio", "option", "switch", "combobox", "textbox", "searchbox", "slider", "spinbutton", "treeitem",
    "gridcell", "listbox", "menu", "row"]);
  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "SVG", "PATH", "META", "LINK", "HEAD"]);
  const CARD_HINT = /\b(cc-|card|cvv|cvc|csc|iban|expir|securitycode|kartk|karte|carta|tarjeta|carte)/i;

  function refOf(el) {
    let r = known.get(el);
    if (!r) {
      r = "e" + next++;
      known.set(el, r);
      refs.set(r, new WeakRef(el));
    }
    return r;
  }

  function byRef(ref) {
    const w = refs.get(String(ref || "").trim());
    const el = w && w.deref();
    return el && el.isConnected ? el : null;
  }

  function clean(s, n = 90) {
    s = String(s || "").replace(/\s+/g, " ").trim();
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }

  function visible(el) {
    if (!(el instanceof Element)) return false;
    const st = getComputedStyle(el);
    if (st.display === "none" || st.visibility === "hidden" || st.visibility === "collapse" || +st.opacity === 0 && el.tagName !== "INPUT") return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1 || el.tagName === "OPTION";
  }

  function roleOf(el) {
    const own = (el.getAttribute("role") || "").split(" ")[0].toLowerCase();
    if (own) return own;
    const t = el.tagName;
    if (t === "A" && el.hasAttribute("href")) return "link";
    if (t === "BUTTON" || t === "SUMMARY") return "button";
    if (t === "SELECT") return el.multiple ? "listbox" : "combobox";
    if (t === "TEXTAREA") return "textbox";
    if (t === "OPTION") return "option";
    if (t === "IFRAME" || t === "FRAME") return "frame";
    if (/^H[1-6]$/.test(t)) return "heading";
    if (t === "IMG") return "img";
    if (t === "INPUT") {
      const ty = (el.type || "text").toLowerCase();
      return { button: "button", submit: "button", reset: "button", image: "button", checkbox: "checkbox", radio: "radio",
        range: "slider", number: "spinbutton", search: "searchbox", file: "file", hidden: "" }[ty] ?? "textbox";
    }
    if (el.isContentEditable && (!el.parentElement || !el.parentElement.isContentEditable)) return "textbox";
    return "";
  }

  function nameOf(el) {
    const al = el.getAttribute("aria-label");
    if (al && al.trim()) return clean(al);
    const lb = el.getAttribute("aria-labelledby");
    if (lb) {
      const s = lb.split(/\s+/).map(id => { const x = document.getElementById(id); return x ? x.innerText || x.textContent : ""; }).join(" ");
      if (s.trim()) return clean(s);
    }
    if (el.labels && el.labels.length) return clean([...el.labels].map(l => l.innerText || l.textContent).join(" "));
    const t = el.tagName;
    if (t === "IMG") return clean(el.alt || el.title);
    if (t === "INPUT") {
      const ty = (el.type || "").toLowerCase();
      if (["button", "submit", "reset"].includes(ty)) return clean(el.value || ty);
      if (ty === "image") return clean(el.alt || el.title || "image button");
      return clean(el.placeholder || el.title || el.name || "");
    }
    if (t === "TEXTAREA" || t === "SELECT") return clean(el.placeholder || el.title || el.name || "");
    let s = el.innerText || el.textContent || "";
    if (!s.trim()) {
      const img = el.querySelector && el.querySelector("img[alt], svg[aria-label], [title]");
      s = img ? img.getAttribute("alt") || img.getAttribute("aria-label") || img.getAttribute("title") || "" : "";
    }
    return clean(s || el.title || "");
  }

  function secret(el) {
    if (!el || el.tagName !== "INPUT" && el.tagName !== "TEXTAREA") return false;
    const ty = (el.type || "").toLowerCase();
    const hint = [el.autocomplete, el.name, el.id, el.getAttribute("aria-label"), el.placeholder].join(" ");
    return ty === "password" || /current-password|new-password|one-time-code/i.test(el.autocomplete || "") || CARD_HINT.test(hint);
  }

  function valueOf(el) {
    if (secret(el)) return el.value ? "(hidden)" : "";
    if (el.tagName === "SELECT") return clean(el.selectedOptions && el.selectedOptions[0] ? el.selectedOptions[0].text : "", 60);
    if ("value" in el && typeof el.value === "string" && !["button", "submit", "reset"].includes((el.type || "").toLowerCase())) return clean(el.value, 80);
    if (el.isContentEditable) return clean(el.innerText, 80);
    return "";
  }

  function states(el, role) {
    const out = [];
    if (role === "checkbox" || role === "radio" || role === "switch") {
      const c = el.checked ?? el.getAttribute("aria-checked") === "true";
      out.push(c ? "checked" : "not checked");
    }
    if (el.getAttribute("aria-selected") === "true" || el.selected && role === "option") out.push("selected");
    if (el.getAttribute("aria-expanded") === "true") out.push("expanded");
    if (el.getAttribute("aria-expanded") === "false") out.push("collapsed");
    if (el.disabled || el.getAttribute("aria-disabled") === "true") out.push("disabled");
    if (el.required) out.push("required");
    return out;
  }

  function clickable(el) {
    if (el.tagName === "LABEL" || el.tagName === "DIV" || el.tagName === "SPAN" || el.tagName === "LI" || el.tagName === "TD") {
      if (el.hasAttribute("onclick") || el.getAttribute("tabindex") === "0") return true;
      try { return getComputedStyle(el).cursor === "pointer" && !(el.parentElement && getComputedStyle(el.parentElement).cursor === "pointer"); }
      catch (e) { return false; }
    }
    return false;
  }

  function where(el) {
    const r = el.getBoundingClientRect();
    if (r.bottom < 0) return " ↑";
    if (r.top > innerHeight) return " ↓";
    return "";
  }

  // one look at the page: headings, what can be pressed or filled (with its name eN), and short text between
  function snapshot(opt = {}) {
    const max = Math.max(1500, Math.min(40000, +opt.max || 6000));
    const all = !!opt.all;
    const lines = [];
    let size = 0, seen = 0, cut = false;
    const add = s => {
      if (cut) return;
      if (size + s.length + 1 > max) { cut = true; return; }
      lines.push(s); size += s.length + 1;
    };
    const textSeen = new Set();
    // quiet: inside a table row already said as one line (only what can be pressed or filled gets its own line)
    const walk = (root, depth, quiet = false) => {
      const kids = root.children || [];
      for (const el of kids) {
        if (cut || ++seen > MAX_NODES) { cut = cut || seen > MAX_NODES; return; }
        if (SKIP.has(el.tagName.toUpperCase())) continue;
        if (el.getAttribute("aria-hidden") === "true" && !el.querySelector("input, button, a[href], select, textarea")) continue;
        if (!visible(el)) { if (el.tagName !== "DETAILS" && el.tagName !== "OPTION") continue; }
        if (!quiet && (el.tagName === "TR" || el.getAttribute("role") === "row")) {
          // a table row is one line, its cells in order: a model can't put loose cells back into rows
          const cells = [...el.children].filter(c => c.tagName === "TD" || c.tagName === "TH"
            || /^(cell|gridcell|columnheader|rowheader)$/.test(c.getAttribute("role") || ""));
          if (cells.length > 1) {
            const parts = cells.map(c => clean(c.innerText || c.textContent || "", all ? 200 : 90));
            if (parts.some(Boolean)) add(`row "${parts.join(" | ")}"`);
            if (el.querySelector("input, select, textarea, button, a[href], [role=button], [role=link], [onclick]")) walk(el, depth + 1, true);
            continue;
          }
        }
        const role = roleOf(el);
        if (role === "heading") {
          add(`${"#".repeat(+(el.tagName[1] || 2))} ${nameOf(el)}`);
          continue;
        }
        if (role === "frame") { add(`frame "${clean(el.title || el.name || el.src, 60)}"`); continue; }
        if (role === "file") { add(`file input "${nameOf(el)}" [${refOf(el)}]`); continue; }
        if (role === "img" && !all) { if (el.alt && el.closest("a,button") === null) add(`img "${clean(el.alt, 60)}"`); continue; }
        if (role && (INTERACTIVE_ROLES.has(role) && role !== "row" && role !== "gridcell" || role === "img") || clickable(el)) {
          const r = role || "clickable";
          const nm = nameOf(el);
          let line = `${r} "${nm}"`;
          const v = valueOf(el);
          if (v && v !== nm) line += ` value="${v}"`;
          const s = states(el, r);
          if (s.length) line += " " + s.join(" ");
          if (r === "link" && el.getAttribute("href") && !/^javascript:/i.test(el.getAttribute("href"))) {
            const h = el.href;
            if (all || h.length < 90) line += ` → ${clean(h, 120)}`;
          }
          if (r === "combobox" && el.tagName === "SELECT") {
            const opts = [...el.options].slice(0, 12).map(o => clean(o.text, 30));
            line += ` options: ${opts.join(" | ")}${el.options.length > 12 ? ` … (${el.options.length})` : ""}`;
          }
          add(line + ` [${refOf(el)}]` + where(el));
          if (el.tagName === "SELECT" || r === "textbox" || r === "searchbox" || r === "combobox" && el.tagName === "INPUT") continue;
          if (r === "link" || r === "button" || r === "tab" || r === "menuitem" || r === "option" || r === "clickable") {
            if (!el.querySelector("input, select, textarea, button, a[href]")) continue;
          }
        } else if (!role || role === "row" || role === "gridcell") {
          // short text that isn't inside anything pressable: read where it stands
          let own = "";
          for (const n of el.childNodes) if (n.nodeType === 3) own += n.textContent;
          own = clean(own, all ? 400 : 160);
          if (!quiet && own.length > 1) {
            const twice = own.length > 60 && textSeen.has(own);    // a long notice said again: once is enough
            textSeen.add(own);                                      // (short words like a subject repeat for real)
            if (!twice && (all || own.length > 2)) add(`text "${own}"`);
          }
        }
        if (el.shadowRoot) walk(el.shadowRoot, depth + 1, quiet);
        walk(el, depth + 1, quiet);
      }
    };
    walk(document.body || document.documentElement, 0);
    const h = document.documentElement.scrollHeight, y = scrollY, vh = innerHeight;
    return {
      title: document.title, url: location.href, lines, cut,
      scroll: { y: Math.round(y), h: Math.round(h), vh: Math.round(vh) },
      focus: document.activeElement && document.activeElement !== document.body ? refOf(document.activeElement) : "",
    };
  }

  // the page as plain text: the main part first (an article, <main>), tables as rows
  function text(opt = {}) {
    const max = Math.max(1000, Math.min(60000, +opt.max || 12000));
    const root = document.querySelector("main, [role=main], article") || document.body || document.documentElement;
    let s = (root.innerText || root.textContent || "").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
    if (root !== document.body && s.length < 400 && document.body) s = document.body.innerText.trim();
    return { title: document.title, url: location.href, text: s.slice(0, max), cut: s.length > max, length: s.length };
  }

  function find(q, limit = 20) {
    const words = String(q || "").toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return { hits: [] };
    const hits = [];
    let seen = 0;
    const walk = root => {
      for (const el of root.children || []) {
        if (++seen > MAX_NODES * 2 || hits.length >= limit * 3) return;
        if (SKIP.has(el.tagName.toUpperCase())) continue;
        const role = roleOf(el);
        if ((role && role !== "heading" && role !== "frame" || clickable(el)) && visible(el)) {
          const nm = nameOf(el);
          const hay = [nm, role, el.placeholder, el.title, el.name, el.id, el.getAttribute("href"), valueOf(el)].join(" ").toLowerCase();
          const score = words.filter(w => hay.includes(w)).length;
          if (score) hits.push({ score, line: `${role || "clickable"} "${nm}" [${refOf(el)}]${where(el)}` });
        } else if (!role && visible(el)) {
          let own = "";
          for (const n of el.childNodes) if (n.nodeType === 3) own += n.textContent;
          const lo = own.toLowerCase();
          const score = words.filter(w => lo.includes(w)).length;
          if (score && own.trim().length > 1) hits.push({ score: score - 0.5, line: `text "${clean(own, 120)}" [${refOf(el)}]${where(el)}` });
        }
        if (el.shadowRoot) walk(el.shadowRoot);
        walk(el);
      }
    };
    walk(document.body || document.documentElement);
    hits.sort((a, b) => b.score - a.score);
    return { hits: hits.slice(0, limit).map(h => h.line), url: location.href };
  }

  function formOf(el) {
    const f = el.closest && el.closest("form");
    if (!f) return null;
    const search = f.getAttribute("role") === "search" || !!f.querySelector("input[type=search]")
      || /search|cerca|suche|busca|recherche|szukaj|пошук|поиск|query|\bq\b/i.test([f.action, f.id, f.className, f.getAttribute("aria-label")].join(" "))
      || !!f.querySelector("input[name=q], input[name=query], input[name=search], input[name=s]");
    const pass = !!f.querySelector("input[type=password]");
    const sub = f.querySelector("button[type=submit], input[type=submit], button:not([type])");
    return { search, password: pass, submit: sub ? nameOf(sub) : "", fields: f.querySelectorAll("input:not([type=hidden]), select, textarea").length };
  }

  function captcha(el) {
    const s = [el.className, el.id, el.title, el.getAttribute("src"), el.closest && el.closest("[class*=captcha], [id*=captcha], .g-recaptcha, .h-captcha, .cf-turnstile") ? "captcha" : ""].join(" ");
    return /captcha|recaptcha|turnstile|challenge-platform|arkose|funcaptcha/i.test(s);
  }

  function info(el) {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const role = roleOf(el) || (clickable(el) ? "clickable" : el.tagName.toLowerCase());
    const a = el.closest && el.closest("a[href]");
    return {
      ref: refOf(el), role, name: nameOf(el), tag: el.tagName.toLowerCase(), type: (el.type || "").toLowerCase(),
      href: a ? a.href : "", download: !!(a && a.hasAttribute("download")), value: valueOf(el),
      secret: secret(el), editable: !!(el.isContentEditable || /^(INPUT|TEXTAREA)$/.test(el.tagName) && !["button", "submit", "reset", "checkbox", "radio", "file", "image"].includes((el.type || "").toLowerCase())),
      form: formOf(el), captcha: captcha(el), disabled: !!el.disabled,
      x: Math.round(r.left + r.width / 2), y: Math.round(r.top + Math.min(r.height / 2, 20)), w: Math.round(r.width), h: Math.round(r.height),
      inView: r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth,
      url: location.href,
    };
  }

  function inspect(o) {
    if (o.ref) {
      const el = byRef(o.ref);
      if (!el) return { error: "gone" };
      return info(el);
    }
    const el = document.elementFromPoint(+o.x, +o.y);
    if (!el) return { error: "nothing" };
    const target = el.closest("a[href], button, input, select, textarea, [role], [onclick], label, summary") || el;
    return info(target);
  }

  function reveal(ref) {
    const el = byRef(ref);
    if (!el) return { error: "gone" };
    const r0 = el.getBoundingClientRect();
    if (r0.top < 0 || r0.bottom > innerHeight || r0.left < 0 || r0.right > innerWidth) el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
    return info(el);
  }

  const nativeSet = (el, v) => {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const d = Object.getOwnPropertyDescriptor(proto, "value");
    if (d && d.set) d.set.call(el, v); else el.value = v;
  };
  const fire = (el, ...names) => names.forEach(n => el.dispatchEvent(new Event(n, { bubbles: true })));

  function fill(ref, value) {
    const el = byRef(ref);
    if (!el) return { error: "gone" };
    if (secret(el)) return { error: "secret" };
    const role = roleOf(el);
    el.scrollIntoView({ block: "center", behavior: "instant" });
    if (el.tagName === "SELECT") {
      const want = String(value).toLowerCase().trim();
      const opt = [...el.options].find(o => o.value.toLowerCase() === want || o.text.toLowerCase().trim() === want)
        || [...el.options].find(o => o.text.toLowerCase().includes(want));
      if (!opt) return { error: "no option", options: [...el.options].slice(0, 30).map(o => o.text.trim()) };
      nativeSet(el, opt.value);
      fire(el, "input", "change");
      return { ok: true, value: opt.text.trim() };
    }
    if (role === "checkbox" || role === "radio" || role === "switch") {
      const on = value === true || /^(true|yes|on|1|checked|так|sì|si|ja|oui|tak)$/i.test(String(value));
      const cur = el.checked ?? el.getAttribute("aria-checked") === "true";
      if (cur !== on) el.click();
      return { ok: true, value: (el.checked ?? el.getAttribute("aria-checked") === "true") ? "checked" : "not checked" };
    }
    if (el.isContentEditable) {
      el.focus();
      document.execCommand("selectAll", false);
      document.execCommand("insertText", false, String(value));
      return { ok: true, value: clean(el.innerText, 80) };
    }
    if ("value" in el) {
      el.focus();
      nativeSet(el, String(value));
      fire(el, "input", "change");
      return { ok: true, value: clean(el.value, 80) };
    }
    return { error: "not a field" };
  }

  // for elements inside frames: the page's own click and typing (the background uses real input in the top page)
  function clickDom(ref) {
    const el = byRef(ref);
    if (!el) return { error: "gone" };
    el.scrollIntoView({ block: "center", behavior: "instant" });
    el.focus && el.focus();
    el.click();
    return { ok: true };
  }

  function typeDom(ref, value, clear) {
    const el = ref ? byRef(ref) : document.activeElement;
    if (!el) return { error: "gone" };
    if (secret(el)) return { error: "secret" };
    el.focus();
    if (clear) document.execCommand("selectAll", false);
    if (!document.execCommand("insertText", false, String(value)) && "value" in el) {
      nativeSet(el, (clear ? "" : el.value) + String(value));
      fire(el, "input", "change");
    }
    return { ok: true };
  }

  function focused() {
    const el = document.activeElement;
    return el && el !== document.body && document.hasFocus() ? info(el) : null;
  }
  function focusRef(ref) {
    const el = byRef(ref);
    if (!el) return { error: "gone" };
    el.scrollIntoView({ block: "center", behavior: "instant" });
    el.focus();
    return info(el);
  }

  // a file field gets a mark for a moment, so the background can hand it files through the debugger
  function mark(ref, m) {
    const el = byRef(ref);
    if (!el || el.tagName !== "INPUT" || (el.type || "").toLowerCase() !== "file") return false;
    el.setAttribute("data-lanterna-mark", m);
    return true;
  }

  // ---------------------------------------------------------------- "Lanterna works in this tab"
  let shown = null;
  function overlay(on, words = {}) {
    if (!on) { if (shown) { shown.remove(); shown = null; } return { ok: true }; }
    if (!shown) {
      shown = document.createElement("lanterna-indicator");
      const root = shown.attachShadow({ mode: "closed" });
      root.innerHTML = `<style>
        :host { all: initial; }
        .edge { position: fixed; inset: 0; pointer-events: none; z-index: 2147483646;
          box-shadow: inset 0 0 0 3px rgba(245,181,68,.95), inset 0 0 28px rgba(245,181,68,.45); border-radius: 2px; }
        .pill { position: fixed; left: 50%; bottom: 18px; transform: translateX(-50%); z-index: 2147483647;
          display: flex; align-items: center; gap: 10px; padding: 7px 8px 7px 14px; border-radius: 999px;
          background: #141927; color: #F3EEE4; font: 500 13px/1.2 system-ui, "Segoe UI", sans-serif;
          box-shadow: 0 6px 24px rgba(0,0,0,.35); border: 1px solid rgba(245,181,68,.6); pointer-events: auto; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: #F5B544; animation: p 1.4s ease-in-out infinite; }
        .rec .dot { background: #E5534B; }
        button { all: unset; cursor: pointer; padding: 5px 11px; border-radius: 999px; background: #F5B544; color: #141927; font-weight: 600; }
        button:focus-visible { outline: 2px solid #fff; outline-offset: 2px; }
        @keyframes p { 50% { opacity: .35; } }
        @media (prefers-reduced-motion: reduce) { .dot { animation: none; } }
      </style><div class="edge"></div><div class="pill"><span class="dot"></span><span class="txt"></span><button type="button"></button></div>`;
      root.querySelector("button").onclick = e => { e.stopPropagation(); chrome.runtime.sendMessage({ t: shown && shown._rec ? "record_stop" : "stop" }); };
      shown._root = root;
      (document.body || document.documentElement).appendChild(shown);
    }
    const root = shown._root;
    shown._rec = !!words.rec;
    root.querySelector(".pill").classList.toggle("rec", !!words.rec);
    root.querySelector(".txt").textContent = words.text || "Lanterna is working in this tab";
    root.querySelector("button").textContent = words.stop || "Stop";
    root.querySelector(".edge").style.display = words.rec ? "none" : "";
    return { ok: true };
  }

  // a picture of the page for the model shows the page, not Lanterna's frame and bar over it
  function veil(hide) {
    if (!shown) return { ok: true };
    if (hide) shown.style.setProperty("display", "none", "important");
    else shown.style.removeProperty("display");
    return new Promise(done => {
      let over = false;
      const end = () => { if (!over) { over = true; done({ ok: true }); } };
      requestAnimationFrame(() => requestAnimationFrame(end));
      setTimeout(end, 150);                                     // a tab in the background draws no frames
    });
  }

  // ---------------------------------------------------------------- recording the user's steps
  let rec = null;
  function describe(el) {
    const i = info(el.closest("a[href], button, input, select, textarea, [role], label, summary") || el);
    return { role: i.role, name: i.name, secret: i.secret, url: location.href };
  }
  function recStart() {
    if (rec) return { ok: true };
    const send = step => chrome.runtime.sendMessage({ t: "record_step", step });
    const onClick = e => { if (e.isTrusted && !(shown && e.composedPath().includes(shown))) send({ kind: "click", ...describe(e.target) }); };
    const onChange = e => {
      if (!e.isTrusted) return;
      const el = e.target, d = describe(el);
      const v = el.tagName === "SELECT" ? (el.selectedOptions[0] || {}).text : el.type === "checkbox" || el.type === "radio" ? (el.checked ? "on" : "off") : el.value;
      send({ kind: "input", ...d, value: d.secret ? "" : clean(v, 200) });
    };
    const onSubmit = e => { if (e.isTrusted) send({ kind: "submit", ...describe(e.target) }); };
    const onKey = e => { if (e.isTrusted && e.key === "Enter" && e.target && /^(INPUT)$/.test(e.target.tagName)) send({ kind: "enter", ...describe(e.target) }); };
    addEventListener("click", onClick, true);
    addEventListener("change", onChange, true);
    addEventListener("submit", onSubmit, true);
    addEventListener("keydown", onKey, true);
    rec = () => { removeEventListener("click", onClick, true); removeEventListener("change", onChange, true); removeEventListener("submit", onSubmit, true); removeEventListener("keydown", onKey, true); };
    return { ok: true };
  }
  function recStop() { if (rec) { rec(); rec = null; } return { ok: true }; }

  function selection() {
    const s = String(getSelection() || "").trim();
    return { text: s.slice(0, 4000), title: document.title, url: location.href };
  }

  globalThis.__lanternaPage = { v: V, snapshot, text, find, inspect, reveal, fill, clickDom, typeDom, focused, focusRef, mark, overlay, veil, recStart, recStop, selection };
})();
