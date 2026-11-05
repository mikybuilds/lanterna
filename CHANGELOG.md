# Changelog

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
