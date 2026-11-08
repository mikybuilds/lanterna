# Changelog

## Unreleased

**New**
- **Private chat:** the 🕶 button next to New chat (F7 in the terminal app) opens a chat that lives only in memory: it is never written to disk, synced or put in a backup, memory and your other chats aren't used, and no side model names it or suggests follow-ups. It is gone for good as soon as you leave it or close Lanterna. The model you ask still gets your messages, as always.
- **Encrypted weekly backups and restore:** set a password in Settings → Chats → Backups, and once a week Lanterna saves all chats, memory, reminders and regular tasks in one encrypted file (AES-256) in Documents\Lanterna backups (you can pick another folder, for example a USB stick or a synced folder). The last 4 are kept; nothing else in the folder is touched. The password is never stored: only a key made from it sits in the Windows secure store, like your API keys, and no keys or sign-ins go into a backup. “Restore from a backup…” opens such a file on any computer with its password (or an older plain JSON backup) and brings back only what is missing: a chat deleted by mistake comes back, nothing here is removed or changed.
- **Ask about a snip (Windows):** snip a part of the screen with Win+Shift+S (or copy any picture), press the quick-question hotkey, and the quick window shows the picture with Explain, Translate (the text in it) and Ask about it. Like copied text, Lanterna looks at the clipboard only at that moment, skips copies marked private, and sends nothing until you press a button. A model that understands pictures is needed (Gemini, or a local photo model).
- **Your own instructions and chat roles:** in Settings → Chats → Instructions and roles, tell Lanterna once how to answer in every chat (who you are, the tone, the length). The 🎭 button under the message box gives one chat a role: Tutor (explains step by step and asks you questions), Translator (every message into English, or from any language into yours) or Proofreader (corrects spelling and grammar and lists the changes). F6 in the terminal app.
- **Lanterna remembers your earlier chats:** ask “what did you suggest last time about my bike?” and the model looks through your saved chats on this computer (by words, then reads the one it found). It happens only when you talk about something said before, and “What went to the model” shows which words and which chat. Private chats are never looked at.
- **Second opinion:** a button under the last answer (F4 in the terminal app) asks the same question to another model — from another service when you have one — and shows its answer right under the first one, to compare. The second model doesn't see the first answer and can only look things up (search, weather, rates, math): it never changes memory, reminders, files or your PC. Retry and Edit take both answers back.
- **Long files: only the parts that fit your question.** A long attachment (a manual, a contract, a book) no longer sends just its start: Lanterna picks the parts that fit what you asked and says so in “What went to the model”. Press “Whole file” on the file before sending to send all of it.
- **Scanned PDFs and more file types:** a PDF with no text layer (a scan, a photo of a document) goes to the model as pictures of its first 4 pages, so a model that sees pictures can read it. Excel (XLSX), PowerPoint (PPTX), OpenDocument (ODT, ODS, ODP) and e-books (EPUB) are read too, in chats and in folders you share.
- **Answers read aloud:** press 🔊 under an answer (F3 in the terminal app), or let every new answer be read by itself. Choose in Settings → Voice → Reading aloud: the voices Windows already has (nothing to download), or Piper with natural voices in 7 languages. Piper is a separate free program with its own license (GPL), so it is not part of Lanterna: it is downloaded on request from its own page as pinned files checked by SHA-256, and works offline. Code and links are skipped.
- **Easier Settings:** tabs by topic at the top (General, Models, Memory and reminders, Chats, Voice, Computer and tools, Account) and a box that finds a setting by its words. The last tab is remembered.
- **Exchange rates and units:** “how much is 100 dollars in hryvnias?” uses today's official National Bank of Ukraine rate (about 60 currencies, any pair), and “5 miles in km”, “6 sotkas in hectares”, “350 °F in °C” are converted exactly, not guessed. Units work offline.
- **Audio files become text:** attach a voice message or a recording (MP3, WAV, OGG, M4A, FLAC, WEBM…) and ask about it. Lanterna turns it into text with the voice input you set up (Groq online, or whisper.cpp on your PC for MP3/WAV/OGG/FLAC) and sends the text to the model.
- **Morning summary** (Settings → Reminders, off by default): once a day at the time you pick, a short note for the day — the weather in your city, today's reminders and regular tasks. It is made on your computer without a model; only the weather comes from Open-Meteo, and only if you set a city. “Show it now” previews it.
- **Repeating reminders:** “remind me every day at 9 to take my pills” makes a reminder that comes back every day, on weekdays, every week or every month. It needs no model and no internet: just the reminder at its time. Missed times (the PC was off) are skipped, not shown one by one. Settings → Reminders marks them with 🔁.
- **Snooze 10 min:** a reminder in the window has a “Snooze 10 min” button (F8 in the terminal app). A repeating reminder keeps its own time.
- **Search your chats:** the box above the chat list finds words in chat names and messages (any case, any language). Click a result: the chat opens at the first message with those words. In the terminal app too.
- **Help with text you just copied (Windows):** copy some text, press the quick-question hotkey, and the quick window offers Translate, Explain and Fix mistakes. Lanterna looks at the clipboard only at that moment, skips copies a password manager marks as private, and sends nothing until you press a button. You can turn it off in Settings → Always at hand.
- **A free hotkey by itself:** if another app already uses Ctrl+Shift+Space, Lanterna picks the next free one once and tells you which. A hotkey you picked yourself is never changed.
- **Models check themselves:** once a day Lanterna quietly sends one tiny request to the first untested models in its queue (6 at most), so a question never waits on a model that doesn't answer. A model that hung or is gone rests for longer each time (1 hour, 6 hours, a day, three days), even after a restart, and comes back by itself once it answers again.

