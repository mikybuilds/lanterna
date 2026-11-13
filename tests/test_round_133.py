"""Round 133 (1.1.8b3): «Is this a scam?» for a message, a letter or a link, without opening the link.

- scam_check (a model tool, on this computer) finds fake bank, delivery and shop addresses (a brand's name on
  someone else's site), look-alike letters, an "@" trick, a bare IP, short links, cheap endings, bait words, no https,
  and the words of a scam (card data or codes, a hurry or a block, a prize or payout, a delivery fee, a move to a
  messenger, "it's me from a new number"). It opens no link: opening one can tell the senders the number is alive.
- read_page refuses a link with strong signs, so the model doesn't open it by accident either, and "What went to the
  model" doesn't say a page was opened.
- The empty chat has a «🛡 Is this a scam?» button (the terminal too): the question goes in the box, the message is
  pasted after it.
"""
import asyncio
import json
from pathlib import Path

import pytest

from lanterna import gui, scam, sent, tools
from lanterna.thinking import tool_step

UI = Path(gui.__file__).parent / "ui"


# ---------------------------------------------------------------- addresses
@pytest.mark.parametrize("text, host, sign", [
    ("Терміново підтвердіть дані: https://privatbank-ua.secure-login.top/verify", "privatbank-ua.secure-login.top",
     "it looks like PrivatBank but the site is secure-login.top"),
    ("Перейдіть на privat-bonus.top, щоб отримати виплату", "privat-bonus.top", "PrivatBank"),
    ("Оплатіть доставку: http://novaposhta.delivery-pay.xyz/p/8812", "novaposhta.delivery-pay.xyz", "no https"),
    ("olx.ua.dostavka-olx.com/pay?id=4412", "olx.ua.dostavka-olx.com", "it looks like OLX but the site is dostavka-olx.com"),
    ("Ви виграли! www.apple-prize.click", "www.apple-prize.click", "Apple"),
    ("https://telegram-premium.top/free", "telegram-premium.top", "a cheap .top address"),
    ("https://privatbank.ua@203.0.113.7/login", "203.0.113.7", "only for show"),
    ("https://xn--privtbank-3yh.ua/", "xn--privtbank-3yh.ua", "two alphabets"),
    ("https://мonobank.ua/", "мonobank.ua", "two alphabets"),
])
def test_a_fake_address_is_found_and_never_opened(text, host, sign):
    [link] = scam.links(text)
    assert link.host == host and link.strong
    assert any(sign in s for s in link.signs), link.signs
    assert scam.refuse(link.url).startswith("Not opened: this link looks like a scam")


@pytest.mark.parametrize("text, sign", [
    ("Ваша посилка чекає: bit.ly/3xYz12", "a short link"),
    ("https://асе.com/", "other letters than it seems"),
    ("https://a.b.c.d.example.com/", "many parts"),
])
def test_a_weaker_sign_is_said_but_the_page_may_open(text, sign):
    [link] = scam.links(text)
    assert not link.strong and any(sign in s for s in link.signs) and scam.refuse(link.url) == ""


@pytest.mark.parametrize("url", [
    "https://www.privat24.ua/", "https://novaposhta.ua/tracking/?cargo_number=20450000000000", "https://diia.gov.ua/services",
    "https://login.microsoftonline.com/common", "https://outlook.office.com/mail/", "steamcommunity.com/id/x",
    "rozetka.com.ua/ua/mobile-phones/c80003/", "https://сайт.укр/", "https://t.me/novaposhta_bot", "applebees.com/menu",
    "https://www.amazonaws.com/", "poster.com/x", "https://promotion.com/", "https://privateinternetaccess.com/",
])
def test_real_sites_and_ordinary_words_have_no_signs(url):
    [link] = scam.links(url)
    assert link.signs == [] and scam.refuse(url) == ""


def test_file_names_and_abbreviations_are_not_links():
    assert scam.links("README.md і app.py та photo.jpg, див. т.д. і т.п., версія 1.2.3, число 3.14") == []


# ---------------------------------------------------------------- the words and the report
@pytest.mark.parametrize("text, why", [
    ("Мам, це я з нового номера, скинь 2000 на картку", "from a new number"),
    ("Для отримання призу введіть CVV", "card data"),
    ("Ваша картка заблокована", "threatens a block"),
    ("Компенсація від ООН 6500 грн", "a prize or a payout"),
    ("Посилка затримана, оплатіть доставку 25 грн", "pay for a delivery"),
    ("Напишіть нам у Telegram, щоб отримати виплату", "messenger"),
    ("Hai vinto un premio!", "a prize"),
])
def test_the_words_of_a_scam_are_found(text, why):
    assert any(why in s for s in scam.text_signs(text))


