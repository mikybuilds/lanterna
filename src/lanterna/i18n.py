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
    "Network problem: {err}": {"uk": "Проблема з мережею: {err}", "it": "Problema di rete: {err}"},
    "Error: {err}": {"uk": "Помилка: {err}", "it": "Errore: {err}"},
    "Bye!": {"uk": "До зустрічі!", "it": "Ciao!"},
    "Saved.": {"uk": "Збережено.", "it": "Salvato."},
    "Looking for free models…": {"uk": "Шукаю безкоштовні моделі…", "it": "Cerco modelli gratuiti…"},
    "No free models found. Add a key: lanterna key set groq":
        {"uk": "Безкоштовних моделей не знайдено. Додай ключ: lanterna key set groq",
         "it": "Nessun modello gratuito trovato. Aggiungi una chiave: lanterna key set groq"},
    "Service": {"uk": "Сервіс", "it": "Servizio"},
    "Model": {"uk": "Модель", "it": "Modello"},
    "Score": {"uk": "Оцінка", "it": "Punteggio"},
    "Status": {"uk": "Стан", "it": "Stato"},
    "ok": {"uk": "працює", "it": "funziona"},
    "limited": {"uk": "ліміт", "it": "limite"},
    "untested": {"uk": "не перевірено", "it": "non testato"},
    "switched to {m}": {"uk": "перейшов на {m}", "it": "passato a {m}"},
    "All free models are busy or out of limits. Try again in a minute.":
        {"uk": "Усі безкоштовні моделі зайняті або вичерпали ліміт. Спробуй за хвилину.",
         "it": "Tutti i modelli gratuiti sono occupati o al limite. Riprova tra un minuto."},
    # full-screen terminal app
    "Welcome to Lanterna": {"uk": "Вітаю в Lanterna", "it": "Benvenuto in Lanterna"},
    "A friendly assistant on free AI models.": {"uk": "Дружній помічник на безкоштовних моделях ШІ.", "it": "Un assistente amichevole sui modelli IA gratuiti."},
    "Lanterna is free and open source.": {"uk": "Lanterna безкоштовна і з відкритим кодом.", "it": "Lanterna è gratuita e open source."},
    "Your name": {"uk": "Твоє ім'я", "it": "Il tuo nome"},
    "Next": {"uk": "Далі", "it": "Avanti"},
    "Back": {"uk": "Назад", "it": "Indietro"},
    "Choose": {"uk": "Вибрати", "it": "Scegli"},
    "Cancel": {"uk": "Скасувати", "it": "Annulla"},
    "Close": {"uk": "Закрити", "it": "Chiudi"},
    "Save": {"uk": "Зберегти", "it": "Salva"},
    "Key for {p}": {"uk": "Ключ для {p}", "it": "Chiave per {p}"},
    "1. Sign in or create a free account.": {"uk": "1. Увійди або створи безкоштовний акаунт.", "it": "1. Accedi o crea un account gratuito."},
    "2. Create an API key and copy it.": {"uk": "2. Створи API-ключ і скопіюй його.", "it": "2. Crea una chiave API e copiala."},
    "3. Paste it here.": {"uk": "3. Встав його сюди.", "it": "3. Incollala qui."},
    "Paste the key here": {"uk": "Встав ключ сюди", "it": "Incolla qui la chiave"},
    "Paste a key first.": {"uk": "Спершу встав ключ.", "it": "Prima incolla una chiave."},
    "Your key stays on this computer, in the system's secure vault.":
        {"uk": "Ключ лишається на цьому комп'ютері, у захищеному сховищі системи.",
         "it": "La chiave resta su questo computer, nel portachiavi sicuro del sistema."},
    "Open the site": {"uk": "Відкрити сайт", "it": "Apri il sito"},
    "Check the key": {"uk": "Перевірити ключ", "it": "Controlla la chiave"},
    "New chat": {"uk": "Нова розмова", "it": "Nuova chat"},
    "Delete chat": {"uk": "Видалити розмову", "it": "Elimina chat"},
    "Delete this chat?": {"uk": "Видалити цю розмову?", "it": "Eliminare questa chat?"},
    "Delete": {"uk": "Видалити", "it": "Elimina"},
    "Settings": {"uk": "Налаштування", "it": "Impostazioni"},
    "Models": {"uk": "Моделі", "it": "Modelli"},
    "About": {"uk": "Про програму", "it": "Informazioni"},
    "Quit": {"uk": "Вийти", "it": "Esci"},
    "Message Lanterna…": {"uk": "Напиши Lanterna…", "it": "Scrivi a Lanterna…"},
    "Thinking…": {"uk": "Думаю…", "it": "Sto pensando…"},
    "Hi, {name}! Ask me anything.": {"uk": "Привіт, {name}! Питай що завгодно.", "it": "Ciao, {name}! Chiedimi quello che vuoi."},
    "Hi! Ask me anything.": {"uk": "Привіт! Питай що завгодно.", "it": "Ciao! Chiedimi quello che vuoi."},
    "Wait for the reply to finish.": {"uk": "Зачекай, доки відповідь закінчиться.", "it": "Aspetta che la risposta finisca."},
    "No working key. Add one in Settings (Ctrl+S).": {"uk": "Немає робочого ключа. Додай його в Налаштуваннях (Ctrl+S).", "it": "Nessuna chiave valida. Aggiungine una nelle Impostazioni (Ctrl+S)."},
    "Language": {"uk": "Мова", "it": "Lingua"},
    "Name": {"uk": "Ім'я", "it": "Nome"},
    "Keys": {"uk": "Ключі", "it": "Chiavi"},
    "Add": {"uk": "Додати", "it": "Aggiungi"},
    "Change": {"uk": "Змінити", "it": "Cambia"},
    "Remove": {"uk": "Прибрати", "it": "Rimuovi"},
    "not set": {"uk": "немає", "it": "non impostata"},
    "Show models": {"uk": "Показати моделі", "it": "Mostra modelli"},
    "Free models right now": {"uk": "Безкоштовні моделі зараз", "it": "Modelli gratuiti adesso"},
    "Search again": {"uk": "Шукати знову", "it": "Cerca di nuovo"},
    "Now using: {m}": {"uk": "Зараз працює: {m}", "it": "In uso ora: {m}"},
    "Star on GitHub": {"uk": "Зірка на GitHub", "it": "Stella su GitHub"},
    # stage 4: tools, files, memory, reminders
    "Checking the weather": {"uk": "Дивлюся погоду", "it": "Controllo il meteo"},
    "Searching the web": {"uk": "Шукаю в інтернеті", "it": "Cerco sul web"},
    "Reading a page": {"uk": "Читаю сторінку", "it": "Leggo una pagina"},
    "Calculating": {"uk": "Рахую", "it": "Calcolo"},
    "Counting dates": {"uk": "Рахую дати", "it": "Calcolo le date"},
    "Saving to memory": {"uk": "Запам'ятовую", "it": "Salvo in memoria"},
    "Updating memory": {"uk": "Оновлюю пам'ять", "it": "Aggiorno la memoria"},
    "Setting a reminder": {"uk": "Ставлю нагадування", "it": "Imposto un promemoria"},
    "Checking reminders": {"uk": "Дивлюся нагадування", "it": "Controllo i promemoria"},
    "Cancelling a reminder": {"uk": "Скасовую нагадування", "it": "Annullo un promemoria"},
    "Attach": {"uk": "Файл", "it": "Allega"},
    "Attach a file or photo": {"uk": "Додати файл або фото", "it": "Allega un file o una foto"},
    "Type or paste the path. Photos, PDF, Word, text and code files work.":
        {"uk": "Введи або встав шлях. Підходять фото, PDF, Word, текстові файли й код.",
         "it": "Scrivi o incolla il percorso. Vanno bene foto, PDF, Word, testo e codice."},
    "File not found.": {"uk": "Файл не знайдено.", "it": "File non trovato."},
    "To understand photos, add a free Gemini key in Settings.":
        {"uk": "Щоб розуміти фото, додай безкоштовний ключ Gemini в Налаштуваннях.",
         "it": "Per capire le foto, aggiungi una chiave Gemini gratuita nelle Impostazioni."},
    "Memory": {"uk": "Пам'ять", "it": "Memoria"},
    "Add a fact": {"uk": "Додати факт", "it": "Aggiungi un fatto"},
    "Nothing yet. Say “remember that…” in a chat.":
        {"uk": "Поки порожньо. Скажи в чаті «запам'ятай, що…».", "it": "Ancora niente. Scrivi «ricorda che…» in chat."},
    "Reminders": {"uk": "Нагадування", "it": "Promemoria"},
    "Reminder": {"uk": "Нагадування", "it": "Promemoria"},
    "No reminders. Say “remind me in 20 minutes…” in a chat.":
        {"uk": "Нагадувань немає. Скажи в чаті «нагадай через 20 хвилин…».",
         "it": "Nessun promemoria. Scrivi «ricordami tra 20 minuti…» in chat."},
}


def t(text: str, lang: str = "en", **kw) -> str:
    s = text if lang == "en" else _T.get(text, {}).get(lang, text)
    return s.format(**kw) if kw else s