**Fixed**
- **Sync:** a message removed on one device (Retry, Edit) now goes on the others too, and an older copy from another device no longer brings back anything you deleted.
- **Memory in any language:** "forget my allergy" now finds "Allergy to peanuts" in Ukrainian and other languages, and the same fact in another case isn't saved twice. When memory is full, nothing old is dropped behind your back: Lanterna says so and asks what to forget.
- **The window can call only its own list of actions**, not the rest of Lanterna (the database, MCP, Confirm cards).
- **Honest notes:** "What went to the model" names files attached earlier that go along with the chat again; a regular task that fails tells you once; when every free model is out of limits, Lanterna says when the first one is back and suggests adding another free service.
- **Notifications come from Lanterna's own tray icon** (a click opens Lanterna), not from PowerShell, so they also work where PowerShell is locked.
- **Screenshots take the screen under the mouse**, not always the main one.
- **The right model's name** under each answer when two answers run at the same time; a broken search page is reported as "search failed", not "nothing found"; the terminal app redraws long answers less often.
- **A question could look stuck for minutes.** Some new online models (for example gemini-3.7-flash) accept a question and then say nothing. Lanterna now gives an online model 30 seconds to start answering, then moves on to the next one and leaves the silent one alone. A slow answer that has already started is not cut off.
- **"Thinking…" disappeared** when the chat was redrawn while an answer was still coming (opening the window from the tray, clicking the chat in the list). Now the live answer stays in place, and Retry / Edit show up only when it's done.

## 1.0.0 — always at hand, regular tasks, voice and MCP

**New**
- **Always at hand (Windows):** Lanterna lives next to the clock. Closing the window keeps it running in the tray (Settings → Always at hand). Quit it from the tray icon's menu.
- **Quick question:** press Ctrl+Shift+Space anywhere to open a small window, ask, and close it with Esc. "Open in Lanterna" continues the chat in the big window. You can pick another hotkey or turn it off in Settings.
- **Ask about your screen:** the camera button in the quick window, or "Ask about my screen" in the tray menu, attaches a screenshot to your question.
- **Start with Windows:** off by default. When it's on, Lanterna starts hidden in the tray.
- **Regular tasks:** say "every morning at 8 tell me the weather in Kyiv" or "in the evening tell me if it will rain tomorrow", or add one in Settings → Regular tasks.
  - Lanterna does the task on schedule and sends you a notification. Each task keeps its results in its own chat.
  - With a condition ("only if it rains"), Lanterna stays quiet when it's not true.
  - Tasks use only safe tools (weather, web search, pages) and run while Lanterna is open or in the tray. They stay on this computer.
  - In Settings you can run, pause or delete a task.
- **Voice input:** press the microphone next to the message box (or F2, also in the terminal), speak, and press it again. Your words appear in the box, so you can fix them before sending.
  - Choose how in Settings → Voice input: off (the default), online with Groq Whisper (fast, needs the Groq key), or on this computer with whisper.cpp (nothing leaves your PC).
  - On this computer: a one-time download of the speech engine and a model (Quick 60 MB, Better 190 MB or Best 574 MB). Every file is checked before it's used.
  - A recording stops by itself after 2 minutes. Esc cancels it.
