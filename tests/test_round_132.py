"""Round 132 (1.1.8b2): private data is asked about before it goes online.

- A card number (Luhn-checked), an IBAN (its check digits), a password, a PIN or CVV, or a key or token in a message
  for an online model: Lanterna says what it found and where the message goes, and offers to put •••• in its place.
  Cancel keeps the message in the box. Only what the user typed is looked at, on this computer.
- Nothing is asked in local mode (it stays on this computer) or when the warning is off (Settings → General).
"""
import asyncio
import re
from pathlib import Path

import pytest

from lanterna import gui, sync
from lanterna.config import Settings
from lanterna.sensitive import find, mask

UI = Path(gui.__file__).parent / "ui"
# test keys are put together here, so this file itself doesn't look like it holds a key
GSK = "gsk_" + "a1B2" * 13
SK = "sk-proj-" + "Zx9" * 14
PEM = "-----BEGIN OPENSSH " + "PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH " + "PRIVATE KEY-----"
JWT = "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" + "." + "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
BOT = "1234567890:AA" + "h" * 33


# ---------------------------------------------------------------- what counts
@pytest.mark.parametrize("text, kind, hint", [
    ("Моя картка 4111 1111 1111 1111, термін 12/27", "card", "•••• 1111"),
    ("card 4242424242424242 please", "card", "•••• 4242"),
    ("Amex 3782 822463 10005", "card", "•••• 0005"),
    ("MC 5555-5555-5555-4444.", "card", "•••• 4444"),
    ("Рахунок UA21 3223 1300 0002 6007 2335 6600 1 для оплати", "iban", "UA21 … 6001"),
    ("IBAN: UA213223130000026007233566001", "iban", "UA21 … 6001"),
    ("Konto DE89 3704 0044 0532 0130 00", "iban", "DE89 … 3000"),
    ("Przelew na PL61 1090 1014 0000 0712 1981 2874", "iban", "PL61 … 2874"),
    ("gb82 west 1234 5698 7654 32", "iban", "GB82 … 5432"),
    ("мій ключ " + GSK, "key", "gsk_…"),
    ("export OPENAI_API_KEY=" + SK, "key", "sk-p…"),
    ('api_key = "abcd1234efgh5678ijkl"', "key", "abc…"),
    (PEM + "\nдякую", "key", "-----BEGIN…"),
    ("Authorization: Bearer " + JWT, "key", "eyJh…"),
    ("бот " + BOT, "key", "…"),
    ("PIN 1234", "pin", ""),
    ("Пін-код картки 4821", "pin", ""),
    ("CVV: 123", "pin", ""),
    ("мій пароль від пошти: Kotik2024", "password", ""),
    ("password=hunter22", "password", ""),
    ("the password is hunter22", "password", ""),
    ("пароль — це Kotik2024", "password", ""),
    ("пароль від wifi — Kotik2024", "password", ""),
    ("мій пароль Kotik2024", "password", ""),
])
def test_private_data_is_found(text, kind, hint):
    finds = find(text)
    assert [(f.kind, f.hint) for f in finds] == [(kind, hint)]


@pytest.mark.parametrize("text", [
    "Номер замовлення 4000123412341235",                 # does not pass the Luhn check
    "Телефон +380 67 123 45 67, у 2024 році, ISBN 978-3-16-148410-0",
    "Рахунок 26007233566001, МФО 322313",               # an old account number, not an IBAN
    "UA21 3223 1300 0002 6007 2335 6600 2",            # wrong check digits
    "Ціна 1234567890123.45 грн",
    "Пароль: забув.", "Як змінити пароль?", "Пароль - це важливо",
    "Password reset link: https://example.com/reset",
    'password = os.environ["DB_PASS"]', "password: ${DB_PASS}", "password: ****", "passwd: password updated successfully",
    "pin the chat to the top", "Скільки цифр у CVV?",
    "Мені 4 роки 2 місяці, а братові 1234 дні",
])
def test_ordinary_text_is_not_private(text):
    assert find(text) == []


def test_hidden_text_keeps_the_question_and_never_shows_the_secret():
    text = ("Моя картка 4111 1111 1111 1111, а пароль від банку: Kotik2024. IBAN UA213223130000026007233566001, "
            "ключ " + GSK + ". Чи безпечно так зберігати?")
    finds = find(text)
    assert [f.kind for f in finds] == ["card", "password", "iban", "key"]
    assert mask(text, finds) == ("Моя картка •••• 1111, а пароль від банку: ••••. IBAN UA21 •••• 6001, "
                                 "ключ gsk_••••. Чи безпечно так зберігати?")
    for f in finds:                                     # what the warning shows is never the whole thing
        assert len(f.hint.replace("•", "").replace("…", "").replace(" ", "")) <= 8
        assert "Kotik" not in f.hint and GSK[4:] not in f.hint
    assert mask(PEM + "\nдякую", find(PEM + "\nдякую")) == "[private key ••••]\nдякую"
    assert "4111 1111 1111 1111 3 рази".replace("4111 1111 1111 1111", "•••• 1111") == mask(
        "4111 1111 1111 1111 3 рази", find("4111 1111 1111 1111 3 рази"))    # a number after it is not the card


