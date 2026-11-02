"use strict";
// Lanterna window UI. Talks to the Python backend through pywebview (window) or HTTP (dev mode, ?token=…).

const TOKEN = new URLSearchParams(location.search).get("token");
const api = new Proxy({}, {
  get: (_, name) => (...args) => window.pywebview && window.pywebview.api
    ? window.pywebview.api[name](...args)
    : fetch("api/" + name, { method: "POST", headers: { "X-Token": TOKEN || "", "Content-Type": "application/json" }, body: JSON.stringify(args) })
        .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }),
});

// ---------------------------------------------------------------- strings (key = English)
const STR = {
  "Choose your language": { uk: "Вибери мову", it: "Scegli la lingua" },
  "You can change it later in Settings.": { uk: "Її можна змінити пізніше в Налаштуваннях.", it: "Puoi cambiarla più tardi nelle Impostazioni." },
  "Made by": { uk: "Створив", it: "Creato da" },
  "A friendly assistant that runs on free cloud models — or on your own PC.": { uk: "Дружній асистент на безкоштовних хмарних моделях — або на твоєму ПК.", it: "Un assistente amichevole che usa modelli cloud gratuiti — o il tuo PC." },
  "What should I call you?": { uk: "Як до тебе звертатися?", it: "Come ti chiami?" },
  "Your name": { uk: "Твоє ім'я", it: "Il tuo nome" },
  "Continue": { uk: "Далі", it: "Avanti" },
  "Back": { uk: "Назад", it: "Indietro" },
  "How should Lanterna think?": { uk: "Як Lanterna думатиме?", it: "Come deve pensare Lanterna?" },
  "Pick what fits your computer.": { uk: "Вибери, що підходить твоєму комп'ютеру.", it: "Scegli ciò che si adatta al tuo computer." },
  "Cloud": { uk: "Хмара", it: "Cloud" },
  "Free models online. Works on any laptop.": { uk: "Безкоштовні моделі онлайн. Працює на будь-якому ноутбуці.", it: "Modelli gratuiti online. Funziona su qualsiasi portatile." },
  "Local": { uk: "Локально", it: "Locale" },
  "Models run on your graphics card. Fully private.": { uk: "Моделі працюють на твоїй відеокарті. Повна приватність.", it: "I modelli girano sulla tua scheda video. Totalmente privato." },
  "Auto": { uk: "Авто", it: "Auto" },
  "Local first, cloud when needed.": { uk: "Спершу локально, хмара — коли треба.", it: "Prima locale, cloud quando serve." },
  "Recommended": { uk: "Рекомендовано", it: "Consigliato" },
  "Soon": { uk: "Скоро", it: "Presto" },
  "Pick your first free service": { uk: "Вибери перший безкоштовний сервіс", it: "Scegli il primo servizio gratuito" },
  "You'll need a free account there. Other services can be added later as backups.": { uk: "Там потрібен безкоштовний акаунт. Інші сервіси можна додати пізніше як запасні.", it: "Serve un account gratuito. Altri servizi si possono aggiungere dopo come riserva." },
  "Fastest": { uk: "Найшвидший", it: "Il più veloce" },
  "Smartest & most generous": { uk: "Найрозумніший і найщедріший", it: "Il più intelligente e generoso" },
  "Replies almost instantly": { uk: "Відповідає майже миттєво", it: "Risponde quasi all'istante" },
  "Strong open models (GPT-OSS, Qwen)": { uk: "Сильні відкриті моделі (GPT-OSS, Qwen)", it: "Modelli aperti potenti (GPT-OSS, Qwen)" },
  "Quick sign-up with Google or GitHub": { uk: "Швидка реєстрація через Google або GitHub", it: "Registrazione veloce con Google o GitHub" },
  "Smaller daily limit": { uk: "Менший денний ліміт", it: "Limite giornaliero più basso" },
  "Big free limits": { uk: "Великі безкоштовні ліміти", it: "Limiti gratuiti ampi" },
  "Understands photos and documents": { uk: "Розуміє фото й документи", it: "Capisce foto e documenti" },
  "Very long conversation memory": { uk: "Дуже довга пам'ять розмови", it: "Memoria di conversazione molto lunga" },
  "Needs a Google account": { uk: "Потрібен Google-акаунт", it: "Serve un account Google" },
  "Get your free {p} key": { uk: "Отримай безкоштовний ключ {p}", it: "Ottieni la chiave gratuita di {p}" },
  "It takes about a minute.": { uk: "Це займе приблизно хвилину.", it: "Ci vuole circa un minuto." },
  "Open the {p} key page": { uk: "Відкрий сторінку ключів {p}", it: "Apri la pagina delle chiavi di {p}" },
  "Open": { uk: "Відкрити", it: "Apri" },
  "Sign in or create a free account": { uk: "Увійди або створи безкоштовний акаунт", it: "Accedi o crea un account gratuito" },
  "Press <b>Create API key</b> and copy it": { uk: "Натисни <b>Create API key</b> і скопіюй його", it: "Premi <b>Create API key</b> e copiala" },
  "Paste it here": { uk: "Встав його сюди", it: "Incollala qui" },
  "Paste your key": { uk: "Встав свій ключ", it: "Incolla la tua chiave" },
  "Check": { uk: "Перевірити", it: "Verifica" },
  "Checking…": { uk: "Перевіряю…", it: "Controllo…" },
  "The key works!": { uk: "Ключ працює!", it: "La chiave funziona!" },
  "This key doesn't work. Check that you copied all of it.": { uk: "Цей ключ не працює. Перевір, чи скопіював його повністю.", it: "Questa chiave non funziona. Controlla di averla copiata tutta." },
  "No internet connection to {p}.": { uk: "Немає з'єднання з {p}.", it: "Nessuna connessione a {p}." },
  "Something went wrong: {e}": { uk: "Щось пішло не так: {e}", it: "Qualcosa è andato storto: {e}" },
  "Your key is kept in your system's secure vault and is only ever sent to {p}.": { uk: "Ключ зберігається в захищеному сховищі системи й надсилається лише до {p}.", it: "La chiave resta nel portachiavi sicuro del sistema e viene inviata solo a {p}." },
  "Start chatting": { uk: "Почати розмову", it: "Inizia a chattare" },
  "New chat": { uk: "Нова розмова", it: "Nuova chat" },
  "Chats": { uk: "Розмови", it: "Chat" },
  "Settings": { uk: "Налаштування", it: "Impostazioni" },
  "About": { uk: "Про програму", it: "Info" },
  "Hi, {n}!": { uk: "Привіт, {n}!", it: "Ciao, {n}!" },
  "Hi!": { uk: "Привіт!", it: "Ciao!" },
  "What's on your mind?": { uk: "Про що поговоримо?", it: "Di cosa parliamo?" },
  "Message Lanterna…": { uk: "Напиши Lanterna…", it: "Scrivi a Lanterna…" },
  "Lanterna can make mistakes. Check important facts.": { uk: "Lanterna може помилятися. Перевіряй важливі факти.", it: "Lanterna può sbagliare. Verifica i fatti importanti." },
  "switched to {m}": { uk: "перейшов на {m}", it: "passato a {m}" },
  "All free models are busy or out of limits. Try again in a minute.": { uk: "Усі безкоштовні моделі зайняті або вичерпали ліміт. Спробуй за хвилину.", it: "Tutti i modelli gratuiti sono occupati o al limite. Riprova tra un minuto." },
  "No connection. Check your internet.": { uk: "Немає з'єднання. Перевір інтернет.", it: "Nessuna connessione. Controlla internet." },
  "Add a key in Settings to start.": { uk: "Додай ключ у Налаштуваннях, щоб почати.", it: "Aggiungi una chiave nelle Impostazioni per iniziare." },
  "Retry": { uk: "Ще раз", it: "Riprova" },
  "Delete this chat?": { uk: "Видалити цю розмову?", it: "Eliminare questa chat?" },
  "Language": { uk: "Мова", it: "Lingua" },
  "Name": { uk: "Ім'я", it: "Nome" },
  "Services": { uk: "Сервіси", it: "Servizi" },
  "Add keys for more services: when one runs out of free limit, Lanterna switches to the next.": { uk: "Додай ключі інших сервісів: коли в одного закінчиться безкоштовний ліміт, Lanterna перейде на наступний.", it: "Aggiungi chiavi di altri servizi: quando uno finisce il limite gratuito, Lanterna passa al successivo." },
  "No key": { uk: "Немає ключа", it: "Nessuna chiave" },
  "Add": { uk: "Додати", it: "Aggiungi" },
  "Change": { uk: "Змінити", it: "Cambia" },
  "Remove": { uk: "Прибрати", it: "Rimuovi" },
  "Cancel": { uk: "Скасувати", it: "Annulla" },
  "Close": { uk: "Закрити", it: "Chiudi" },
  "Remove the key for {p}?": { uk: "Прибрати ключ для {p}?", it: "Rimuovere la chiave di {p}?" },
  "Free models right now": { uk: "Безкоштовні моделі зараз", it: "Modelli gratuiti adesso" },
  "Search again": { uk: "Шукати знову", it: "Cerca di nuovo" },
  "Searching for free models…": { uk: "Шукаю безкоштовні моделі…", it: "Cerco modelli gratuiti…" },
  "ok": { uk: "працює", it: "funziona" },
  "limited": { uk: "ліміт", it: "limite" },
  "untested": { uk: "не перевірено", it: "non testato" },
  "Save": { uk: "Зберегти", it: "Salva" },
  "Saved": { uk: "Збережено", it: "Salvato" },
  "Version {v}": { uk: "Версія {v}", it: "Versione {v}" },
  "Free and open source (MIT). No ads, no tracking — your chats stay on your computer.": { uk: "Безкоштовно й з відкритим кодом (MIT). Без реклами й стеження — розмови лишаються на твоєму комп'ютері.", it: "Gratis e open source (MIT). Niente pubblicità né tracciamento — le chat restano sul tuo computer." },
  "Star on GitHub": { uk: "Зірочка на GitHub", it: "Stella su GitHub" },
  "Project page": { uk: "Сторінка проєкту", it: "Pagina del progetto" },
  "just now": { uk: "щойно", it: "adesso" },
  "Today": { uk: "Сьогодні", it: "Oggi" },
  "Earlier": { uk: "Раніше", it: "Prima" },
  "Explain something simply": { uk: "Поясни щось простими словами", it: "Spiegami qualcosa in modo semplice" },
  "Help me plan my week": { uk: "Допоможи спланувати тиждень", it: "Aiutami a pianificare la settimana" },
  "Write a short message for me": { uk: "Напиши за мене коротке повідомлення", it: "Scrivi un breve messaggio per me" },
  "Give me an idea for today": { uk: "Дай ідею на сьогодні", it: "Dammi un'idea per oggi" },
  "Attach a file or photo": { uk: "Додати файл або фото", it: "Allega un file o una foto" },
  "is bigger than 20 MB": { uk: "більший за 20 МБ", it: "è più grande di 20 MB" },
  "Checking the weather": { uk: "Дивлюся погоду", it: "Controllo il meteo" },
  "Searching the web": { uk: "Шукаю в інтернеті", it: "Cerco sul web" },
  "Reading a page": { uk: "Читаю сторінку", it: "Leggo una pagina" },
  "Calculating": { uk: "Рахую", it: "Calcolo" },
  "Counting dates": { uk: "Рахую дати", it: "Calcolo le date" },
  "Saving to memory": { uk: "Запам'ятовую", it: "Salvo in memoria" },
  "Updating memory": { uk: "Оновлюю пам'ять", it: "Aggiorno la memoria" },
  "Setting a reminder": { uk: "Ставлю нагадування", it: "Imposto un promemoria" },
  "Checking reminders": { uk: "Дивлюся нагадування", it: "Controllo i promemoria" },
  "Cancelling a reminder": { uk: "Скасовую нагадування", it: "Annullo un promemoria" },
  "To understand photos, add a free Gemini key in Settings.": { uk: "Щоб розуміти фото, додай безкоштовний ключ Gemini в Налаштуваннях.", it: "Per capire le foto, aggiungi una chiave Gemini gratuita nelle Impostazioni." },
  "Memory": { uk: "Пам'ять", it: "Memoria" },
  "Facts Lanterna remembers about you. They stay on this computer and are sent to the model with each message.": { uk: "Факти, які Lanterna пам'ятає про тебе. Вони лежать на цьому комп'ютері й надсилаються моделі разом із кожним повідомленням.", it: "Fatti che Lanterna ricorda di te. Restano su questo computer e vengono inviati al modello con ogni messaggio." },
  "Nothing yet. Say “remember that…” in a chat.": { uk: "Поки порожньо. Скажи в чаті «запам'ятай, що…».", it: "Ancora niente. Scrivi «ricorda che…» in chat." },
  "Add a fact": { uk: "Додати факт", it: "Aggiungi un fatto" },
  "Reminders": { uk: "Нагадування", it: "Promemoria" },
  "No reminders. Say “remind me in 20 minutes…” in a chat.": { uk: "Нагадувань немає. Скажи в чаті «нагадай через 20 хвилин…».", it: "Nessun promemoria. Scrivi «ricordami tra 20 minuti…» in chat." },
  "Reminders pop up while Lanterna is open.": { uk: "Нагадування спливають, поки Lanterna відкрита.", it: "I promemoria appaiono mentre Lanterna è aperta." },
  "Reminder": { uk: "Нагадування", it: "Promemoria" },
};
let LANG = "en";
const t = (s, vars = {}) => {
  let out = LANG === "en" ? s : (STR[s] && STR[s][LANG]) || s;
  for (const [k, v] of Object.entries(vars)) out = out.split("{" + k + "}").join(v);
  return out;
};