- **MCP servers (advanced):** connect outside tools made by other people: a program on this computer (for example `npx -y @modelcontextprotocol/server-memory`) or an https:// address. Settings → MCP servers, also in the terminal.
  - Off by default. Turning it on first shows a window about the risks, and you have to tick "I understand the risks".
  - Before adding a server, Lanterna shows the exact command or address it will use.
  - Before every tool call there is a card with what goes to the server. It runs only after Confirm, unless you let that tool run without asking (window app: tick it in Settings).
  - Keys and tokens for servers go to the system's secure store. You can paste the usual `{"mcpServers": …}` JSON from a server's page.
  - Server answers go to the model marked as outside data, not instructions. Programs started for MCP end when Lanterna ends.

## 0.6.0 — edit and retry, save chats, memory that updates itself

**New**
- **Edit and Retry:** under your last message there is Edit (the question comes back to the box, its answer goes), under the last answer Retry (a new answer replaces it). Terminal: Ctrl+E and Ctrl+R.
- **Save a chat:** the save button at the top writes the chat as a Markdown file to Downloads (click the notice to see it in the folder). Terminal: Ctrl+X.
- **Backup:** Settings → Chats → "Save a backup of all chats" puts all chats, memory and reminders in one JSON file. It's plain text, so keep it somewhere safe.
- **Memory that updates itself** (off by default, Settings → Chats → "Learn about me from chats"): when you tell something about yourself, a fast model adds lasting facts to Memory, such as your job, city or what you like. Each new fact shows as "Remembered: …" with Undo. It never saves passwords or numbers and skips facts it already knows.

**Fixed**
- Retry after an error no longer saves your question twice.

## 0.5.0 — a smarter chat: questions first, chat names, follow-ups, long chats

**New**
- **Chat names:** after the first answer, a fast model gives a new chat a short name in your language (for example "Феррара за один день") instead of the first line of your message. A name you typed yourself is kept. Settings → Chats → "Name new chats automatically" (on by default; one small extra request).
- Small side jobs like this go to a fast model with generous limits (not Gemini, whose 5 requests a minute are kept for answers); in Local mode they stay on your computer.
- **What to ask next:** up to 3 buttons under an answer with natural follow-up questions; one click sends it. Settings → Chats → "Suggest what to ask next". Only from a fast online model that isn't Gemini, so it never eats the answer limit; not in Local mode.
- **Why it searches:** the "what I'm doing" line now also says why, in the model's own words — "Searching the web: Palazzo dei Diamanti orari — to find the opening hours".

- **Long chats are remembered:** past 30 messages the older part used to be simply dropped. Now a fast model writes a short summary of it (names, facts, decisions, code names), and the model gets the summary plus the newest 20 messages. The chat shows where the summary begins; the summary stays on this device. Settings → Chats → "Remember long chats".

- **Questions before a big task:** when you ask for something big ("write me a calculator program", "help me write an essay"), the model can first ask 1–4 short questions with option buttons, a field for your own answer and Skip. Your answers go to it as instructions; it asks only once per task. Window and terminal. Settings → Chats → "Ask before big tasks".

**Fixed**
- Terminal app: the "Try one:" idea buttons on the start screen filled the box but didn't send.
- "What went to the model" counted two messages too many (the first message already said "and 2 earlier messages").

## 0.4.0 — more reliable answers with web search

**Changed**
- Fewer wasted searches: the same (or almost the same) web search or tool call is not run twice in one answer, and near the end of its tool rounds the model is told to stop searching and answer. Saves free-limit requests (Gemini allows only 5 a minute).
- **Long web pages:** instead of the first 4000 characters, the model gets the parts of the page that fit the question (found locally, no extra model request). Gemini gets more of the page, Groq and local models less, so they stay within their limits.
- **Models that can't use tools** (some small local models): for questions about news, prices, "today" and so on, Lanterna searches the web first and gives the results to the model, so it doesn't make up fresh facts.
- Clearer tool descriptions with examples (search queries, reminders, memory, sorting folders); the model is told to look up exact function and menu names in programs instead of guessing.

**Fixed**
- Wikipedia pages could not be opened (HTTP 403): Lanterna now tells sites where it comes from, as Wikipedia asks.

## 0.3.6 — Gemini answers after a web search again

**Fixed**
- Gemini sometimes gave no answer at all after searching the web (the reply stayed empty). The last round now tells it to answer instead of taking the tool list away; if a model still sends nothing, it is asked once more, and then a clear message with Retry is shown.
- "What went to the model" and a few other window strings were in English in Ukrainian and Italian.

## 0.3.5 — undo, a check-up and four more languages

