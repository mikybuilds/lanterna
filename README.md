<p align="center"><img src="assets/logo.svg" width="120" alt="Lanterna logo"></p>

<h1 align="center">Lanterna</h1>
<p align="center">A friendly AI assistant that runs on <b>free cloud models</b> — or on <b>your own local models</b> if your PC is strong enough.<br>
<sub>by mikybuilds · MIT licence</sub></p>

> **Status: early development (v0.0.4).** The Windows app and the full-screen terminal app work, with automatic free-model discovery and fallback. The Windows installer, memory/tools and local models are coming — see the roadmap below.

<p align="center"><img src="docs/screen-chat.jpg" width="720" alt="Lanterna chat window"></p>

## Why

Running a good model locally needs a strong graphics card. Lanterna lets anyone chat with a capable assistant using free tiers from cloud providers, and switches to local models (Ollama) on machines that can handle them.

- **Free.** Uses free API tiers. Lanterna never calls a paid model.
- **Private keys.** Your API keys are stored in your system's secure vault (Windows Credential Manager / GNOME Keyring), never in plain files or logs.
- **No telemetry.** Lanterna sends nothing to its author.
- **Human tone.** Warm, short when you're short, honest when it isn't sure.
- **English, Українська, Italiano.**

## Try it (developer preview)

```bash
pipx install git+https://github.com/mikybuilds/lanterna
lanterna
```

On first launch you pick a language, your name and your first free service:

| | Groq — *Fastest* | Google Gemini — *Smartest & most generous* |
|---|---|---|
| Speed | replies almost instantly | fast |
| Free limits | smaller daily limit | big free limits |
| Extras | strong open models (GPT-OSS, Qwen) | understands photos and documents, long memory |
| Get a key | [console.groq.com/keys](https://console.groq.com/keys) | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

In a terminal `lanterna` opens a full-screen app (chats on the left, Ctrl+N new chat, Ctrl+S settings, Ctrl+O models). `lanterna chat` gives a simple line-by-line chat.

<p align="center"><img src="docs/screen-terminal.png" width="720" alt="Lanterna in a terminal"></p>

Window app: `pip install "lanterna[gui]"` then `lanterna-gui`, or build `Lanterna.exe` with `packaging/build_windows.ps1`.

Other commands: `lanterna models` (free models available right now), `lanterna key set <provider>`, `lanterna key list`, `lanterna setup`, `lanterna about`.

## Roadmap

- [x] Core, Groq chat in the terminal, secure key storage, personality
- [x] All free services (Groq, Gemini, OpenRouter, Cerebras, Mistral, GitHub Models) and automatic discovery of models that are free right now, with fallback when a limit is reached
- [x] Windows app (window with chats, settings, first-run setup)
- [ ] Windows installer (Setup.exe)
- [x] Full-screen terminal app for Ubuntu / GNOME (mouse + keyboard, same chats as the window app)
- [ ] Memory, reminders, web search, files & photos, weather
- [ ] Local models via Ollama with hardware-based recommendations
- [ ] Voice

## Good to know

Free limits are set by each provider and may change. In cloud mode your messages are processed by the provider you choose; for full privacy use local mode.

## Licence

MIT © 2026 mikybuilds
