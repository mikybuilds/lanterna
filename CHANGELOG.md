# Changelog

## Unreleased

- **Lanterna finds why something doesn't work, and fixes it.** Say what is wrong in your own words ("Stalker goes black in a mission", "the game won't start", "there is no sound", "the printer doesn't print"), and Lanterna looks for the cause itself before it asks you anything, the way a friend at your computer would. It finds the game or program (Steam, Epic, GOG, Xbox or the list of installed programs) and looks through its folder for what is out of place: a folder renamed by a "skip the intro videos" trick, which hides the story videos too and can leave a black screen; mods, and files that hook into the game (ReShade, frame generation…). It reads the game's newest log and crash reports, and what Windows noted: crashes and the file they happened in (the graphics driver, an overlay, the game itself), how old the graphics driver is, overlays running now, Steam's own state of the game, free space. For Windows itself it checks the sound, the internet, the printers and Windows Update. Then it checks the likeliest cause on the web, explains it simply and offers one fix on a card: rename a folder or file back, change one setting in the game's settings file (the old file is kept), move mods aside into a folder next to them, clear a shader cache (into the Recycle Bin), start Steam's check of the game's files, clear the DNS cache, turn off a proxy that was left on, choose the default printer, or remove stuck print jobs. All of them except Steam's check and the print jobs can be undone in Settings → What Lanterna did. The game must be closed: Lanterna checks that when it makes the card and again when you press Confirm. With "Lanterna acts on its own" on in a chat, the fixes that can be undone happen at once. A new chat has a Fixes row: it puts "Doesn't work:" in the box, and you add the name of the game or program. Lanterna never reads browsers, password managers, wallets, mail, messengers or files that may hold passwords or sign-ins, never changes saved games, and takes your name, the computer's name and e-mail addresses out of what goes to the model.
- **On Linux too.** The same help works on Linux (Fedora, Ubuntu and others). Lanterna finds Steam games, the Linux ones and the Windows ones that run through Proton (their saves, settings and logs are in the game's Proton folder, and Lanterna looks there), games in Heroic (Epic and GOG) and Lutris, Flatpak and Snap apps and the programs of the app menu. It reads what the system noted: crashes (systemd-coredump, or apport on Ubuntu), the graphics card hanging or being reset, memory running out (the kernel's own lines, and systemd-oomd closing Steam), the graphics driver and its version (Mesa, NVIDIA's own driver, or the open nouveau driver that runs games very slowly), two graphics cards, and Proton's log when you turn it on for the game (Lanterna says how). It notices a game on an NTFS disk, where Proton games often break, and anti-cheat that allows online play on Linux only when the game's makers want it. For the system itself it checks the sound (PipeWire or PulseAudio: the output the sound goes to, a muted or almost silent output or microphone, the sound service), the internet (NetworkManager: Wi-Fi off or weak, DNS, a VPN, a proxy left on), the printers (CUPS: paused, offline, stuck jobs, a PDF printer as the default) and updates (dnf, apt or rpm-ostree: a failed update and why, one waiting for a restart, a full /boot). The fixes on Linux: the same ones for a game's own files, clearing a shader cache (into the Trash) and Steam's check of the files, and for the system: send the sound to another output, turn on a muted or very quiet output or microphone, restart the sound service, turn off the desktop's proxy (GNOME or KDE), choose the default printer, remove your own stuck print jobs. They change only your own settings and never need the computer's password; all of them except the restart, the print jobs and Steam's check can be undone. For what needs the password (a driver, an update, the printing service), Lanterna gives you the exact command to run.
- **Videos from a link.** Send a link on its own (YouTube, TikTok, Instagram, X, Facebook, Vimeo, Twitch, Reddit, SoundCloud and over a thousand other sites, or a page with a video in it), and Lanterna saves the video into Downloads, up to 1080p as MP4, which plays everywhere. No model is needed for it. The line under the reply shows how far it is ("Downloading «…»: 45%"), and the reply names the video with its quality and size; under it is a link that opens the video, and Show in folder. Ask in words for more: "only the sound as MP3", or "download the whole playlist" (a card lists its videos first, at most 50, and they go into a folder of their own). The first time a card installs the free program yt-dlp that does the downloading: on Windows with winget, which brings FFmpeg and Deno, the two helpers it needs; on Linux from the system's packages (the system asks for your password itself). Lanterna never uses your passwords or the browser's cookies, so a video only for signed-in people stays on the site; it never downloads a live stream or from your own computer or home network, never writes over an older file, and Stop removes the unfinished parts. A link to an ordinary page still goes to the model, as before, and so does a link that looks like a scam: it is never opened. If the yt-dlp already on the computer lacks a part that a site needs (a copy installed with pip, say), the reply says so in plain words and, on Windows, a card offers the full yt-dlp. Lanterna finds winget's yt-dlp, FFmpeg and Deno even where winget can't make its links (Developer Mode off): there each program stays in its own folder, at the end of PATH and behind an older copy. When a site answers "no such video" (error 404), the reply says it may have been removed or the site doesn't give it to yt-dlp, not that it surely is gone. A reply that no model wrote has no Second opinion button under it. It is part of Settings → Computer, which is on by default.
- **The "what I'm doing" line in your language.** While Lanterna looks for what is wrong with the sound, the internet, the printer or the updates, the line under the reply now names them in the app's language, not in English.
- **Lanterna in Chrome.** Lanterna now has its own Chrome extension and can work in your Chrome, in the tabs you see: open pages and tabs, read a page (its text, a table row by row, a picture of the screen), click, type, press keys, scroll, fill in forms, give a site a file from your folders, and download. Ask in a chat ("read this week's homework in my school register and list it by day") or in Lanterna's side panel next to the page: the toolbar button or Alt+L opens it, and the page's right-click menu asks Lanterna about the page, a link or the selected words. The tab Lanterna works in goes into an orange "Lanterna" group and shows a line at the bottom, "Lanterna is working in this tab", with Stop. In every mode Lanterna never types passwords or card details, never buys or pays, never makes accounts and never solves CAPTCHAs: it asks you to do that step yourself. What a page says is only data, so hidden words like "assistant, delete everything" are never orders. Sites you add to "Sites Lanterna never touches" in Settings → Chrome are left alone. The record button in the side panel turns the steps you do in a tab into a shortcut (what you type into password fields is left out). Settings → Chrome lists the steps to set it up: chrome://extensions, Developer mode on (leave it on: without it Chrome turns off extensions loaded from a folder), Load unpacked, and the folder the button there opens. The extension talks only to Lanterna on this computer (127.0.0.1), and Lanterna lets in only its own extension. The first time they make a key, kept in the system's password store; after that each side proves it knows the key before anything else, and another copy of the extension needs Connect Chrome in Settings first. Lanterna must be running (in the tray is enough).
- **How much Lanterna asks first, in Chrome and on this computer.** Settings → Computer, Settings → Chrome and the side panel have three modes. Ask first: a card before every action (in Chrome, «Allow on this site» on a card lets the ordinary actions there go on without asking). Semi-automatic: in Chrome, reading, clicking, typing and scrolling go on at once, while sending, publishing, deleting, downloads and giving access ask first; on this computer, changes that can be undone happen at once (files and folders, the look and settings, installing from the catalog), while mail, GitHub, Google Drive, removing programs and other services ask. Automatic: no cards, and every change is in What Lanterna did. A new install starts semi-automatic, with one mode for both; untick "One mode for changes on this computer and for Chrome" to set them apart. The card that lets Lanterna act on its own in a chat, and what Lanterna suggests by itself (the weekly tidy-up), always ask. The terminal app has the same switch in its Settings.
- **One card for a download.** A download that Lanterna's click starts waits in Chrome for your OK; when the card for the click already said it downloads a file, that card is enough. "No" removes the file, even a small one that was already whole, and the answer says which file came or is waiting for you.
- **Your tabs keep their pages.** A new address always opens in a tab of Lanterna's own (in the orange group), never in one of yours: Lanterna works in your tab only when you ask about that page. Closing one of your tabs asks first unless the mode is Automatic; the tabs Lanterna opened close without a card.
- **Lanterna knows itself.** Ask it about Lanterna (what it can do, where a setting is, how to install or update it, how to add its Chrome extension) and it answers from its own help, made for this version and this computer, instead of searching the web, which knows only older versions. Before, "how do I install your extension?" got the answer that there was no extension. For the extension it gives the steps with the buttons named as in the window, and says whether the extension is connected already.
- **The steps are in your language.** While Lanterna answers, the line under the answer and the Steps list show the model's own notes only when they are in your language. A model that thinks in English (Gemini does, in a Ukrainian or Italian chat too) used to put lines like "Clarifying Extension Loading" there; now that line says «Thinking…» in your language, and the list keeps Lanterna's own steps. The model's note on why it uses a tool follows the same rule, now also in Italian, German, Spanish, French and Polish.
- **The side panel ends where the chat ends.** Scrolling down in Lanterna's side panel in Chrome went past the chat into a dark empty screen with the lantern and an empty button: the note for when Lanterna isn't running was always there, under the chat. And when Lanterna wasn't running, the panel looked empty: that note was below a screen of nothing. Now the panel shows the chat or the note, never both. Lanterna updates its extension in Chrome by itself the next time Chrome connects to it.

## 1.1.10 — A new look, games and programs, the whole disk

**New**
- **A new look for the window.** The window now has the same calm style as the project's site: charcoal with one amber color, thin lines, an exact grid and its own fonts (Onest and JetBrains Mono, free fonts that come with the app). The glows, gradients, blur and springy motion are gone, and the light theme got the same care. Line icons replace the emoji (thinking steps, cards, roles, settings, menus). The lantern is a flat drawing that breathes only while Lanterna thinks, then goes out. A new chat shows the lamp and a short list of what Lanterna can do; a click puts the example in the box. The terminal app only takes the new colors.
- **Pictures where there are numbers.** "Where did my space go?" draws how full the disk is and what takes the space, above the answer; the picture stays with the chat on this computer only and never goes to the model or to sync. A sort card shows each folder as a row with a bar and a few names, and a click opens the whole list, with an icon for each kind of file. Settings shows each model's limit as a bar (red when little is left) and how full the disk is, beside the graphics card and the memory. A plan shows its steps as a bar. The limit under the message box stands right after the Folder and Role buttons and says when it fills up again only when little is left. Sizes are written the way the window's language writes them (68,9 ГБ).
- **Games, little programs and game mods.** Ask "make me a snake game", "a little program that counts my expenses" or "a Minecraft datapack that…", and Lanterna writes the files into its own folder, Documents/Lanterna projects/<project>, without a card for each file (nothing outside that folder is touched or replaced). A browser game is one page that works offline; a program is Python with nothing to install; for a mod it first looks up the current format of that game and version. Then it looks the files over for mistakes without running them (Python, JSON, HTML and the script inside it, brackets and quotes in JavaScript, CSS, Java, C#, Lua…, files a page uses that are missing, a file cut off in the middle) and fixes what it finds. Lanterna never starts a program it made, and never writes files that could run one by a double click (.exe, .bat, .js, .ps1…). It opens the folder or a web page only when you ask.
- **A task list, like Claude's.** For a big job Lanterna first asks a few questions with buttons when your message leaves out what changes the result (or when you ask it to: "ask me first", "уточни"), then makes a plan: the steps stand over the message box, ✓ done, the one it is doing now lit up, the next ones below, with "2 of 5 done", a button for the project folder and × to hide it. In the terminal too. Working through a plan it can use up to 12 tools in one answer (4 otherwise); if the job doesn't fit, it says what is left and "go on" carries on from that step. Jobs on this computer in several steps (sorting into your own folders, moving groups of files, programs) get the task list too, one step per card.
- **What fills the disk, all of it.** "Where did my space go?" now gets the whole disk, not only your own folders: Lanterna counts every folder on it and names the biggest things by what they are, with what each one is and how it is freed: a Steam game by its name, Visual Studio and its download cache, the graphics driver's shader cache, Chrome's cache, Telegram's files, the temporary files, Windows itself, your own folders. On a full disk the first count after the computer starts can take a minute or two (later ones take seconds), and the line that shows what Lanterna is doing shows how much it has counted so far. If the count isn't finished after two minutes, Lanterna says what it has so far, and the next question gets the whole disk. Steam's games are listed by name and size, also the ones on your other disks, and one can be removed on a card: Steam's own Uninstall opens, and Steam asks once more. You also see the biggest files (the names of files in your own folders only with Help free up disk space on), kinds of files (videos, archives, disk images…), how full your other disks are, and what Lanterna couldn't count, such as old restore points (it can open System Protection, where they are deleted). Ask about one folder or another disk and it looks inside. The biggest programs, the downloaded Ollama models (one can be removed on a card, and Settings → Local models downloads it again) and Windows' own files (the hibernation and page files, Windows.old, update downloads) are there too, and Lanterna can open Windows' Disk Cleanup. Lanterna only looks: nothing is moved or deleted without a card. Links, junctions and OneDrive files kept only online are left out of the count, because they take no space on the disk. When Help free up disk space is off, Lanterna offers to turn it on, on a card.
- **New free service: Cloudflare Workers AI.** 10,000 free "neurons" a day, a few dozen answers from models like GPT-OSS 120B, Gemma 4 and Qwen3. Add it in Settings → Models with an API token made from Cloudflare's "Workers AI" template: Lanterna finds your Account ID itself (with several accounts, paste the ID after the token). Lanterna counts the neurons on this computer and stops at 9,000, so Cloudflare never costs anything, even on a paid plan, and models that would use the free neurons up in a few answers are left out.
- **An answer can't pretend it did something.** When a model writes that it moved files, installed a program or made a card ("I moved everything", "✅ Done", "press Confirm") but no tool did it, Lanterna takes those words back and asks the model once more: it makes the real card for you to confirm, or says plainly that it can't. If it still claims it, the ⚠️ line under the answer says so. Lanterna's own lines about cards (✅ done, ✖ cancelled, ⚠️ failed) now reach the model as Lanterna's notes, so it no longer copies them for changes that never happened, and "I moved them" counts as true only after a card that really moved them.
- **A group of files on one card.** "All installers to Programs", "every .jar to Mods", "files older than a month", "the ones with minecraft in the name" or a pattern like *.exe: one card lists every file that fits and says which rule picked them, and it makes the folder itself (no separate folder card first). Files still downloading and files already on another card that waits are left out, so several groups never take the same file twice. A rule takes files only; a folder moves when you name it.
- **Visual Studio with C++, one card per program, the whole error.** Visual Studio is now installed with the parts you need, and the card lists them: C++ (Desktop development with C++) brings the compiler; without it Visual Studio is only an editor. A Visual Studio that is already installed without C++ gets a card that adds it with Visual Studio's own installer (close Visual Studio first). While a card for a program waits or runs, no second card for the same program (or for another Visual Studio) is made. After an install Lanterna looks whether the program is really there, and for Visual Studio whether the C++ compiler is, and the card says so. A failed install shows the whole error, its code explained in plain words (another install is running, it was cancelled, no internet, a restart finishes it…), without winget's licence lines.
- **Why g++, python or node "isn't found".** For "g++ doesn't work", "python is not recognized" or "cannot find -lmingw32: Illegal byte sequence", Lanterna first looks, changing nothing (it only runs each tool it finds with --version): where g++, gcc, gdb, clang, python, node, java, dotnet, git and VS Code are, their versions, which one a terminal opened now runs (Path as Windows has it now), what is installed but not in Path, and whether Visual Studio has its C++ compiler. It knows what breaks GCC (MinGW) on Windows: a folder with non-English letters in its path (winget puts WinLibs into your user folder, so a Cyrillic user name is enough), the same in TEMP or in the code's folder, a file instead of a folder in Path, and the Microsoft Store's python shortcut. For each one it says the fix, for example which folder to put at the top of Path, or to copy MinGW to C:\mingw64.
- **A weaker model in the middle of changes.** When the model making changes on the computer reaches its limit for the minute and only clearly weaker models are free, Lanterna waits for it once, up to 30 seconds, and the line that shows what it is doing says so. When a weaker model still takes over, one line above its answer says so (once per chat), so you look at its cards carefully before you confirm.
- **Clearer thinking, for every model.** Each answer now comes with short rules on how to think: work out what you really want, reason a hard question through step by step, check numbers and facts, read the answer once more before sending it, and say plainly when it isn't sure or ask about a missing detail instead of guessing.

**Fixed**
- **Counts that read right.** The word after a number now takes the form the number needs, in every language of the app: "1 file, 2 files", «1 файл, 3 файли, 5 файлів», "1 plik, 3 pliki, 5 plików". A card for one file no longer says "Sort 1 files" or "Move 1 items", and the same goes for what an undo brought back, a restored backup, the length of a long message, Check Lanterna and the requests counted under the message box. Big numbers are written the way the window's language writes them (1 059).
- **Closing Settings keeps your chat open.** Opening Settings and closing them again (also with a click on the limit under the message box) brought back the first chat of the list. Now the chat you were in stays open, and so does a new empty one.
- **Sorting no longer gets stuck on the folder's name.** A model that called Downloads "Завантаження", wrote "Downloads/видалення/…" or the whole path to Downloads, or used a pattern with a folder (Mods/*.jar, that one was a Lanterna bug) got an error, and no card came. Now they all mean the same folder, and no second Downloads is made inside Downloads. When a move still fails, the answer can't say "I'll sort them now" or "let's confirm": the model gets the error once, to fix its call or to say plainly that it didn't work. Words about work after the answer ("I'll start sorting right away"), a tool it says it uses but didn't call, and lines it writes in Lanterna's own [Lanterna: …] form count as such words too, and those lines are taken out of the answer.
- **"Let me look" is no promise when it did look.** An answer that starts with "let me take a look" above what Lanterna's tools found is no longer taken back, so the model doesn't write it all again with an apology. Words about what you did yourself ("you already cleaned out Downloads") no longer count as the model claiming it did them. And when an answer is written again, the new one no longer apologizes for the old one.
- **Links in answers look and act like links.** They were only orange text: the pointer stayed a text cursor and nothing happened on hover (a click did open them). Now they are underlined, the pointer turns into a hand, the line lights up under it and the whole address shows on hover; Tab and Enter open them too. A full stop or comma right after an address is no longer part of the link, and an address in quotes («https://…») is a link too.
- **Leaving the Google step at once no longer closes the terminal app.** When the Google sign-in step (or the sync box in Settings) was closed before it had fully appeared, on a slow computer or with a quick key, the terminal app stopped with an error. Now it just goes on.

## 1.1.9 — Formulas, tables and quotes in answers

**New**
- **Formulas, drawn.** When an answer has a formula (the LaTeX models write: `$…$`, `$$…$$`, `\(…\)`, `\[…\]`), the window now draws it as in a textbook: fractions, roots, powers and indices, Greek letters, sums and integrals, matrices, systems of equations, and chemistry (`\ce{H2SO4}`). A formula on its own line sits in the middle of the answer, and a long one scrolls sideways instead of leaving it. It works offline: KaTeX (MIT license) comes with Lanterna, its fonts too. Money stays money (`$5 and $20` is not a formula), code is never touched, and a formula KaTeX can't read stays as the model wrote it. Copying a drawn formula gives its LaTeX, and screen readers get it as MathML.
- **Tables, lines and quotes in answers.** A table in an answer is a real table in the window (a wide one scrolls sideways), `---` is a line across, a line that starts with `>` is a quote, and `~~text~~` is crossed out. They showed as signs before.
- **Formulas as text where they can't be drawn.** In the terminal app a formula becomes text you can read (I = Q/Δt, x = (-b ± √(b² - 4ac))/(2a), SO₄²⁻), and one on its own line keeps its own line. Reading aloud reads that text, not dollar signs and backslashes. A chat's name and the suggested next messages show no LaTeX either.

## 1.1.8 — Stop, a light theme, real sources, a scam check

**New**
- **Stop.** While Lanterna answers, the send button turns into Stop (Esc does the same, in the terminal too). The answer ends where it is and the words written so far stay in the chat; stopped before a word, no empty answer is kept.
- **A light theme.** Settings → General → Theme: Dark (as before), Light, or Like the system (it follows Windows or GNOME, also when they switch while Lanterna is open). Warm paper with the same lantern; amber is darker where it is text, so all text reads at least 4.5:1, as in the dark theme. It is kept on this computer and the window opens in it without a dark flash. In the terminal: Ctrl+P → Light theme.
- **Sources under an answer.** When Lanterna looked something up on the internet, the answer ends with «Sources:», the pages it really opened (a short name, the whole address shows before you click), and, folded, the search results the model saw. Only what the tools opened counts: a link the model wrote itself (it can make one up) is never a source, and a link that looks like a scam is never shown. They are kept with the answer on this computer, shown when you open the chat again, in the terminal and in a chat saved as a Markdown file.
- **Is this a scam?** Paste a message, a letter or a link and ask (or press «🛡 Is this a scam?» in an empty chat): Lanterna looks for the usual signs without opening the link: a bank's, a delivery's or a shop's name on someone else's site (privatbank-ua.secure-login.top), look-alike letters, the "@" trick, short links, cheap endings, requests for card data or SMS codes, a hurry, a prize or a delivery fee, "it's me from a new number". Then it explains them simply and says how to check for sure. A link that looks fake is not opened even if the model asks for it, since opening one can tell the senders your number is alive.
- **Private data is asked about before it goes online.** A card number, IBAN, password, PIN or CVV, or an API key or token in your message: before it goes to an online model, Lanterna says what it found and where the message would go, and can put •••• in its place (Hide and send), so the model still helps. Cancel keeps the message in the box to change it. Card numbers and IBANs must pass their check digits, so ordinary long numbers don't count. The check runs on this computer, nothing is asked in Local mode, and Settings → General can turn it off. In the terminal too.
- **Reminders also when Lanterna is closed.** At a reminder's time the system starts Lanterna for a moment to show it as a notification: on Windows a task of your own in Task Scheduler (no administrator rights), on Linux a systemd user timer. If the computer was off or asleep then, it comes right after you sign in, with the time it was due. Nothing runs in between, a reminder never comes twice (also with the window and the terminal open at once), and with no reminders left the task or timer goes away. Settings → Memory and reminders → "Remind me when Lanterna is closed too" (on) turns it off, on this computer; uninstalling Lanterna or `lanterna desktop --remove` takes it away.
- **Rename and pin chats.** Every chat in the list has a "⋯" button (or right-click the chat): Pin to top, Rename, Delete. Pinned chats stay at the top of the list in their own group, and a pin goes to your other computers with sync. The menu works from the keyboard too. In the terminal: Ctrl+P → Rename chat / Pin chat.
- **Real Word and LibreOffice documents.** Ask for a .docx or .odt file (in the working folder, on the desktop, in Documents…) and Lanterna makes a real document: headings, lists, bold, italic, quotes and code become real formatting, a table's rows become lines with tabs. Word, LibreOffice and Google Docs open it, and Word doesn't say "Compatibility Mode". The card waiting for Confirm says it becomes a document. An existing document is still never changed: Lanterna offers a new name.
- **CSV tables Excel opens right.** A new .csv file starts with the mark Excel needs to show Cyrillic and other letters (rewriting one keeps what it had; adding to one never puts the mark in the middle and no longer leaves an empty row). On Windows Lanterna also tells the model which separators Excel on this computer expects (in Ukraine ";" between columns and a decimal comma), so the table opens in columns, not all in the first one. Reading a Word file keeps "&", "<", tabs and line breaks (they came as "&amp;" or were lost); a LibreOffice file keeps tabs and a code line's indent.
- **Bigger text, clearer pale text.** Ctrl+= and Ctrl+− make the chat text bigger or smaller and Ctrl+0 brings it back (any keyboard layout), or choose it in Settings → General → Text size, from 90 to 150 %. It is kept on this computer, and everything in the chat grows with it, the cards waiting for Confirm too. Pale text (dates, hints, labels) is easier to read now: at least 4.5:1 against every background, it was about 3:1.
- **For screen readers and the keyboard.** NVDA, Narrator and Orca now hear "Thinking…", the answer, a change waiting for Confirm and errors, and who wrote each message; every button that is only a picture has a name. Ctrl+N starts a new chat and Ctrl+K goes to the chat search (with any keyboard layout); Esc closes the chat list in a narrow window.
- **Lanterna's own window on Linux.** `lanterna desktop` now puts the window in the app menu where it can open (pywebview with the system's GTK WebKit, or Qt's WebEngine), with Lanterna's name and icon in the dock and Alt+Tab. Where it can't yet, the menu opens the terminal app as before and the command shows what gives it the window on your system: two pipx commands, plus the system's packages only where they are missing (Fedora Workstation already has them; otherwise `sudo dnf install python3-gobject webkit2gtk4.1`, and the README has them for Ubuntu, Debian and Arch too). The window's frame is dark or light like Lanterna's theme ("system" follows GNOME's dark style), and Update now keeps the window working. Started without those parts, the window says so in a notification instead of not opening. `lanterna desktop --terminal` keeps the terminal app in the menu.

**Fixed**
- **Your documents stay whole.** Lanterna no longer puts text into an existing Word, Excel, PDF or picture file (it would break it), and makes no Excel, PDF or picture file of text (it wouldn't open); it offers what it can make instead. Adding to the end of a file now keeps a copy of the old one, with Undo, as rewriting it does. Two copies made in the same second no longer overwrite each other.

## 1.1.7 — A lantern that thinks with you, a window that moves

**New**
- **The lantern from the logo thinks with you.** Answers have no picture next to them any more: while the model works, only a small lantern stands before "Thinking…". It is lit with a flash, lights up and dims, sways a little as if someone carried it and flares at each new step; the line shows each step as it comes (and "Writing the answer…" while it writes), with a soft light running over the words. When the answer is ready, the flame sinks into the wick, a wisp of smoke goes up and the line becomes the list of steps.
- **The big lantern** on the first screens, the empty chat and About flickers like a real flame, with a few sparks rising from it.
- **A window that moves, gently:** messages rise in, yours grows out of the message box, the answer is written with an amber caret. The message box breathes and the top of the window lights up a little while the model works; the send button flies off when you send.
- **Dialogs and menus** open and close smoothly; **notices** slide in with a thin line that shows how long they stay (it waits while the pointer is over them); **cards** rise in and turn green when done, red when something failed.
- **Buttons** press down and lift, cards and connectors light up under the pointer, the settings gear turns, and rings go out from the mic while it records.
- **Copy an answer** with the button next to Read aloud, and **copy code** with the button that shows on a code block.
- **A round "down" button** over the message box when you scroll up: one click takes you back to the latest message.
- **Dragging files over the window** says to let go of them to attach them.
- **It stays light:** the movements are small and short, the big lantern stands still while the window is in the background, and everything calms down when the system asks for less motion (Windows: Settings → Accessibility → Visual effects → Animation effects; GNOME: Reduce animation).

**Fixed**
- **A card coming in could push the chat past the end** while you were reading the answer: the chat now stays at the end.
- **The folder under the message box could show crossed out** when Lanterna didn't get the chat's folder.
- **The buttons under a fresh answer** (Read aloud, Retry, Second opinion) were in two rows and in one row after opening the chat again; now always in one.

## 1.1.6 — About 120 connectors, honest replies, the right program installed

**New**
- **Many more connectors:** about 120 ready-made ones now (was about 75), each checked: Basecamp, Craft, Shortcut, Jotform, Fathom, Otter.ai, Krisp, Whimsical, Picsart, HeyGen, DigitalOcean, Railway, Heroku, Lovable, Postman, PlanetScale, Sanity, Replicate, DeepWiki, Kaggle, Interactive Brokers, Paddle, Alpha Vantage, CoinGecko, Scite, Consensus, Mapbox, beehiiv, Bitly, Porkbun and more. Xero, Zendesk, ElevenLabs and a few others are listed with why they can't be connected.
- **Browse shows every category at once**, like Claude's directory: the popular ones first, then each category with its first few and **Show all**.

**Fixed**
- **"Installing…, almost done" while nothing happened.** When a model couldn't use tools, Lanterna answered with it anyway, and they only described work they never did. Now a model that can use tools answers when one is free, every model is told nothing happens between replies, and a reply that says it is doing something while nothing ran gets a warning under it.
- **Terminal app:** closing Connectors while a search was still running could crash it.
- **Connectors window:** the Yours / Browse switch and “Add your own” were squeezed into small squares; the check mark of a long name stays right after it.
- **Logos in Connectors:** each service shows its own logo (from Simple Icons) instead of a letter, where one exists; mail has an envelope.
- **Installing programs on Linux found the wrong program or failed.** The search looked only in Flatpak, whose loose search offered unrelated apps (asking for htop found "Beat And Match To Pass"), and every install went to `--user flathub`, which Fedora doesn't have, so it failed. Now the search also looks in the system's packages (dnf, apt), keeps only programs that have the words you asked for (whole words: "htop" is in pcp-htop, not in "beatmatchtopass") and says where each one comes from. Two words like "gnome tweaks" find gnome-tweaks. A Flatpak installs from the place that has it (on Fedora that's for the whole system, so it asks for your password). A program that is already installed isn't installed again: its Undo would have removed your own copy. That also holds when Fedora and Flathub name the same program with different capital letters (VLC is `org.videolan.vlc` in one, `org.videolan.VLC` in the other).
- **Program search on Windows** also listed programs that only have the letters inside a word: asking for htop listed seven Splashtop programs. Like on Linux, it now keeps only programs whose name, id or winget tag has the words, closest first. Two words like "libre office" or "team viewer" find LibreOffice and TeamViewer.
- **The warning under "installing…, almost done" didn't show when the model had only searched first.** A search doesn't install anything either: a reply that says it is installing or will let you know later, after only looking things up, now gets the warning too.
- **The lines under a reply** said `app_search` or `pc_info`, with a note in English ("to install htop"). They now say what was looked for, in your language ("Looking for the program: htop").
- **"Second opinion" over the wrong message:** when a chat was opened again, the notes after a confirmed card got the "Second opinion" title.
- **A card to switch to the dark theme when it was already dark.** Lanterna now says it already is.
- **Undo had the same name as Cancel** (Ukrainian in the terminal app, Italian and French everywhere). It is "Повернути як було" (Ripristina, Rétablir) now. "3 моделей" is now "моделей: 3".
- **Connectors:** logos that are only the name written out (Cal.com, Egnyte, Wix, Kaggle, Zapier) showed as a dash or tiny letters; those show their first letter now. "Added" is a word, so it isn't mixed up with the tick that means "made by the service itself", and that tick no longer lands on a line of its own after a long name. The window keeps its size when you switch tabs and categories, and **Show all** has a way back.

## 1.1.5 — Open things, change the look, do it on its own when you ask

**New**
- **Open things:** "open Google", "start Telegram", "open my plan.pdf" — programs from the system menu, websites in your browser and files from your folders open right away (program files never).
- **Change the look:** wallpaper, accent color, icons, pointer, fonts, text size, night light, do not disturb, clock, window buttons and volume on GNOME; wallpaper, transparency, taskbar and Explorer options on Windows. Several at once on one card, with Undo.
- **Do it on its own, when you ask:** after you agree on a plan, Lanterna can ask to act on its own in that chat for a while. Reversible changes on the computer then happen without cards (with Undo in What Lanterna did); removing programs, mail and outside services still ask. **Stop** is over the message box.

**Fixed**
- **"Make a file on my desktop" went to Google Drive** and the answer said it was on the desktop. Lanterna can now create a text file in your own folders (after Confirm), and uses Google Drive only when you ask for it.

## 1.1.4 — Connectors, sync without a password, an easier terminal app

**New**
- **Connectors** (sidebar), with two tabs like Claude's directory. **Browse**: about 75 ready-made connectors from the services themselves (Notion, Linear, Jira and Confluence, Asana, Canva, Miro, Dropbox, Stripe, Supabase, Vercel, Zapier…), by category, with search. **Yours**: what you connected, with sign-in, on/off and Remove.
- **Sign in through the browser**: press + and the service's own sign-in page opens; the sign-in is kept in the system's secure vault and renewed on its own.
- **Search the public MCP Registry** from Browse, shown apart from the checked ones, with who made each server.
- **Mail**: Gmail, ukr.net, iCloud, Yahoo, Zoho or any IMAP mail through an app password. Lanterna can list, read (without marking as read), sort into folders or labels, save drafts and send; every change waits for Confirm.
- **When a service can't be connected** (Gmail's own connector, Slack, Figma…), Connectors says why and offers another way, and Lanterna can look for a connector or a workaround itself when you ask it to work with a service.
- **Sync without a password**: just your Google account; other devices only need to sign in. The copy is then only as safe as that account, so API keys stay on each device.
- **An easier terminal app (Linux):** **Ctrl+P** (or F1, or ☰ in the sidebar) opens a menu with every command and its key, in your language: type a few letters to find one. The bottom line shows only five keys. Connectors, Settings and All commands are buttons under the chats. Settings is in tabs like the window and opens where you left it. **Connectors** with Yours and Browse, mail included, now work in the terminal too. An empty chat says how to send, attach and find commands.
- **Forgot your sync password? Start over** (also `lanterna sync reset`): the copy in Google Drive is made again from your devices; no chat is lost.

**Fixed**
- **Terminal keys that Linux terminals take for themselves:** "What Lanterna did" is now F9 (Ctrl+H is Backspace in many terminals; it still works where the terminal sends it). Enter in the mail form goes to the next field instead of trying to connect.
- **Sync after the copy was deleted:** a device that still had the old password could put the old copy back. Now it waits for the new password instead.
- **Memory read oddly:** facts came out as “They like teen movies” and showed asterisks (*Fear*). New facts are written like notes (“Likes teen movies.”), and Markdown marks no longer show in Settings → Memory, also on facts saved before (the saved text itself isn't changed).

## 1.1.3 — More free services, Cerebras gone, lists that keep counting

**New**
- **Three more free services:** NVIDIA (strong open models such as Kimi, DeepSeek, Nemotron), Z.ai (only its free GLM Flash models, so nothing is ever charged) and Cohere (1,000 free requests a month). Add their keys in Settings → Models.
- **What to know before signing up:** each service in Settings → Models now says what it asks for (a phone number, personal use only) and whether it may use what you send to train its models.
- **Lists in your messages:** in the message box, Shift+Enter on a line like “1. …” starts “2. ” by itself (“- …” gives the next “- ”); Shift+Enter on an empty item ends the list. Sent, such lines show as a real list, like in Claude or ChatGPT; everything else in your message stays exactly as you typed it.

**Fixed**
- **Cerebras is gone:** its free plan ended in July 2026 (now a card trial, then pay per use). Lanterna never spends your money, so it no longer uses Cerebras; a saved Cerebras choice falls back to your other services.
- **Numbered lists showed 1, 1, 1:** when an answer had text between the items (“1. Film … Vibe: … 2. Film …”), every item started a new list from 1. The numbers now continue, lines under an item stay with it, and when a model writes “1.” before every item, Lanterna counts on. The terminal app counts on too.

## 1.1.2 — Update now works when GitHub's download link doesn't

**Fixed**
- **Update now works when GitHub's download link doesn't:** on 8 November 2026 GitHub's usual release download link answered “HTTP 504” for every release, so Update now stopped with “download failed”. Lanterna now takes the same file through GitHub's API in that case, and it is still checked against the release's SHA-256 before it runs.
- **What's new** in the update notice shows plain text, without `**` marks.

## 1.1.1 — GitHub Models is gone

**Fixed**
- **GitHub Models is gone:** GitHub shut the service down on 30 July 2026, and its address now answers a plain "OK" to everything, so checking a key showed “JSONDecodeError”. Lanterna no longer offers it; an old setting, saved model list or synced key that names it is ignored. If a service ever answers like that again, the key check says it answered oddly and may have closed, and the key isn't saved.

## 1.1.0 — read aloud, second opinion, private chat, backups and more

**New**
- **Ready-made MCP servers:** Settings → Computer and tools → MCP servers now lists four checked servers you add with one button: Files in a folder, Git repository (both limited to the folder you pick), Web browser (a fresh profile each time, none of your sign-ins) and Step-by-step thinking. Each has its version fixed, so the code that runs can't change until a Lanterna update moves it (then an “Update to …” button appears). They need Node.js or uv; the card says so and links to it. A server you add by hand with `npx -y package` and no version gets a warning: each start may run newer code nobody checked.
- **`lanterna ask` for scripts and pipes:** `lanterna ask "why is the sky blue?"` prints just the answer, so it can go into a file or another program. Text piped in goes with the question: `git diff | lanterna ask "write a commit message"`, `type log.txt | lanterna ask "what went wrong?"` (a long input sends the parts that fit the question; a PDF or picture works too). `-f file` attaches files, `--role tutor|translator|proofreader` gives it a role, `--no-tools` turns off search, weather, rates and math. Memory about you isn't sent, it can't change anything on your PC, and nothing is saved unless you add `--save`.
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
