# Security

## Reporting a vulnerability

Please don't open a public issue for a security problem. Use **Report a vulnerability** on the
[Security tab](https://github.com/mikybuilds/lanterna/security) of this repository: only the maintainer sees the
report. Say which version you use (About in the app, or `lanterna --version`), what you did and what happened.
You will get an answer within a week.

Fixes go to the latest version only. Lanterna updates itself (or tells you the command on Linux), so please update
before reporting.

## Where your secrets are

| What | Where it is kept | Never in |
|---|---|---|
| API keys of the model services | The system vault: Windows Credential Manager, GNOME Keyring or KWallet, macOS Keychain (`keys.py`) | settings, logs, chats, bug reports, backups |
| Sign-ins of Google, GitHub, connectors and MCP servers | The same vault, renewed on their own | settings, logs, the synced copy |
| Mail app passwords | The same vault | files, logs |
| The sync or backup password | Not kept at all. Only a key made from it with scrypt sits in the vault | anywhere |

An environment variable such as `GROQ_API_KEY` is used instead of the stored key when it is set (for servers and
CI). Long tokens are split into several vault entries because Windows allows only 2,560 bytes per entry.

`sync.py` contains the OAuth client ID and "client secret" of the Lanterna desktop app. This is not a leak: for apps
that people download, Google does not treat that value as a secret, because it can't be hidden in the app. It
only lets Lanterna open Google's sign-in page under its own name. Reaching anyone's data still needs that person to
sign in and agree, and Lanterna asks only for its own hidden app folder in Drive.

## What leaves your computer

- **Cloud mode:** your message, the recent part of the chat and your memory list go to the model service you
  chose, under that service's terms. **Local mode (Ollama):** nothing leaves your computer.
- **Before a message goes online**, `sensitive.py` looks for card numbers, IBANs, passwords, PINs and keys in
  what you typed, on your computer, and warns you before sending (unless you turned the warning off).
- **Under each reply**, "What went to the model" lists the kinds of data that reply sent (the chat, memory,
  attachments, the tools that ran) and where. It names files, never their contents.
- **Sync** sends one file to a hidden folder of your own Google Drive. It is encrypted on your computer with
  AES-256-GCM, with a key made from your sync password, so Google can't read it. In the mode without a password,
  the key sits next to the file in the same hidden folder, so the copy is only as safe as your Google account. In
  that mode API keys are not synced.
- **Backups** are encrypted the same way. They contain no API keys and no sign-ins.
- **On its own**, Lanterna makes one request: the update check when it starts (a plain request for the latest
  release, nothing about you). You can turn it off in Settings → Updates. Everything else (weather, search, model
  checks, the morning summary) happens because you asked or turned it on. The README's
  [Privacy](README.md#privacy) section lists each of them.

There is no telemetry and no Lanterna account.

## What the model can and can't do

The model never gets a shell or free access to the computer. It only calls tools, and those are limited by design:

- **Every change is a card.** Writing or moving files, installing or removing programs, changing a setting,
  sending mail, pushing to GitHub, uploading to Drive, calling an MCP tool: the user sees exactly what will happen
  and presses Confirm. Nothing changes before that. Most changes can be undone from "What Lanterna did".
- **Acting without cards** can be turned on for one chat, for up to 2 hours. It covers only changes that stay on
  this computer and can be undone, plus installing from the official catalog. Mail, GitHub, Google Drive, removing
  programs and outside tools still ask every time.
- **Folders:** only your standard folders (Downloads, Desktop, Documents, Pictures, Videos, Music) and the one
  working folder you picked. Paths are resolved and must stay inside them, with no `..` and no links out. Hidden
  files are skipped. Files Windows would run (`.exe`, `.bat`, `.ps1`, `.lnk`…) are never written. Nothing is
  deleted for good: files go to the Recycle Bin and a replaced file is backed up first.
- **Programs** come only from winget's official catalog on Windows, and from Flatpak or the distribution's
  package manager on Linux. A password, when the system needs one, is asked by the system itself, never by Lanterna.
- **Settings** come from a fixed list (theme, power plan, startup programs and a few more).
- **Web pages, files, mail and MCP answers are data.** The model is told to ignore any instructions inside them.
  Pages on this computer or the local network are never opened, so a web page can't make Lanterna reach your router
  or other devices.
- **GitHub** is a GitHub App with one write permission (Contents) on the repositories you choose. Sign-in uses the
  device flow, so there is no password or app secret on your computer. Files that look like secrets (`.env`, keys,
  tokens inside) are never pushed.
- **Google Drive** uses the `drive.file` permission: Lanterna sees only the files it created.
- **MCP servers** are made by other people. They are off until you turn them on after a warning, each one is added
  by hand, and a server that runs as a program runs with your rights. Only add servers you trust.

## How the project protects itself

- `tools/scan_secrets.py --history` runs in CI on every push. It fails if an API key, a private key, an e-mail
  address or a personal path is found in any file or anywhere in the git history.
- Tests never touch the network or real keys, and each test gets its own empty data folder.
- Releases are built by GitHub Actions from a tag. The app downloads an update to a temporary folder and checks it
  against the SHA-256 on the release page before installing it.
- Piper voices and the whisper.cpp engine are downloaded only when you ask, from pinned addresses, and checked by
  SHA-256.