**New**
- **Four more languages:** Deutsch, Español, Français, Polski (window app, terminal app and command line).
- **What Lanterna did:** a list of every confirmed change on this computer with **Undo** — moved and sorted files go back, files come back from the Recycle Bin (Windows and Linux), a new empty folder is removed, a file's old version comes back, theme / power plan / startup apps switch back, an installed program is uninstalled. Kept on this device only.
- **Check Lanterna** (About → Check Lanterna, `lanterna doctor`): every part with ✓ / ! / ✗ and a plain sentence; copy it or put it into a bug report.
- **Linux: Update now** for pipx installs — Lanterna runs the upgrade and offers Restart.
- **Weekly tidy-up of Downloads** and **help freeing disk space** — both off by default, in Settings → Computer.
- **What went to the model** under each reply.
- **Try one:** ready example buttons in an empty chat.
- **Local model as a spare** when the free online limits run out (Cloud mode, on by default), and **Install Ollama** with winget on Windows.
- CI takes SVG screenshots of every terminal-app screen in every language and fails on untranslated text.

**Changed**
- Window app: the sidebar buttons at the bottom are stacked, so long names in any language fit.

## 0.3.4 — no more browser messages over the terminal app

**Fixed**
- Terminal app on Linux: the browser opened for Google sign-in (or any link, folder or Settings page) printed its own log lines over Lanterna's screen. Programs Lanterna starts are now cut off from its terminal.

## 0.3.3 — one Google sign-in for everything, and help with your computer

**New**
- **Sign in with Google first**: right after picking the language, setup offers Sign in with Google (you can skip it; installs set up before see it once). After the sync password a new device gets your chats, settings and API keys and skips the rest of the setup.
- Sync now also carries the main settings (mode, service, models) and the model services' API keys, inside the same file encrypted with your sync password. The newest change wins; a device that is already set up wins over a fresh install. Folders, local models and sign-ins stay on each device.
- The same sign-in connects the Google Drive connector too, so there is no second sign-in. Disconnecting Drive keeps sync.
- **Help with this computer** (Settings → Computer, on by default). Ask "sort my Downloads", "find duplicates on my Desktop", "install VLC", "my PC is slow", "turn on dark mode":
  - Lanterna knows where your Downloads, Desktop, Documents, Pictures, Videos and Music are and looks there on its own. System folders, program folders, AppData and hidden files are off limits; files that look like passwords or keys are never opened.
  - Sorting puts files into folders by type and/or month, skips files still downloading, and can be **undone** with one button.
  - Moving, renaming, new folders and **Recycle Bin** (never deleted for good) each wait for Confirm.
  - Programs: search, install, update and uninstall with **winget** on Windows, **dnf / Flatpak** on Linux. The card shows the publisher, version, source and the exact command before Confirm.
  - Settings: a fixed list of safe actions only — light/dark theme, power plan, which apps start with the computer, opening a Settings page. Plus a read-only check-up: disk space, memory, what uses the processor now, what starts with the computer. No other commands are ever run.
- Terminal app: the same Google step, the computer help, and the chat list follows sync without a restart.

**Fixed**
- Lanterna could say "Done" before you pressed Confirm; now it says what will happen.

## 0.3.2 — the new look shows up after updating

**Fixed**
- After updating, the window could keep showing the previous version's interface from its cache, so the limit bar and the folder button under the message box were missing. Lanterna now clears only the window's cache when its interface files change; chats, settings and sign-ins are not touched.

**Changed**
- Every commit pushed through the GitHub connector shows Lanterna Assistant as a co-author; the switch to turn that off is gone. It is only a name on the commit and gives no access.

## 0.3.1 — GitHub, a folder per chat, and see what Lanterna is doing

**New**
- **GitHub connector** (Settings → Connectors): ask "push this to my repository" and Lanterna prepares one commit with the files from the chat's folder; you see the repository, the files and the message, and press Confirm. It is a GitHub App you install only on the repositories you choose, with one permission (files). It can't delete repositories or change settings; files that look like passwords or keys are never pushed. Commits show Lanterna Assistant as a co-author (can be turned off); it gets no access from that.
- **Limit bar** under the message box: how much of the free limit of the model in use is left, and when it resets (Gemini: midnight in California). Click it for all limits.
- **Folder of each chat**: the button under the message box shows which folder this chat works in; change it right there, or use no folder for this chat. New chats start with the folder from Settings.
- Instead of three jumping dots you see what Lanterna is doing right now: "Searching the web: …", "Preparing the file hello.txt", or the model's own short thought headings (Gemini). After the answer they fold into "Thinking · steps: N"; click to see them.

