<p align="center"><img src="assets/logo.svg" width="120" alt="Lanterna logo"></p>

<h1 align="center">Lanterna</h1>
<p align="center">A friendly AI assistant that runs on <b>free cloud models</b> — or on <b>your own local models</b> if your PC is strong enough.<br>
<sub>by mikybuilds · MIT licence</sub></p>

> **Status: early preview (v0.3.4).** Windows window app and a full-screen terminal app for Linux, with memory, reminders, web search, weather, files and photos, a working folder per chat, help with your computer (folders, programs, safe settings), Google Drive and GitHub connectors, free-model discovery with fallback, and optional local models through Ollama. Expect rough edges — [issues](../../issues) are welcome.

<p align="center"><b><a href="#windows-10--11">⬇ Install on Windows</a></b> · <b><a href="#linux">🐧 Install on Linux</a></b></p>

<p align="center"><img src="docs/screen-chat.png" width="760" alt="Lanterna chat window"></p>

## Why

Running a good model locally needs a strong graphics card. Lanterna lets anyone chat with a capable assistant using free tiers from cloud providers, and switches to local models (Ollama) on machines that can handle them.

- **Free.** Uses free API tiers. Lanterna never calls a paid model.
- **Private keys.** Your API keys are stored in your system's secure vault (Windows Credential Manager, or GNOME Keyring / KWallet on Linux), never in plain files or logs.
- **No telemetry.** Lanterna sends nothing to its author.
- **Same chats on every device** (optional): sign in with Google and your chats are kept, encrypted, in a hidden folder of your own Google Drive.
- **Human tone.** Warm, short when you're short, honest when it isn't sure.
- **English, Українська, Italiano, Deutsch, Español, Français, Polski.**

## Install

### Windows 10 / 11

1. Open the [latest release](../../releases/latest) and download **`Lanterna-Setup-x.y.z.exe`**.
2. Run it. No admin rights needed; Lanterna appears in the Start menu.

> Windows will say **"Windows protected your PC" / Unknown publisher**: the installer isn't code-signed (signing costs money). Click **More info → Run anyway**. The installer is built from this repository by the [release workflow](.github/workflows/release.yml), so you can check what's inside. Prefer no installer? Take the portable zip from the same release.

### Linux

A full-screen app that runs in the terminal, with mouse support. Made for any desktop (GNOME, KDE Plasma, Xfce…) and distribution.

**You need:** Python **3.10 or newer**, plus `pipx` and `git`. Check your Python with `python3 --version` — Ubuntu 22.04+, Fedora 36+, Debian 12+, Linux Mint 21+, openSUSE Tumbleweed and Arch all have a new enough one.

**1.** Open a terminal and install pipx and git (once) with your system's package manager:

| Distribution | Command |
|---|---|
| Ubuntu, Debian, Linux Mint, Pop!_OS | `sudo apt update && sudo apt install -y pipx git` |
| Fedora | `sudo dnf install -y pipx git` |
| Arch, Manjaro | `sudo pacman -S --needed python-pipx git` |
| openSUSE | `sudo zypper install python3-pipx git` |

Then run this, close the terminal and open a new one:

```bash
pipx ensurepath
```

**2.** Install Lanterna:

```bash
pipx install git+https://github.com/mikybuilds/lanterna
```

**3.** Add it to your app menu (optional), then find it there by typing *Lanterna*:

```bash
lanterna desktop
```

Or just type `lanterna` in any terminal.

Update: Lanterna tells you when a new version is out; then run `pipx upgrade lanterna` · Remove: `lanterna desktop --remove && pipx uninstall lanterna`

Keys are kept in your system keyring (GNOME Keyring, KWallet). On a server without a keyring, set the key as an environment variable instead (e.g. `GROQ_API_KEY`).

> Tested automatically on Ubuntu 22.04 and 24.04 on every change. Other distributions use the same steps; if something doesn't work, please [open an issue](../../issues).

### First launch