def test_the_report_says_nothing_was_opened_and_how_sure_it_is():
    sms = "ПриватБанк: картка заблокована! Терміново підтвердіть дані: https://privatbank-ua.secure-login.top/verify"
    out = scam.report(sms)
    assert out.startswith("Checked on this computer; no link was opened")
    assert "Overall: likely a scam." in out and "call the bank, the service or the person" in out
    assert "Overall: some signs, be careful." in scam.report("Ваша посилка чекає: bit.ly/3xYz12")
    assert "Overall: no clear signs." in scam.report("Привіт, як справи? Завтра о 18:00 біля кіно")
    assert "No link and none of the usual scam signs" in scam.report("Привіт, як справи?")
    assert "no sign in the address itself (that alone doesn't make it safe" in scam.report("https://www.privat24.ua/")


# ---------------------------------------------------------------- the model's tools
def test_the_model_gets_the_check_and_cannot_open_a_fake_link(monkeypatch):
    opened = []
    monkeypatch.setattr(tools, "read_page", lambda url, **kw: opened.append(url) or "the page text")
    tb = tools.Toolbox(None)
    out = tb.run("read_page", json.dumps({"url": "https://privatbank-ua.secure-login.top/verify"}))
    assert out.startswith("Not opened: this link looks like a scam") and "scam_check" in out and opened == []
    assert tb.run("read_page", json.dumps({"url": "https://www.privat24.ua/"})) == "the page text"
    assert opened == ["https://www.privat24.ua/"]
    check = tb.run("scam_check", json.dumps({"text": "Ви виграли! www.apple-prize.click"}))
    assert "it looks like Apple" in check and "no link was opened" in check and len(opened) == 1
    names = lambda ctx: {s["function"]["name"] for s in tb.schemas(ctx)}            # noqa: E731
    for ask in ("Чи це не шахраї?", "Is this a scam?", "È una truffa?", "Czy to oszustwo?", "Глянь https://x.ua/a",
                "Ваша посилка: bit.ly/3xYz12", "Чи безпечно відкривати посилання?"):
        assert "scam_check" in names(ask), ask
    assert "scam_check" not in names("Яка погода завтра у Львові?")
    assert "scam_check" in tools.LOOKUP_TOOLS and "scam_check" in tools.READ_ONLY_TOOLS     # a second opinion may use it
    assert "opens no link" in {t.name: t for t in tb._make()}["scam_check"].description
    assert tool_step("scam_check", "{}", "uk") == "Шукаю ознаки шахрайства"


def test_what_went_to_the_model_doesnt_say_a_fake_page_was_opened():
    rows = sent.build("M", False, 0, False, 0, [], 0, [("read_page", json.dumps({"url": "https://privat-bonus.top/x"})),
                                                       ("read_page", json.dumps({"url": "https://www.privat24.ua/"})),
                                                       ("scam_check", json.dumps({"text": "x"}))])
    opened = [r["v"]["site"] for r in rows if r["t"] == "A web page was opened: {site}"]
    assert opened == ["www.privat24.ua"]


# ---------------------------------------------------------------- the window and the terminal
def test_the_empty_chat_offers_the_check_without_sending():
    js = (UI / "app.js").read_text(encoding="utf-8")
    i = js.index("function showEmpty()")
    empty = js[i:js.index("\n}\n", i)]
    assert 'data-fill="scam"' in empty and 't("Is this a scam? Check a message or a link")' in empty
    fill = empty[empty.index("if (b.dataset.fill) {"):]
    fill = fill[:fill.index("return;")]
    assert '$("#send").click()' not in fill and 'toast(t("Paste the message or the link' in fill


pytest.importorskip("textual")
from textual.widgets import Button, Input  # noqa: E402

from lanterna.tui import LanternaApp  # noqa: E402
from test_tui import api, chat_ready, wait_for  # noqa: E402,F401  (the fake model and vault)


def test_the_terminal_puts_the_question_in_the_box(api):  # noqa: F811
    api.save_settings({"onboarded": True, "name": "Bo", "lang": "uk", "provider": "groq"})

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(120, 40)) as pilot:
            assert await wait_for(pilot, lambda: chat_ready(app))
            scr = app.screen
            btn = scr.query_one("#ideascam", Button)
            assert "Чи це не шахраї?" in str(btn.label)
            btn.press()
            box = scr.query_one("#composer", Input)
            assert await wait_for(pilot, lambda: box.value == "Чи це не шахраї? ")
            await pilot.pause()
            assert scr.tid is None and scr._stream is None                 # nothing was sent
    asyncio.run(go())


def test_new_strings_are_translated_everywhere():
    from lanterna import i18n
    for s in ("Checking for signs of a scam", "Is this a scam? Check a message or a link", "Is this a scam? ",
              "Paste the message or the link after the question and send it. Lanterna doesn't open the link."):
        assert set(i18n._T[s]) == {"uk", "it"}, s
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(s), (lang, s)