**Fixed**
- A confirmation card could vanish when the chat was redrawn (after closing Settings, a sync or switching chats), so there was nothing to press. Cards waiting for Confirm now always come back at the end of the chat.
- Closing Settings while an answer was being written hid that answer until the chat was opened again.
- Lanterna said "I created the file" before you confirmed; now it says what will happen.

## 0.3.0 — your folder, Google Drive, limits and one-click updates

**New**
- **Working folder** (Settings → Working folder): choose one folder and Lanterna can look at its files, find and read them (text, code, PDF, Word), and create, change or move files there. Every change shows a card with what will happen and a **Confirm** button first. Nothing is ever deleted, a rewritten file is backed up, and Lanterna sees nothing outside that folder.
- **Google Drive connector** (Settings → Connectors): ask "make a folder School in my Drive" or "upload plan.md to Drive" — after you confirm, it's done. Lanterna asks Google only for its own files (`drive.file`): it can't see the rest of your Drive.
- **Limits** (Settings → Limits): requests per model today, what each service says is left, and which models are resting after a limit and for how long.
- **Update now**: the installed app downloads the new version, checks it against the release checksum, installs it over the old one and opens again. No more Setup files piling up in Downloads.

**Fixed**
- With Gemini 3, questions that use a tool (weather, search, reminders…) jumped through many models ("switched to …" again and again) and could stop working for the rest of the day. Lanterna now sends back the extra data Gemini needs, so the first model answers.
- A model that hangs is set aside for 15 minutes on its own instead of blocking the whole service.
- Gemma models on Gemini no longer show their hidden reasoning (`<thought>…`) in the reply.
- A daily limit ("retry in 1h31m") is understood and remembered, even after a restart, so Lanterna doesn't try that model again and again. Instead of a ladder of "switched to …" lines you see one.
- One broken answer no longer pauses every model of that service.

## 0.2.0 — your chats on all your devices

**New**
- Sign in with Google to see the same chats on all your devices (Settings → Account and sync, or `lanterna sync in`). Chats, memory, reminders, name and language are kept in a hidden folder of your own Google Drive, encrypted with a sync password only you know. API keys are not synced.
- If the sign-in page opens in the wrong browser, copy its link and open it where you use Google.

## 0.1.2 — Gemini fix and bug reports

**New**
- Report a bug from the app (About → Report a bug, Settings, or `lanterna bug`): you write what happened, see the exact text, then send it yourself. Lanterna can add the version, system, mode and last errors, never chats, keys or your name.

**Fixed**
- With Google Gemini a reply could fail with "'list' object has no attribute 'get'" instead of moving on to the next model (Gemini sends its errors in a different shape).
- Gemini models for images, audio, live voice and robots are no longer tried for chat, so the first reply comes faster.

## 0.1.1 — update notice and Ubuntu menu

**New**
- When a new version is out, Lanterna tells you at start, with what's new and the exact steps for your kind of install (installer, portable zip, pipx…). You can turn this off in Settings.
- `lanterna update` in the terminal shows the same.
- `lanterna desktop` adds Lanterna to the GNOME app menu (Super → type Lanterna).
- Clear Ubuntu / GNOME install steps in the README, checked automatically on Ubuntu 22.04 and 24.04.

**Fixed**
- In the terminal app a chat could show twice in the chat list.
- Local models screen in the terminal app: all recommended models are visible in small windows too.

## 0.1.0 — first public preview

**Two apps, one assistant**
- Windows window app with chats, settings and a first-run setup (language, name, mode, first free service).
- Full-screen terminal app for Ubuntu / GNOME (mouse and keyboard) with the same chats; `lanterna chat` for a plain line-by-line chat.
- English, Ukrainian and Italian.

**Free cloud models**
- Groq, Google Gemini, OpenRouter, Cerebras, Mistral and GitHub Models with your own free keys, stored in the system's secure vault.
- Finds the models that are free right now and ranks them; when one hits its limit, the next one answers.

**Local models (optional)**
- Checks your graphics card, RAM and disk and suggests models that fit; downloads through Ollama only when you press Download, with progress.
- Cloud, Local and Auto modes. Auto answers on your PC and sends hard questions (proofs, code, analysis) to a bigger online model; you can turn that off.

**Tools**
- Memory you can see and edit, reminders with system notifications, web search and page reading, weather and air quality, files (PDF, Word, text, code) and photos, exact math and dates.

**Privacy**
- No telemetry. Chats, memory and reminders stay on your computer. The only request Lanterna makes on its own is the update check when you open About.

**Known limits**
- Windows shows "Unknown publisher" for the installer (the code is not signed): choose *More info → Run anyway*.
- macOS is not tested.
