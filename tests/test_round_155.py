"""Round 155 (1.1.11b9): the model's own notes only in the user's language.

Gemini thinks in English even in a Ukrainian chat: its headings («Clarifying Extension Loading») went into the
Steps list under the answer, and the line under a reply being written showed them too. Now a heading or a line of
the model's own thinking shows only when it is in the app's language; otherwise that line says «Думаю…» (the
window's "Thinking…"), and the list keeps Lanterna's own steps. The model's "why" for a tool follows the same rule,
now also in Italian, German, Spanish, French and Polish windows (there an English line has no Cyrillic to tell it).
"""
from pathlib import Path

from lanterna import thinking
from lanterna.thinking import Steps, fits_lang, looks_english, tool_step

JS = (Path(thinking.__file__).parent / "ui" / "app.js").read_text(encoding="utf-8")


def test_the_heading_from_the_check_of_b8_is_no_step_in_a_ukrainian_chat():
    s = Steps("uk")
    s.tool("lanterna_help", '{"topic": "chrome"}')
    s.thought("**Clarifying Extension Loading**\n\nI need to explain how to load the unpacked extension.\n")
    assert s.view() == {"steps": [{"kind": "tool", "text": "Дивлюся довідку Lanterna"}], "live": ""}
    assert 'p.live || t("Thinking…")' in JS and '"Thinking…": { uk: "Думаю…"' in JS   # "" = «Думаю…» in the window


def test_headings_in_the_users_language_still_are_steps():
    s = Steps("uk")
    s.thought("**Аналізую запит**\n\nКористувач питає про розширення.\n**Formulating the Answer**\n")
    assert [x["text"] for x in s.items] == ["Аналізую запит"] and s.live == ""
    s.thought("**Складаю відповідь**\n")
    assert [x["text"] for x in s.items] == ["Аналізую запит", "Складаю відповідь"] and s.live == "Складаю відповідь"


def test_raw_thinking_shows_only_lines_in_the_users_language():
    s = Steps("uk")
    s.tool("web_search", '{"query": "Lanterna"}')
    s.thought("The user wants to install the extension.\n")
    assert s.live == "" and len(s.items) == 1                    # not the finished search, and not English
    s.thought("Користувач хоче встановити розширення.\n")
    assert s.live == "Користувач хоче встановити розширення."
    s.thought("")                                                # nothing new: the line stays
    assert s.live == "Користувач хоче встановити розширення."


def test_latin_languages_lose_english_and_keep_their_own():
    english = ["Clarifying Extension Loading", "Understanding the User's Intent", "Extension Installation Steps",
               "Formulating the response", "Plan for the answer"]
    own = {"it": ["Analisi della richiesta", "Riepilogo", "Pianificazione della risposta"],
           "de": ["Überprüfung der Anfrage", "Erweiterung installieren"],
           "es": ["Análisis de la solicitud"], "fr": ["Analyse de la demande"],
           "pl": ["Analiza prośby użytkownika", "To jest plan"]}
    for lang, lines in own.items():
        s = Steps(lang)
        s.thought("".join(f"**{x}**\n" for x in english + lines))
        assert [x["text"] for x in s.items] == lines, lang
    assert all(looks_english(x) for x in english)
    assert not any(looks_english(x) for lines in own.values() for x in lines)


def test_an_english_window_keeps_english_and_drops_cyrillic():
    s = Steps("en")
    s.thought("**Clarifying Extension Loading**\n**Аналізую запит**\n")
    assert [x["text"] for x in s.items] == ["Clarifying Extension Loading"] and s.live == ""
    assert fits_lang("Clarifying Extension Loading", "en") and not fits_lang("Clarifying Extension Loading", "uk")


def test_the_models_why_follows_the_same_rule():
    en_why = '{"query": "Ferrara", "intent": "to find the opening hours"}'
    it_why = '{"query": "Ferrara", "intent": "per trovare gli orari"}'
    assert tool_step("web_search", en_why, "it") == "Cerco sul web: Ferrara"           # English: left out
    assert tool_step("web_search", it_why, "it") == "Cerco sul web: Ferrara — per trovare gli orari"
    assert tool_step("web_search", en_why, "en").endswith("— to find the opening hours")
