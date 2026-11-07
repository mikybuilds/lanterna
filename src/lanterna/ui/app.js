"use strict";
// Lanterna window UI. Talks to the Python backend through pywebview (window) or HTTP (dev mode, ?token=…).

const TOKEN = new URLSearchParams(location.search).get("token");
const QUICK = location.hash === "#quick";      // the small quick-question window (Windows, hotkey / tray)
const api = new Proxy({}, {
  get: (_, name) => (...args) => window.pywebview && window.pywebview.api
    ? window.pywebview.api[name](...args)
    : fetch("api/" + name, { method: "POST", headers: { "X-Token": TOKEN || "", "Content-Type": "application/json" }, body: JSON.stringify(args) })
        .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }),
});

// ---------------------------------------------------------------- strings (key = English)
const STR = {
  "Choose your language": { uk: "Вибери мову", it: "Scegli la lingua" },
  "You can change it later in Settings.": { uk: "Її можна змінити пізніше в Налаштуваннях.", it: "Puoi cambiarla più tardi nelle Impostazioni." },
  "Made by": { uk: "Створив", it: "Creato da" },
  "A friendly assistant that runs on free cloud models — or on your own PC.": { uk: "Дружній асистент на безкоштовних хмарних моделях — або на твоєму ПК.", it: "Un assistente amichevole che usa modelli cloud gratuiti — o il tuo PC." },
  "What should I call you?": { uk: "Як до тебе звертатися?", it: "Come ti chiami?" },
  "Your name": { uk: "Твоє ім'я", it: "Il tuo nome" },
  "Continue": { uk: "Далі", it: "Avanti" },
  "Back": { uk: "Назад", it: "Indietro" },
  "How should Lanterna think?": { uk: "Як Lanterna думатиме?", it: "Come deve pensare Lanterna?" },
  "Pick what fits your computer.": { uk: "Вибери, що підходить твоєму комп'ютеру.", it: "Scegli ciò che si adatta al tuo computer." },
  "Cloud": { uk: "Хмара", it: "Cloud" },
  "Free models online. Works on any laptop.": { uk: "Безкоштовні моделі онлайн. Працює на будь-якому ноутбуці.", it: "Modelli gratuiti online. Funziona su qualsiasi portatile." },
  "Local": { uk: "Локально", it: "Locale" },
  "Models run on your graphics card. Fully private.": { uk: "Моделі працюють на твоїй відеокарті. Повна приватність.", it: "I modelli girano sulla tua scheda video. Totalmente privato." },
  "Auto": { uk: "Авто", it: "Auto" },
  "Local first, cloud when needed.": { uk: "Спершу локально, хмара — коли треба.", it: "Prima locale, cloud quando serve." },
  "Recommended": { uk: "Рекомендовано", it: "Consigliato" },
  "Soon": { uk: "Скоро", it: "Presto" },
  "Pick your first free service": { uk: "Вибери перший безкоштовний сервіс", it: "Scegli il primo servizio gratuito" },
  "You'll need a free account there. Other services can be added later as backups.": { uk: "Там потрібен безкоштовний акаунт. Інші сервіси можна додати пізніше як запасні.", it: "Serve un account gratuito. Altri servizi si possono aggiungere dopo come riserva." },
  "Fastest": { uk: "Найшвидший", it: "Il più veloce" },
  "Smartest & most generous": { uk: "Найрозумніший і найщедріший", it: "Il più intelligente e generoso" },
  "Replies almost instantly": { uk: "Відповідає майже миттєво", it: "Risponde quasi all'istante" },
  "Strong open models (GPT-OSS, Qwen)": { uk: "Сильні відкриті моделі (GPT-OSS, Qwen)", it: "Modelli aperti potenti (GPT-OSS, Qwen)" },
  "Quick sign-up with Google or GitHub": { uk: "Швидка реєстрація через Google або GitHub", it: "Registrazione veloce con Google o GitHub" },
  "Smaller daily limit": { uk: "Менший денний ліміт", it: "Limite giornaliero più basso" },
  "Big free limits": { uk: "Великі безкоштовні ліміти", it: "Limiti gratuiti ampi" },
  "Understands photos and documents": { uk: "Розуміє фото й документи", it: "Capisce foto e documenti" },
  "Very long conversation memory": { uk: "Дуже довга пам'ять розмови", it: "Memoria di conversazione molto lunga" },
  "Needs a Google account": { uk: "Потрібен Google-акаунт", it: "Serve un account Google" },
  "Get your free {p} key": { uk: "Отримай безкоштовний ключ {p}", it: "Ottieni la chiave gratuita di {p}" },
  "It takes about a minute.": { uk: "Це займе приблизно хвилину.", it: "Ci vuole circa un minuto." },
  "Open the {p} key page": { uk: "Відкрий сторінку ключів {p}", it: "Apri la pagina delle chiavi di {p}" },
  "Open": { uk: "Відкрити", it: "Apri" },
  "Sign in or create a free account": { uk: "Увійди або створи безкоштовний акаунт", it: "Accedi o crea un account gratuito" },
  "Press <b>Create API key</b> and copy it": { uk: "Натисни <b>Create API key</b> і скопіюй його", it: "Premi <b>Create API key</b> e copiala" },
  "Paste it here": { uk: "Встав його сюди", it: "Incollala qui" },
  "Paste your key": { uk: "Встав свій ключ", it: "Incolla la tua chiave" },
  "Check": { uk: "Перевірити", it: "Verifica" },
  "Checking…": { uk: "Перевіряю…", it: "Controllo…" },
  "The key works!": { uk: "Ключ працює!", it: "La chiave funziona!" },
  "This key doesn't work. Check that you copied all of it.": { uk: "Цей ключ не працює. Перевір, чи скопіював його повністю.", it: "Questa chiave non funziona. Controlla di averla copiata tutta." },
  "No internet connection to {p}.": { uk: "Немає з'єднання з {p}.", it: "Nessuna connessione a {p}." },
  "Something went wrong: {e}": { uk: "Щось пішло не так: {e}", it: "Qualcosa è andato storto: {e}" },
  "Your key is kept in your system's secure vault and is only ever sent to {p}.": { uk: "Ключ зберігається в захищеному сховищі системи й надсилається лише до {p}.", it: "La chiave resta nel portachiavi sicuro del sistema e viene inviata solo a {p}." },
  "Start chatting": { uk: "Почати розмову", it: "Inizia a chattare" },
  "New chat": { uk: "Нова розмова", it: "Nuova chat" },
  "Chats": { uk: "Розмови", it: "Chat" },
  "Settings": { uk: "Налаштування", it: "Impostazioni" },
  "About": { uk: "Про програму", it: "Info" },
  "Hi, {n}!": { uk: "Привіт, {n}!", it: "Ciao, {n}!" },
  "Hi!": { uk: "Привіт!", it: "Ciao!" },
  "What's on your mind?": { uk: "Про що поговоримо?", it: "Di cosa parliamo?" },
  "Message Lanterna…": { uk: "Напиши Lanterna…", it: "Scrivi a Lanterna…" },
  "Lanterna can make mistakes. Check important facts.": { uk: "Lanterna може помилятися. Перевіряй важливі факти.", it: "Lanterna può sbagliare. Verifica i fatti importanti." },
  "switched to {m}": { uk: "перейшов на {m}", it: "passato a {m}" },
  "All free models are busy or out of limits. Try again in a minute.": { uk: "Усі безкоштовні моделі зайняті або вичерпали ліміт. Спробуй за хвилину.", it: "Tutti i modelli gratuiti sono occupati o al limite. Riprova tra un minuto." },
  "No connection. Check your internet.": { uk: "Немає з'єднання. Перевір інтернет.", it: "Nessuna connessione. Controlla internet." },
  "Add a key in Settings to start.": { uk: "Додай ключ у Налаштуваннях, щоб почати.", it: "Aggiungi una chiave nelle Impostazioni per iniziare." },
  "Retry": { uk: "Ще раз", it: "Riprova" },
  "Delete this chat?": { uk: "Видалити цю розмову?", it: "Eliminare questa chat?" },
  "Language": { uk: "Мова", it: "Lingua" },
  "Name": { uk: "Ім'я", it: "Nome" },
  "Services": { uk: "Сервіси", it: "Servizi" },
  "Add keys for more services: when one runs out of free limit, Lanterna switches to the next.": { uk: "Додай ключі інших сервісів: коли в одного закінчиться безкоштовний ліміт, Lanterna перейде на наступний.", it: "Aggiungi chiavi di altri servizi: quando uno finisce il limite gratuito, Lanterna passa al successivo." },
  "No key": { uk: "Немає ключа", it: "Nessuna chiave" },
  "Add": { uk: "Додати", it: "Aggiungi" },
  "Change": { uk: "Змінити", it: "Cambia" },
  "Remove": { uk: "Прибрати", it: "Rimuovi" },
  "Cancel": { uk: "Скасувати", it: "Annulla" },
  "Close": { uk: "Закрити", it: "Chiudi" },
  "Remove the key for {p}?": { uk: "Прибрати ключ для {p}?", it: "Rimuovere la chiave di {p}?" },
  "Free models right now": { uk: "Безкоштовні моделі зараз", it: "Modelli gratuiti adesso" },
  "Search again": { uk: "Шукати знову", it: "Cerca di nuovo" },
  "Searching for free models…": { uk: "Шукаю безкоштовні моделі…", it: "Cerco modelli gratuiti…" },
  "ok": { uk: "працює", it: "funziona" },
  "limited": { uk: "ліміт", it: "limite" },
  "untested": { uk: "не перевірено", it: "non testato" },
  "Save": { uk: "Зберегти", it: "Salva" },
  "Saved": { uk: "Збережено", it: "Salvato" },
  "Version {v}": { uk: "Версія {v}", it: "Versione {v}" },
  "Free and open source (MIT). No ads, no tracking — your chats stay on your computer.": { uk: "Безкоштовно й з відкритим кодом (MIT). Без реклами й стеження — розмови лишаються на твоєму комп'ютері.", it: "Gratis e open source (MIT). Niente pubblicità né tracciamento — le chat restano sul tuo computer." },
  "Star on GitHub": { uk: "Зірочка на GitHub", it: "Stella su GitHub" },
  "Project page": { uk: "Сторінка проєкту", it: "Pagina del progetto" },
  "just now": { uk: "щойно", it: "adesso" },
  "Today": { uk: "Сьогодні", it: "Oggi" },
  "Earlier": { uk: "Раніше", it: "Prima" },
  "Explain something simply": { uk: "Поясни щось простими словами", it: "Spiegami qualcosa in modo semplice" },
  "Help me plan my week": { uk: "Допоможи спланувати тиждень", it: "Aiutami a pianificare la settimana" },
  "Write a short message for me": { uk: "Напиши за мене коротке повідомлення", it: "Scrivi un breve messaggio per me" },
  "Give me an idea for today": { uk: "Дай ідею на сьогодні", it: "Dammi un'idea per oggi" },
  "Attach a file or photo": { uk: "Додати файл або фото", it: "Allega un file o una foto" },
  "is bigger than 20 MB": { uk: "більший за 20 МБ", it: "è più grande di 20 MB" },
  "Checking the weather": { uk: "Дивлюся погоду", it: "Controllo il meteo" },
  "Searching the web": { uk: "Шукаю в інтернеті", it: "Cerco sul web" },
  "Reading a page": { uk: "Читаю сторінку", it: "Leggo una pagina" },
  "Calculating": { uk: "Рахую", it: "Calcolo" },
  "Counting dates": { uk: "Рахую дати", it: "Calcolo le date" },
  "Saving to memory": { uk: "Запам'ятовую", it: "Salvo in memoria" },
  "Updating memory": { uk: "Оновлюю пам'ять", it: "Aggiorno la memoria" },
  "Setting a reminder": { uk: "Ставлю нагадування", it: "Imposto un promemoria" },
  "Checking reminders": { uk: "Дивлюся нагадування", it: "Controllo i promemoria" },
  "Cancelling a reminder": { uk: "Скасовую нагадування", it: "Annullo un promemoria" },
  "To understand photos, add a free Gemini key in Settings.": { uk: "Щоб розуміти фото, додай безкоштовний ключ Gemini в Налаштуваннях.", it: "Per capire le foto, aggiungi una chiave Gemini gratuita nelle Impostazioni." },
  "Memory": { uk: "Пам'ять", it: "Memoria" },
  "Facts Lanterna remembers about you. They stay on this computer and are sent to the model with each message.": { uk: "Факти, які Lanterna пам'ятає про тебе. Вони лежать на цьому комп'ютері й надсилаються моделі разом із кожним повідомленням.", it: "Fatti che Lanterna ricorda di te. Restano su questo computer e vengono inviati al modello con ogni messaggio." },
  "Nothing yet. Say “remember that…” in a chat.": { uk: "Поки порожньо. Скажи в чаті «запам'ятай, що…».", it: "Ancora niente. Scrivi «ricorda che…» in chat." },
  "Add a fact": { uk: "Додати факт", it: "Aggiungi un fatto" },
  "Reminders": { uk: "Нагадування", it: "Promemoria" },
  "No reminders. Say “remind me in 20 minutes…” in a chat.": { uk: "Нагадувань немає. Скажи в чаті «нагадай через 20 хвилин…».", it: "Nessun promemoria. Scrivi «ricordami tra 20 minuti…» in chat." },
  "Reminders pop up while Lanterna is open.": { uk: "Нагадування спливають, поки Lanterna відкрита.", it: "I promemoria appaiono mentre Lanterna è aperta." },
  "Reminder": { uk: "Нагадування", it: "Promemoria" },
  // local models
  "GB": { uk: "ГБ", it: "GB" },
  "Checking this computer…": { uk: "Перевіряю цей комп'ютер…", it: "Controllo questo computer…" },
  "Graphics card": { uk: "Відеокарта", it: "Scheda video" },
  "RAM": { uk: "Оперативна пам'ять", it: "RAM" },
  "Free disk": { uk: "Вільно на диску", it: "Disco libero" },
  "No graphics card found": { uk: "Відеокарту не знайдено", it: "Nessuna scheda video trovata" },
  "This computer is better with cloud models. Small local models will be slow.": { uk: "Цьому комп'ютеру краще підходять хмарні моделі. Малі локальні працюватимуть повільно.", it: "Questo computer va meglio con i modelli cloud. Quelli locali piccoli saranno lenti." },
  "Small local models will work. Hard questions are better in the cloud.": { uk: "Малі локальні моделі працюватимуть. Складні питання краще віддавати хмарі.", it: "I modelli locali piccoli funzionano. Le domande difficili vanno meglio nel cloud." },
  "Good for local models of about 8B. Auto mode fits best.": { uk: "Добре тягне локальні моделі розміру ~8B. Найкраще підходить режим «Авто».", it: "Va bene per modelli locali da circa 8B. La modalità Auto è la più adatta." },
  "Strong card: bigger local models fit.": { uk: "Потужна карта: влізуть більші локальні моделі.", it: "Scheda potente: ci stanno modelli locali più grandi." },
  "Very strong card: the biggest open models fit.": { uk: "Дуже потужна карта: влізуть найбільші відкриті моделі.", it: "Scheda molto potente: ci stanno i modelli aperti più grandi." },
  "Ollama {v} is running": { uk: "Ollama {v} працює", it: "Ollama {v} è attivo" },
  "Local models need Ollama, a free app. Install it, start it, then press Check again.": { uk: "Для локальних моделей потрібна Ollama — безкоштовна програма. Встанови її, запусти й натисни «Перевірити знову».", it: "I modelli locali richiedono Ollama, un'app gratuita. Installala, avviala e premi Controlla di nuovo." },
  "Download Ollama": { uk: "Завантажити Ollama", it: "Scarica Ollama" },
  "Check again": { uk: "Перевірити знову", it: "Controlla di nuovo" },
  "Recommended for this computer": { uk: "Рекомендовано для цього комп'ютера", it: "Consigliati per questo computer" },
  "For chatting": { uk: "Для розмов", it: "Per chiacchierare" },
  "For harder questions": { uk: "Для складніших питань", it: "Per domande difficili" },
  "For photos": { uk: "Для фото", it: "Per le foto" },
  "Installed": { uk: "Встановлено", it: "Installato" },
  "Download ({s})": { uk: "Завантажити ({s})", it: "Scarica ({s})" },
  "Not enough disk space": { uk: "Мало місця на диску", it: "Spazio su disco insufficiente" },
  "Download failed: {e}": { uk: "Не вдалося завантажити: {e}", it: "Download non riuscito: {e}" },
  "Checking files…": { uk: "Перевіряю файли…", it: "Controllo i file…" },
  "Starting…": { uk: "Починаю…", it: "Avvio…" },
  "Downloads start only when you press the button. Models are stored by Ollama on this computer.": { uk: "Завантаження почнеться лише після натискання кнопки. Моделі зберігає Ollama на цьому комп'ютері.", it: "Il download parte solo quando premi il pulsante. I modelli restano su questo computer, gestiti da Ollama." },
  "Set up local models": { uk: "Налаштуй локальні моделі", it: "Configura i modelli locali" },
  "Lanterna checked what this computer can run.": { uk: "Lanterna перевірила, що потягне цей комп'ютер.", it: "Lanterna ha controllato cosa può far girare questo computer." },
  "Use the cloud instead": { uk: "Краще хмара", it: "Usa il cloud" },
  "Download at least one model to continue.": { uk: "Щоб продовжити, завантаж хоча б одну модель.", it: "Scarica almeno un modello per continuare." },
  "Mode": { uk: "Режим", it: "Modalità" },
  "Cloud": { uk: "Хмара", it: "Cloud" },
  "Local": { uk: "Локально", it: "Locale" },
  "Auto": { uk: "Авто", it: "Auto" },
  "Send hard questions to the cloud": { uk: "Складні питання віддавати хмарі", it: "Manda le domande difficili al cloud" },
  "Long questions, proofs, code and analysis go to a bigger online model. Private chats: turn it off.": { uk: "Довгі питання, доведення, код і аналіз отримає більша онлайн-модель. Для приватних розмов — вимкни.", it: "Domande lunghe, dimostrazioni, codice e analisi vanno a un modello online più grande. Per chat private: disattivalo." },
  "Local models": { uk: "Локальні моделі", it: "Modelli locali" },
  "Chat model": { uk: "Модель для розмов", it: "Modello per la chat" },
  "Photo model": { uk: "Модель для фото", it: "Modello per le foto" },
  "Automatic": { uk: "Автоматично", it: "Automatico" },
  "None": { uk: "Немає", it: "Nessuno" },
  "Ollama isn't running. Start it, or switch to Cloud in Settings.": { uk: "Ollama не запущена. Запусти її або перемкнися на «Хмару» в Налаштуваннях.", it: "Ollama non è attivo. Avvialo o passa al Cloud nelle Impostazioni." },
  "No local model yet. Download one in Settings → Local models.": { uk: "Локальної моделі ще немає. Завантаж її в Налаштуваннях → Локальні моделі.", it: "Nessun modello locale. Scaricane uno in Impostazioni → Modelli locali." },
  "Checking for updates…": { uk: "Перевіряю оновлення…", it: "Controllo gli aggiornamenti…" },
  "Version {v} is available": { uk: "Доступна версія {v}", it: "È disponibile la versione {v}" },
  "Download": { uk: "Завантажити", it: "Scarica" },
  "Lanterna {v} is out": { uk: "Вийшла Lanterna {v}", it: "È uscita Lanterna {v}" },
  "You have {v}.": { uk: "У тебе {v}.", it: "Hai la {v}." },
  "What's new": { uk: "Що нового", it: "Novità" },
  "How to update": { uk: "Як оновити", it: "Come aggiornare" },
  "Later": { uk: "Пізніше", it: "Più tardi" },
  "Copy": { uk: "Копіювати", it: "Copia" },
  "Copied": { uk: "Скопійовано", it: "Copiato" },
  "Release page": { uk: "Сторінка релізу", it: "Pagina della release" },
  "Updates": { uk: "Оновлення", it: "Aggiornamenti" },
  "Check for a new version when Lanterna starts": { uk: "Перевіряти нову версію під час запуску", it: "Controlla se c'è una nuova versione all'avvio" },
  "A plain request to the project's release page, nothing about you.": { uk: "Простий запит до сторінки релізів проєкту, нічого про тебе.", it: "Una semplice richiesta alla pagina delle release del progetto, niente su di te." },
  "You have the latest version": { uk: "У тебе найновіша версія", it: "Hai l'ultima versione" },
  "Your system has no secure key storage. Set the key as an environment variable instead, e.g. GROQ_API_KEY.": { uk: "У системі немає захищеного сховища ключів. Задай ключ як змінну середовища, напр. GROQ_API_KEY.", it: "Il sistema non ha un archivio sicuro per le chiavi. Imposta la chiave come variabile d'ambiente, es. GROQ_API_KEY." },
  "To understand photos, download a photo model in Settings → Local models.": { uk: "Щоб розуміти фото, завантаж модель для фото в Налаштуваннях → Локальні моделі.", it: "Per capire le foto, scarica un modello per le foto in Impostazioni → Modelli locali." },
  "Report a bug": { uk: "Повідомити про помилку", it: "Segnala un bug" },
  "Found a bug?": { uk: "Знайшов помилку?", it: "Hai trovato un bug?" },
  "Tell what went wrong. You see the whole text first, and you send it yourself.": { uk: "Розкажи, що пішло не так. Спершу ти бачиш увесь текст і надсилаєш його сам.", it: "Racconta cosa non va. Prima vedi tutto il testo, e lo invii tu." },
  "What did you do, what happened, and what did you expect?": { uk: "Що ти робив, що сталося і чого ти очікував?", it: "Cosa hai fatto, cosa è successo e cosa ti aspettavi?" },
  "Add app and system info": { uk: "Додати дані про програму й систему", it: "Aggiungi info su app e sistema" },
  "Version, system, mode and the last errors. Never chats, keys or your name.": { uk: "Версія, система, режим і останні помилки. Ніколи — чати, ключі чи твоє ім'я.", it: "Versione, sistema, modalità e ultimi errori. Mai chat, chiavi o il tuo nome." },
  "This is exactly what will be sent:": { uk: "Ось що саме буде надіслано:", it: "Ecco esattamente cosa verrà inviato:" },
  "Write e-mail": { uk: "Написати листа", it: "Scrivi e-mail" },
  "Open on GitHub": { uk: "Відкрити на GitHub", it: "Apri su GitHub" },
  "Copy text": { uk: "Скопіювати текст", it: "Copia il testo" },
  "Write a few words first.": { uk: "Спершу напиши кілька слів.", it: "Scrivi prima qualche parola." },
  "Your mail app opens with the letter ready. Check it and press Send.": { uk: "Відкриється твоя поштова програма з готовим листом. Перевір і натисни «Надіслати».", it: "Si apre la tua app di posta con la lettera pronta. Controlla e premi Invia." },
  "No mail app? Copy the text and send it to {email} from any mail.": { uk: "Немає поштової програми? Скопіюй текст і надішли на {email} з будь-якої пошти.", it: "Niente app di posta? Copia il testo e invialo a {email} da qualsiasi posta." },
  "The text is long, so the letter is shortened. The full text is copied: paste it into the letter.": { uk: "Текст довгий, тому лист скорочено. Повний текст скопійовано — встав його в лист.", it: "Il testo è lungo, quindi la lettera è accorciata. Il testo completo è copiato: incollalo nella lettera." },
  "Reports by e-mail are coming soon. For now open it on GitHub (free account) or copy the text.": { uk: "Звіти поштою скоро будуть. Поки що відкрий звіт на GitHub (безкоштовний акаунт) або скопіюй текст.", it: "Le segnalazioni via e-mail arrivano presto. Per ora aprila su GitHub (account gratuito) o copia il testo." },
  "Account and sync": { uk: "Акаунт і синхронізація", it: "Account e sincronizzazione" },
  "Sign in with Google to see your chats on all your devices.": { uk: "Увійди через Google, щоб бачити свої чати на всіх пристроях.", it: "Accedi con Google per vedere le tue chat su tutti i dispositivi." },
  "Sign in with Google": { uk: "Увійти через Google", it: "Accedi con Google" },
  "Lanterna uses only a hidden folder of its own in your Google Drive. Your chats, settings and API keys there are encrypted with a password only you know.": { uk: "Lanterna використовує тільки свою приховану папку у твоєму Google Drive. Чати, налаштування й API-ключі там зашифровані паролем, який знаєш лише ти.", it: "Lanterna usa solo una sua cartella nascosta nel tuo Google Drive. Lì chat, impostazioni e chiavi API sono cifrate con una password che conosci solo tu." },
  "Your chats, settings and API keys on all your devices. The same sign-in also connects Google Drive.": { uk: "Твої чати, налаштування й API-ключі на всіх пристроях. Цей самий вхід підключає і Google Drive.", it: "Chat, impostazioni e chiavi API su tutti i tuoi dispositivi. Lo stesso accesso collega anche Google Drive." },
  "Already use Lanterna on another device? Sign in and everything comes over by itself.": { uk: "Вже користуєшся Lanterna на іншому пристрої? Увійди, і все підтягнеться саме.", it: "Usi già Lanterna su un altro dispositivo? Accedi e tutto arriva da solo." },
  "Continue without an account": { uk: "Продовжити без акаунта", it: "Continua senza account" },
  "You can sign in later in Settings → Account and sync.": { uk: "Увійти можна й пізніше: Налаштування → Акаунт і синхронізація.", it: "Puoi accedere più tardi in Impostazioni → Account e sincronizzazione." },
  "Google didn't give Lanterna the permission it needs. Sign in again and leave the box for Lanterna's own folder ticked.": { uk: "Google не дав Lanterna потрібного дозволу. Увійди знову й залиш позначку біля власної папки Lanterna.", it: "Google non ha dato a Lanterna il permesso necessario. Accedi di nuovo e lascia spuntata la casella per la cartella di Lanterna." },
  "Finish signing in in your browser…": { uk: "Заверши вхід у браузері…", it: "Completa l'accesso nel browser…" },
  "Opened in the wrong browser? Copy the link and open it in the browser you use for Google.": { uk: "Відкрилось не в тому браузері? Скопіюй посилання й відкрий його в браузері, де ти заходиш у Google.", it: "Si è aperto nel browser sbagliato? Copia il link e aprilo nel browser che usi per Google." },
  "Copy link": { uk: "Скопіювати посилання", it: "Copia il link" },
  "Choose a sync password (at least 8 characters). You will need it on your other devices.": { uk: "Придумай пароль синхронізації (щонайменше 8 символів). Він знадобиться на інших пристроях.", it: "Scegli una password di sincronizzazione (almeno 8 caratteri). Ti servirà sugli altri dispositivi." },
  "If you forget it, the chats on your devices stay, but the copy in Google Drive can't be opened.": { uk: "Якщо забудеш його, чати на пристроях залишаться, але копію в Google Drive відкрити не вийде.", it: "Se la dimentichi, le chat sui dispositivi restano, ma la copia su Google Drive non si potrà aprire." },
  "Enter the sync password you chose on your other device.": { uk: "Введи пароль синхронізації, який ти придумав на іншому пристрої.", it: "Inserisci la password di sincronizzazione scelta sull'altro dispositivo." },
  "Sync password": { uk: "Пароль синхронізації", it: "Password di sincronizzazione" },
  "Wrong password.": { uk: "Неправильний пароль.", it: "Password sbagliata." },
  "At least 8 characters.": { uk: "Щонайменше 8 символів.", it: "Almeno 8 caratteri." },
  "The sync password was changed on another device. Enter the new one.": { uk: "Пароль синхронізації змінили на іншому пристрої. Введи новий.", it: "La password di sincronizzazione è stata cambiata su un altro dispositivo. Inserisci quella nuova." },
  "You were signed out. Sign in again to keep syncing.": { uk: "Тебе вивело з акаунта. Увійди знову, щоб синхронізація працювала далі.", it: "Sei uscito dall'account. Accedi di nuovo per continuare a sincronizzare." },
  "Signed in as {account}": { uk: "Ти увійшов як {account}", it: "Accesso come {account}" },
  "Signed in with Google": { uk: "Вхід через Google виконано", it: "Accesso con Google effettuato" },
  "Last synced at {time}": { uk: "Остання синхронізація о {time}", it: "Ultima sincronizzazione alle {time}" },
  "Syncing…": { uk: "Синхронізую…", it: "Sincronizzo…" },
  "Sync now": { uk: "Синхронізувати", it: "Sincronizza ora" },
  "Sign out": { uk: "Вийти", it: "Esci" },
  "Sign out and delete the copy in Google Drive": { uk: "Вийти й видалити копію з Google Drive", it: "Esci ed elimina la copia su Google Drive" },
  "Delete the encrypted copy of your chats from Google Drive? Chats on this device stay.": { uk: "Видалити зашифровану копію чатів з Google Drive? Чати на цьому пристрої залишаться.", it: "Eliminare la copia cifrata delle chat da Google Drive? Le chat su questo dispositivo restano." },
  "Couldn't sync: {error}": { uk: "Не вдалося синхронізувати: {error}", it: "Sincronizzazione non riuscita: {error}" },
  "(tried {n} models)": { uk: "(спробував {n} моделей)", it: "(provati {n} modelli)" },
  "Requests today: {n}": { uk: "Запитів сьогодні: {n}", it: "Richieste oggi: {n}" },
  "Refused: {n}": { uk: "Відхилено: {n}", it: "Rifiutate: {n}" },
  "Update now": { uk: "Оновити зараз", it: "Aggiorna ora" },
  "Update by hand": { uk: "Оновити вручну", it: "Aggiorna a mano" },
  "Lanterna downloads the update, checks it, installs it over this version and opens again. Your chats, settings and keys stay as they are.": { uk: "Lanterna завантажить оновлення, перевірить його, встановить поверх цієї версії й відкриється знову. Чати, налаштування й ключі залишаться як є.", it: "Lanterna scarica l'aggiornamento, lo controlla, lo installa sopra questa versione e si riapre. Chat, impostazioni e chiavi restano come sono." },
  "Downloading the update… {done} of {total} MB": { uk: "Завантажую оновлення… {done} з {total} МБ", it: "Scarico l'aggiornamento… {done} di {total} MB" },
  "Installing… Lanterna will close and open again in a moment.": { uk: "Встановлюю… Lanterna зараз закриється й відкриється знову.", it: "Installo… Lanterna si chiuderà e si riaprirà tra un attimo." },
  "The update didn't work: {error}": { uk: "Оновлення не вдалося: {error}", it: "L'aggiornamento non è riuscito: {error}" },
  "This version keeps working. You can update by hand.": { uk: "Ця версія працює далі. Можна оновити вручну.", it: "Questa versione continua a funzionare. Puoi aggiornare a mano." },
  "Limits": { uk: "Ліміти", it: "Limiti" },
  "How much of the free limits is left. Counted on this computer from what the services answer; nothing is sent.": { uk: "Скільки залишилось безкоштовних лімітів. Рахується на цьому комп'ютері з того, що відповідають сервіси; нічого нікуди не надсилається.", it: "Quanto resta dei limiti gratuiti. Calcolato su questo computer da ciò che rispondono i servizi; non viene inviato nulla." },
  "No requests to online models yet today.": { uk: "Сьогодні ще не було запитів до онлайн-моделей.", it: "Oggi ancora nessuna richiesta ai modelli online." },
  "{n} requests today": { uk: "{n} запитів сьогодні", it: "{n} richieste oggi" },
  "{n} refused": { uk: "{n} відхилено", it: "{n} rifiutate" },
  "{left} of {limit} left today": { uk: "сьогодні залишилось {left} з {limit}", it: "oggi ne restano {left} su {limit}" },
  "full again in {t}": { uk: "оновиться через {t}", it: "si ricarica tra {t}" },
  "resting, back in {t}": { uk: "відпочиває, повернеться через {t}", it: "in pausa, torna tra {t}" },
  "The service doesn't say how much is left; it is shown when the limit is reached.": { uk: "Сервіс не каже, скільки залишилось; це буде видно, коли ліміт закінчиться.", it: "Il servizio non dice quanto resta; si vedrà quando il limite sarà raggiunto." },
  "Requests left today": { uk: "Запитів на сьогодні", it: "Richieste rimaste oggi" },
  "Requests left this minute": { uk: "Запитів на цю хвилину", it: "Richieste rimaste in questo minuto" },
  "Requests left this hour": { uk: "Запитів на цю годину", it: "Richieste rimaste in quest'ora" },
  "Requests left this month": { uk: "Запитів на цей місяць", it: "Richieste rimaste questo mese" },
  "Requests left": { uk: "Залишилось запитів", it: "Richieste rimaste" },
  "Tokens left today": { uk: "Токенів на сьогодні", it: "Token rimasti oggi" },
  "Tokens left this minute": { uk: "Токенів на цю хвилину", it: "Token rimasti in questo minuto" },
  "Tokens left this hour": { uk: "Токенів на цю годину", it: "Token rimasti in quest'ora" },
  "Tokens left this month": { uk: "Токенів на цей місяць", it: "Token rimasti questo mese" },
  "Tokens left": { uk: "Залишилось токенів", it: "Token rimasti" },
  "{n} s": { uk: "{n} с", it: "{n} s" },
  "{n} min": { uk: "{n} хв", it: "{n} min" },
  "{n} h": { uk: "{n} год", it: "{n} h" },
  "Working folder": { uk: "Робоча папка", it: "Cartella di lavoro" },
  "Lanterna can look at the files in one folder you choose, and create or change files there after you confirm each change. It never deletes anything and sees nothing outside this folder.": { uk: "Lanterna може переглядати файли в одній папці, яку ти вибереш, і створювати чи змінювати там файли після того, як ти підтвердиш кожну зміну. Вона нічого не видаляє й не бачить нічого поза цією папкою.", it: "Lanterna può guardare i file in una cartella che scegli tu, e creare o modificare file lì dopo che confermi ogni modifica. Non elimina mai nulla e non vede nulla fuori da questa cartella." },
  "The files it opens are sent to the model in use (to the online service in Cloud mode).": { uk: "Файли, які вона відкриває, надсилаються моделі, що зараз працює (у хмарному режимі — онлайн-сервісу).", it: "I file che apre vengono inviati al modello in uso (al servizio online in modalità Cloud)." },
  "Choose a folder": { uk: "Вибрати папку", it: "Scegli una cartella" },
  "Stop using it": { uk: "Більше не використовувати", it: "Non usarla più" },
  "Folder path": { uk: "Шлях до папки", it: "Percorso della cartella" },
  "No folder chosen.": { uk: "Папку не вибрано.", it: "Nessuna cartella scelta." },
  "not found": { uk: "не знайдено", it: "non trovata" },
  "There is no such folder.": { uk: "Такої папки немає.", it: "Questa cartella non esiste." },
  "Choose a smaller folder: not a whole disk, your whole home folder or a system folder.": { uk: "Вибери меншу папку: не цілий диск, не всю домашню папку й не системну.", it: "Scegli una cartella più piccola: non un intero disco, non tutta la cartella home né una cartella di sistema." },
  "Create {path}": { uk: "Створити {path}", it: "Creare {path}" },
  "Rewrite {path}": { uk: "Переписати {path}", it: "Riscrivere {path}" },
  "Add to {path}": { uk: "Дописати в {path}", it: "Aggiungere a {path}" },
  "Create the folder {path}": { uk: "Створити папку {path}", it: "Creare la cartella {path}" },
  "Move {path} → {to}": { uk: "Перемістити {path} → {to}", it: "Spostare {path} → {to}" },
  "Create the folder {name} in Google Drive": { uk: "Створити папку {name} у Google Drive", it: "Creare la cartella {name} su Google Drive" },
  "Upload {path} to Google Drive": { uk: "Завантажити {path} у Google Drive", it: "Caricare {path} su Google Drive" },
  "Save {name} to Google Drive": { uk: "Зберегти {name} у Google Drive", it: "Salvare {name} su Google Drive" },
  "Cancelled: {what}": { uk: "Скасовано: {what}", it: "Annullato: {what}" },
  "Cancelled": { uk: "Скасовано", it: "Annullato" },
  "Couldn't do it: {error}": { uk: "Не вдалося: {error}", it: "Non è riuscito: {error}" },
  "Lanterna will do this only after you confirm.": { uk: "Lanterna зробить це тільки після твого підтвердження.", it: "Lanterna lo farà solo dopo la tua conferma." },
  "Confirm": { uk: "Підтвердити", it: "Conferma" },
  "Done": { uk: "Готово", it: "Fatto" },
  "Working…": { uk: "Виконую…", it: "Eseguo…" },
  "Downloads": { uk: "Завантаження", it: "Download" },
  "Desktop": { uk: "Робочий стіл", it: "Scrivania" },
  "Documents": { uk: "Документи", it: "Documenti" },
  "Pictures": { uk: "Зображення", it: "Immagini" },
  "Videos": { uk: "Відео", it: "Video" },
  "Music": { uk: "Музика", it: "Musica" },
  "Images": { uk: "Картинки", it: "Immagini" },
  "Archives": { uk: "Архіви", it: "Archivi" },
  "Installers": { uk: "Інсталятори", it: "Installer" },
  "Code": { uk: "Код", it: "Codice" },
  "Torrents": { uk: "Торенти", it: "Torrent" },
  "Fonts": { uk: "Шрифти", it: "Font" },
  "Other": { uk: "Інше", it: "Altro" },
  "Sort {count} files in {place}": { uk: "Розкласти {count} файлів у папці {place}", it: "Ordinare {count} file in {place}" },
  "Sorted {count} files in {place}": { uk: "Розкладено {count} файлів у папці {place}", it: "Ordinati {count} file in {place}" },
  "Move {count} items to {to}": { uk: "Перемістити {count} шт. у {to}", it: "Spostare {count} elementi in {to}" },
  "Moved {count} items to {to}": { uk: "Переміщено {count} шт. у {to}", it: "Spostati {count} elementi in {to}" },
  "Rename {path} → {to}": { uk: "Перейменувати {path} → {to}", it: "Rinominare {path} → {to}" },
  "Renamed {path} → {to}": { uk: "Перейменовано {path} → {to}", it: "Rinominato {path} → {to}" },
  "Move {count} items to the Recycle Bin": { uk: "Перемістити {count} шт. у Кошик", it: "Spostare {count} elementi nel Cestino" },
  "Moved {count} items to the Recycle Bin": { uk: "Переміщено {count} шт. у Кошик", it: "Spostati {count} elementi nel Cestino" },
  "Install {name}": { uk: "Встановити {name}", it: "Installare {name}" },
  "Installed {name}": { uk: "Встановлено {name}", it: "Installato {name}" },
  "Update {name}": { uk: "Оновити {name}", it: "Aggiornare {name}" },
  "Updated {name}": { uk: "Оновлено {name}", it: "Aggiornato {name}" },
  "Remove {name}": { uk: "Видалити {name}", it: "Rimuovere {name}" },
  "Removed {name}": { uk: "Видалено {name}", it: "Rimosso {name}" },
  "Switch to the dark theme": { uk: "Увімкнути темну тему", it: "Passare al tema scuro" },
  "Switched to the dark theme": { uk: "Увімкнено темну тему", it: "Tema scuro attivato" },
  "Switch to the light theme": { uk: "Увімкнути світлу тему", it: "Passare al tema chiaro" },
  "Switched to the light theme": { uk: "Увімкнено світлу тему", it: "Tema chiaro attivato" },
  "Switch the power plan to {name}": { uk: "Перемкнути план живлення на «{name}»", it: "Passare al piano energia «{name}»" },
  "Power plan: {name}": { uk: "План живлення: {name}", it: "Piano energia: {name}" },
  "Start {name} with the computer": { uk: "Запускати {name} разом із комп'ютером", it: "Avviare {name} con il computer" },
  "{name} starts with the computer": { uk: "{name} запускається разом із комп'ютером", it: "{name} si avvia con il computer" },
  "Don't start {name} with the computer": { uk: "Не запускати {name} разом із комп'ютером", it: "Non avviare {name} con il computer" },
  "{name} no longer starts with the computer": { uk: "{name} більше не запускається разом із комп'ютером", it: "{name} non si avvia più con il computer" },
  "{n} files still downloading are left alone.": { uk: "{n} файлів, які ще завантажуються, не чіпаю.", it: "{n} file ancora in download restano dove sono." },
  "You can undo the sort afterwards.": { uk: "Розкладання можна буде скасувати.", it: "Potrai annullare l'ordinamento." },
  "Undo": { uk: "Повернути як було", it: "Annulla" },
  "They go to the Recycle Bin: you can restore them from there.": { uk: "Вони підуть у Кошик: звідти їх можна відновити.", it: "Vanno nel Cestino: puoi recuperarli da lì." },
  "Reason: {r}": { uk: "Причина: {r}", it: "Motivo: {r}" },
  "Publisher: {p}": { uk: "Видавець: {p}", it: "Editore: {p}" },
  "from {s}": { uk: "з {s}", it: "da {s}" },
  "Command": { uk: "Команда", it: "Comando" },
  "Windows may ask for administrator rights.": { uk: "Windows може попросити права адміністратора.", it: "Windows potrebbe chiedere i diritti di amministratore." },
  "The system will ask for your password.": { uk: "Система попросить твій пароль.", it: "Il sistema chiederà la tua password." },
  "Installing… this can take a few minutes.": { uk: "Встановлюю… це може зайняти кілька хвилин.", it: "Installo… può richiedere qualche minuto." },
  "Now: {x}": { uk: "Зараз: {x}", it: "Ora: {x}" },
  "dark": { uk: "темна", it: "scura" },
  "light": { uk: "світла", it: "chiara" },
  "It can be turned back on the same way.": { uk: "Так само можна буде увімкнути назад.", it: "Si può riattivare allo stesso modo." },
  "Computer": { uk: "Комп'ютер", it: "Computer" },
  "Let Lanterna help with this computer": { uk: "Дозволити Lanterna допомагати з цим комп'ютером", it: "Lascia che Lanterna aiuti con questo computer" },
  "Your folders (Downloads, Desktop, Documents, Pictures, Videos, Music), programs and a few safe settings. Lanterna looks on its own; every change — moving, the Recycle Bin, installing, a setting — waits for your Confirm. File names and the files it opens go to the model in use.": { uk: "Твої папки (Завантаження, Робочий стіл, Документи, Зображення, Відео, Музика), програми й кілька безпечних налаштувань. Дивитися Lanterna може сама; кожна зміна — переміщення, Кошик, встановлення, налаштування — чекає твого «Підтвердити». Назви файлів і файли, які вона відкриває, отримує модель, що зараз працює.", it: "Le tue cartelle (Download, Scrivania, Documenti, Immagini, Video, Musica), i programmi e alcune impostazioni sicure. Lanterna guarda da sola; ogni modifica — spostare, il Cestino, installare, un'impostazione — aspetta la tua conferma. I nomi dei file e i file che apre vanno al modello in uso." },
  "Thinking…": { uk: "Думаю…", it: "Sto pensando…" },
  "No folder": { uk: "Без папки", it: "Nessuna cartella" },
  "Push {count} files to {repo}": { uk: "Запушити файлів: {count} у {repo}", it: "Fare push di {count} file su {repo}" },
  "Create the repository {name} on GitHub": { uk: "Створити репозиторій {name} на GitHub", it: "Creare il repository {name} su GitHub" },
  "branch {b}": { uk: "гілка {b}", it: "branch {b}" },
  "main branch": { uk: "основна гілка", it: "branch principale" },
  "Commit message": { uk: "Опис коміту", it: "Messaggio del commit" },
  "Files": { uk: "Файли", it: "File" },
  "Left out (look like passwords or keys, or too big):": { uk: "Не увійдуть (схожі на паролі чи ключі, або завеликі):", it: "Esclusi (sembrano password o chiavi, o troppo grandi):" },
  "Co-author: Lanterna Assistant": { uk: "Співавтор: Lanterna Assistant", it: "Coautore: Lanterna Assistant" },
  "private": { uk: "приватний", it: "privato" },
  "public": { uk: "публічний", it: "pubblico" },
  "Confirm opens GitHub with the form filled in: press “Create repository” there, then add it to Lanterna.": { uk: "«Підтвердити» відкриє GitHub із заповненою формою: натисни там «Create repository», а потім додай його в Lanterna.", it: "Conferma apre GitHub con il modulo compilato: premi “Create repository”, poi aggiungilo a Lanterna." },
  "Open on GitHub": { uk: "Відкрити на GitHub", it: "Apri su GitHub" },
  "Add it to Lanterna": { uk: "Додати в Lanterna", it: "Aggiungilo a Lanterna" },
  "Lets the assistant push files from the chat's folder to the repositories you choose, after you confirm each push. It can't delete repositories or change their settings.": { uk: "Асистент зможе пушити файли з папки чату в репозиторії, які ти вибереш, — кожен пуш після твого підтвердження. Видаляти репозиторії чи змінювати їхні налаштування він не може.", it: "L'assistente può fare push dei file dalla cartella della chat ai repository che scegli, dopo la tua conferma per ogni push. Non può eliminare repository né cambiarne le impostazioni." },
  "Type this code on GitHub:": { uk: "Введи цей код на GitHub:", it: "Inserisci questo codice su GitHub:" },
  "Open GitHub": { uk: "Відкрити GitHub", it: "Apri GitHub" },
  "Copy code": { uk: "Копіювати код", it: "Copia il codice" },
  "Waiting for GitHub…": { uk: "Чекаю на GitHub…", it: "In attesa di GitHub…" },
  "Choose repositories": { uk: "Вибрати репозиторії", it: "Scegli i repository" },
  "Connected as @{account}": { uk: "Підключено як @{account}", it: "Connesso come @{account}" },
  "Every commit shows Lanterna Assistant next to you as a co-author. That is only a name on the commit, not access.": { uk: "У кожному коміті GitHub покаже Lanterna Assistant поруч із тобою як співавтора. Це лише ім'я в коміті, а не доступ.", it: "Ogni commit mostra Lanterna Assistant accanto a te come coautore. È solo un nome nel commit, non un accesso." },
  "The GitHub connector isn't set up in this version yet.": { uk: "Конектор GitHub у цій версії ще не налаштований.", it: "Il connettore GitHub non è ancora configurato in questa versione." },
  "The code expired. Press Connect again.": { uk: "Код застарів. Натисни «Підключити» ще раз.", it: "Il codice è scaduto. Premi di nuovo Connetti." },
  "GitHub was disconnected. Connect it again.": { uk: "GitHub відключився. Підключи його знову.", it: "GitHub si è disconnesso. Collegalo di nuovo." },
  "Disconnect forgets the sign-in on this computer. To remove the access on GitHub too: GitHub → Settings → Applications.": { uk: "«Відключити» забуває вхід на цьому комп'ютері. Щоб забрати доступ і на GitHub: GitHub → Settings → Applications.", it: "Disconnetti dimentica l'accesso su questo computer. Per rimuoverlo anche su GitHub: GitHub → Settings → Applications." },
  "New chats start with this folder; each chat can change it under the message box.": { uk: "З цією папкою починають нові чати; кожен чат може змінити її під полем вводу.", it: "Le nuove chat iniziano con questa cartella; ogni chat può cambiarla sotto il campo del messaggio." },
  "Folder of this chat": { uk: "Папка цього чату", it: "Cartella di questa chat" },
  "Lanterna can read and (after you confirm) change files only in this folder.": { uk: "Lanterna читає і (після твого підтвердження) змінює файли тільки в цій папці.", it: "Lanterna legge e (dopo la tua conferma) modifica i file solo in questa cartella." },
  "Choose another folder…": { uk: "Вибрати іншу папку…", it: "Scegli un'altra cartella…" },
  "No folder for this chat": { uk: "Без папки для цього чату", it: "Nessuna cartella per questa chat" },
  "Same as in Settings: {name}": { uk: "Як у налаштуваннях: {name}", it: "Come nelle impostazioni: {name}" },
  "Same as in Settings (none)": { uk: "Як у налаштуваннях (без папки)", it: "Come nelle impostazioni (nessuna)" },
  "Folder path": { uk: "Шлях до папки", it: "Percorso della cartella" },
  "{left} of {limit}": { uk: "{left} з {limit}", it: "{left} di {limit}" },
  "reset in {t}": { uk: "ресет через {t}", it: "reset tra {t}" },
  "{n} requests today": { uk: "запитів сьогодні: {n}", it: "richieste oggi: {n}" },
  "Local model · no limits": { uk: "Локальна модель · без лімітів", it: "Modello locale · nessun limite" },
  "{m}: {left} of {limit} requests left ({period}). Resets in {t}.": { uk: "{m}: залишилось {left} з {limit} запитів ({period}). Скидається через {t}.", it: "{m}: restano {left} di {limit} richieste ({period}). Si azzera tra {t}." },
  "{m}: {n} requests today; the service doesn't say its limit.": { uk: "{m}: запитів сьогодні — {n}; сервіс не каже свій ліміт.", it: "{m}: {n} richieste oggi; il servizio non dice il suo limite." },
  "about — Google tells the exact number only when it is reached": { uk: "приблизно — точне число Google каже, тільки коли ліміт вичерпано", it: "circa — Google dice il numero esatto solo quando si raggiunge" },
  "per day": { uk: "на день", it: "al giorno" },
  "per minute": { uk: "на хвилину", it: "al minuto" },
  "per hour": { uk: "на годину", it: "all'ora" },
  "Click for all limits": { uk: "Натисни, щоб побачити всі ліміти", it: "Clicca per tutti i limiti" },
  "Thinking · steps: {n}": { uk: "Хід думок · кроків: {n}", it: "Ragionamento · passi: {n}" },
  "This card has expired. Ask again.": { uk: "Ця картка застаріла. Попроси ще раз.", it: "Questa scheda è scaduta. Chiedi di nuovo." },
  "{n} characters": { uk: "{n} символів", it: "{n} caratteri" },
  "Folder in Google Drive: {f}": { uk: "Папка в Google Drive: {f}", it: "Cartella su Google Drive: {f}" },
  "Folder in Google Drive: My Drive": { uk: "Папка в Google Drive: Мій диск", it: "Cartella su Google Drive: Il mio Drive" },
  "as a Google Doc": { uk: "як Google Документ", it: "come documento Google" },
  "as a text file": { uk: "як текстовий файл", it: "come file di testo" },
  "Open in Google Drive": { uk: "Відкрити в Google Drive", it: "Apri su Google Drive" },
  "Connectors": { uk: "Конектори", it: "Connettori" },
  "Connect": { uk: "Підключити", it: "Collega" },
  "Disconnect": { uk: "Відключити", it: "Scollega" },
  "Connected": { uk: "Підключено", it: "Collegato" },
  "Connected as {account}": { uk: "Підключено як {account}", it: "Collegato come {account}" },
  "Lets the assistant create folders and save files in your Google Drive, after you confirm each one. It sees only what it created itself.": { uk: "Помічник зможе створювати папки й зберігати файли у твоєму Google Drive після того, як ти підтвердиш кожну дію. Він бачить тільки те, що створив сам.", it: "L'assistente potrà creare cartelle e salvare file nel tuo Google Drive, dopo che confermi ogni azione. Vede solo ciò che ha creato lui." },
  "Google Drive was disconnected. Connect it again.": { uk: "Google Drive відключено. Підключи його знову.", it: "Google Drive è stato scollegato. Collegalo di nuovo." },
};
let LANG = "en";
const t = (s, vars = {}) => {
  let out = LANG === "en" ? s : (STR[s] && STR[s][LANG]) || (S && S.strings && S.strings[s]) || s;
  for (const [k, v] of Object.entries(vars)) out = out.split("{" + k + "}").join(v);
  return out;
};