On first launch you pick a language, your name and your first free service:

| | Groq — *Fastest* | Google Gemini — *Smartest & most generous* |
|---|---|---|
| Speed | replies almost instantly | fast |
| Free limits | smaller daily limit | big free limits |
| Extras | strong open models (GPT-OSS, Qwen) | understands photos and documents, long memory |
| Get a key | [console.groq.com/keys](https://console.groq.com/keys) | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

More free services can be added any time in Settings → Models (each needs its own free key; none asks for a card):

| Service | What to know |
|---|---|
| OpenRouter | only its free models are used: 50 requests a day |
| Mistral | needs a phone number; on the free plan Mistral may use what you send to train its models |
| NVIDIA | needs a phone number; free for personal use and testing, about 40 requests a minute |
| Z.ai (GLM) | only its free GLM Flash models are used, so nothing is ever charged |
| Cohere | 1,000 free requests a month, for personal use only |

Lanterna only ever uses free models, so a key never costs you money. Cerebras and GitHub Models were removed when they stopped being free.

In a terminal `lanterna` opens a full-screen app (chats on the left, Ctrl+N new chat, Ctrl+S settings, Ctrl+O models). `lanterna chat` gives a simple line-by-line chat.

<p align="center"><img src="docs/screen-terminal.png" width="720" alt="Lanterna in a terminal"></p>

`lanterna ask "question"` prints one answer, for scripts: `git diff | lanterna ask "write a commit message"` sends the piped text with the question (`-f file` attaches a file, `--save` keeps it as a chat; memory about you isn't sent).

Other commands: `lanterna models` (free models available right now), `lanterna local` (local models), `lanterna key set <provider>`, `lanterna key list`, `lanterna setup`, `lanterna about`.

## Your chats on all your devices

Lanterna offers **Sign in with Google** right after you pick the language (you can skip it); later it is in **Settings → Account and sync** (in a terminal: `lanterna sync in`). Then choose a sync password; on your other devices sign in with the same Google account and enter the same password — the chats, settings and API keys come over by themselves, and setup is done.

- Lanterna asks Google for its own hidden folder in your Google Drive (`drive.appdata`) and, in the same sign-in, for the Google Drive connector (`drive.file`: only files Lanterna creates). It can't see your other files. You may untick the Drive part on Google's page; sync still works.
- Chats, memory, reminders, your name and language, the main settings (mode, service, models) and the API keys of the model services are kept there as one file encrypted with AES-256 and your sync password, so Google can't read them. Working folders, local models and sign-ins to Google or GitHub stay on each device.
- Syncs when something changes and every two minutes while Lanterna is open. Deleting a chat deletes it everywhere.
- **Sign out and delete the copy in Google Drive** removes everything from Drive; chats on your devices stay.
- Forgot the sync password? Chats on your devices are safe; sign out with *delete the copy* and start again with a new password.

## Your folder and Google Drive

**Settings → Working folder → Choose a folder** (the folder new chats start with; each chat can change it with the folder button under the message box). Then just ask: "what's in my homework file?", "make plan.md with a plan for tonight", "move the old notes into a folder Archive".

- Lanterna sees only that folder (not a whole disk, your home folder or system folders). Reading is immediate; every change — a new or rewritten file, a new folder, a move — shows a card with the change and a **Confirm** button. Nothing is ever deleted; a rewritten file is backed up in Lanterna's own folder first. Files Windows could run (.exe, .bat, .ps1…) are never written.
- The files it opens go to the model in use (to the online service in Cloud mode, nowhere in Local mode).

**Settings → Connectors → Google Drive → Connect.** Then: "create a folder School in my Drive", "upload plan.md to the School folder", "save these notes to Drive as a Google Doc". Each one waits for **Confirm**. Lanterna asks Google only for `drive.file`: it sees and changes only what it created, never the rest of your Drive. **Disconnect** removes the permission.

**Settings → Connectors → GitHub → Connect.** Lanterna shows a short code; type it on GitHub. Then choose which repositories it may use (**Choose repositories**). Now you can ask: "push my mod to mikybuilds/my-mod". You see a card with the repository, the branch, the files and the commit message, and nothing is sent before **Confirm**.

- It is the GitHub App *Lanterna Assistant* with one permission: the files (Contents) of the repositories you pick. It can't create or delete repositories, change settings or add people; for a new repository it opens GitHub's own page filled in.
- No password or token is typed into Lanterna; the sign-in is kept in your system's vault. Files that look like passwords or keys (`.env`, private keys, API tokens inside) are never pushed.
- Commits are yours; every one shows Lanterna Assistant as a co-author. That is only a name on the commit, not access.

## Connectors

**Connectors** (sidebar) has two tabs, like the directory in Claude:

- **Browse**: about 75 ready-made connectors from the services themselves — Notion, Linear, Jira and Confluence, Asana, monday.com, ClickUp, Todoist, Airtable, Miro, Canva, Dropbox, Stripe, PayPal, Supabase, Vercel, Sentry, Zapier, Make and more — by category, with search. Press **+**: the service's own sign-in page opens in your browser, and you choose there what Lanterna may do. Searching also looks through the public MCP Registry (servers anyone can publish; shown separately, with who made them).
- **Yours**: what you connected — Mail, Google Drive, GitHub and the connectors you added — with sign-in, on/off, the list of tools, **Sign out** and **Remove**.
- Some services let only apps they approved connect (Gmail's and Google Calendar's own connectors, Microsoft 365, Slack, Figma, HubSpot…). They are listed as unavailable with the reason and, where there is one, another way: for Gmail it is **Mail**. If nothing fits, ask Lanterna: it looks for a connector itself or suggests a workaround with its own tools.
- **Mail** works with Gmail, ukr.net, iCloud, Yahoo, Zoho and any mail with IMAP, through an *app password* (a separate password your mail service makes just for Lanterna; you can revoke it there). Then ask: "sort my inbox into folders", "find the bank letters from last month", "draft a reply to Olena". Reading never marks letters as read; sorting, drafts and sending each wait for **Confirm**, and nothing is deleted.

## Help with this computer

**Settings → Computer** (on by default). Just ask: "sort my Downloads", "what takes the most space in Downloads?", "find duplicate photos", "install VLC", "update my programs", "my computer is slow", "turn on dark mode", "stop Discord from starting with Windows".

- **Folders:** Lanterna finds your Downloads, Desktop, Documents, Pictures, Videos and Music by itself and may look there freely. System and program folders, AppData and hidden files are off limits, and files that look like passwords or keys are never opened.
- **Changes wait for Confirm:** sorting into folders (by type or month — skips files still downloading, and has an **Undo** button), moving, renaming, new folders and moving to the **Recycle Bin**. Nothing is deleted for good.
- **Programs:** search, install, update and uninstall with `winget` on Windows and `dnf` / Flatpak on Linux. The card shows the program, publisher, version, source and the exact command; the install starts only after Confirm.
- **Settings:** only a fixed list of safe actions — theme, power plan, apps that start with the computer, opening a Settings page — plus a read-only check-up (free disk space, memory, what is using the processor). Lanterna never runs any other command.
- File names and the files it opens go to the model in use, like a message (nowhere in Local mode).
- **What Lanterna did** (sidebar; `Ctrl+H` in the terminal app): every confirmed change on this computer, newest first, with **Undo** where possible — files come back from folders and the Recycle Bin, a setting switches back, an installed program is removed again. Kept on this device only (`history.json`, last 300).
- **Optional, off by default** (Settings → Computer): a **weekly tidy-up** of Downloads (a chat with a sort card; nothing moves before Confirm) and **help freeing disk space** (what takes space, plus a note when the disk is almost full; things go only to the Recycle Bin, after Confirm).

## Limits and updates

- The **bar under the message box** shows how much of the free limit of the model in use is left and when it resets; click it for the details.
- **Settings → Limits** shows, per model, how many requests you made today, what the service says is left (Groq, Mistral and some others tell it; Gemini only says it when the limit is reached) and which models are resting after a limit.
- **What went to the model:** under each reply a fold-out line lists what this answer sent and where — your message and how many earlier ones, memory facts, file names, a search, a web page. Never contents of files you didn't open. Stored with the reply on this device only.
- **Out of free limits?** In Cloud mode a downloaded local model answers when every online model is resting or there is no internet (Settings → Local models; on by default, can be turned off). On Windows the same screen can install Ollama with winget after you confirm.
- **Check Lanterna** (About, or `lanterna doctor`): keys, internet, sync, folders, programs and local models, each with a plain sentence. A bug report includes the quick checks (never keys, chats or your name).
- **Update now** (in the update notice, installed app): Lanterna downloads the new Setup, checks its SHA-256 against the release page, installs it silently over the old version and opens again. Chats, settings and keys stay. On Linux (pipx) Update now runs the pipx upgrade itself; you only start Lanterna again.

## Roadmap

- [x] Core, Groq chat in the terminal, secure key storage, personality
- [x] All free services (Groq, Gemini, OpenRouter, Mistral, NVIDIA, Z.ai, Cohere) and automatic discovery of models that are free right now, with fallback when a limit is reached
- [x] Windows app (window with chats, settings, first-run setup)
- [x] Windows installer (Setup.exe) and portable zip, built by the release workflow
- [x] Update notice at start with steps for your kind of install (can be turned off)
- [x] Full-screen terminal app for Linux (mouse + keyboard, same chats as the window app)
- [x] Memory, reminders, web search, files & photos, weather, exact math and dates
- [x] Local models via Ollama with hardware-based recommendations, and an Auto mode
- [x] Working folder with confirmation cards, Google Drive connector, limits view, one-click updates
- [x] GitHub connector, a folder per chat, limit bar, live "what I'm doing" steps
- [x] 1.0: always at hand (tray, quick-question hotkey, screen questions), regular tasks, voice input, MCP servers
- [x] 1.1: reading aloud, morning summary, rates and units, audio and more file types, second opinion, roles, snips, private chat, encrypted backups, `lanterna ask`, ready-made MCP servers

## What it can do

- **Remember** things you tell it ("remember that I'm allergic to peanuts"). You can see and edit the list in Settings.
- **Reminders** ("remind me in 20 minutes to stretch", "every weekday at 8 the bus"): a system notification while Lanterna is open, with "Snooze 10 min". They can repeat every day, on weekdays, every week or every month without using a model. Missed ones show up the next time you open it.
- **Search the web** (DuckDuckGo, no key) and read pages, with the site name as the source.
- **Weather and air quality** for any city (Open-Meteo, no key).
- **Exchange rates and units**: today's official National Bank of Ukraine rate for about 60 currencies, and exact unit conversions (miles, sotkas, °F…) that work offline.
- **Files and photos**: PDF (scans too), Word, Excel, PowerPoint, OpenDocument, EPUB, text and code files, photos and audio recordings (📎 button, drag and drop, or Ctrl+F / `/file path` in the terminal). A long file sends the parts that fit your question; “Whole file” sends all of it.
- **Exact math and dates**: numbers are computed by code, not guessed by the model.
- **Regular tasks** ("every morning at 8 tell me the weather in Kyiv", "in the evening tell me if it will rain tomorrow"): Lanterna does them on schedule and sends a notification, or stays quiet when your condition isn't true. Only safe tools (weather, web search, pages). Settings → Regular tasks.
- **Voice input**: the microphone next to the message box (or F2), off by default. Online with Groq Whisper, or on this computer with whisper.cpp (a one-time, checked download; nothing leaves your PC). Your words land in the box, so you can fix them before sending.
- **Always at hand (Windows)**: Lanterna stays in the tray when you close the window. Ctrl+Shift+Space opens a small quick-question window anywhere; its camera button (or "Ask about my screen" in the tray menu) attaches a screenshot. Copied some text a moment ago? The quick window offers Translate, Explain and Fix mistakes. Start with Windows is off until you turn it on.
- **Search your chats**: the box above the chat list finds words in any chat. Ask “what did you suggest last time about…?” and the model looks through your earlier chats itself.
- **Answers read aloud** (🔊, or every answer by itself): the voices Windows has, or Piper with natural voices in 7 languages (a separate program, downloaded on request).
- **Morning summary** (off by default): the weather, today's reminders and regular tasks in one note at the time you pick.
- **Second opinion**: the same question to another model, its answer right under the first one.
- **Your own instructions and roles**: tell Lanterna once how to answer; give a chat a role (Tutor, Translator, Proofreader).
- **Ask about a snip (Windows)**: Win+Shift+S, then the quick-question hotkey: Explain, Translate or Ask about the picture.
- **Private chat** (🕶, F7 in the terminal app): never written to disk, synced or backed up, no memory used, gone when you leave it.
- **Encrypted weekly backups** (Settings → Chats → Backups): one AES-256 file a week in Documents\Lanterna backups, the last 4 kept; restore on any computer with the password.
- **MCP servers (advanced, off by default)**: add outside tools — a program on this computer or an https:// address, or one of four ready-made servers with a fixed version (files or Git in a folder you pick, a web browser, step-by-step thinking). Turning it on first shows the risks, adding a server shows the exact command, and every tool call waits for Confirm unless you allow that tool.

## Local models (optional)

If your PC has a graphics card, Lanterna can run models on it with [Ollama](https://ollama.com/download) (free). It checks your graphics card memory, RAM and free disk and suggests what fits:

| Graphics card memory | Suggested mode | Models |
|---|---|---|
| none / under 3 GB | Cloud | — (a tiny model only with 16 GB RAM, slow) |
| 3–5 GB | Auto | gemma4:e2b-it-qat, qwen3:4b, qwen3-vl:4b-instruct |
| 6–10 GB | Auto | gemma4:e4b-it-qat, qwen3:8b, qwen3-vl:8b-instruct |
| 11–19 GB | Local | gemma4:12b, qwen3:14b, qwen3-vl:8b-instruct |
| 20 GB and more | Local | gemma4:26b, qwen3:30b-a3b, qwen3-vl:30b-a3b-instruct |

- **Cloud**: free online models, works on any laptop.
- **Local**: everything stays on your computer.
- **Auto**: the local model answers everyday questions; long questions, proofs, code and analysis go to a bigger online model (you can turn this off in Settings). Photos go to the local photo model.

Downloads start only when you press **Download (X GB)**, with progress shown. In the terminal: `lanterna local` (what fits), `lanterna local pull qwen3:8b`, `lanterna local mode auto`.

<p align="center"><img src="docs/screen-local.png" width="640" alt="Local models: hardware check and recommended models"></p>
<p align="center"><img src="docs/screen-modes.png" width="420" alt="Mode setting: Cloud, Local, Auto"> <img src="docs/screen-terminal-local.png" width="420" alt="Local models in the terminal app"></p>

## Privacy

- **No telemetry, no account with Lanterna.** Chats, memory and reminders are stored in a local database in your user folder. If you sign in with Google, an encrypted copy is kept in your own Google Drive (see above). The Google Drive connector, if you connect it, can only touch files Lanterna created there. The GitHub connector, if you connect it, can only write files in the repositories you chose, and only after you confirm. Help with this computer (Settings → Computer) sees only your standard folders, and every change waits for Confirm. [Privacy policy](https://mikybuilds.github.io/lanterna/privacy.html).
- **Cloud mode:** your messages go only to the service you chose (Groq, Gemini…), under its own terms. On their free plans Gemini and Mistral may use what you send to improve their models. **Local mode:** nothing leaves your computer.
- Your memory list is sent to the model together with your messages, so it can use it. You can see and delete it in Settings.
- Web pages and files Lanterna reads are treated as information, never as instructions. So are answers from MCP servers.
- **Voice input** is off by default. Online (Groq Whisper), your recording goes to Groq to become text; on this computer (whisper.cpp) it never leaves your PC. Recordings are not kept.
- **MCP servers** are off by default and made by other people. What a tool is asked goes to that server; a program server runs with your rights. Tokens for servers stay in the system's secure vault.
- **Connectors** are MCP servers too, so they need MCP servers turned on. You sign in on the service's own page; Lanterna never sees that password and keeps only the sign-in it gets back, in the system's secure vault, renewed on its own. Sign out or remove a connector and that sign-in is deleted. What you ask a connector goes to that service. Servers from the public MCP Registry are made by anyone and are not checked by Lanterna.
- **Mail**: the app password stays in the system's secure vault, never in files or logs. Letters Lanterna reads go to the model in use, like a message; the model is told to treat them as information, never as instructions.
- **Exchange rates** come from the National Bank of Ukraine (bank.gov.ua), only when you ask about money; the request carries nothing about you.
- **Reading aloud** with Windows voices stays on your PC. Piper is downloaded only when you ask (pinned files checked by SHA-256) and then works offline.
- **Audio files** you attach are turned into text by the voice input you chose: online with Groq, or on your PC with whisper.cpp.
- **Snips and copied pictures**: Lanterna looks at the clipboard only when you open the quick window, skips copies marked private, and sends the picture only when you press a button.
- **Private chats** live only in memory: never written to disk, synced or put in a backup. The model you ask still gets those messages, as always.
- **Backups** are encrypted with your password before they are written; the password itself is never stored (only a key made from it, in the system's secure vault), and no API keys or sign-ins go into a backup.
- **`lanterna ask`** sends your question and what you pipe into it to the model, without your memory, and saves nothing unless you add `--save`.
- **Screenshots** are taken only when you press the camera button or "Ask about my screen", and go to the model like an attached photo.
- **Copied text**: Lanterna notes only *when* something was copied, never what. It reads the clipboard only when you open the quick window within 90 seconds of copying, skips copies a password manager marks as private, and sends the text only when you press Translate, Explain or Fix mistakes.
- **Model checks**: once a day, up to 6 tiny "Hi" requests go to models in your queue that haven't been tried yet, so they're known to answer before you need them.
- **Morning summary**, if you turn it on and set a city, asks Open-Meteo for that city's weather once a day.
- Apart from what you turn on yourself (above), the only request Lanterna makes on its own is the update check when it starts (a plain request for the latest release, nothing about you). Turn it off in **Settings → Updates**. The limits view is counted from the services' own answers, on your computer.
- Bug reports are never sent automatically: you see the whole text and send it yourself (see below).

## Found a bug?

Open **About → Report a bug** (or **Settings → Found a bug?**, or `lanterna bug` in a terminal). Write what happened; Lanterna adds the version, the system, the mode and the last errors — never chats, memory, keys or your name, and you can untick that. You see the exact text, then open it as a [GitHub issue](../../issues) or copy it. Sending it by e-mail from your own mail app is coming soon.

## Good to know

Free limits are set by each provider and may change. macOS is not tested yet.

## Development

```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev,gui]"
python -m pytest -q                                  # tests (no network, no keys needed)
python tools/scan_secrets.py --history               # make sure no key, e-mail or personal path is committed
lanterna-gui --browser                               # window UI in your browser (dev server on 127.0.0.1)
```

Windows build: `powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1` (also makes Setup.exe when Inno Setup 6 is installed). Releases: bump `__version__`, add a `CHANGELOG.md` entry, push a tag `vX.Y.Z` — the release workflow tests, builds and publishes the installer.

## Licence

MIT © 2026 mikybuilds
