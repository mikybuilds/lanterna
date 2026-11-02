# Changelog

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
