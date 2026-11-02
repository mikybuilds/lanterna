"""Interface strings. Key = English text; add a row for every new string."""
from __future__ import annotations

LANGS = {"en": "English", "uk": "Українська", "it": "Italiano"}

_T: dict[str, dict[str, str]] = {
    "Made by {author}": {"uk": "Створив {author}", "it": "Creato da {author}"},
    "What should I call you?": {"uk": "Як до тебе звертатися?", "it": "Come ti chiami?"},
    "Pick your first free service:": {"uk": "Вибери перший безкоштовний сервіс:", "it": "Scegli il primo servizio gratuito:"},
    "Fastest": {"uk": "Найшвидший", "it": "Il più veloce"},
    "Smartest & most generous": {"uk": "Найрозумніший і найщедріший", "it": "Il più intelligente e generoso"},
    "Replies almost instantly · strong open models (GPT-OSS, Qwen) · smaller daily limit":
        {"uk": "Відповідає майже миттєво · сильні відкриті моделі (GPT-OSS, Qwen) · менший денний ліміт",
         "it": "Risponde quasi all'istante · modelli aperti potenti (GPT-OSS, Qwen) · limite giornaliero più basso"},
    "Big free limits · understands photos and documents · long memory · needs a Google account":
        {"uk": "Великі безкоштовні ліміти · розуміє фото й документи · довга пам'ять · потрібен Google-акаунт",
         "it": "Limiti gratuiti ampi · capisce foto e documenti · memoria lunga · serve un account Google"},
    "You can add the other services later as backups.":
        {"uk": "Інші сервіси можна додати пізніше як запасні.", "it": "Gli altri servizi si possono aggiungere dopo come riserva."},
    "Get a free key here: {url}": {"uk": "Безкоштовний ключ тут: {url}", "it": "Chiave gratuita qui: {url}"},
    "Create an account, press “Create API key”, copy it and paste it below. It is stored in your system's secure vault.":
        {"uk": "Створи акаунт, натисни «Create API key», скопіюй і встав нижче. Ключ збережеться в захищеному сховищі системи.",
         "it": "Crea un account, premi «Create API key», copiala e incollala qui sotto. Viene salvata nel portachiavi sicuro del sistema."},
    "Paste key (hidden)": {"uk": "Встав ключ (не видно)", "it": "Incolla la chiave (nascosta)"},
    "Checking the key…": {"uk": "Перевіряю ключ…", "it": "Controllo la chiave…"},
    "Key works ✓": {"uk": "Ключ працює ✓", "it": "La chiave funziona ✓"},
    "The key didn't work: {err}": {"uk": "Ключ не спрацював: {err}", "it": "La chiave non funziona: {err}"},
    "No key for {p}. Run: lanterna key set {id}": {"uk": "Немає ключа для {p}. Запусти: lanterna key set {id}", "it": "Nessuna chiave per {p}. Esegui: lanterna key set {id}"},
    "Type a message. /exit to quit, /new for a new chat.":
        {"uk": "Пиши повідомлення. /exit — вийти, /new — нова розмова.", "it": "Scrivi un messaggio. /exit per uscire, /new per una nuova chat."},
    "New chat.": {"uk": "Нова розмова.", "it": "Nuova chat."},
    "Limit reached on {p}. Try again in a bit (automatic switching comes in the next version).":
        {"uk": "Ліміт на {p} вичерпано. Спробуй трохи пізніше (автоперемикання — у наступній версії).",
         "it": "Limite raggiunto su {p}. Riprova tra poco (il cambio automatico arriva nella prossima versione)."},
    "Network problem: {err}": {"uk": "Проблема з мережею: {err}", "it": "Problema di rete: {err}"},
    "Error: {err}": {"uk": "Помилка: {err}", "it": "Errore: {err}"},
    "Bye!": {"uk": "До зустрічі!", "it": "Ciao!"},
    "Saved.": {"uk": "Збережено.", "it": "Salvato."},
}


def t(text: str, lang: str = "en", **kw) -> str:
    s = text if lang == "en" else _T.get(text, {}).get(lang, text)
    return s.format(**kw) if kw else s