// ---------------------------------------------------------------- tiny helpers
const $ = (sel, root = document) => root.querySelector(sel);
const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (id, cls = "i") => `<svg class="${cls}"><use href="#i-${id}"/></svg>`;
const h = html => { const d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstElementChild; };

function md(text) {
  // safe, minimal Markdown: everything is escaped first
  const blocks = String(text).split(/```/);
  return blocks.map((b, i) => {
    if (i % 2) { const code = b.replace(/^[\w+-]*\n/, ""); return `<pre><code>${esc(code.replace(/\n$/, ""))}</code></pre>`; }
    const lines = esc(b).split("\n");
    let html = "", list = null;
    const inline = s => s
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a data-href="$2">$1</a>')
      .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a data-href="$2">$2</a>');
    const close = () => { if (list) { html += `</${list}>`; list = null; } };
    let para = [];
    const flush = () => { if (para.length) { html += `<p>${inline(para.join("<br>"))}</p>`; para = []; } };
    for (const ln of lines) {
      let m;
      if ((m = ln.match(/^\s*[-*•]\s+(.*)/))) { flush(); if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1])}</li>`; }
      else if ((m = ln.match(/^\s*\d+[.)]\s+(.*)/))) { flush(); if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[1])}</li>`; }
      else if ((m = ln.match(/^#{1,4}\s+(.*)/))) { flush(); close(); html += `<h3>${inline(m[1])}</h3>`; }
      else if (!ln.trim()) { flush(); close(); }
      else { close(); para.push(ln); }
    }
    flush(); close();
    return html;
  }).join("");
}


// ---------------------------------------------------------------- tools, files, reminders
const TOOL_TEXT = { weather: "Checking the weather", web_search: "Searching the web", read_page: "Reading a page",
  calculate: "Calculating", date_calc: "Counting dates", remember: "Saving to memory", forget: "Updating memory",
  set_reminder: "Setting a reminder", list_reminders: "Checking reminders", cancel_reminder: "Cancelling a reminder" };
const toolChip = s => { const [emo, name] = String(s).split(" "); return `<div class="tool">${esc(emo)} ${esc(t(TOOL_TEXT[name] || name))}</div>`; };

let pending = [];        // files waiting to be sent: {name, size, data(base64)}
const MAX_FILE = 20 * 1024 * 1024;

function readFile(f) {
  return new Promise((ok, fail) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",", 2)[1] || "");
    r.onerror = () => fail(r.error);
    r.readAsDataURL(f);
  });
}

async function addFiles(list) {
  for (const f of Array.from(list || [])) {
    if (f.size > MAX_FILE) { toast(`${f.name} ${t("is bigger than 20 MB")}`); continue; }
    pending.push({ name: f.name, size: f.size, data: await readFile(f) });
  }
  paintFiles();
}

function paintFiles() {
  const box = $("#files");
  if (!box) return;
  box.hidden = !pending.length;
  box.innerHTML = pending.map((f, i) => `<span class="file">${icon("clip")}<span>${esc(f.name)}</span><button data-i="${i}" title="${t("Remove")}">${icon("x")}</button></span>`).join("");
  box.querySelectorAll("button").forEach(b => b.onclick = () => { pending.splice(+b.dataset.i, 1); paintFiles(); });
  $("#input").oninput();
}

function toast(text, sticky = false) {
  // short notices fade out; reminders stay until closed
  const el = h(`<div class="toast${sticky ? " sticky" : ""}"><span></span><button title="${t("Close")}">${icon("x")}</button></div>`);
  el.querySelector("span").textContent = text;
  const close = () => { el.classList.add("out"); setTimeout(() => el.remove(), 600); };
  el.querySelector("button").onclick = close;
  const stack = $("#toasts") || document.body.appendChild(h(`<div id="toasts"></div>`));
  stack.append(el);
  if (!sticky) setTimeout(close, 6000);
}

async function watchAlerts() {
  try {
    const list = await api.alerts();
    list.forEach(a => toast(a.kind ? (a.kind === "tidy" ? "🧹 " : "💾 ") + a.text : `⏰ ${t("Reminder")}: ${a.text}`, true));
    if (list.some(a => a.tid)) refreshThreads();
  } catch (e) { /* app closing */ }
  setTimeout(watchAlerts, 10000);
}

// ---------------------------------------------------------------- state
let S = null;          // backend state
let thread = null;     // current thread id
let busy = false;

async function boot() {
  document.body.prepend($("#tpl-icons").content.cloneNode(true));
  S = await api.state();
  LANG = S.settings.lang || "en";
  document.documentElement.lang = LANG;
  if (QUICK) {
    const ready = S.settings.onboarded && (S.providers.some(p => p.has_key) || S.settings.mode === "local");
    if (ready) return renderQuick();
    $("#app").className = "";
    $("#app").innerHTML = `<div class="quick-note">${esc(t("Finish setting up Lanterna in the main window first."))}</div>`;
    return;
  }
  // dev mode only (browser + token): open one screen directly, used to take the README screenshots
  const view = TOKEN && new URLSearchParams(location.search).get("view");
  if (view === "local") return renderOnboard("L");
  if (view === "settings" || view === "about") { renderMain(); return view === "about" ? openAbout() : openSettings(); }
  if (view === "bug") { renderMain(); return openBugReport(); }
  if (view === "sync") { renderMain(); openSettings(); return setTimeout(() => { const s = $("#sync"); if (s) s.scrollIntoView(); }, 400); }
  if (view === "update") { renderMain(); return api.check_update().then(u => u.newer && showUpdate(u)); }
  if (S.settings.onboarded && (S.providers.some(p => p.has_key) || S.settings.mode === "local")) {
    if (!S.settings.sync_asked && (await api.sync_status()).phase === "off") return renderOnboard("G");
    renderMain(); checkUpdateOnStart();
  }
  else renderOnboard(S.settings.onboarded ? 3 : 0);
}

document.addEventListener("click", e => {
  const a = e.target.closest("a[data-href]");
  if (a) { e.preventDefault(); api.open_url(a.dataset.href); }
});

// ---------------------------------------------------------------- onboarding
const PROVIDER_INFO = {
  groq: { icon: "bolt", tag: "Fastest", pros: ["Replies almost instantly", "Strong open models (GPT-OSS, Qwen)", "Quick sign-up with Google or GitHub"], cons: ["Smaller daily limit"] },
  gemini: { icon: "spark", tag: "Smartest & most generous", pros: ["Big free limits", "Understands photos and documents", "Very long conversation memory"], cons: ["Needs a Google account"] },
};
const pname = id => (S.providers.find(p => p.id === id) || {}).name || id;

function renderOnboard(step) {
  const app = $("#app");
  app.className = "";
  const order = [0, "G", 1, 2, 3, 4], at = order.indexOf(step === "L" ? 3 : step);
  const dots = `<div class="dots">${order.map((_, i) => `<span class="${i <= at ? "on" : ""}"></span>`).join("")}</div>`;
  let body = "";
  if (step === "G") {
    body = `<div class="step">
      <div class="hero-logo"><img src="logo.svg" alt=""></div>
      <h1>${t("Sign in with Google")}</h1>
      <p class="lead">${t("Your chats, settings and API keys on all your devices. The same sign-in also connects Google Drive.")}
        ${t("Already use Lanterna on another device? Sign in and everything comes over by itself.")}</p>
      <div class="card sync-card" id="sync-first"></div>
      <button class="back" id="no-acct">${t("Continue without an account")}</button>
      <small class="faint" style="margin-top:6px">${t("You can sign in later in Settings → Account and sync.")}</small>
    </div>`;
  } else if (step === 0) {
    body = `<div class="step">
      <div class="hero-logo"><img src="logo.svg" alt=""></div>
      <h1>${t("Choose your language")}</h1><p class="lead">${t("You can change it later in Settings.")}</p>
      <div class="langs">${Object.entries(S.langs).map(([k, v]) => `<button class="lang" data-lang="${k}">${v}<small>${{ en: "Hello", uk: "Привіт", it: "Ciao", de: "Hallo", es: "Hola", fr: "Salut", pl: "Cześć" }[k]}</small></button>`).join("")}</div>
    </div>`;
  } else if (step === 1) {
    body = `<div class="step">
      <div class="hero-logo"><img src="logo.svg" alt=""></div>
      <div class="wordmark">Lanterna</div>
      <div class="byline">${t("Made by")} <b>${esc(S.author)}</b> · <a class="link" data-href="${S.homepage}">GitHub</a></div>
      <p class="lead">${t("A friendly assistant that runs on free cloud models — or on your own PC.")}</p>
      <form class="stack" id="f-name">
        <label class="muted" for="name" style="text-align:left">${t("What should I call you?")}</label>
        <input class="field" id="name" maxlength="40" autocomplete="given-name" placeholder="${t("Your name")}" value="${esc(S.settings.name || "")}">
        <button class="btn primary" type="submit">${t("Continue")}</button>
      </form>
      <button class="back" data-back="G">← ${t("Back")}</button>
    </div>`;
  } else if (step === 2) {
    const mode = (id, ic, title, desc, extra, dis) => `<button class="card mode-row" data-mode="${id}" ${dis ? "disabled" : ""}>
      <div class="ic">${icon(ic)}</div><div style="flex:1"><h3>${t(title)}</h3><p>${t(desc)}</p></div>${extra}</button>`;
    body = `<div class="step">
      <h1>${t("How should Lanterna think?")}</h1><p class="lead">${t("Pick what fits your computer.")}</p>
      <div class="cards">
        ${mode("cloud", "cloud", "Cloud", "Free models online. Works on any laptop.", `<span class="badge amber">${t("Recommended")}</span>`, false)}
        ${mode("local", "chip", "Local", "Models run on your graphics card. Fully private.", "", false)}
        ${mode("auto", "auto", "Auto", "Local first, cloud when needed.", "", false)}
      </div>
      <button class="back" data-back="1">← ${t("Back")}</button>
    </div>`;
  } else if (step === "L") {
    body = `<div class="step" style="max-width:640px">
      <h1>${t("Set up local models")}</h1><p class="lead">${t("Lanterna checked what this computer can run.")}</p>
      <div class="card local-card" id="local"></div>
      <div class="status err" id="need" hidden>${t("Download at least one model to continue.")}</div>
      <button class="btn primary" id="go-local" style="margin-top:16px;min-width:220px">${t("Continue")}</button>
      <button class="back" id="to-cloud" style="margin-top:10px">${t("Use the cloud instead")}</button>
      <button class="back" data-back="2">← ${t("Back")}</button>
    </div>`;
  } else if (step === 3) {
    body = `<div class="step" style="max-width:760px">
      <h1>${t("Pick your first free service")}</h1><p class="lead">${t("You'll need a free account there. Other services can be added later as backups.")}</p>
      <div class="cards two">${S.first.map(id => {
        const inf = PROVIDER_INFO[id];
        return `<button class="card" data-first="${id}">
          <div class="head"><div class="ic">${icon(inf.icon)}</div><div><h3>${esc(pname(id))}</h3><div class="tag">${t(inf.tag)}</div></div></div>
          <ul>${inf.pros.map(x => `<li>${icon("check")}${t(x)}</li>`).join("")}${inf.cons.map(x => `<li class="minus">${icon("info")}${t(x)}</li>`).join("")}</ul>
        </button>`;
      }).join("")}</div>
      <button class="back" data-back="2">← ${t("Back")}</button>
    </div>`;
  } else {
    const id = S.settings.provider || "groq";
    const p = S.providers.find(x => x.id === id);
    body = `<div class="step">
      <h1>${t("Get your free {p} key", { p: esc(p.name) })}</h1><p class="lead">${t("It takes about a minute.")}</p>
      <div class="keybox">
        <ol class="keysteps">
          <li><div style="flex:1">${t("Open the {p} key page", { p: esc(p.name) })}</div><button class="btn ghost small" data-open="${esc(p.key_url)}">${t("Open")} ${icon("ext")}</button></li>
          <li>${t("Sign in or create a free account")}</li>
          <li><span>${t("Press <b>Create API key</b> and copy it")}</span></li>
          <li>${t("Paste it here")}</li>
        </ol>
        ${keyRow(id)}
        <div class="note">${icon("lock")}<span>${t("Your key is kept in your system's secure vault and is only ever sent to {p}.", { p: esc(p.name) })}</span></div>
      </div>
      <button class="btn primary" id="go" style="margin-top:20px;min-width:220px" ${p.has_key ? "" : "disabled"}>${t("Start chatting")}</button>
      <button class="back" data-back="3">← ${t("Back")}</button>
    </div>`;
  }
  app.innerHTML = `<div class="onboard">${dots}${body}</div>`;

  app.querySelectorAll("[data-lang]").forEach(b => b.onclick = async () => {
    LANG = b.dataset.lang; S = await api.save_settings({ lang: LANG });
    renderOnboard(!S.settings.sync_asked && (await api.sync_status()).phase === "off" ? "G" : 1);
  });
  app.querySelectorAll("[data-back]").forEach(b => b.onclick = () => renderOnboard(isNaN(+b.dataset.back) ? b.dataset.back : +b.dataset.back));
  if (step === "G") {
    const ready = () => !!(S.providers.some(p => p.has_key) || S.settings.mode === "local");
    const next = async () => {                              // signed in (and synced) or skipped
      S = await api.save_settings({ sync_asked: true });
      LANG = S.settings.lang || LANG;
      if (ready()) { S = await api.save_settings({ onboarded: true }); renderMain(); checkUpdateOnStart(); }
      else renderOnboard(S.settings.onboarded ? 3 : 1);
    };
    syncPanel($("#sync-first"), next);
    $("#no-acct").onclick = next;
  }
  app.querySelectorAll("[data-mode]").forEach(b => b.onclick = async () => {
    S = await api.save_settings({ mode: b.dataset.mode }); renderOnboard(b.dataset.mode === "cloud" ? 3 : "L");
  });
  if (step === "L") {
    localPanel($("#local"));
    $("#to-cloud").onclick = async () => { S = await api.save_settings({ mode: "cloud" }); renderOnboard(3); };
    $("#go-local").onclick = async () => {
      if (S.settings.mode === "auto") return renderOnboard(3);
      const st = await api.local_status();
      if (!st.running || !st.models.length) { $("#need").hidden = false; return; }
      S = await api.save_settings({ onboarded: true }); renderMain();
    };
  }
  app.querySelectorAll("[data-first]").forEach(b => b.onclick = async () => { S = await api.save_settings({ provider: b.dataset.first }); renderOnboard(4); });
  app.querySelectorAll("[data-open]").forEach(b => b.onclick = () => api.open_url(b.dataset.open));
  const f = $("#f-name");
  if (f) { $("#name").focus(); f.onsubmit = async e => { e.preventDefault(); S = await api.save_settings({ name: $("#name").value.trim() }); renderOnboard(2); }; }
  if (step === 4) {
    wireKeyRow(app, S.settings.provider || "groq", () => { $("#go").disabled = false; $("#go").focus(); });
    $("#go").onclick = async () => { S = await api.save_settings({ onboarded: true }); renderMain(); };
  }
}

// ---------------------------------------------------------------- local models (Ollama)
const ROLE_TEXT = { chat: "For chatting", think: "For harder questions", vision: "For photos" };
const TIER_TEXT = {
  none: "This computer is better with cloud models. Small local models will be slow.",
  small: "Small local models will work. Hard questions are better in the cloud.",
  medium: "Good for local models of about 8B. Auto mode fits best.",
  large: "Strong card: bigger local models fit.",
  huge: "Very strong card: the biggest open models fit.",
};
const gb = x => `${(Math.round((x || 0) * 10) / 10).toLocaleString(LANG)} ${t("GB")}`;
let pullTimer = null;

// Hardware, Ollama status and recommended models with Download buttons. onChange runs when a download finishes.
async function localPanel(box, onChange) {
  box.innerHTML = `<div class="status"><span class="spinner"></span>${t("Checking this computer…")}</div>`;
  const [hw, st] = await Promise.all([api.hardware(), api.local_status()]);
  const H = hw.hw, A = hw.advice;
  const gpu = H.gpu ? `${esc(H.gpu)}${H.vram_gb ? ` · ${gb(H.vram_gb)}${H.vram_exact ? "" : "?"}` : ""}` : t("No graphics card found");
  const installed = new Set(st.models.map(m => m.name));
  box.innerHTML = `
    <div class="hw">
      <div><small>${t("Graphics card")}</small><b>${gpu}</b></div>
      <div><small>${t("RAM")}</small><b>${gb(H.ram_gb)}</b></div>
      <div><small>${t("Free disk")}</small><b>${gb(H.disk_free_gb)}</b></div>
    </div>
    <p class="tier">${t(TIER_TEXT[A.tier])}</p>
    ${st.running ? `<div class="status ok">${icon("check")} ${t("Ollama {v} is running", { v: esc(st.version) })}</div>`
      : `<div class="note">${icon("info")}<span>${t("Local models need Ollama, a free app. Install it, start it, then press Check again.")}</span></div>
         <div class="row-btns">${st.can_install ? `<button class="btn primary small" data-install>${t("Install Ollama")}</button>` : ""}
         <button class="btn ${st.can_install ? "ghost" : "primary"} small" data-open="${esc(st.download_page)}">${t("Download Ollama")} ${icon("ext")}</button>
         <button class="btn ghost small" data-recheck>${icon("refresh")} ${t("Check again")}</button></div>`}
    <h4>${t("Recommended for this computer")}</h4>
    <div class="lmodels">${A.models.map(m => `<div class="lrow" data-m="${esc(m.name)}" data-size="${m.size_gb}">
      <div class="nm"><b>${esc(m.name)}</b><small>${t(ROLE_TEXT[m.role])} · ${gb(m.size_gb)}</small></div><div class="act"></div></div>`).join("")}</div>
    <p class="faint small-note">${t("Downloads start only when you press the button. Models are stored by Ollama on this computer.")}</p>
    <label class="check"><input type="checkbox" id="local-fallback" ${st.fallback !== false ? "checked" : ""}>
      <span><b>${t("Use a local model when the online limits run out")}</b><small>${t("In Cloud mode, when every free online model is out of its limit or there is no internet, a model downloaded here answers instead. It stays on this computer.")}</small></span></label>`;
  box.querySelectorAll("[data-open]").forEach(b => b.onclick = () => api.open_url(b.dataset.open));
  const lf = box.querySelector("#local-fallback");
  lf.onchange = async () => { S = await api.save_settings({ local_fallback: lf.checked }); };
  const inst = box.querySelector("[data-install]");
  if (inst) inst.onclick = async () => {
    if (!confirm(t("Install Ollama with winget? Windows may ask for administrator rights.") + "\n\nwinget install --id Ollama.Ollama --exact")) return;
    inst.disabled = true; inst.innerHTML = `<span class="spinner"></span>${t("Installing… this can take a few minutes.")}`;
    const r = await api.install_ollama();
    toast(r.text);
    localPanel(box, onChange);
  };
  const re = box.querySelector("[data-recheck]");
  if (re) re.onclick = () => localPanel(box, onChange);

  const paint = pulls => {
    const by = Object.fromEntries(pulls.map(p => [p.name, p]));
    let active = false;
    box.querySelectorAll(".lrow").forEach(row => {
      const name = row.dataset.m, p = by[name], act = row.querySelector(".act");
      if (p && p.status === "done") installed.add(name);
      if (installed.has(name)) act.innerHTML = `<span class="badge green">${icon("check")} ${t("Installed")}</span>`;
      else if (p && ["starting", "downloading", "verifying"].includes(p.status)) {
        active = true;
        const label = p.status === "verifying" ? t("Checking files…") : p.status === "starting" ? t("Starting…")
          : `${p.percent}% · ${gb(p.done_bytes / 1e9)} / ${gb(p.total_bytes / 1e9)}`;
        act.innerHTML = `<div class="bar"><i style="width:${p.percent}%"></i></div><span class="faint">${label}</span>
          <button class="btn ghost small" data-cancel>${t("Cancel")}</button>`;
        act.querySelector("[data-cancel]").onclick = async () => paint(await api.cancel_pull(name));
      } else {
        const size = +row.dataset.size, noDisk = H.disk_free_gb && H.disk_free_gb < size + 1;
        const err = p && p.status === "error" ? `<span class="status err">${esc(t("Download failed: {e}", { e: p.error }))}</span>` : "";
        act.innerHTML = `${err}<button class="btn ${err ? "ghost" : "primary"} small" data-pull ${!st.running || noDisk ? "disabled" : ""}>
          ${noDisk ? t("Not enough disk space") : t("Download ({s})", { s: gb(size) })}</button>`;
        act.querySelector("[data-pull]").onclick = async () => { await api.pull_model(name); paint(await api.pulls()); };
      }
    });
    clearTimeout(pullTimer);
    if (active && document.body.contains(box)) pullTimer = setTimeout(async () => {
      const next = await api.pulls();
      if (next.some(p => p.status === "done" && !installed.has(p.name)) && onChange) onChange();
      paint(next);
    }, 700);
  };
  paint(st.pulls || []);
}

function keyRow(id) {
  return `<div class="keyrow" data-key="${id}">
      <div class="wrap"><input class="field" type="password" placeholder="${t("Paste your key")}" spellcheck="false" autocomplete="off">
        <button class="eye" type="button" title="Show">${icon("eye")}</button></div>
      <button class="btn primary chk" style="height:48px">${t("Check")}</button>
    </div><div class="status"></div>`;
}

function wireKeyRow(root, id, onOk) {
  const row = root.querySelector(`[data-key="${id}"]`);
  const inp = row.querySelector("input"), st = row.nextElementSibling, btn = row.querySelector(".chk");
  row.querySelector(".eye").onclick = () => { inp.type = inp.type === "password" ? "text" : "password"; };
  const go = async () => {
    if (!inp.value.trim()) return inp.focus();
    btn.disabled = true; st.className = "status"; st.innerHTML = `<span class="spinner"></span>${t("Checking…")}`;
    let r;
    try { r = await api.check_key(id, inp.value); } catch (e) { r = { ok: false, error: "other", message: String(e) }; }
    btn.disabled = false;
    if (r.ok) {
      inp.value = ""; st.className = "status ok"; st.innerHTML = `${icon("check")} ${t("The key works!")}`;
      S = await api.state(); onOk && onOk();
    } else {
      st.className = "status err";
      st.textContent = r.error === "auth" || r.error === "bad_request" ? t("This key doesn't work. Check that you copied all of it.")
        : r.error === "network" ? t("No internet connection to {p}.", { p: pname(id) })
        : r.error === "vault" ? t("Your system has no secure key storage. Set the key as an environment variable instead, e.g. GROQ_API_KEY.") : t("Something went wrong: {e}", { e: r.message || r.error });
    }
  };
  btn.onclick = go;
  inp.onkeydown = e => { if (e.key === "Enter") go(); };
  inp.focus();
}

// ---------------------------------------------------------------- main
function renderMain() {
  const app = $("#app");
  app.className = "";
  app.innerHTML = `<div class="shell">
    <aside class="side">
      <div class="brand"><img src="logo.svg" alt=""><b>Lanterna</b></div>
      <button class="btn ghost newchat" id="new">${icon("plus")} ${t("New chat")}</button>
      <nav class="threads" id="threads"></nav>
      <div class="side-foot">
        <button id="open-history">${icon("history")} ${t("What Lanterna did")}</button>
        <button id="open-settings">${icon("gear")} ${t("Settings")}</button>
        <button id="open-about">${icon("info")} ${t("About")}</button>
      </div>
    </aside>
    <main class="main">
      <div class="top"><button class="menu" id="menu">${icon("menu")}</button><div class="title" id="title">Lanterna</div><div class="chip" id="model" hidden><i></i><span></span></div><button class="iconbtn" id="save-chat" title="${esc(t("Save chat"))}" hidden>${icon("save")}</button></div>
      <div class="scroll" id="scroll"><div class="msgs" id="msgs"></div></div>
      <div class="composer">
        <div class="files" id="files" hidden></div>
        <div class="box"><button class="attach" id="attach" title="${t("Attach a file or photo")}">${icon("clip")}</button>
          <input type="file" id="file" multiple hidden>
          <textarea id="input" rows="1" placeholder="${t("Message Lanterna…")}"></textarea>
          <button class="send" id="send" disabled title="Send">${icon("send")}</button></div>
        <div class="under">
          <button class="lim" id="lim" hidden><span class="lim-track"><i></i></span><span class="lim-tx"></span></button>
          <div class="fold-wrap"><button class="fold" id="fold">${icon("folder")}<span></span>${icon("down", "i caret")}</button></div>
          <span class="hint">${t("Lanterna can make mistakes. Check important facts.")}</span>
        </div>
      </div>
    </main>
  </div>`;
  $("#new").onclick = () => openThread(null);
  $("#open-settings").onclick = openSettings;
  $("#open-about").onclick = openAbout;
  $("#open-history").onclick = openHistory;
  $("#menu").onclick = () => $(".shell").classList.toggle("open");
  const inp = $("#input");
  const fit = () => {
    // empty box: natural one-line height (measuring before layout gives a huge scrollHeight)
    inp.style.height = "auto";
    if (inp.value) inp.style.height = Math.min(inp.scrollHeight, 200) + "px";
    $("#send").disabled = (!inp.value.trim() && !pending.length) || busy; };
  inp.oninput = fit;
  inp.onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } };
  $("#send").onclick = send;
  $("#attach").onclick = () => $("#file").click();
  $("#file").onchange = e => { addFiles(e.target.files); e.target.value = ""; };
  const main = $(".main");
  main.ondragover = e => { e.preventDefault(); main.classList.add("drop"); };
  main.ondragleave = e => { if (e.target === main) main.classList.remove("drop"); };
  main.ondrop = e => { e.preventDefault(); main.classList.remove("drop"); addFiles(e.dataTransfer.files); };
  inp.onpaste = e => { const fs = e.clipboardData && e.clipboardData.files; if (fs && fs.length) { e.preventDefault(); addFiles(fs); } };
  pending = []; paintFiles();
  $("#lim").onclick = () => { openSettings(); setTimeout(() => { const l = $("#limits"); if (l) l.scrollIntoView({ block: "center" }); }, 300); };
  $("#fold").onclick = e => { e.stopPropagation(); folderMenu(); };
  paintLimit();
  refreshThreads().then(list => openThread(!QUICK && list.length ? list[0].id : null));
  api.models(false).then(r => setModel(r.current));
  if (!QUICK && !window.__alerts) { window.__alerts = true; watchAlerts(); watchSync(); }
}

// ---------------------------------------------------------------- the quick-question window (Windows)
let quickAt = 0;
function renderQuick() {
  renderMain();
  document.body.classList.add("quick");
  $(".top").innerHTML = `<div class="title" id="title">${esc(t("Quick question"))}</div><div class="chip" id="model" hidden><i></i><span></span></div>
    <button class="iconbtn" id="q-shot" title="${esc(t("Attach a screenshot"))}">${icon("camera")}</button>
    <button class="iconbtn" id="q-open" title="${esc(t("Open in Lanterna"))}">${icon("ext")}</button>
    <button class="iconbtn" id="q-close" title="${esc(t("Close"))}">${icon("x")}</button>`;
  api.models(false).then(r => setModel(r.current));
  $("#q-shot").onclick = async () => {
    const f = await api.screenshot();
    if (f && f.data) { pending.push(f); paintFiles(); $("#input").oninput(); }
    $("#input").focus();
  };
  $("#q-open").onclick = () => api.open_in_main(thread);
  $("#q-close").onclick = () => api.quick_hide();
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !document.querySelector(".veil")) api.quick_hide(); });
}

// called by the app when the hotkey (or the tray) opens the quick window; file = a screenshot to attach
window.quickOpen = file => {
  if (!$("#input")) return;
  const stale = Date.now() - quickAt > 10 * 60 * 1000;          // back within 10 minutes: the same quick chat
  quickAt = Date.now();
  if (stale && !busy) openThread(null);
  if (file && file.data) { pending.push(file); paintFiles(); $("#input").oninput(); }
  setTimeout(() => $("#input").focus(), 60);
};

// the main window comes back from the tray (maybe with a quick chat to go on with)
window.onShown = tid => {
  if (!$("#threads")) return;
  refreshThreads();
  if (tid) openThread(tid);
};

function setModel(label) {
  const c = $("#model");
  if (!c) return;
  c.hidden = !label;
  c.querySelector("span").textContent = label || "";
}

// the mini-questionnaire before a big task: options as buttons, "Other" as text; the answers go as my next message
function askForm(qs) {
  const f = h(`<div class="ask"><b>${esc(t("Questions for you:"))}</b>${qs.map((q, i) => `<div class="ask-q" data-i="${i}">
      <div>${i + 1}. ${esc(q.question)}</div>
      <div class="ask-opts">${(q.options || []).map((o, j) => `<button class="btn ghost small" data-j="${j}">${esc(o)}</button>`).join("")}</div>
      <input class="field ask-other" placeholder="${esc(t("Other"))}…"></div>`).join("")}
    <div class="ask-act"><button class="btn primary small ask-send">${esc(t("Send answers"))}</button>
      <button class="btn ghost small ask-skip">${esc(t("Skip"))}</button></div></div>`);
  f.querySelectorAll(".ask-q").forEach(row => {
    const q = qs[+row.dataset.i], other = row.querySelector(".ask-other");
    row.querySelectorAll("[data-j]").forEach(b => b.onclick = () => {
      if (!q.multi) row.querySelectorAll("[data-j]").forEach(x => x !== b && x.classList.remove("on"));
      b.classList.toggle("on"); if (!q.multi) other.value = "";
    });
    other.oninput = () => { if (!q.multi && other.value) row.querySelectorAll("[data-j]").forEach(x => x.classList.remove("on")); };
  });
  const go = text => { if (busy) return; f.remove(); $("#input").value = text; send(); };
  f.querySelector(".ask-send").onclick = () => go(t("My answers to your questions:") + "\n" + qs.map((q, i) => {
    const row = f.querySelector(`.ask-q[data-i="${i}"]`);
    const picked = [...row.querySelectorAll("[data-j].on")].map(b => q.options[+b.dataset.j]);
    const own = row.querySelector(".ask-other").value.trim();
    const ans = [...picked, ...(own ? [own] : [])].join(", ");
    return `${i + 1}. ${q.question} — ${ans || t("(skipped)")}`;
  }).join("\n"));
  f.querySelector(".ask-skip").onclick = () => go(t("Skip the questions: do it your way and tell me what you assumed."));
  return f;
}

async function refreshThreads() {
  const list = await api.threads();
  const now = Date.now() / 1000, dayStart = new Date().setHours(0, 0, 0, 0) / 1000;
  const today = list.filter(x => x.updated >= dayStart), older = list.filter(x => x.updated < dayStart);
  const item = x => `<button class="th ${x.id === thread ? "on" : ""}" data-id="${x.id}"><span>${esc(x.title || t("New chat"))}</span>
      <i class="del" data-del="${x.id}" title="Delete">${icon("trash")}</i></button>`;
  $("#threads").innerHTML = (today.length ? `<h6>${t("Today")}</h6>${today.map(item).join("")}` : "") + (older.length ? `<h6>${t("Earlier")}</h6>${older.map(item).join("")}` : "");
  $("#threads").querySelectorAll(".th").forEach(b => b.onclick = e => {
    const d = e.target.closest("[data-del]");
    if (d) { e.stopPropagation(); if (confirm(t("Delete this chat?"))) api.delete_thread(+d.dataset.del).then(() => { if (+d.dataset.del === thread) thread = null; refreshThreads().then(l => openThread(thread || (l[0] && l[0].id) || null)); }); return; }
    openThread(+b.dataset.id); $(".shell").classList.remove("open");
  });
  return list;
}

// "Remembered: …" with Undo (the side model added a fact to Memory)
function memoryToast(f) {
  toast(t("Remembered: {fact}", { fact: f.text }));
  const all = document.querySelectorAll(".toast"), el = all[all.length - 1];
  if (!el) return;
  const undo = h(`<button class="btn ghost small">${esc(t("Undo"))}</button>`);
  undo.onclick = async () => { await api.delete_fact(f.id); el.querySelector("span").textContent = t("Removed from memory."); undo.remove(); };
  el.insertBefore(undo, el.lastElementChild);
}

async function savedToast(r) {
  if (!r || !r.ok) return toast(t("Nothing to save yet."));
  toast(t("Saved to {name}", { name: r.name }) + " · " + t("Show in folder"));
  const all = document.querySelectorAll(".toast"), last = all[all.length - 1];
  if (last) { last.style.cursor = "pointer"; last.onclick = () => api.show_saved(r.path); }
}

async function openThread(id) {
  thread = id;
  const sv = $("#save-chat");
  if (sv) { sv.hidden = !id; sv.onclick = async () => { if (thread) savedToast(await api.export_chat(thread)); }; }
  newChatFolder = undefined;
  paintFolder();
  const msgs = $("#msgs");
  msgs.innerHTML = "";
  if (!id) { $("#title").textContent = QUICK ? t("Quick question") : "Lanterna"; showEmpty(); refreshThreads(); $("#input").focus(); return; }
  const [list, items] = await Promise.all([api.threads(), api.messages(id)]);
  const th = list.find(x => x.id === id);
  $("#title").textContent = (th && th.title) || t("New chat");
  if (!items.length) showEmpty();
  items.forEach(m => {
    if (m.after_summary) msgs.append(h(`<div class="switch">${esc("↑ " + t("Older messages are summarized for the model"))}</div>`));
    m.role === "user" ? addUser(m.content) : addBot(m.content, m.model, m.sent);
  });
  const waiting = await api.cards(id);               // changes still waiting for Confirm: not kept in the history
  if (waiting.length && thread === id) {               // at the end: the reply that proposed them may still be coming
    const last = msgs.lastElementChild;
    const host = last && last.classList.contains("bot") ? last : addBot("");
    const box = h(`<div class="ccs"></div>`);
    waiting.forEach(c => box.append(actCard(c)));
    host.querySelector(".md").after(box);
  }
  paintLastActions();
  refreshThreads();
  scrollDown(true);
  $("#input").focus();
}

// "Edit" under my last message and "Retry" under the last answer (no branches: the old ones are replaced)
function clearLastActions() { document.querySelectorAll(".last-act").forEach(x => x.remove()); }
function paintLastActions() {
  clearLastActions();
  const all = [...document.querySelectorAll("#msgs > .msg")];
  const bot = all[all.length - 1], user = all[all.length - 2];
  if (!bot || !user || !bot.classList.contains("bot") || !user.classList.contains("user") || bot.querySelector(".ask")) return;
  const edit = h(`<div class="last-act user-act"><button class="btn ghost small">${icon("edit")} ${esc(t("Edit"))}</button></div>`);
  edit.querySelector("button").onclick = async () => {
    if (busy) return;
    const r = await api.edit_last(thread);
    if (!r.ok) return;
    bot.remove(); user.remove(); clearLastActions();
    const inp = $("#input"); inp.value = r.text; inp.oninput(); inp.focus();
  };
  user.after(edit);
  const again = h(`<button class="btn ghost small last-act">${icon("refresh")} ${esc(t("Retry"))}</button>`);
  again.onclick = () => { if (busy) return; bot.remove(); clearLastActions(); send({ retry: true, text: "", files: [], again: true }); };
  bot.querySelector(".body").append(again);
}

function showEmpty() {
  const name = S.settings.name;
  const sugg = S.settings.pc_access !== false
    ? ["Sort my Downloads", "Why is my computer slow?", "What's the weather tomorrow?", "Remind me in 20 minutes to take a break",
       "Explain something simply", "Help me plan my week"]
    : ["What's the weather tomorrow?", "Remind me in 20 minutes to take a break", "Explain something simply", "Help me plan my week",
       "Write a short message for me", "Give me an idea for today"];
  $("#msgs").innerHTML = `<div class="empty" style="min-height:calc(100vh - 230px)">
    <div class="hero-logo"><img src="logo.svg" alt=""></div>
    <h2>${name ? t("Hi, {n}!", { n: esc(name) }) : t("Hi!")}</h2><p>${t("What's on your mind?")}</p>
    <div class="sugg">${sugg.map(s => `<button>${t(s)}</button>`).join("")}</div></div>`;
  $("#msgs").querySelectorAll(".sugg button").forEach(b => b.onclick = () => {   // one click sends it
    const i = $("#input"); i.value = b.textContent; i.oninput(); if (!busy) $("#send").click(); else i.focus();
  });
}

function addUser(text) {
  const e = $(".empty"); if (e) e.remove();
  const el = h(`<div class="msg user"></div>`); el.textContent = text; $("#msgs").append(el); return el;
}

function sentBox(lines) {
  if (!lines || !lines.length) return "";
  return `<details class="sent"><summary>${icon("lock")} ${t("What went to the model")}</summary>
    <ul>${lines.map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>`;
}

function addBot(text, model, sent) {
  const e = $(".empty"); if (e) e.remove();
  const el = h(`<div class="msg bot"><img class="av" src="logo.svg" alt=""><div class="body"><div class="md"></div>${model ? `<div class="meta">${esc(model)}</div>` : ""}${sentBox(sent)}</div></div>`);
  if (text === null) el.querySelector(".md").before(h(`<div class="think"><span class="think-dot"></span><span class="think-tx">${t("Thinking…")}</span></div>`));
  else el.querySelector(".md").innerHTML = md(text);
  $("#msgs").append(el); return el;
}

function scrollDown(force) {
  const s = $("#scroll");
  if (force || s.scrollHeight - s.scrollTop - s.clientHeight < 160) s.scrollTop = s.scrollHeight;
}

async function send(retryText) {
  const inp = $("#input");
  const retry = typeof retryText === "object" && retryText !== null && retryText.retry === true;
  const text = retry ? retryText.text : inp.value.trim();
  const files = retry ? retryText.files : pending;
  const again = retry && retryText.again === true;     // answer the last question again: the server replaces it
  if ((!text && !files.length && !again) || busy) return;
  busy = true; $("#send").disabled = true;
  document.querySelectorAll(".follow").forEach(x => x.remove());   // old follow-up ideas go when you write
  if (!thread) {
    thread = (await api.new_thread()).id;
    if (newChatFolder !== undefined) { await api.set_chat_folder(thread, newChatFolder, false); newChatFolder = undefined; }
  }
  if (!retry) {
    pending = []; inp.value = ""; paintFiles();
    const names = files.map(f => (/[.](png|jpe?g|webp|gif|bmp)$/i.test(f.name) ? "🖼 " : "📎 ") + f.name);
    addUser([text, ...names].filter(Boolean).join(String.fromCharCode(10, 10)));
  }
  const bot = addBot(null);
  const box = bot.querySelector(".md");
  scrollDown(true);
  clearLastActions();
  const r = await api.send(thread, text, files.map(f => ({ name: f.name, data: f.data })), again);
  refreshThreads().then(l => { const th = l.find(x => x.id === thread); if (th) $("#title").textContent = th.title; });
  if (!r.ok) {
    busy = false; inp.oninput();
    if (r.error === "file") box.innerHTML = `<div class="err-box">${esc(r.message || "")}</div>`; else bot.remove();
    return;
  }
  let text_ = "", offset = 0, notes = 0, tools = 0, cards = 0, titling = false, suggesting = false, learning = false;
  const sentTo = thread;
  const chips = h(`<div class="tools"></div>`);
  bot.querySelector(".body").prepend(chips);
  const acts = h(`<div class="ccs"></div>`);
  bot.querySelector(".md").after(acts);
  const think = bot.querySelector(".think");
  const thinkDone = steps => {                         // the live line becomes a folded list of the steps
    if (!think.isConnected) return;
    if (!steps || !steps.length) { think.remove(); return; }
    const d = h(`<details class="thinks"><summary>${esc(t("Thinking · steps: {n}", { n: steps.length }))}</summary>
      <ol>${steps.map(x => `<li class="${x.kind === "tool" ? "st-tool" : "st-think"}">${esc(x.text)}</li>`).join("")}</ol></details>`);
    think.replaceWith(d);
  };
  const step = async () => {
    let p;
    try { p = await api.poll(r.stream, offset); } catch (e) { p = { done: true, error: { kind: "network", message: String(e) } }; }
    (p.notes || []).slice(notes).forEach((m, i) => {   // one line, updated: not a ladder of "switched to" notes
      let sw = bot.previousElementSibling;
      if (!sw || !sw.classList.contains("switch")) { sw = h(`<div class="switch"></div>`); bot.before(sw); }
      const tried = notes + i + 2;                        // the first model plus every switch so far
      sw.textContent = "↪ " + t("switched to {m}", { m }) + (tried > 2 ? " " + t("(tried {n} models)", { n: tried }) : "");
      setModel(m);
    });
    notes = (p.notes || []).length;
    (p.tools || []).slice(tools).forEach(s => chips.insertAdjacentHTML("beforeend", toolChip(s)));
    tools = (p.tools || []).length;
    (p.cards || []).slice(cards).forEach(c => acts.append(actCard(c)));
    cards = (p.cards || []).length;
    if (think.isConnected && think.tagName !== "DETAILS") think.querySelector(".think-tx").textContent = p.live || t("Thinking…");
    if (p.final !== undefined) { text_ = p.final; titling = !!p.titling; suggesting = !!p.suggesting; learning = !!p.learning; box.innerHTML = md(text_); if (p.model) { setModel(p.model); bot.querySelector(".body").insertAdjacentHTML("beforeend", `<div class="meta">${esc(p.model)}</div>`); }
      if (p.sent && p.sent.length) bot.querySelector(".body").insertAdjacentHTML("beforeend", sentBox(p.sent));
      if (p.questions && p.questions.length && !box.querySelector(".ask")) { box.innerHTML = ""; box.append(askForm(p.questions)); } }
    else if (p.text) { text_ += p.text; offset = p.offset; box.innerHTML = md(text_); }
    scrollDown();
    if (p.error) {
      const k = p.error.kind;
      const msg = k === "rate" ? t("All free models are busy or out of limits. Try again in a minute.") + " " + t("Tip: a local model (Settings → Local models) answers when the limits run out.")
        : k === "network" ? (S.settings.mode === "local" ? t("Ollama isn't running. Start it, or switch to Cloud in Settings.") : t("No connection. Check your internet.")) : k === "auth" ? t("Add a key in Settings to start.")
        : k === "vision" ? (S.settings.mode === "local" ? t("To understand photos, download a photo model in Settings → Local models.") : t("To understand photos, add a free Gemini key in Settings."))
        : k === "local" ? (p.error.message === "no local models" ? t("No local model yet. Download one in Settings → Local models.") : t("Ollama isn't running. Start it, or switch to Cloud in Settings."))
        : k === "empty" ? t("The model sent no answer. Press Retry or ask in other words.")
        : t("Something went wrong: {e}", { e: p.error.message });
      box.innerHTML = `<div class="err-box">${esc(msg)}</div><button class="btn ghost small" style="margin-top:10px">${icon("refresh")} ${t("Retry")}</button>`;
      box.querySelector("button").onclick = () => { bot.remove(); send({ retry: true, text, files, again: true }); };
    }
    if (p.done) {
      thinkDone(p.error ? [] : p.steps); busy = false; inp.oninput(); paintLimit();
      if (!bot.isConnected && thread === sentTo) openThread(thread);   // the chat was redrawn meanwhile (Settings closed…)
      else if (!p.error && thread === sentTo) paintLastActions();
      if (titling) api.wait_title(sentTo).then(tt => {    // a fast model is naming the new chat
        refreshThreads(); if (tt && thread === sentTo) $("#title").textContent = tt; });
      if (learning) api.wait_memory(sentTo).then(list => (list || []).forEach(memoryToast));   // memory updated itself
      if (suggesting) api.wait_follow_ups(sentTo).then(list => {   // follow-up buttons under the answer
        if (!list || !list.length || !bot.isConnected || busy || thread !== sentTo) return;
        const row = h(`<div class="follow">${list.map(x => `<button class="btn ghost small">${esc(x)}</button>`).join("")}</div>`);
        row.querySelectorAll("button").forEach((b, i) => b.onclick = () => { if (busy) return; $("#input").value = list[i]; send(); });
        bot.querySelector(".body").append(row); scrollDown();
      });
      return;
    }
    setTimeout(step, 60);
  };
  step();
}

// ---------------------------------------------------------------- dialogs
function dialog(title, html, onClose) {
  const v = h(`<div class="veil"><div class="dialog" role="dialog" aria-label="${esc(title)}"><header><h2>${esc(title)}</h2><button>${icon("x")}</button></header>${html}</div></div>`);
  const close = () => { v.remove(); document.removeEventListener("keydown", esc_); onClose && onClose(); };
  const esc_ = e => { if (e.key === "Escape") close(); };
  v.onclick = e => { if (e.target === v) close(); };
  v.querySelector("header button").onclick = close;
  document.addEventListener("keydown", esc_);
  document.body.append(v);
  return v;
}

function openSettings() {
  const v = dialog(t("Settings"), `<section id="set-body"></section>`, () => { LANG = S.settings.lang; renderMain(); });
  const body = v.querySelector("#set-body");
  const paint = () => {
    body.innerHTML = `
      <h4>${t("Language")}</h4>
      <div class="seg" id="seg">${Object.entries(S.langs).map(([k, n]) => `<button data-l="${k}" class="${k === LANG ? "on" : ""}">${n}</button>`).join("")}</div>
      <h4 style="margin-top:22px">${t("Name")}</h4>
      <div class="keyrow"><div class="wrap"><input class="field" id="set-name" maxlength="40" value="${esc(S.settings.name || "")}"></div><button class="btn ghost" id="save-name" style="height:48px">${t("Save")}</button></div>
      <h4 style="margin-top:22px">${t("Mode")}</h4>
      <div class="seg" id="seg-mode">${["cloud", "local", "auto"].map(m => `<button data-mode="${m}" class="${m === S.settings.mode ? "on" : ""}">${t({ cloud: "Cloud", local: "Local", auto: "Auto" }[m])}</button>`).join("")}</div>
      ${S.settings.mode === "auto" ? `<label class="check"><input type="checkbox" id="auto-cloud" ${S.settings.auto_cloud ? "checked" : ""}>
        <span><b>${t("Send hard questions to the cloud")}</b><small>${t("Long questions, proofs, code and analysis go to a bigger online model. Private chats: turn it off.")}</small></span></label>` : ""}
      ${S.settings.mode !== "cloud" ? `<h4 style="margin-top:22px">${t("Local models")}</h4>
        <div id="picks"></div><div class="card local-card" id="local"></div>` : ""}
      <h4 style="margin-top:22px">${t("Services")}</h4>
      <p class="muted" style="margin:0 0 6px;font-size:13.5px">${t("Add keys for more services: when one runs out of free limit, Lanterna switches to the next.")}</p>
      <div>${S.providers.filter(p => !p.local).map(p => `<div class="row" data-p="${p.id}">
        <div class="grow"><b>${esc(p.name)}</b><small>${p.has_key ? esc(p.masked) : t("No key")}</small></div>
        <a class="link" style="font-size:13px" data-href="${esc(p.key_url)}">${icon("ext")}</a>
        ${p.has_key ? `<button class="btn ghost small" data-act="rm">${t("Remove")}</button>` : ""}
        <button class="btn ${p.has_key ? "ghost" : "primary"} small" data-act="add">${p.has_key ? t("Change") : t("Add")}</button>
      </div>`).join("")}</div>
      <h4 style="margin-top:22px;display:flex;align-items:center">${t("Limits")}<button class="btn ghost small" id="lim-refresh" style="margin-left:auto">${icon("refresh")}</button></h4>
      <p class="muted" style="margin:0 0 6px;font-size:13.5px">${t("How much of the free limits is left. Counted on this computer from what the services answer; nothing is sent.")}</p>
      <div id="limits"></div>
      <h4 style="margin-top:22px">${t("Memory")}</h4>
      <p class="muted" style="margin:0 0 6px;font-size:13.5px">${t("Facts Lanterna remembers about you. They stay on this computer and are sent to the model with each message.")}</p>
      <div id="facts"></div>
      <div class="keyrow"><div class="wrap"><input class="field" id="fact-new" maxlength="300" placeholder="${t("Add a fact")}"></div><button class="btn ghost" id="fact-add" style="height:48px">${icon("plus")}</button></div>
      <h4 style="margin-top:22px">${t("Reminders")}</h4>
      <p class="muted" style="margin:0 0 6px;font-size:13.5px">${t("Reminders pop up while Lanterna is open.")}</p>
      <div id="rems"></div>
      <h4 style="margin-top:22px">${t("Working folder")}</h4>
      <div id="workdir"></div>
      <h4 style="margin-top:22px">${t("Chats")}</h4>
      <label class="check" style="margin-top:0"><input type="checkbox" id="ai-titles" ${S.settings.ai_titles !== false ? "checked" : ""}>
        <span><b>${t("Name new chats automatically")}</b><small>${t("After the first answer, a fast online model (or the local one in Local mode) gives the chat a short name. One small extra request.")}</small></span></label>
      <label class="check"><input type="checkbox" id="follow-ups" ${S.settings.follow_ups !== false ? "checked" : ""}>
        <span><b>${t("Suggest what to ask next")}</b><small>${t("Up to 3 buttons under an answer with follow-up questions, written by a fast online model (not Gemini, and not in Local mode). One small extra request per answer.")}</small></span></label>
      <label class="check"><input type="checkbox" id="compact-chats" ${S.settings.compact_chats !== false ? "checked" : ""}>
        <span><b>${t("Remember long chats")}</b><small>${t("When a chat gets long, a fast model writes a short summary of its older part, so Lanterna still remembers it. The summary stays on this device. One small extra request every 10 messages.")}</small></span></label>
      <label class="check"><input type="checkbox" id="ask-first" ${S.settings.ask_first !== false ? "checked" : ""}>
        <span><b>${t("Ask before big tasks")}</b><small>${t("Before a big task (a program, a plan, a project) the model may first ask you 1-4 short questions with options. Your answers become its instructions.")}</small></span></label>
      <label class="check"><input type="checkbox" id="auto-memory" ${S.settings.auto_memory ? "checked" : ""}>
        <span><b>${t("Learn about me from chats")}</b><small>${t("When you tell something about yourself (job, city, what you like), a fast model adds it to Memory. You see each new fact and can undo it. Never passwords or numbers. Off by default.")}</small></span></label>
      <button class="btn ghost small" id="backup-all" style="margin-top:12px">${icon("save")} ${t("Save a backup of all chats")}</button>
      <small class="muted" style="display:block;margin-top:6px">${t("All chats, memory and reminders in one JSON file in Downloads. It is plain text: keep it somewhere safe.")}</small>
      <div id="desk-set" hidden>
      <h4 style="margin-top:22px">${t("Always at hand")}</h4>
      <label class="check"><input type="checkbox" id="tray" ${S.settings.tray !== false ? "checked" : ""}>
        <span><b>${t("Keep Lanterna in the tray")}</b><small>${t("Closing the window keeps Lanterna running next to the clock: reminders and regular tasks still work, and the hotkey opens a quick question. Quit from the tray icon's menu.")}</small></span></label>
      <label class="check"><input type="checkbox" id="autostart">
        <span><b>${t("Start with Windows")}</b><small>${t("Lanterna starts hidden in the tray when you sign in to Windows.")}</small></span></label>
      <div class="row-field"><span>${t("Quick question hotkey")}</span><select class="field" id="hotkey"></select></div>
      <small class="muted" id="hotkey-warn" hidden style="display:block;margin-top:6px">${t("Another app already uses this hotkey. Pick another one.")}</small>
      </div>
      <h4 style="margin-top:22px">${t("Computer")}</h4>
      <label class="check" style="margin-top:0"><input type="checkbox" id="pc-access" ${S.settings.pc_access !== false ? "checked" : ""}>
        <span><b>${t("Let Lanterna help with this computer")}</b><small>${t("Your folders (Downloads, Desktop, Documents, Pictures, Videos, Music), programs and a few safe settings. Lanterna looks on its own; every change — moving, the Recycle Bin, installing, a setting — waits for your Confirm. File names and the files it opens go to the model in use.")}</small></span></label>
      <label class="check"><input type="checkbox" id="tidy-weekly" ${S.settings.tidy_weekly ? "checked" : ""}>
        <span><b>${t("Weekly tidy-up of Downloads")}</b><small>${t("Once a week, if new files are lying loose in Downloads, Lanterna makes a chat with a card to sort them into folders. Nothing moves until you confirm.")}</small></span></label>
      <label class="check"><input type="checkbox" id="space-help" ${S.settings.space_help ? "checked" : ""}>
        <span><b>${t("Help free up disk space")}</b><small>${t("Lanterna can show what takes up space (big and old files, old installers, the Recycle Bin) and warns you when the disk is almost full. Removing goes only to the Recycle Bin, after you confirm.")}</small></span></label>
      <h4 style="margin-top:22px">${t("Updates")}</h4>
      <label class="check" style="margin-top:0"><input type="checkbox" id="upd-check" ${S.settings.update_check !== false ? "checked" : ""}>
        <span><b>${t("Check for a new version when Lanterna starts")}</b><small>${t("A plain request to the project's release page, nothing about you.")}</small></span></label>
      <h4 style="margin-top:22px">${t("Account and sync")}</h4>
      <div id="sync"></div>
      <h4 style="margin-top:22px">${t("Connectors")}</h4>
      <div id="connectors"></div>
      <h4 style="margin-top:22px">${t("Found a bug?")}</h4>
      <p class="muted" style="margin:0 0 8px;font-size:13.5px">${t("Tell what went wrong. You see the whole text first, and you send it yourself.")}</p>
      <button class="btn ghost small" id="set-bug">${t("Report a bug")}</button>
      <h4 style="margin-top:22px;display:flex;align-items:center">${t("Free models right now")}<button class="btn ghost small" id="refresh" style="margin-left:auto">${icon("refresh")} ${t("Search again")}</button></h4>
      <div class="models" id="models"></div>`;
    body.querySelectorAll("[data-l]").forEach(b => b.onclick = async () => { LANG = b.dataset.l; S = await api.save_settings({ lang: LANG }); v.querySelector("header h2").textContent = t("Settings"); paint(); });
    $("#save-name", body).onclick = async e => { S = await api.save_settings({ name: $("#set-name", body).value.trim() }); e.target.textContent = t("Saved"); };
    body.querySelectorAll(".row[data-p]").forEach(row => {
      const id = row.dataset.p;
      row.querySelectorAll("[data-act]").forEach(b => b.onclick = async () => {
        if (b.dataset.act === "rm") { if (confirm(t("Remove the key for {p}?", { p: pname(id) }))) { S = await api.delete_key(id); paint(); } return; }
        if (row.nextElementSibling && row.nextElementSibling.classList.contains("keyrow")) return;
        row.insertAdjacentHTML("afterend", keyRow(id));
        wireKeyRow(body, id, () => setTimeout(paint, 900));
      });
    });
    body.querySelectorAll("#seg-mode [data-mode]").forEach(b => b.onclick = async () => { S = await api.save_settings({ mode: b.dataset.mode }); paint(); });
    const ac = $("#auto-cloud", body);
    if (ac) ac.onchange = async () => { S = await api.save_settings({ auto_cloud: ac.checked }); };
    const pa = $("#pc-access", body);
    pa.onchange = async () => { S = await api.save_settings({ pc_access: pa.checked }); };
    for (const [id, key] of [["#tidy-weekly", "tidy_weekly"], ["#space-help", "space_help"], ["#ai-titles", "ai_titles"], ["#follow-ups", "follow_ups"], ["#compact-chats", "compact_chats"], ["#ask-first", "ask_first"], ["#auto-memory", "auto_memory"]]) {
      const el = $(id, body);
      el.onchange = async () => { S = await api.save_settings({ [key]: el.checked }); };
    }
    $("#backup-all", body).onclick = async () => savedToast(await api.export_all());
    api.desktop_status().then(d => {             // Windows window app: tray, Start with Windows, hotkey
      const box = $("#desk-set", body);
      if (!box || !d.available) return;
      box.hidden = false;
      const tr = $("#tray", body), au = $("#autostart", body), hk = $("#hotkey", body), warn = $("#hotkey-warn", body);
      au.checked = d.autostart;
      hk.innerHTML = d.hotkeys.map(x => `<option value="${esc(x.id)}">${esc(x.id ? x.label : t("Off"))}</option>`).join("");
      hk.value = d.hotkey;
      warn.hidden = !d.hotkey || d.hotkey_ok;
      tr.onchange = async () => { S = await api.save_settings({ tray: tr.checked }); };
      au.onchange = async () => { await api.save_settings({ autostart: au.checked }); au.checked = (await api.desktop_status()).autostart; };
      hk.onchange = async () => { S = await api.save_settings({ hotkey: hk.value }); const n = await api.desktop_status(); warn.hidden = !n.hotkey || n.hotkey_ok; };
    });
    const uc = $("#upd-check", body);
    uc.onchange = async () => { S = await api.save_settings({ update_check: uc.checked }); };
    $("#set-bug", body).onclick = () => openBugReport();
    syncPanel($("#sync", body));
    limitsPanel($("#limits", body));
    $("#lim-refresh", body).onclick = () => limitsPanel($("#limits", body));
    workdirPanel($("#workdir", body));
    connectorsPanel($("#connectors", body));
    if ($("#local", body)) { paintPicks(); localPanel($("#local", body), () => { paintPicks(); loadModels(false); }); }
    $("#refresh", body).onclick = () => loadModels(true);
    loadModels(false);
    paintFacts(); paintRems();
    $("#fact-add", body).onclick = async () => { const i = $("#fact-new", body); if (i.value.trim()) { await api.add_fact(i.value.trim()); i.value = ""; paintFacts(); } };
    $("#fact-new", body).onkeydown = e => { if (e.key === "Enter") $("#fact-add", body).click(); };
  };
  const paintPicks = async () => {
    const st = await api.local_status(), box = $("#picks", body);
    if (!box || !st.running || !st.models.length) { if (box) box.innerHTML = ""; return; }
    const sel = (role, list, none) => `<select class="field" data-role="${role}">
        <option value="">${t(none)}</option>${list.map(m => `<option ${st.picks[role] === m.name ? "selected" : ""}>${esc(m.name)}</option>`).join("")}</select>`;
    box.innerHTML = `<div class="picks">
      <label><small>${t("Chat model")}</small>${sel("chat", st.models, "Automatic")}</label>
      <label><small>${t("Photo model")}</small>${sel("vision", st.models.filter(m => m.vision), "Automatic")}</label></div>`;
    box.querySelectorAll("select").forEach(s => s.onchange = async () => { await api.set_local_model(s.dataset.role, s.value); loadModels(false); });
  };
  const paintFacts = async () => {
    const list = await api.facts(), box = $("#facts", body);
    box.innerHTML = list.length ? list.map(f => `<div class="row"><div class="grow">${esc(f.text)}</div><button class="btn ghost small" data-f="${f.id}" title="${t("Remove")}">${icon("trash")}</button></div>`).join("")
      : `<p class="faint" style="margin:4px 0;font-size:13.5px">${t("Nothing yet. Say “remember that…” in a chat.")}</p>`;
    box.querySelectorAll("[data-f]").forEach(b => b.onclick = async () => { await api.delete_fact(+b.dataset.f); paintFacts(); });
  };
  const paintRems = async () => {
    const list = await api.reminders(), box = $("#rems", body);
    box.innerHTML = list.length ? list.map(r => `<div class="row"><div class="grow"><b>${esc(r.text)}</b><small>${esc(r.when)}</small></div><button class="btn ghost small" data-r="${r.id}">${t("Cancel")}</button></div>`).join("")
      : `<p class="faint" style="margin:4px 0;font-size:13.5px">${t("No reminders. Say “remind me in 20 minutes…” in a chat.")}</p>`;
    box.querySelectorAll("[data-r]").forEach(b => b.onclick = async () => { await api.cancel_reminder(+b.dataset.r); paintRems(); });
  };
  const loadModels = async refresh => {
    const box = $("#models", body);
    box.innerHTML = `<div class="status"><span class="spinner"></span>${t("Searching for free models…")}</div>`;
    const r = await api.models(refresh);
    if (!r.ok) { box.innerHTML = `<div class="status err">${t("Add a key in Settings to start.")}</div>`; return; }
    const cls = { ok: "green", limited: "amber", untested: "" };
    box.innerHTML = r.models.slice(0, 12).map(m => `<div class="mrow"><div class="nm"><small>${esc(m.provider)}</small>${esc(m.model)}</div>
      <span class="faint">${m.latency ? m.latency.toFixed(1) + "s" : ""}</span><span class="badge ${cls[m.status] || ""}">${t(m.status)}</span></div>`).join("");
    setModel(r.current);
  };
  paint();
}

function openAbout() {
  const v = dialog(t("About"), `<div class="about">
    <div class="hero-logo"><img src="logo.svg" alt=""></div>
    <div class="wordmark">Lanterna</div>
    <div class="byline">${t("Made by")} <b>${esc(S.author)}</b> · ${t("Version {v}", { v: esc(S.version) })}</div>
    <p class="muted" style="max-width:380px;margin:0 auto 22px">${t("Free and open source (MIT). No ads, no tracking — your chats stay on your computer.")}</p>
    <div class="update" id="update"></div>
    <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap">
      <button class="btn primary" data-o="1">${icon("star")} ${t("Star on GitHub")}</button>
      <button class="btn ghost" data-o="1">${t("Project page")} ${icon("ext")}</button>
    </div>
    <div style="display:flex;gap:8px;justify-content:center;margin-top:14px">
      <button class="btn ghost small" id="about-doctor">${t("Check Lanterna")}</button>
      <button class="btn ghost small" id="about-bug">${t("Report a bug")}</button></div></div>`);
  $("#about-bug", v).onclick = () => { v.remove(); openBugReport(); };
  $("#about-doctor", v).onclick = () => { v.remove(); openDoctor(); };
  v.querySelectorAll("[data-o]").forEach(b => b.onclick = () => api.open_url(S.homepage));
  const box = $("#update", v);
  box.innerHTML = `<span class="spinner"></span>${t("Checking for updates…")}`;
  api.check_update().then(u => {
    if (!u.latest) { box.innerHTML = ""; return; }                 // offline or no release yet: stay quiet
    box.innerHTML = u.newer
      ? `<b>${t("Version {v} is available", { v: esc(u.latest) })}</b> <button class="btn primary small" id="get-update">${t("How to update")}</button>`
      : `${icon("check")} ${t("You have the latest version")}`;
    const b = $("#get-update", v);
    if (b) b.onclick = () => { v.remove(); showUpdate(u); };
  }).catch(() => { box.innerHTML = ""; });
}

// ---------------------------------------------------------------- what Lanterna did
function openHistory() {
  const v = dialog(t("What Lanterna did"), `<section class="hist">
    <p class="muted" style="margin:0 0 12px">${t("Changes you confirmed on this computer, newest first. Undo puts files back, takes them out of the Recycle Bin or switches a setting back.")}</p>
    <div id="hist-list"><span class="spinner"></span></div>
    <div class="upd-actions"><button class="btn ghost small" id="hist-clear">${t("Clear the list")}</button>
      <span style="flex:1"></span><button class="btn primary" id="hist-close">${t("Close")}</button></div></section>`);
  $("#hist-close", v).onclick = () => v.remove();
  const when = s => new Date(s * 1000).toLocaleString(LANG, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const fill = list => {
    const box = $("#hist-list", v);
    if (!list.length) { box.innerHTML = `<p class="muted">${t("Nothing yet. When you confirm a change on a card, it shows up here.")}</p>`; return; }
    box.innerHTML = list.map(x => `<div class="hist-row${x.undone ? " undone" : ""}" data-id="${esc(x.id)}">
      <span class="hist-when">${when(x.at)}</span>
      <span class="hist-title">${esc(x.title)}${x.undone ? `<small>↩ ${esc(x.note || t("Undone"))}</small>` : ""}</span>
      ${x.can_undo ? `<button class="btn ghost small" data-undo="1">${t("Undo")}</button>` : "<span></span>"}</div>`).join("");
    box.querySelectorAll("[data-undo]").forEach(b => b.onclick = async () => {
      const row = b.closest(".hist-row");
      b.disabled = true; b.innerHTML = `<span class="spinner"></span>`;
      const r = await api.history_undo(row.dataset.id);
      if (!r.ok) toast(r.text);
      fill(await api.history_list());
    });
  };
  $("#hist-clear", v).onclick = async () => fill(await api.history_clear());
  api.history_list().then(fill);
}

// ---------------------------------------------------------------- check Lanterna
function openDoctor() {
  const v = dialog(t("Check Lanterna"), `<section class="doctor">
    <div id="doc-list"><span class="spinner"></span>${t("Checking Lanterna…")}</div>
    <p id="doc-sum" class="muted"></p>
    <div class="upd-actions">
      <button class="btn ghost" id="doc-copy" disabled>${t("Copy")}</button>
      <button class="btn ghost" id="doc-bug">${t("Report a bug")}</button>
      <span style="flex:1"></span>
      <button class="btn primary" id="doc-close">${t("Close")}</button>
    </div></section>`);
  $("#doc-close", v).onclick = () => v.remove();
  $("#doc-bug", v).onclick = () => { v.remove(); openBugReport(); };
  const mark = { ok: "✓", warn: "!", fail: "✗", info: "·" };
  api.doctor(true).then(res => {
    $("#doc-list", v).innerHTML = res.checks.map(c => `<div class="doc-row doc-${c.status}">
      <span class="doc-mark">${mark[c.status]}</span><b>${esc(c.title)}</b><span>${esc(c.detail)}</span></div>`).join("");
    $("#doc-sum", v).textContent = t(res.worst === "ok" ? "Everything works." : "Something needs attention (see the lines above).");
    const cp = $("#doc-copy", v);
    cp.disabled = false;
    cp.onclick = async () => { try { await navigator.clipboard.writeText(res.text); cp.textContent = t("Copied"); } catch (e) { /* no clipboard */ } };
  });
}

// ---------------------------------------------------------------- update notice
function showUpdate(u) {
  const notes = (u.notes || []).map(n => `<li>${esc(n)}</li>`).join("");
  const cmd = u.command ? `<div class="upd-cmd"><code id="upd-cmd">${esc(u.command)}</code><button class="btn ghost small" id="upd-copy">${t("Copy")}</button></div>` : "";
  let cmdShown = false;                                     // the command goes right under the "run:" step
  const steps = (u.steps || []).map(s => {
    const here = cmd && !cmdShown && s.endsWith(":");
    if (here) cmdShown = true;
    return `<li>${esc(s)}${here ? cmd : ""}</li>`;
  }).join("");
  const v = dialog(t("Lanterna {v} is out", { v: u.latest }), `<section class="upd">
    <p class="muted" style="margin:0 0 14px">${t("You have {v}.", { v: esc(u.current) })}</p>
    ${notes ? `<h4>${t("What's new")}</h4><ul class="upd-notes">${notes}</ul>` : ""}
    ${u.auto ? `<p class="upd-auto" id="upd-auto">${t("Lanterna downloads the update, checks it, installs it over this version and opens again. Your chats, settings and keys stay as they are.")}</p>
      <details class="upd-hand"><summary>${t("Update by hand")}</summary><ol class="upd-steps">${steps}</ol></details>`
      : `<h4>${t("How to update")}</h4><ol class="upd-steps">${steps}</ol>`}
    ${cmdShown ? "" : cmd}
    <div class="upd-actions">
      <button class="btn ghost" id="upd-page">${t("Release page")} ${icon("ext")}</button>
      <span style="flex:1"></span>
      <button class="btn ghost" id="upd-later">${t("Later")}</button>
      ${u.download ? `<button class="btn ${u.auto ? "ghost" : "primary"}" id="upd-dl">${t("Download")}</button>` : ""}
      ${u.auto ? `<button class="btn primary" id="upd-now">${t("Update now")}</button>` : ""}
    </div></section>`);
  $("#upd-page", v).onclick = () => api.open_url(u.url);
  $("#upd-later", v).onclick = () => v.remove();
  const dl = $("#upd-dl", v);
  if (dl) dl.onclick = () => api.open_url(u.download);
  const now = $("#upd-now", v);
  if (now) now.onclick = async () => {
    now.disabled = true; if (dl) dl.disabled = true;
    const box = $("#upd-auto", v);
    const mb = n => (n / 1048576).toFixed(1);
    const tick = st => {
      if (st.phase === "downloading") {
        const pct = st.total ? Math.round(st.done * 100 / st.total) : 0;
        box.innerHTML = `<span class="spinner"></span>${t("Downloading the update… {done} of {total} MB", { done: mb(st.done), total: st.total ? mb(st.total) : "?" })}
          <span class="upd-bar"><i style="width:${pct}%"></i></span>`;
      } else if (st.phase === "installing") {
        box.innerHTML = `<span class="spinner"></span>${u.auto_kind === "pipx" ? t("Updating with pipx… this can take a minute or two.")
          : t("Installing… Lanterna will close and open again in a moment.")}`;
        if (u.auto_kind !== "pipx") return;
      } else if (st.phase === "restart") {
        box.innerHTML = `${icon("check")} ${t("Lanterna {v} is installed. Start it again to use it.", { v: esc(u.latest) })}`;
        now.remove(); if (dl) dl.remove();
        return;
      } else if (st.phase === "error") {
        box.innerHTML = `<span class="sync-err">${esc(t("The update didn't work: {error}", { error: st.error }))}</span> ${t("This version keeps working. You can update by hand.")}`;
        now.disabled = false; if (dl) dl.disabled = false;
        return;
      }
      setTimeout(async () => tick(await api.update_status()), 400);
    };
    tick(await api.update_install());
  };
  const cp = $("#upd-copy", v);
  if (cp) cp.onclick = async () => {
    try { await navigator.clipboard.writeText(u.command); }
    catch (e) {                                          // older webviews: copy through a selection
      const r = document.createRange(); r.selectNodeContents($("#upd-cmd", v));
      const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r); document.execCommand("copy");
    }
    cp.textContent = t("Copied");
  };
  return v;
}

// ---------------------------------------------------------------- under the message box: limit bar, folder of the chat
const PERIOD = { day: "per day", minute: "per minute", hour: "per hour" };
let limitTimer = null;
async function paintLimit() {
  const b = $("#lim");
  if (!b) return;
  clearTimeout(limitTimer);
  limitTimer = setTimeout(paintLimit, 60000);              // the reset countdown moves
  let r;
  try { r = await api.limit_now(); } catch (e) { return; }
  if (!r || !r.label) { b.hidden = true; return; }
  b.hidden = false;
  const fill = b.querySelector("i"), tx = b.querySelector(".lim-tx");
  b.classList.remove("low", "out", "unknown", "local");
  if (r.local) {
    b.classList.add("local"); fill.style.width = "100%";
    tx.textContent = t("Local model · no limits"); b.title = r.label; return;
  }
  if (r.limit == null) {
    b.classList.add("unknown"); fill.style.width = "0";
    tx.textContent = t("{n} requests today", { n: r.used });
    b.title = t("{m}: {n} requests today; the service doesn't say its limit.", { m: r.label, n: r.used }) + "\n" + t("Click for all limits");
    return;
  }
  const frac = Math.max(0, Math.min(1, r.left / Math.max(1, r.limit)));
  fill.style.width = (frac * 100).toFixed(1) + "%";
  if (r.left <= 0) b.classList.add("out"); else if (frac < 0.25) b.classList.add("low");
  const left = (r.approx ? "≈" : "") + r.left;
  tx.textContent = t("{left} of {limit}", { left, limit: r.limit }) + (r.reset_in != null ? " · " + t("reset in {t}", { t: fmtSecs(r.reset_in) }) : "");
  b.title = t("{m}: {left} of {limit} requests left ({period}). Resets in {t}.", { m: r.label, left, limit: r.limit,
    period: t(PERIOD[r.period] || "per day"), t: r.reset_in != null ? fmtSecs(r.reset_in) : "?" })
    + (r.approx ? "\n≈ " + t("about — Google tells the exact number only when it is reached") : "") + "\n" + t("Click for all limits");
}

let newChatFolder;      // a folder picked for a chat that has no messages yet (applied when it is created)
async function paintFolder() {
  const b = $("#fold");
  if (!b) return;
  const f = await api.chat_folder(thread || 0);
  const path = newChatFolder !== undefined ? newChatFolder : f.path;
  const name = newChatFolder !== undefined ? (newChatFolder.split(/[\\/]/).filter(Boolean).pop() || newChatFolder) : f.name;
  b.querySelector("span").textContent = path ? (name || path) : t("No folder");
  b.classList.toggle("none", !path);
  b.classList.toggle("missing", newChatFolder === undefined && f.missing);
  b.title = path ? t("Folder of this chat") + ": " + path : t("Folder of this chat") + ": " + t("No folder");
  b.dataset.path = path || "";
  b.dataset.def = f.default || "";
  b.dataset.own = newChatFolder !== undefined || f.own ? "1" : "";
}

function folderMenu() {
  const old = $(".fold-menu");
  if (old) { old.remove(); return; }
  const b = $("#fold"), path = b.dataset.path, def = b.dataset.def;
  const defName = def ? def.split(/[\\/]/).filter(Boolean).pop() : "";
  const m = h(`<div class="fold-menu" role="menu">
    <div class="fm-head"><b>${esc(t("Folder of this chat"))}</b><small>${esc(path || t("No folder"))}</small>
      <p>${esc(t("Lanterna can read and (after you confirm) change files only in this folder."))}</p></div>
    <button data-a="pick">${icon("folder")} ${esc(t("Choose another folder…"))}</button>
    ${path ? `<button data-a="none">${icon("x")} ${esc(t("No folder for this chat"))}</button>` : ""}
    ${b.dataset.own && def !== path ? `<button data-a="def">${icon("refresh")} ${esc(def ? t("Same as in Settings: {name}", { name: defName }) : t("Same as in Settings (none)"))}</button>` : ""}
    <div class="fm-row" hidden><input class="field" placeholder="${esc(t("Folder path"))}"><button class="btn primary small">${t("Save")}</button></div>
    <p class="sync-err fm-err"></p></div>`);
  b.parentElement.append(m);
  const close = e => { if (!m.contains(e.target)) { m.remove(); document.removeEventListener("mousedown", close); } };
  setTimeout(() => document.addEventListener("mousedown", close), 0);
  const errs = { not_found: t("There is no such folder."), too_broad: t("Choose a smaller folder: not a whole disk, your whole home folder or a system folder.") };
  const apply = async (p, followDefault) => {
    if (!thread) {                                       // no chat yet: remember it for the first message
      const chk = followDefault ? { ok: true } : (p ? await api.check_folder(p) : { ok: true, path: "" });
      if (!chk.ok) { m.querySelector(".fm-err").textContent = errs[chk.error] || chk.error; return; }
      newChatFolder = followDefault ? undefined : chk.path;
    } else {
      const r = await api.set_chat_folder(thread, p, !!followDefault);
      if (!r.ok) { m.querySelector(".fm-err").textContent = errs[r.error] || r.error; return; }
    }
    m.remove(); document.removeEventListener("mousedown", close); paintFolder();
  };
  m.querySelectorAll("[data-a]").forEach(x => x.onclick = async () => {
    const a = x.dataset.a;
    if (a === "none") return apply("", false);
    if (a === "def") return apply("", true);
    const r = await api.choose_folder(path || def || "");
    if (r.error === "no_dialog") {                          // browser mode: type the path
      const row = m.querySelector(".fm-row"); row.hidden = false;
      const inp = row.querySelector("input"); inp.value = path || ""; inp.focus();
      row.querySelector("button").onclick = () => apply(inp.value.trim(), false);
      inp.onkeydown = e => { if (e.key === "Enter") apply(inp.value.trim(), false); };
      return;
    }
    if (r.ok) return apply(r.path, false);
    if (r.error !== "cancelled") m.querySelector(".fm-err").textContent = errs[r.error] || r.error;
  });
}

// ---------------------------------------------------------------- confirmation cards
const ACT_KEYS = { write_new: "Create {path}", write_replace: "Rewrite {path}", write_append: "Add to {path}",
  mkdir: "Create the folder {path}", move: "Move {path} → {to}", drive_folder: "Create the folder {name} in Google Drive",
  drive_upload: "Upload {path} to Google Drive", drive_text: "Save {name} to Google Drive",
  github_push: "Push {count} files to {repo}", github_new_repo: "Create the repository {name} on GitHub",
  pc_sort: "Sort {count} files in {place}", pc_move: "Move {count} items to {to}", pc_rename: "Rename {path} → {to}",
  pc_mkdir: "Create the folder {path}", pc_trash: "Move {count} items to the Recycle Bin",
  app_install: "Install {name}", app_upgrade: "Update {name}", app_uninstall: "Remove {name}",
  sys_power: "Switch the power plan to {name}" };
const placeName = p => p ? t(p.charAt(0).toUpperCase() + p.slice(1)) : "";
function actKey(c) {
  const d = c.details || {};
  if (c.kind === "sys_theme") return d.theme === "dark" ? "Switch to the dark theme" : "Switch to the light theme";
  if (c.kind === "sys_startup") return d.on ? "Start {name} with the computer" : "Don't start {name} with the computer";
  return ACT_KEYS[c.kind] || "Change";
}
const cardIcon = k => k.startsWith("github_") ? "🐙" : k.startsWith("drive_") ? "☁️" : k === "pc_trash" ? "🗑" :
  k.startsWith("pc_") ? "🗂" : k.startsWith("app_") ? "📦" : k.startsWith("sys_") ? "⚙️" : "📁";

function actCard(c) {
  const d = c.details || {};
  let to = d.to || "";
  if (c.kind === "pc_move" && d.to_place) to = placeName(d.to_place) + (to && to !== "." ? "/" + to : "");
  const title = t(actKey(c), { path: d.path || "", to, name: d.name || "", repo: d.repo || "", count: d.count || 0, place: placeName(d.place) });
  const meta = [];
  const gh = c.kind.startsWith("github_");
  let extra = "";
  if (c.kind === "github_push") {
    meta.push(d.branch ? t("branch {b}", { b: d.branch }) : t("main branch"));
    meta.push(((d.size || 0) / 1048576).toFixed(2) + " MB");
    const more = d.count > (d.files || []).length ? `\n… +${d.count - d.files.length}` : "";
    extra = `<div class="cc-lbl">${t("Commit message")}</div><pre class="cc-prev">${esc(d.message || "")}</pre>
      <div class="cc-meta">${esc(t("Co-author: Lanterna Assistant"))}</div>
      <div class="cc-lbl">${t("Files")}</div><pre class="cc-prev">${esc((d.files || []).join("\n"))}${more}</pre>
      ${(d.skipped || []).length ? `<div class="cc-meta sync-err">${esc(t("Left out (look like passwords or keys, or too big):"))} ${esc(d.skipped.join("; "))}</div>` : ""}`;
  } else if (c.kind === "github_new_repo") {
    meta.push(t(d.private ? "private" : "public"));
    extra = `<div class="cc-meta">${esc(t("Confirm opens GitHub with the form filled in: press “Create repository” there, then add it to Lanterna."))}</div>`;
  } else if (c.kind === "pc_sort") {
    meta.push(((d.size || 0) / 1048576).toFixed(1) + " MB");
    extra = `<div class="cc-groups">${(d.groups || []).map(g => `<details><summary>📁 <b>${esc(g.to)}</b> <span class="muted">— ${g.count}</span></summary>
      <pre class="cc-prev">${esc(g.files.join("\n"))}${g.count > g.files.length ? `\n… +${g.count - g.files.length}` : ""}</pre></details>`).join("")}</div>
      ${d.skipped ? `<div class="cc-meta">${esc(t("{n} files still downloading are left alone.", { n: d.skipped }))}</div>` : ""}
      <div class="cc-meta">${esc(t("You can undo the sort afterwards."))}</div>`;
  } else if (c.kind === "pc_move" || c.kind === "pc_trash") {
    meta.push(((d.size || 0) / 1048576).toFixed(1) + " MB");
    const more = d.count > (d.files || []).length ? `\n… +${d.count - d.files.length}` : "";
    extra = `<div class="cc-lbl">${t("Files")}</div><pre class="cc-prev">${esc((d.files || []).join("\n"))}${more}</pre>
      ${d.reason ? `<div class="cc-meta">${esc(t("Reason: {r}", { r: d.reason }))}</div>` : ""}
      ${c.kind === "pc_trash" ? `<div class="cc-meta">${esc(t("They go to the Recycle Bin: you can restore them from there."))}</div>` : ""}`;
  } else if (c.kind.startsWith("app_")) {
    if (d.publisher) meta.push(t("Publisher: {p}", { p: d.publisher }));
    if (d.version) meta.push(t("Version {v}", { v: d.version }));
    meta.push(t("from {s}", { s: d.source || "" }));
    extra = `${d.description ? `<p class="cc-desc">${esc(d.description)}</p>` : ""}
      <div class="cc-lbl">${t("Command")}</div><pre class="cc-prev">${esc(d.command || "")}</pre>
      ${d.admin ? `<div class="cc-meta">${esc(t(d.source === "winget" ? "Windows may ask for administrator rights." : "The system will ask for your password."))}</div>` : ""}`;
  } else if (c.kind === "sys_startup") {
    extra = `<pre class="cc-prev">${esc(d.command || "")}</pre><div class="cc-meta">${esc(t("It can be turned back on the same way."))}</div>`;
  } else if (c.kind === "sys_theme" || c.kind === "sys_power") {
    if (d.was) meta.push(t("Now: {x}", { x: t(d.was) }));
  } else if (c.kind.startsWith("drive_")) {
    if (d.folder !== undefined) meta.push(d.folder ? t("Folder in Google Drive: {f}", { f: d.folder }) : t("Folder in Google Drive: My Drive"));
    if (c.kind === "drive_text") meta.push(d.doc ? t("as a Google Doc") : t("as a text file"));
    if (d.size != null) meta.push((d.size / 1048576).toFixed(1) + " MB");
  } else {
    if (d.folder) meta.push("📁 " + d.folder.split(/[\\/]/).filter(Boolean).pop());
    if (d.chars != null) meta.push(t("{n} characters", { n: d.chars.toLocaleString() }));
  }
  const prev = d.preview ? `<pre class="cc-prev">${esc(d.preview)}${(d.chars || 0) > 1500 ? "\n…" : ""}</pre>` : "";
  const el = h(`<div class="cc"><div class="cc-h">${cardIcon(c.kind)} <b>${esc(title)}</b></div>
    ${meta.length ? `<div class="cc-meta">${esc(meta.join(" · "))}</div>` : ""}${prev}${extra}
    <div class="cc-foot"><span class="cc-q">${t("Lanterna will do this only after you confirm.")}</span>
      <button class="btn ghost small" data-a="no">${t("Cancel")}</button><button class="btn primary small" data-a="yes">${t("Confirm")}</button></div></div>`);
  const foot = el.querySelector(".cc-foot");
  const done = r => {
    const link = (r.result || "").includes("|https://") ? r.result.split("|")[1] : "";
    const msg = r.state === "done" ? "✅ " + esc(r.text || t("Done"))
      : r.state === "cancelled" ? esc(t("Cancelled"))
      : r.state === "failed" ? `<span class="sync-err">⚠️ ${esc(t("Couldn't do it: {error}", { error: r.result }))}</span>`
      : esc(t("This card has expired. Ask again."));
    const inst = c.kind === "github_new_repo" && r.state === "done" && d.install
      ? `<button class="btn primary small" data-inst>${t("Add it to Lanterna")} ${icon("ext")}</button>` : "";
    foot.innerHTML = `<span class="cc-q">${msg.replace(/ — https:\/\/\S+$/, "")}</span>${link && c.kind !== "github_new_repo" ? `<button class="btn ghost small" data-open>${t(gh ? "Open on GitHub" : "Open in Google Drive")} ${icon("ext")}</button>` : ""}${inst}`;
    const o = foot.querySelector("[data-open]");
    if (o) o.onclick = () => api.open_url(link);
    const ins = foot.querySelector("[data-inst]");
    if (ins) ins.onclick = () => api.open_url(d.install);
    const undo = c.kind === "pc_sort" && r.state === "done" && d.undo;
    if (undo && !foot.querySelector("[data-undo]")) {
      const b = h(`<button class="btn ghost small" data-undo>${t("Undo")}</button>`);
      foot.appendChild(b);
      b.onclick = async () => { b.disabled = true; const u = await api.pc_undo(d.undo); b.replaceWith(h(`<span class="cc-q">${u.ok ? "↩ " : "⚠️ "}${esc(u.text)}</span>`)); };
    }
  };
  if (c.state !== "pending") done(c);
  el.querySelectorAll("[data-a]").forEach(b => b.onclick = async () => {
    el.querySelectorAll("[data-a]").forEach(x => x.disabled = true);
    if (b.dataset.a === "yes") foot.querySelector(".cc-q").innerHTML = `<span class="spinner"></span>${t(c.kind.startsWith("app_") ? "Installing… this can take a few minutes." : "Working…")}`;
    done(await (b.dataset.a === "yes" ? api.action_confirm(c.id) : api.action_cancel(c.id)));
  });
  return el;
}

// ---------------------------------------------------------------- working folder
async function workdirPanel(box) {
  if (!box || !box.isConnected) return;
  const w = await api.workdir();
  const errs = { not_found: t("There is no such folder."), too_broad: t("Choose a smaller folder: not a whole disk, your whole home folder or a system folder.") };
  box.innerHTML = `<p class="muted sync-p">${t("Lanterna can look at the files in one folder you choose, and create or change files there after you confirm each change. It never deletes anything and sees nothing outside this folder.")}
      ${t("The files it opens are sent to the model in use (to the online service in Cloud mode).")}
      ${t("New chats start with this folder; each chat can change it under the message box.")}</p>
    ${w.path ? `<div class="row"><div class="grow"><b>📁 ${esc(w.name || w.path)}</b><small>${esc(w.path)}${w.missing ? " · " + t("not found") : ""}</small></div>
      <button class="btn ghost small" id="wd-off">${t("Stop using it")}</button><button class="btn ghost small" id="wd-pick">${t("Change")}</button></div>`
      : `<button class="btn primary small" id="wd-pick">${t("Choose a folder")}</button>`}
    <div class="keyrow" id="wd-row" style="display:none"><div class="wrap"><input class="field" id="wd-path" placeholder="${t("Folder path")}"></div><button class="btn ghost" id="wd-save" style="height:48px">${t("Save")}</button></div>
    <p class="sync-err" id="wd-err"></p>`;
  const show = r => { if (r.ok) workdirPanel(box); else if (r.error !== "cancelled") $("#wd-err", box).textContent = errs[r.error] || r.error; };
  $("#wd-pick", box).onclick = async () => {
    const r = await api.pick_folder();
    if (r.error === "no_dialog") { $("#wd-row", box).style.display = ""; $("#wd-path", box).focus(); return; }
    show(r);
  };
  $("#wd-save", box).onclick = async () => show(await api.set_workdir($("#wd-path", box).value));
  const off = $("#wd-off", box);
  if (off) off.onclick = async () => show(await api.set_workdir(""));
}

// ---------------------------------------------------------------- connectors
async function connectorsPanel(box) {
  if (!box || !box.isConnected) return;
  box.innerHTML = `<div id="cn-drive"></div><div id="cn-gh"></div>`;
  drivePanel($("#cn-drive", box));
  githubPanel($("#cn-gh", box));
}

async function githubPanel(box) {
  if (!box || !box.isConnected) return;
  const st = await api.github_status();
  const again = ms => setTimeout(() => githubPanel(box), ms);
  const errs = { signed_out: t("GitHub was disconnected. Connect it again."), expired: t("The code expired. Press Connect again."),
    not_configured: t("The GitHub connector isn't set up in this version yet.") };
  const err = st.error ? `<p class="sync-err">${esc(errs[st.error] || st.error)}</p>` : "";
  const ready = st.phase === "ready";
  box.innerHTML = `<div class="row"><div class="grow"><b>🐙 GitHub</b><small class="plain">${ready ? esc(t("Connected as @{account}", { account: st.account || "?" }))
      : !st.configured ? t("The GitHub connector isn't set up in this version yet.")
      : t("Lets the assistant push files from the chat's folder to the repositories you choose, after you confirm each push. It can't delete repositories or change their settings.")}</small></div>
    ${ready ? `<button class="btn ghost small" id="gh-repos">${t("Choose repositories")} ${icon("ext")}</button><button class="btn ghost small" id="gh-off">${t("Disconnect")}</button>`
      : st.phase === "waiting" ? `<button class="btn ghost small" id="gh-cancel">${t("Cancel")}</button>`
      : st.configured ? `<button class="btn primary small" id="gh-on">${t("Connect")}</button>` : ""}</div>
    ${st.phase === "waiting" ? `<div class="gh-code"><span class="muted">${t("Type this code on GitHub:")}</span><b>${esc(st.code)}</b>
      <button class="btn ghost small" id="gh-copy">${t("Copy code")}</button><button class="btn primary small" id="gh-open">${t("Open GitHub")} ${icon("ext")}</button>
      <small class="muted"><span class="spinner"></span>${t("Waiting for GitHub…")}</small></div>` : ""}
    ${ready ? `<p class="faint" style="font-size:12.5px;margin:10px 0 0">${t("Every commit shows Lanterna Assistant next to you as a co-author. That is only a name on the commit, not access.")}</p>
      <p class="faint" style="font-size:12.5px;margin:6px 0 0">${t("Disconnect forgets the sign-in on this computer. To remove the access on GitHub too: GitHub → Settings → Applications.")}</p>` : ""}
    ${err}`;
  const on = $("#gh-on", box), off = $("#gh-off", box), cancel = $("#gh-cancel", box), cp = $("#gh-copy", box),
    op = $("#gh-open", box), repos = $("#gh-repos", box);
  if (on) on.onclick = async () => { const r = await api.github_connect(); if (r.code) copyText(r.code); githubPanel(box); };
  if (off) off.onclick = async () => { await api.github_disconnect(); githubPanel(box); };
  if (cancel) cancel.onclick = async () => { await api.github_cancel(); githubPanel(box); };
  if (cp) cp.onclick = async () => { await copyText(st.code); cp.textContent = t("Copied"); };
  if (op) op.onclick = () => api.open_url(st.url);
  if (repos) repos.onclick = () => api.open_url(st.install_url);
  if (st.phase === "waiting") again(2000);
}

async function drivePanel(box) {
  if (!box || !box.isConnected) return;
  const st = await api.drive_status();
  const again = ms => setTimeout(() => drivePanel(box), ms);
  const err = st.error ? `<p class="sync-err">${esc(st.error === "signed_out" ? t("Google Drive was disconnected. Connect it again.") : st.error)}</p>` : "";
  const head = `<div class="row"><div class="grow"><b>☁️ Google Drive</b><small class="plain">${st.phase === "ready" ? esc(st.account ? t("Connected as {account}", { account: st.account }) : t("Connected"))
    : t("Lets the assistant create folders and save files in your Google Drive, after you confirm each one. It sees only what it created itself.")}</small></div>
    ${st.phase === "ready" ? `<button class="btn ghost small" id="gd-off">${t("Disconnect")}</button>`
      : st.phase === "waiting" ? `<button class="btn ghost small" id="gd-cancel">${t("Cancel")}</button>`
      : `<button class="btn primary small" id="gd-on">${t("Connect")}</button>`}</div>`;
  const wait = st.phase === "waiting" ? `<p class="muted sync-p"><span class="spinner"></span>${t("Finish signing in in your browser…")}
      ${st.url ? `<button class="btn ghost small" id="gd-copy">${t("Copy link")}</button>` : ""}</p>` : "";
  box.innerHTML = head + wait + err;
  const on = $("#gd-on", box), off = $("#gd-off", box), cancel = $("#gd-cancel", box), cp = $("#gd-copy", box);
  if (on) on.onclick = async () => { await api.drive_connect(); drivePanel(box); };
  if (off) off.onclick = async () => { await api.drive_disconnect(); drivePanel(box); };
  if (cancel) cancel.onclick = async () => { await api.drive_cancel(); again(600); };
  if (cp) cp.onclick = async () => { await copyText(st.url); cp.textContent = t("Copied"); };
  if (st.phase === "waiting") again(1000);
}

// ---------------------------------------------------------------- limits
function fmtSecs(s) {
  if (s == null) return "";
  if (s < 90) return t("{n} s", { n: Math.max(1, Math.round(s)) });
  if (s < 5400) return t("{n} min", { n: Math.round(s / 60) });
  return t("{n} h", { n: Math.round(s / 3600) });
}

async function limitsPanel(box) {
  if (!box || !box.isConnected) return;
  const rows = await api.limits();
  if (!rows.length) { box.innerHTML = `<p class="faint" style="margin:4px 0;font-size:13.5px">${t("No requests to online models yet today.")}</p>`; return; }
  const LBL = {
    "requests:day": "Requests left today", "requests:minute": "Requests left this minute", "requests:hour": "Requests left this hour",
    "requests:month": "Requests left this month", "requests:": "Requests left",
    "tokens:day": "Tokens left today", "tokens:minute": "Tokens left this minute", "tokens:hour": "Tokens left this hour",
    "tokens:month": "Tokens left this month", "tokens:": "Tokens left" };
  box.innerHTML = `<div class="limits">${rows.map(r => {
    const parts = [];
    if (r.limit) parts.push(`<b>${t("{left} of {limit} left today", { left: r.resting ? 0 : Math.max(0, r.limit - r.used), limit: r.limit })}</b>`);
    r.left.forEach(x => parts.push(`${t(LBL[x.kind + ":" + x.period] || "Requests left")}: <b>${x.remaining.toLocaleString()}</b>${x.limit ? " / " + x.limit.toLocaleString() : ""}${x.reset_in != null ? ` <span class="faint">· ${t("full again in {t}", { t: fmtSecs(x.reset_in) })}</span>` : ""}`));
    if (!r.limit && !r.left.length && !r.resting) parts.push(`<span class="faint">${t("The service doesn't say how much is left; it is shown when the limit is reached.")}</span>`);
    if (r.resting) parts.unshift(`<span class="amber-t">${t("resting, back in {t}", { t: fmtSecs(r.resting) })}</span>`);
    return `<div class="limrow"><div class="nm"><small>${esc(r.service)}</small>${esc(r.model)}</div>
      <div class="lnum">${t("Requests today: {n}", { n: r.used })}${r.refused ? ` · <span class="amber-t">${t("Refused: {n}", { n: r.refused })}</span>` : ""}</div>
      <div class="ldet">${parts.join("<br>")}</div></div>`;
  }).join("")}</div>`;
}

// ---------------------------------------------------------------- Google sign-in & sync
async function syncPanel(box, onReady) {
  if (!box.isConnected) return;
  const st = await api.sync_status();
  if (onReady && st.phase === "ready" && st.last) return onReady();
  const errText = { password: t("Wrong password."), short: t("At least 8 characters."),
    changed: t("The sync password was changed on another device. Enter the new one."),
    signed_out: t("You were signed out. Sign in again to keep syncing."),
    scope: t("Google didn't give Lanterna the permission it needs. Sign in again and leave the box for Lanterna's own folder ticked.") };
  const err = st.error ? `<p class="sync-err">${esc(errText[st.error] || t("Couldn't sync: {error}", { error: st.error }))}</p>` : "";
  const again = ms => setTimeout(() => syncPanel(box, onReady), ms);
  if (st.phase === "off") {
    box.innerHTML = `<p class="muted sync-p">${onReady ? "" : t("Sign in with Google to see your chats on all your devices.")}
      ${t("Lanterna uses only a hidden folder of its own in your Google Drive. Your chats, settings and API keys there are encrypted with a password only you know.")}</p>
      ${err}<button class="btn primary${onReady ? "" : " small"}" id="sync-in">${t("Sign in with Google")}</button>`;
    $("#sync-in", box).onclick = async () => { await api.sync_sign_in(); syncPanel(box, onReady); };
  } else if (st.phase === "waiting") {
    box.innerHTML = `<div class="status"><span class="spinner"></span>${t("Finish signing in in your browser…")}
      <button class="btn ghost small" id="sync-x" style="margin-left:auto">${t("Cancel")}</button></div>`;
    if (st.url) {
      box.insertAdjacentHTML("beforeend", `<p class="muted sync-p">${t("Opened in the wrong browser? Copy the link and open it in the browser you use for Google.")}
        <button class="btn ghost small" id="sync-link">${t("Copy link")}</button></p>`);
      $("#sync-link", box).onclick = async e => { if (await copyText(st.url)) e.target.textContent = t("Copied"); };
    }
    $("#sync-x", box).onclick = async () => { await api.sync_cancel(); again(700); };
    if (!box.dataset.waiting) { box.dataset.waiting = "1"; (function wait() { api.sync_status().then(s2 => { if (s2.phase === "waiting") setTimeout(wait, 1000); else { delete box.dataset.waiting; syncPanel(box, onReady); } }); })(); }
  } else if (st.phase === "password") {
    const intro = st.cloud ? t("Enter the sync password you chose on your other device.")
      : `${t("Choose a sync password (at least 8 characters). You will need it on your other devices.")} ${t("If you forget it, the chats on your devices stay, but the copy in Google Drive can't be opened.")}`;
    box.innerHTML = `${st.account ? `<p class="sync-who">${t("Signed in as {account}", { account: esc(st.account) })}</p>` : ""}
      <p class="muted sync-p">${intro}</p>${err}
      <div class="keyrow"><div class="wrap"><input class="field" type="password" id="sync-pw" autocomplete="new-password" placeholder="${t("Sync password")}"></div>
      <button class="btn primary" id="sync-ok" style="height:48px">${t("Continue")}</button></div>
      <button class="btn ghost small" id="sync-out">${t("Sign out")}</button>`;
    const go = async () => {
      const b = $("#sync-ok", box); b.disabled = true; b.innerHTML = `<span class="spinner"></span>`;
      await api.sync_password($("#sync-pw", box).value);
      syncPanel(box, onReady); if (!onReady) refreshThreads();
    };
    $("#sync-ok", box).onclick = go;
    $("#sync-pw", box).onkeydown = e => { if (e.key === "Enter") go(); };
    $("#sync-out", box).onclick = async () => { await api.sync_sign_out(false); syncPanel(box, onReady); };
    $("#sync-pw", box).focus();
  } else {
    const when = st.last ? new Date(st.last * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
    box.innerHTML = `<p class="sync-who">${st.account ? t("Signed in as {account}", { account: esc(st.account) }) : t("Signed in with Google")}</p>
      <p class="muted sync-p">${st.phase === "syncing" ? `<span class="spinner"></span>${t("Syncing…")}` : when ? t("Last synced at {time}", { time: when }) : ""}</p>${err}
      <div class="sync-actions"><button class="btn ghost small" id="sync-now">${icon("refresh")} ${t("Sync now")}</button>
      <button class="btn ghost small" id="sync-out">${t("Sign out")}</button>
      <button class="btn ghost small danger" id="sync-del">${t("Sign out and delete the copy in Google Drive")}</button></div>`;
    $("#sync-now", box).onclick = async () => { box.querySelector(".sync-p").innerHTML = `<span class="spinner"></span>${t("Syncing…")}`; await api.sync_now(); syncPanel(box); refreshThreads(); };
    $("#sync-out", box).onclick = async () => { await api.sync_sign_out(false); syncPanel(box); };
    $("#sync-del", box).onclick = async () => { if (confirm(t("Delete the encrypted copy of your chats from Google Drive? Chats on this device stay."))) { await api.sync_sign_out(true); syncPanel(box); } };
    if (st.phase === "syncing") again(1000);
  }
}

let syncSeen = null;
async function watchSync() {                      // a sync brought chats from another device: show them
  try {
    const st = await api.sync_status();
    if (syncSeen !== null && st.last && st.last !== syncSeen && !busy) {
      await refreshThreads();
      if (thread && !$("#input").value) {
        const items = await api.messages(thread);
        if (items.length !== $("#msgs").querySelectorAll(".msg").length) openThread(thread);
      }
    }
    syncSeen = st.last || 0;
  } catch (e) { /* app closing */ }
  setTimeout(watchSync, 10000);
}

// ---------------------------------------------------------------- bug report
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; }
  catch (e) {                                            // older webviews: copy through a hidden field
    const ta = h(`<textarea style="position:fixed;opacity:0"></textarea>`);
    ta.value = text; document.body.append(ta); ta.select();
    const ok = document.execCommand("copy"); ta.remove(); return ok;
  }
}

function openBugReport() {
  const v = dialog(t("Report a bug"), `<section class="bug">
    <p class="muted" style="margin:0 0 12px">${t("Tell what went wrong. You see the whole text first, and you send it yourself.")}</p>
    <textarea class="field bug-text" id="bug-text" maxlength="4000" placeholder="${t("What did you do, what happened, and what did you expect?")}"></textarea>
    <label class="check"><input type="checkbox" id="bug-info" checked>
      <span><b>${t("Add app and system info")}</b><small>${t("Version, system, mode and the last errors. Never chats, keys or your name.")}</small></span></label>
    <h4 style="margin-top:16px">${t("This is exactly what will be sent:")}</h4>
    <pre class="bug-preview" id="bug-preview"></pre>
    <p class="bug-note" id="bug-note"></p>
    <div class="upd-actions">
      <button class="btn ghost" id="bug-copy">${t("Copy text")}</button>
      <button class="btn ghost" id="bug-gh">${t("Open on GitHub")} ${icon("ext")}</button>
      <span style="flex:1"></span>
      <button class="btn primary" id="bug-mail" hidden>${t("Write e-mail")}</button>
    </div></section>`);
  const text = $("#bug-text", v), info = $("#bug-info", v), note = $("#bug-note", v);
  let r = null, seq = 0;
  const say = (msg, warn) => { note.textContent = msg; note.classList.toggle("warn", !!warn); };
  const hint = () => r && r.email ? t("No mail app? Copy the text and send it to {email} from any mail.", { email: r.email })
    : t("Reports by e-mail are coming soon. For now open it on GitHub (free account) or copy the text.");
  const refresh = async () => {
    const n = ++seq, res = await api.bug_report(text.value, info.checked);
    if (n !== seq) return;                               // an older answer arrived late
    r = res;
    $("#bug-preview", v).textContent = r.body || "…";
    $("#bug-mail", v).hidden = !r.email;
    say(hint());
  };
  let timer = 0;
  text.oninput = () => { clearTimeout(timer); timer = setTimeout(refresh, 250); };
  info.onchange = refresh;
  const need = async () => { await refresh(); if (r && r.ok) return true; say(t("Write a few words first."), true); text.focus(); return false; };
  $("#bug-copy", v).onclick = async e => { if (await need() && await copyText(r.body)) e.target.textContent = t("Copied"); };
  $("#bug-gh", v).onclick = async () => { if (await need()) api.open_url(r.issue); };
  $("#bug-mail", v).onclick = async () => {
    if (!(await need())) return;
    if (r.cut) { await copyText(r.body); say(t("The text is long, so the letter is shortened. The full text is copied: paste it into the letter."), true); }
    else say(t("Your mail app opens with the letter ready. Check it and press Send.") + " " + hint());
    api.open_mail(r.mailto);
  };
  refresh();
  setTimeout(() => text.focus(), 50);
  return v;
}

let updateAsked = false;
function checkUpdateOnStart() {
  if (updateAsked) return;
  updateAsked = true;
  setTimeout(() => api.update_notice().then(u => {
    if (u && u.newer && !document.querySelector(".veil")) showUpdate(u);
  }).catch(() => {}), 1500);
}

// pywebview injects its API a moment after load; dev mode (token) can start right away
if (TOKEN) boot();
else if (window.pywebview && window.pywebview.api) boot();
else window.addEventListener("pywebviewready", boot);
