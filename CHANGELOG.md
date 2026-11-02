# Changelog

## 0.2.1 — Gemini tools fix

**Fixed**
- With Gemini 3, questions that use a tool (weather, search, reminders…) jumped through many models ("switched to …" again and again) and could stop working for the rest of the day. Lanterna now sends back the extra data Gemini needs, so the first model answers.
- A model that hangs is set aside for 15 minutes on its own instead of blocking the whole service.
- Gemma models on Gemini no longer show their hidden reasoning (`<thought>…`) in the reply.

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