// ---------------------------------------------------------------- tiny helpers
const $ = (sel, root = document) => root.querySelector(sel);
const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (id, cls = "i") => `<svg class="${cls}"><use href="#i-${id}"/></svg>`;
const h = html => { const d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstElementChild; };

function md(text) {
  // safe, minimal Markdown: everything is escaped first
  const blocks = String(text).split(/```/);
  return blocks.map((b, i) => {
    if (i % 2) { const code = b.replace(/^[\w+-]*\n/, ""); return `<pre><code>${esc(code.replace(/\n$/, ""))}</code></pre>`; }
    const lines = esc(b).split("\n");
    let html = "", list = null;
    const inline = s => s
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a data-href="$2">$1</a>')
      .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a data-href="$2">$2</a>');
    const close = () => { if (list) { html += `</${list}>`; list = null; } };
    let para = [];
    const flush = () => { if (para.length) { html += `<p>${inline(para.join("<br>"))}</p>`; para = []; } };
    for (const ln of lines) {
      let m;
      if ((m = ln.match(/^\s*[-*•]\s+(.*)/))) { flush(); if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1])}</li>`; }
      else if ((m = ln.match(/^\s*\d+[.)]\s+(.*)/))) { flush(); if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[1])}</li>`; }
      else if ((m = ln.match(/^#{1,4}\s+(.*)/))) { flush(); close(); html += `<h3>${inline(m[1])}</h3>`; }
      else if (!ln.trim()) { flush(); close(); }
      else { close(); para.push(ln); }
    }
    flush(); close();
    return html;
  }).join("");
}


// ---------------------------------------------------------------- tools, files, reminders
const TOOL_TEXT = { weather: "Checking the weather", web_search: "Searching the web", read_page: "Reading a page",
  calculate: "Calculating", date_calc: "Counting dates", remember: "Saving to memory", forget: "Updating memory",
  set_reminder: "Setting a reminder", list_reminders: "Checking reminders", cancel_reminder: "Cancelling a reminder" };
const toolChip = s => { const [emo, name] = String(s).split(" "); return `<div class="tool">${esc(emo)} ${esc(t(TOOL_TEXT[name] || name))}</div>`; };

let pending = [];        // files waiting to be sent: {name, size, data(base64)}
const MAX_FILE = 20 * 1024 * 1024;

function readFile(f) {
  return new Promise((ok, fail) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",", 2)[1] || "");
    r.onerror = () => fail(r.error);
    r.readAsDataURL(f);
  });
}

async function addFiles(list) {
  for (const f of Array.from(list || [])) {
    if (f.size > MAX_FILE) { toast(`${f.name} ${t("is bigger than 20 MB")}`); continue; }
    pending.push({ name: f.name, size: f.size, data: await readFile(f) });
  }
  paintFiles();
}

function paintFiles() {
  const box = $("#files");
  if (!box) return;
  box.hidden = !pending.length;
  box.innerHTML = pending.map((f, i) => `<span class="file">${icon("clip")}<span>${esc(f.name)}</span><button data-i="${i}" title="${t("Remove")}">${icon("x")}</button></span>`).join("");
  box.querySelectorAll("button").forEach(b => b.onclick = () => { pending.splice(+b.dataset.i, 1); paintFiles(); });
  $("#input").oninput();
}

function toast(text, sticky = false) {
  // short notices fade out; reminders stay until closed
  const el = h(`<div class="toast${sticky ? " sticky" : ""}"><span></span><button title="${t("Close")}">${icon("x")}</button></div>`);
  el.querySelector("span").textContent = text;
  const close = () => { el.classList.add("out"); setTimeout(() => el.remove(), 600); };
  el.querySelector("button").onclick = close;
  const stack = $("#toasts") || document.body.appendChild(h(`<div id="toasts"></div>`));
  stack.append(el);
  if (!sticky) setTimeout(close, 6000);
}

async function watchAlerts() {
  try { (await api.alerts()).forEach(a => toast(`⏰ ${t("Reminder")}: ${a.text}`, true)); } catch (e) { /* app closing */ }
  setTimeout(watchAlerts, 10000);
}

// ---------------------------------------------------------------- state
let S = null;          // backend state
let thread = null;     // current thread id
let busy = false;

async function boot() {
  document.body.prepend($("#tpl-icons").content.cloneNode(true));
  S = await api.state();
  LANG = S.settings.lang || "en";
  document.documentElement.lang = LANG;
  if (S.settings.onboarded && S.providers.some(p => p.has_key)) renderMain();
  else renderOnboard(S.settings.onboarded ? 3 : 0);
}

document.addEventListener("click", e => {
  const a = e.target.closest("a[data-href]");
  if (a) { e.preventDefault(); api.open_url(a.dataset.href); }
});

// ---------------------------------------------------------------- onboarding
const PROVIDER_INFO = {
  groq: { icon: "bolt", tag: "Fastest", pros: ["Replies almost instantly", "Strong open models (GPT-OSS, Qwen)", "Quick sign-up with Google or GitHub"], cons: ["Smaller daily limit"] },
  gemini: { icon: "spark", tag: "Smartest & most generous", pros: ["Big free limits", "Understands photos and documents", "Very long conversation memory"], cons: ["Needs a Google account"] },
};
const pname = id => (S.providers.find(p => p.id === id) || {}).name || id;

function renderOnboard(step) {
  const app = $("#app");
  app.className = "";
  const dots = `<div class="dots">${[0, 1, 2, 3, 4].map(i => `<span class="${i <= step ? "on" : ""}"></span>`).join("")}</div>`;
  let body = "";
  if (step === 0) {
    body = `<div class="step">
      <div class="hero-logo"><img src="logo.svg" alt=""></div>
      <h1>${t("Choose your language")}</h1><p class="lead">${t("You can change it later in Settings.")}</p>
      <div class="langs">${Object.entries(S.langs).map(([k, v]) => `<button class="lang" data-lang="${k}">${v}<small>${{ en: "Hello", uk: "Привіт", it: "Ciao" }[k]}</small></button>`).join("")}</div>
    </div>`;
  } else if (step === 1) {
    body = `<div class="step">
      <div class="hero-logo"><img src="logo.svg" alt=""></div>
      <div class="wordmark">Lanterna</div>
      <div class="byline">${t("Made by")} <b>${esc(S.author)}</b> · <a class="link" data-href="${S.homepage}">GitHub</a></div>
      <p class="lead">${t("A friendly assistant that runs on free cloud models — or on your own PC.")}</p>
      <form class="stack" id="f-name">
        <label class="muted" for="name" style="text-align:left">${t("What should I call you?")}</label>
        <input class="field" id="name" maxlength="40" autocomplete="given-name" placeholder="${t("Your name")}" value="${esc(S.settings.name || "")}">
        <button class="btn primary" type="submit">${t("Continue")}</button>
      </form>
      <button class="back" data-back="0">← ${t("Back")}</button>
    </div>`;
  } else if (step === 2) {
    const mode = (id, ic, title, desc, extra, dis) => `<button class="card mode-row" data-mode="${id}" ${dis ? "disabled" : ""}>
      <div class="ic">${icon(ic)}</div><div style="flex:1"><h3>${t(title)}</h3><p>${t(desc)}</p></div>${extra}</button>`;
    body = `<div class="step">
      <h1>${t("How should Lanterna think?")}</h1><p class="lead">${t("Pick what fits your computer.")}</p>
      <div class="cards">
        ${mode("cloud", "cloud", "Cloud", "Free models online. Works on any laptop.", `<span class="badge amber">${t("Recommended")}</span>`, false)}
        ${mode("local", "chip", "Local", "Models run on your graphics card. Fully private.", `<span class="badge">${t("Soon")}</span>`, true)}
        ${mode("auto", "auto", "Auto", "Local first, cloud when needed.", `<span class="badge">${t("Soon")}</span>`, true)}
      </div>
      <button class="back" data-back="1">← ${t("Back")}</button>
    </div>`;
  } else if (step === 3) {
    body = `<div class="step" style="max-width:760px">
      <h1>${t("Pick your first free service")}</h1><p class="lead">${t("You'll need a free account there. Other services can be added later as backups.")}</p>
      <div class="cards two">${S.first.map(id => {
        const inf = PROVIDER_INFO[id];
        return `<button class="card" data-first="${id}">
          <div class="head"><div class="ic">${icon(inf.icon)}</div><div><h3>${esc(pname(id))}</h3><div class="tag">${t(inf.tag)}</div></div></div>
          <ul>${inf.pros.map(x => `<li>${icon("check")}${t(x)}</li>`).join("")}${inf.cons.map(x => `<li class="minus">${icon("info")}${t(x)}</li>`).join("")}</ul>
        </button>`;
      }).join("")}</div>
      <button class="back" data-back="2">← ${t("Back")}</button>
    </div>`;
  } else {
    const id = S.settings.provider || "groq";
    const p = S.providers.find(x => x.id === id);
    body = `<div class="step">
      <h1>${t("Get your free {p} key", { p: esc(p.name) })}</h1><p class="lead">${t("It takes about a minute.")}</p>
      <div class="keybox">
        <ol class="keysteps">
          <li><div style="flex:1">${t("Open the {p} key page", { p: esc(p.name) })}</div><button class="btn ghost small" data-open="${esc(p.key_url)}">${t("Open")} ${icon("ext")}</button></li>
          <li>${t("Sign in or create a free account")}</li>
          <li><span>${t("Press <b>Create API key</b> and copy it")}</span></li>
          <li>${t("Paste it here")}</li>
        </ol>
        ${keyRow(id)}
        <div class="note">${icon("lock")}<span>${t("Your key is kept in your system's secure vault and is only ever sent to {p}.", { p: esc(p.name) })}</span></div>
      </div>
      <button class="btn primary" id="go" style="margin-top:20px;min-width:220px" ${p.has_key ? "" : "disabled"}>${t("Start chatting")}</button>
      <button class="back" data-back="3">← ${t("Back")}</button>
    </div>`;
  }
  app.innerHTML = `<div class="onboard">${dots}${body}</div>`;

  app.querySelectorAll("[data-lang]").forEach(b => b.onclick = async () => {
    LANG = b.dataset.lang; S = await api.save_settings({ lang: LANG }); renderOnboard(1);
  });
  app.querySelectorAll("[data-back]").forEach(b => b.onclick = () => renderOnboard(+b.dataset.back));
  app.querySelectorAll("[data-mode]").forEach(b => b.onclick = async () => { S = await api.save_settings({ mode: b.dataset.mode }); renderOnboard(3); });
  app.querySelectorAll("[data-first]").forEach(b => b.onclick = async () => { S = await api.save_settings({ provider: b.dataset.first }); renderOnboard(4); });
  app.querySelectorAll("[data-open]").forEach(b => b.onclick = () => api.open_url(b.dataset.open));
  const f = $("#f-name");
  if (f) { $("#name").focus(); f.onsubmit = async e => { e.preventDefault(); S = await api.save_settings({ name: $("#name").value.trim() }); renderOnboard(2); }; }
  if (step === 4) {
    wireKeyRow(app, S.settings.provider || "groq", () => { $("#go").disabled = false; $("#go").focus(); });
    $("#go").onclick = async () => { S = await api.save_settings({ onboarded: true }); renderMain(); };
  }
}

function keyRow(id) {
  return `<div class="keyrow" data-key="${id}">
      <div class="wrap"><input class="field" type="password" placeholder="${t("Paste your key")}" spellcheck="false" autocomplete="off">
        <button class="eye" type="button" title="Show">${icon("eye")}</button></div>
      <button class="btn primary chk" style="height:48px">${t("Check")}</button>
    </div><div class="status"></div>`;
}

function wireKeyRow(root, id, onOk) {
  const row = root.querySelector(`[data-key="${id}"]`);
  const inp = row.querySelector("input"), st = row.nextElementSibling, btn = row.querySelector(".chk");
  row.querySelector(".eye").onclick = () => { inp.type = inp.type === "password" ? "text" : "password"; };
  const go = async () => {
    if (!inp.value.trim()) return inp.focus();
    btn.disabled = true; st.className = "status"; st.innerHTML = `<span class="spinner"></span>${t("Checking…")}`;
    let r;
    try { r = await api.check_key(id, inp.value); } catch (e) { r = { ok: false, error: "other", message: String(e) }; }
    btn.disabled = false;
    if (r.ok) {
      inp.value = ""; st.className = "status ok"; st.innerHTML = `${icon("check")} ${t("The key works!")}`;
      S = await api.state(); onOk && onOk();
    } else {
      st.className = "status err";
      st.textContent = r.error === "auth" || r.error === "bad_request" ? t("This key doesn't work. Check that you copied all of it.")
        : r.error === "network" ? t("No internet connection to {p}.", { p: pname(id) }) : t("Something went wrong: {e}", { e: r.message || r.error });
    }
  };
  btn.onclick = go;
  inp.onkeydown = e => { if (e.key === "Enter") go(); };
  inp.focus();
}

// ---------------------------------------------------------------- main
function renderMain() {
  const app = $("#app");
  app.className = "";
  app.innerHTML = `<div class="shell">
    <aside class="side">
      <div class="brand"><img src="logo.svg" alt=""><b>Lanterna</b></div>
      <button class="btn ghost newchat" id="new">${icon("plus")} ${t("New chat")}</button>
      <nav class="threads" id="threads"></nav>
      <div class="side-foot">
        <button id="open-settings">${icon("gear")} ${t("Settings")}</button>
        <button id="open-about">${icon("info")} ${t("About")}</button>
      </div>
    </aside>
    <main class="main">
      <div class="top"><button class="menu" id="menu">${icon("menu")}</button><div class="title" id="title">Lanterna</div><div class="chip" id="model" hidden><i></i><span></span></div></div>
      <div class="scroll" id="scroll"><div class="msgs" id="msgs"></div></div>
      <div class="composer">
        <div class="files" id="files" hidden></div>
        <div class="box"><button class="attach" id="attach" title="${t("Attach a file or photo")}">${icon("clip")}</button>
          <input type="file" id="file" multiple hidden>
          <textarea id="input" rows="1" placeholder="${t("Message Lanterna…")}"></textarea>
          <button class="send" id="send" disabled title="Send">${icon("send")}</button></div>
        <div class="hint">${t("Lanterna can make mistakes. Check important facts.")}</div>
      </div>
    </main>
  </div>`;
  $("#new").onclick = () => openThread(null);
  $("#open-settings").onclick = openSettings;
  $("#open-about").onclick = openAbout;
  $("#menu").onclick = () => $(".shell").classList.toggle("open");
  const inp = $("#input");
  const fit = () => {
    // empty box: natural one-line height (measuring before layout gives a huge scrollHeight)
    inp.style.height = "auto";
    if (inp.value) inp.style.height = Math.min(inp.scrollHeight, 200) + "px";
    $("#send").disabled = (!inp.value.trim() && !pending.length) || busy; };
  inp.oninput = fit;
  inp.onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } };
  $("#send").onclick = send;
  $("#attach").onclick = () => $("#file").click();
  $("#file").onchange = e => { addFiles(e.target.files); e.target.value = ""; };
  const main = $(".main");
  main.ondragover = e => { e.preventDefault(); main.classList.add("drop"); };
  main.ondragleave = e => { if (e.target === main) main.classList.remove("drop"); };
  main.ondrop = e => { e.preventDefault(); main.classList.remove("drop"); addFiles(e.dataTransfer.files); };
  inp.onpaste = e => { const fs = e.clipboardData && e.clipboardData.files; if (fs && fs.length) { e.preventDefault(); addFiles(fs); } };
  pending = []; paintFiles();
  refreshThreads().then(list => openThread(list.length ? list[0].id : null));
  api.models(false).then(r => setModel(r.current));
  if (!window.__alerts) { window.__alerts = true; watchAlerts(); }
}

function setModel(label) {
  const c = $("#model");
  if (!c) return;
  c.hidden = !label;
  c.querySelector("span").textContent = label || "";
}

async function refreshThreads() {
  const list = await api.threads();
  const now = Date.now() / 1000, dayStart = new Date().setHours(0, 0, 0, 0) / 1000;
  const today = list.filter(x => x.updated >= dayStart), older = list.filter(x => x.updated < dayStart);
  const item = x => `<button class="th ${x.id === thread ? "on" : ""}" data-id="${x.id}"><span>${esc(x.title || t("New chat"))}</span>
      <i class="del" data-del="${x.id}" title="Delete">${icon("trash")}</i></button>`;
  $("#threads").innerHTML = (today.length ? `<h6>${t("Today")}</h6>${today.map(item).join("")}` : "") + (older.length ? `<h6>${t("Earlier")}</h6>${older.map(item).join("")}` : "");
  $("#threads").querySelectorAll(".th").forEach(b => b.onclick = e => {
    const d = e.target.closest("[data-del]");
    if (d) { e.stopPropagation(); if (confirm(t("Delete this chat?"))) api.delete_thread(+d.dataset.del).then(() => { if (+d.dataset.del === thread) thread = null; refreshThreads().then(l => openThread(thread || (l[0] && l[0].id) || null)); }); return; }
    openThread(+b.dataset.id); $(".shell").classList.remove("open");
  });
  return list;
}

async function openThread(id) {
  thread = id;
  const msgs = $("#msgs");
  msgs.innerHTML = "";
  if (!id) { $("#title").textContent = "Lanterna"; showEmpty(); refreshThreads(); $("#input").focus(); return; }
  const [list, items] = await Promise.all([api.threads(), api.messages(id)]);
  const th = list.find(x => x.id === id);
  $("#title").textContent = (th && th.title) || t("New chat");
  if (!items.length) showEmpty();
  items.forEach(m => m.role === "user" ? addUser(m.content) : addBot(m.content, m.model));
  refreshThreads();
  scrollDown(true);
  $("#input").focus();
}

function showEmpty() {
  const name = S.settings.name;
  const sugg = ["Explain something simply", "Help me plan my week", "Write a short message for me", "Give me an idea for today"];
  $("#msgs").innerHTML = `<div class="empty" style="min-height:calc(100vh - 230px)">
    <div class="hero-logo"><img src="logo.svg" alt=""></div>
    <h2>${name ? t("Hi, {n}!", { n: esc(name) }) : t("Hi!")}</h2><p>${t("What's on your mind?")}</p>
    <div class="sugg">${sugg.map(s => `<button>${t(s)}</button>`).join("")}</div></div>`;
  $("#msgs").querySelectorAll(".sugg button").forEach(b => b.onclick = () => { const i = $("#input"); i.value = b.textContent; i.oninput(); i.focus(); });
}

function addUser(text) {
  const e = $(".empty"); if (e) e.remove();
  const el = h(`<div class="msg user"></div>`); el.textContent = text; $("#msgs").append(el); return el;
}

function addBot(text, model) {
  const e = $(".empty"); if (e) e.remove();
  const el = h(`<div class="msg bot"><img class="av" src="logo.svg" alt=""><div class="body"><div class="md"></div>${model ? `<div class="meta">${esc(model)}</div>` : ""}</div></div>`);
  if (text === null) el.querySelector(".md").innerHTML = `<div class="typing"><span></span><span></span><span></span></div>`;
  else el.querySelector(".md").innerHTML = md(text);
  $("#msgs").append(el); return el;
}

function scrollDown(force) {
  const s = $("#scroll");
  if (force || s.scrollHeight - s.scrollTop - s.clientHeight < 160) s.scrollTop = s.scrollHeight;
}

async function send(retryText) {
  const inp = $("#input");
  const retry = typeof retryText === "object" && retryText !== null && retryText.retry === true;
  const text = retry ? retryText.text : inp.value.trim();
  const files = retry ? retryText.files : pending;
  if ((!text && !files.length) || busy) return;
  busy = true; $("#send").disabled = true;
  if (!thread) { thread = (await api.new_thread()).id; }
  if (!retry) {
    pending = []; inp.value = ""; paintFiles();
    const names = files.map(f => (/[.](png|jpe?g|webp|gif|bmp)$/i.test(f.name) ? "🖼 " : "📎 ") + f.name);
    addUser([text, ...names].filter(Boolean).join(String.fromCharCode(10, 10)));
  }
  const bot = addBot(null);
  const box = bot.querySelector(".md");
  scrollDown(true);
  const r = await api.send(thread, text, files.map(f => ({ name: f.name, data: f.data })));
  refreshThreads().then(l => { const th = l.find(x => x.id === thread); if (th) $("#title").textContent = th.title; });
  if (!r.ok) {
    busy = false; inp.oninput();
    if (r.error === "file") box.innerHTML = `<div class="err-box">${esc(r.message || "")}</div>`; else bot.remove();
    return;
  }
  let text_ = "", offset = 0, notes = 0, tools = 0;
  const chips = h(`<div class="tools"></div>`);
  bot.querySelector(".body").prepend(chips);
  const step = async () => {
    let p;
    try { p = await api.poll(r.stream, offset); } catch (e) { p = { done: true, error: { kind: "network", message: String(e) } }; }
    (p.notes || []).slice(notes).forEach(m => { bot.before(h(`<div class="switch">↪ ${esc(t("switched to {m}", { m }))}</div>`)); setModel(m); });
    notes = (p.notes || []).length;
    (p.tools || []).slice(tools).forEach(s => chips.insertAdjacentHTML("beforeend", toolChip(s)));
    tools = (p.tools || []).length;
    if (p.final !== undefined) { text_ = p.final; box.innerHTML = md(text_); if (p.model) { setModel(p.model); bot.querySelector(".body").insertAdjacentHTML("beforeend", `<div class="meta">${esc(p.model)}</div>`); } }
    else if (p.text) { text_ += p.text; offset = p.offset; box.innerHTML = md(text_); }
    scrollDown();
    if (p.error) {
      const k = p.error.kind;
      const msg = k === "rate" ? t("All free models are busy or out of limits. Try again in a minute.")
        : k === "network" ? t("No connection. Check your internet.") : k === "auth" ? t("Add a key in Settings to start.")
        : k === "vision" ? t("To understand photos, add a free Gemini key in Settings.") : t("Something went wrong: {e}", { e: p.error.message });
      box.innerHTML = `<div class="err-box">${esc(msg)}</div><button class="btn ghost small" style="margin-top:10px">${icon("refresh")} ${t("Retry")}</button>`;
      box.querySelector("button").onclick = () => { bot.remove(); send({ retry: true, text, files }); };
    }
    if (p.done) { busy = false; inp.oninput(); return; }
    setTimeout(step, 60);
  };
  step();
}

// ---------------------------------------------------------------- dialogs
function dialog(title, html, onClose) {
  const v = h(`<div class="veil"><div class="dialog" role="dialog" aria-label="${esc(title)}"><header><h2>${esc(title)}</h2><button>${icon("x")}</button></header>${html}</div></div>`);
  const close = () => { v.remove(); document.removeEventListener("keydown", esc_); onClose && onClose(); };
  const esc_ = e => { if (e.key === "Escape") close(); };
  v.onclick = e => { if (e.target === v) close(); };
  v.querySelector("header button").onclick = close;
  document.addEventListener("keydown", esc_);
  document.body.append(v);
  return v;
}

function openSettings() {
  const v = dialog(t("Settings"), `<section id="set-body"></section>`, () => { LANG = S.settings.lang; renderMain(); });
  const body = v.querySelector("#set-body");
  const paint = () => {
    body.innerHTML = `
      <h4>${t("Language")}</h4>
      <div class="seg" id="seg">${Object.entries(S.langs).map(([k, n]) => `<button data-l="${k}" class="${k === LANG ? "on" : ""}">${n}</button>`).join("")}</div>
      <h4 style="margin-top:22px">${t("Name")}</h4>
      <div class="keyrow"><div class="wrap"><input class="field" id="set-name" maxlength="40" value="${esc(S.settings.name || "")}"></div><button class="btn ghost" id="save-name" style="height:48px">${t("Save")}</button></div>
      <h4 style="margin-top:22px">${t("Services")}</h4>
      <p class="muted" style="margin:0 0 6px;font-size:13.5px">${t("Add keys for more services: when one runs out of free limit, Lanterna switches to the next.")}</p>
      <div>${S.providers.filter(p => !p.local).map(p => `<div class="row" data-p="${p.id}">
        <div class="grow"><b>${esc(p.name)}</b><small>${p.has_key ? esc(p.masked) : t("No key")}</small></div>
        <a class="link" style="font-size:13px" data-href="${esc(p.key_url)}">${icon("ext")}</a>
        ${p.has_key ? `<button class="btn ghost small" data-act="rm">${t("Remove")}</button>` : ""}
        <button class="btn ${p.has_key ? "ghost" : "primary"} small" data-act="add">${p.has_key ? t("Change") : t("Add")}</button>
      </div>`).join("")}</div>
      <h4 style="margin-top:22px">${t("Memory")}</h4>
      <p class="muted" style="margin:0 0 6px;font-size:13.5px">${t("Facts Lanterna remembers about you. They stay on this computer and are sent to the model with each message.")}</p>
      <div id="facts"></div>
      <div class="keyrow"><div class="wrap"><input class="field" id="fact-new" maxlength="300" placeholder="${t("Add a fact")}"></div><button class="btn ghost" id="fact-add" style="height:48px">${icon("plus")}</button></div>
      <h4 style="margin-top:22px">${t("Reminders")}</h4>
      <p class="muted" style="margin:0 0 6px;font-size:13.5px">${t("Reminders pop up while Lanterna is open.")}</p>
      <div id="rems"></div>
      <h4 style="margin-top:22px;display:flex;align-items:center">${t("Free models right now")}<button class="btn ghost small" id="refresh" style="margin-left:auto">${icon("refresh")} ${t("Search again")}</button></h4>
      <div class="models" id="models"></div>`;
    body.querySelectorAll("[data-l]").forEach(b => b.onclick = async () => { LANG = b.dataset.l; S = await api.save_settings({ lang: LANG }); v.querySelector("header h2").textContent = t("Settings"); paint(); });
    $("#save-name", body).onclick = async e => { S = await api.save_settings({ name: $("#set-name", body).value.trim() }); e.target.textContent = t("Saved"); };
    body.querySelectorAll(".row[data-p]").forEach(row => {
      const id = row.dataset.p;
      row.querySelectorAll("[data-act]").forEach(b => b.onclick = async () => {
        if (b.dataset.act === "rm") { if (confirm(t("Remove the key for {p}?", { p: pname(id) }))) { S = await api.delete_key(id); paint(); } return; }
        if (row.nextElementSibling && row.nextElementSibling.classList.contains("keyrow")) return;
        row.insertAdjacentHTML("afterend", keyRow(id));
        wireKeyRow(body, id, () => setTimeout(paint, 900));
      });
    });
    $("#refresh", body).onclick = () => loadModels(true);
    loadModels(false);
    paintFacts(); paintRems();
    $("#fact-add", body).onclick = async () => { const i = $("#fact-new", body); if (i.value.trim()) { await api.add_fact(i.value.trim()); i.value = ""; paintFacts(); } };
    $("#fact-new", body).onkeydown = e => { if (e.key === "Enter") $("#fact-add", body).click(); };
  };
  const paintFacts = async () => {
    const list = await api.facts(), box = $("#facts", body);
    box.innerHTML = list.length ? list.map(f => `<div class="row"><div class="grow">${esc(f.text)}</div><button class="btn ghost small" data-f="${f.id}" title="${t("Remove")}">${icon("trash")}</button></div>`).join("")
      : `<p class="faint" style="margin:4px 0;font-size:13.5px">${t("Nothing yet. Say “remember that…” in a chat.")}</p>`;
    box.querySelectorAll("[data-f]").forEach(b => b.onclick = async () => { await api.delete_fact(+b.dataset.f); paintFacts(); });
  };
  const paintRems = async () => {
    const list = await api.reminders(), box = $("#rems", body);
    box.innerHTML = list.length ? list.map(r => `<div class="row"><div class="grow"><b>${esc(r.text)}</b><small>${esc(r.when)}</small></div><button class="btn ghost small" data-r="${r.id}">${t("Cancel")}</button></div>`).join("")
      : `<p class="faint" style="margin:4px 0;font-size:13.5px">${t("No reminders. Say “remind me in 20 minutes…” in a chat.")}</p>`;
    box.querySelectorAll("[data-r]").forEach(b => b.onclick = async () => { await api.cancel_reminder(+b.dataset.r); paintRems(); });
  };
  const loadModels = async refresh => {
    const box = $("#models", body);
    box.innerHTML = `<div class="status"><span class="spinner"></span>${t("Searching for free models…")}</div>`;
    const r = await api.models(refresh);
    if (!r.ok) { box.innerHTML = `<div class="status err">${t("Add a key in Settings to start.")}</div>`; return; }
    const cls = { ok: "green", limited: "amber", untested: "" };
    box.innerHTML = r.models.slice(0, 12).map(m => `<div class="mrow"><div class="nm"><small>${esc(m.provider)}</small>${esc(m.model)}</div>
      <span class="faint">${m.latency ? m.latency.toFixed(1) + "s" : ""}</span><span class="badge ${cls[m.status] || ""}">${t(m.status)}</span></div>`).join("");
    setModel(r.current);
  };
  paint();
}

function openAbout() {
  dialog(t("About"), `<div class="about">
    <div class="hero-logo"><img src="logo.svg" alt=""></div>
    <div class="wordmark">Lanterna</div>
    <div class="byline">${t("Made by")} <b>${esc(S.author)}</b> · ${t("Version {v}", { v: esc(S.version) })}</div>
    <p class="muted" style="max-width:380px;margin:0 auto 22px">${t("Free and open source (MIT). No ads, no tracking — your chats stay on your computer.")}</p>
    <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap">
      <button class="btn primary" data-o="1">${icon("star")} ${t("Star on GitHub")}</button>
      <button class="btn ghost" data-o="1">${t("Project page")} ${icon("ext")}</button>
    </div></div>`).querySelectorAll("[data-o]").forEach(b => b.onclick = () => api.open_url(S.homepage));
}

// pywebview injects its API a moment after load; dev mode (token) can start right away
if (TOKEN) boot();
else if (window.pywebview && window.pywebview.api) boot();
else window.addEventListener("pywebviewready", boot);