# ---------------------------------------------------------------- the app
from test_tui import api, chat_ready, wait_for  # noqa: E402,F401  (the fake model and vault)


def test_the_app_says_what_it_found_and_where_it_goes(api):  # noqa: F811
    assert "check_private" in gui.METHODS
    assert Settings().warn_private is True and "warn_private" in api._BOOLS and "warn_private" in sync.PREFS
    w = api.check_private("Моя картка 4111 1111 1111 1111, чи вона дійсна?")
    assert w == {"found": [{"kind": "card", "what": "Card number", "hint": "•••• 1111"}],
                 "masked": "Моя картка •••• 1111, чи вона дійсна?", "service": "Groq", "maybe": False}
    api.save_settings({"lang": "uk"})
    assert api.check_private("пароль: Kotik2024")["found"][0]["what"] == "Пароль"
    assert api.check_private("Яка погода у Львові?") == {"found": []}
    api.save_settings({"mode": "auto"})                   # local first, the cloud as a backup: it may go online
    assert api.check_private("PIN 1234")["maybe"] is True
    api.save_settings({"mode": "local"})                  # it stays on this computer
    assert api.check_private("PIN 1234") == {"found": []}
    api.save_settings({"mode": "cloud", "warn_private": False})
    assert api.store and api.check_private("PIN 1234") == {"found": []}


def test_nothing_is_asked_when_only_local_models_answer(api, monkeypatch):  # noqa: F811
    from lanterna.discovery import Candidate
    from lanterna.router import Router
    api.save_settings({"mode": "auto"})
    monkeypatch.setattr(api, "_get_router", lambda refresh=False: Router([Candidate("ollama", "qwen3", 40)]))
    assert api.check_private("PIN 1234") == {"found": []}


# ---------------------------------------------------------------- the window
def _fn(js: str, start: str) -> str:
    i = js.index(start)
    return js[i:js.index("\n}\n", i) + 2]


def test_the_window_asks_before_a_new_message_goes():
    js = (UI / "app.js").read_text(encoding="utf-8")
    send = _fn(js, "async function send(")
    check = send.index("api.check_private(text)")
    assert send.index("if (!retry && text) {") < check < send.index("setBusy(true)")    # before anything is shown
    assert 'if (pick === "hide") text = w.masked;' in send and "inp.focus(); return;" in send
    assert "|| busy || privateOpen) return;" in send                                       # Enter twice: one question
    dlg = _fn(js, "function privateDialog(")
    for part in ('id="pv-no"', 'id="pv-send"', 'id="pv-hide"', 'aria-describedby", "pv-say"', '$("#pv-hide", v).focus()',
                 "w.maybe ?", "f.hint ?"):
        assert part in dlg, part
    assert 'id="warn-private"' in js and "save_settings({ warn_private: wp.checked })" in js


# ---------------------------------------------------------------- the terminal
pytest.importorskip("textual")
from textual.widgets import Input  # noqa: E402

from lanterna.tui import ChoiceScreen, LanternaApp  # noqa: E402


def test_the_terminal_asks_and_can_hide_it(api):  # noqa: F811
    api.save_settings({"onboarded": True, "name": "Bo", "lang": "en", "provider": "groq"})

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(120, 40)) as pilot:
            assert await wait_for(pilot, lambda: chat_ready(app))
            scr = app.screen
            box = scr.query_one("#composer", Input)
            box.value = "password: hunter22"
            await pilot.press("enter")
            assert await wait_for(pilot, lambda: isinstance(app.screen, ChoiceScreen))
            assert "Card" not in app.screen.text and "Password" in app.screen.text and "Groq" in app.screen.text
            await pilot.press("escape")                    # Cancel: nothing goes, the message stays to be changed
            assert await wait_for(pilot, lambda: app.screen is scr)
            assert box.value == "password: hunter22" and scr.tid is None
            box.value = "My card 4111 1111 1111 1111, is it safe?"
            await pilot.press("enter")
            assert await wait_for(pilot, lambda: isinstance(app.screen, ChoiceScreen))
            await pilot.press("enter")                     # the first choice: Hide and send
            assert await wait_for(pilot, lambda: scr.tid is not None and scr._stream is None)
            assert api.store.messages(scr.tid)[0]["content"] == "My card •••• 1111, is it safe?"
            assert box.value == ""
    asyncio.run(go())


def test_new_strings_are_translated_everywhere():
    from lanterna import i18n
    for s in ("Card number", "IBAN", "Key or token", "PIN or CVV code", "Password", "Send this to an online model?",
              "This message seems to have private data, and it goes to {service}, outside this computer:",
              "This message seems to have private data, and it may go to {service}, outside this computer:",
              "Lanterna can send •••• in their place: the model can still help without them.", "Hide and send",
              "Send as it is", "Warn before private data goes online",
              "A card number, IBAN, password, PIN or key in your message: Lanterna asks first and can hide it. The check runs on this computer."):
        assert set(i18n._T[s]) == {"uk", "it"}, s
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(s), (lang, s)
        assert re.search(r"\{service\}", s) is None or all("{service}" in i18n.t(s, x) for x in ("uk", "it", "de"))
