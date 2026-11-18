"""Round 148 (1.1.10b10): the word after a number takes the form the number needs, in every language.

"1 файл, 3 файли, 5 файлів", "1 plik, 3 pliki, 5 plików", "1 file, 2 files". A string with a count can have a
list of forms instead of one text: [one, other], and in uk and pl [one, few, many]. The n= (or count=) of t()
picks the form, by the same rules in i18n.plural and in the window's plural(). English keeps its forms in
i18n._EN (the key is the "other" form), and the window gets them with the rest of its strings. The stopgaps of
b9 ("Sort the files in Downloads (3)") are gone: the cards, their done lines, a restored backup and the other
counts read the way people write them.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from lanterna import app, chat, i18n, tui

SRC = Path(__file__).parents[1] / "src" / "lanterna"
JS = (SRC / "ui" / "app.js").read_text(encoding="utf-8")
PH = re.compile(r"\{(\w+)\}")
COUNTS = (0, 1, 2, 3, 4, 5, 11, 12, 14, 21, 22, 25, 101, 111, 112, 122)


def _part(start, end):
    i = JS.index(start)
    return JS[i:JS.index(end, i)]


STR_JS = _part("const STR = {", "\n};\n") + "\n};\n"
T_JS = _part('let LANG = "en";', "// words that stand as a line of their own")        # LANG, S, plural(), t()
RESTORED_JS = _part("const RESTORED = ", "\nasync function paintBackup(")


def _node(code, tmp_path):
    """Runs the window's own code in node; what it printed, read as JSON."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    run = tmp_path / "run.js"
    run.write_text(code, encoding="utf-8")
    r = subprocess.run([node, str(run)], capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _str(tmp_path):
    """The window's own table of words (uk and it)."""
    return _node(STR_JS + "process.stdout.write(JSON.stringify(STR));", tmp_path)


def _counted(table_str):
    """Every string that has forms in some language, the window's own ones included."""
    keys = set(i18n._EN) | {k for k, v in table_str.items() if any(isinstance(f, list) for f in v.values())}
    for lang in i18n.LANGS:
        keys |= {k for k, v in i18n.catalog(lang).items() if isinstance(v, list)}
    return sorted(keys)


# ---------------------------------------------------------------- the rules
# the form a number takes: 0 = one, then uk and pl: 1 = few, 2 = many; the others: 1 = the rest
RULES = {"uk": {0: 2, 1: 0, 2: 1, 4: 1, 5: 2, 11: 2, 12: 2, 14: 2, 21: 0, 22: 1, 25: 2, 101: 0, 111: 2, 112: 2,
                122: 1, 1001: 0, 1059: 2},
         "pl": {0: 2, 1: 0, 2: 1, 4: 1, 5: 2, 11: 2, 12: 2, 14: 2, 21: 2, 22: 1, 25: 2, 101: 2, 111: 2, 112: 2,
                122: 1, 1001: 2, 1059: 2},
         "en": {0: 1, 1: 0, 2: 1, 11: 1, 21: 1, 101: 1},
         "fr": {0: 0, 1: 0, 2: 1, 21: 1}}


def test_each_language_counts_the_way_people_say_it():
    for lang, want in RULES.items():
        assert {n: i18n.plural(n, lang) for n in want} == want, lang
    for lang in ("it", "de", "es"):
        assert [i18n.plural(n, lang) for n in (0, 1, 2, 21)] == [1, 0, 1, 1], lang
    assert i18n.plural(-1, "en") == 0 and i18n.plural(-3, "uk") == 1               # a minus keeps the word
    assert set(i18n.FORMS) == {"uk", "pl"} and set(i18n.FORMS.values()) == {3}
    # a count already written as text still picks its form
    assert i18n.t("{n} characters", "uk", n="1 059") == "1 059 символів"
    assert i18n.t("{n} characters", "en", n="1") == "1 character"


def test_the_window_counts_by_the_same_rules(tmp_path):
    nums = list(range(131)) + [1000, 1001, 1011, 1012, 1021, 1022, 1059, 1_000_001]
    texts = ["1 059", "1\u00a0059", "21", "", "1,000"]
    code = T_JS + f"const NUMS = {json.dumps(nums)}, TEXTS = {json.dumps(texts)}, LANGS = {json.dumps(list(i18n.LANGS))};\n" + (
        "process.stdout.write(JSON.stringify(LANGS.map(l => { LANG = l; "
        "return [NUMS.map(n => plural(n)), TEXTS.map(s => plural(s)), plural(undefined), plural(-3)]; })));")
    got = _node(code, tmp_path)
    for lang, (by_num, by_text, none, minus) in zip(i18n.LANGS, got):
        assert by_num == [i18n.plural(n, lang) for n in nums], lang
        assert by_text == [i18n.plural(i18n._count(s), lang) for s in texts], lang
        assert none == i18n.plural(0, lang) and minus == i18n.plural(3, lang), lang


# ---------------------------------------------------------------- the tables
def test_every_list_of_forms_fits_its_language(tmp_path):
    table_str = _str(tmp_path)
    tables = ([("_EN", "en", i18n._EN)]
              + [("_T", lang, {k: v[lang] for k, v in i18n._T.items() if lang in v}) for lang in ("uk", "it")]
              + [("STR", lang, {k: v[lang] for k, v in table_str.items() if lang in v}) for lang in ("uk", "it")]
              + [(f"{lang}.json", lang, i18n.catalog(lang)) for lang in i18n.FILE_LANGS])
    lists = 0
    for where, lang, table in tables:
        for k, v in table.items():
            if not isinstance(v, list):
                continue
            lists += 1
            assert len(v) == i18n.FORMS.get(lang, 2), (where, lang, k)
            assert "{n}" in k or "{count}" in k, (where, k)                     # the count picks the form
            assert len(set(v)) > 1, (where, lang, k)                            # else one text is enough
            for f in v:
                assert f.strip() and sorted(PH.findall(f)) == sorted(PH.findall(k)), (where, lang, k, f)
    assert lists > 150


def test_english_forms_belong_to_real_strings(tmp_path):
    table_str = _str(tmp_path)
    known = set(i18n._T) | set(table_str) | set().union(*(i18n.catalog(lang) for lang in i18n.FILE_LANGS))
    for k, (one, other) in i18n._EN.items():
        assert k in known, k
        assert other == k and one != k, k                                       # the key itself is the "other"


def test_the_window_and_lanterna_keep_the_same_forms(tmp_path):
    """A counted string in both the window's table and i18n says the same in both (uk, it)."""
    table_str = _str(tmp_path)
    for k, v in table_str.items():
        for lang in ("uk", "it"):
            py = i18n._T.get(k, {}).get(lang)
            if lang in v and py is not None and (isinstance(v[lang], list) or isinstance(py, list)):
                assert v[lang] == py, (k, lang)


# ---------------------------------------------------------------- the window says what Lanterna says
def test_the_window_says_each_count_as_lanterna_does(tmp_path):
    table_str = _str(tmp_path)
    keys = _counted(table_str)
    cases, want = [], []
    for lang in i18n.LANGS:
        cat = i18n.catalog(lang)
        for k in keys:
            if lang in table_str.get(k, {}) and k not in cat:
                continue                                    # a word only the window has (the next test)
            var = "n" if "{n}" in k else "count"
            for c in COUNTS:
                kw = {p: p.upper() for p in PH.findall(k)} | {var: c}
                cases.append([lang, k, kw])
                want.append(i18n.t(k, lang, **kw))
    strings = {lang: {k: v for k, v in i18n.catalog(lang).items() if k in keys} for lang in i18n.LANGS}
    code = STR_JS + T_JS + f"const STRINGS = {json.dumps(strings)}, CASES = {json.dumps(cases)};\n" + (
        "process.stdout.write(JSON.stringify(CASES.map(([l, k, kw]) => "
        "{ LANG = l; S = { strings: STRINGS[l] }; return t(k, kw); })));")
    got = _node(code, tmp_path)
    wrong = [(c, w, g) for c, w, g in zip(cases, want, got) if w != g]
    assert not wrong, wrong[:5]
    assert len(cases) > 1500


def test_the_window_writes_numbers_its_way(tmp_path):
    strings = {lang: i18n.catalog(lang) for lang in ("en", "pl")}
    cases = [["uk", None, "{n} characters", {"n": 1059}], ["uk", None, "{n} characters", {"n": 21}],
             ["uk", None, "{m}: {n} requests today; the service doesn't say its limit.", {"m": "Gemini", "n": 3}],
             ["uk", None, "Sort {count} files in {place}", {"count": "3", "place": "Downloads"}],   # a count as text
             ["en", "en", "{n} characters", {"n": 1}], ["en", "en", "{n} characters", {"n": 1000}],
             ["en", None, "{n} characters", {"n": 1}],                    # before the first state: the key as it is
             ["pl", "pl", "{n} requests today", {"n": 22}], ["pl", "pl", "{n} requests today", {"n": 25}]]
    code = T_JS + STR_JS + f"const STRINGS = {json.dumps(strings)}, CASES = {json.dumps(cases)};\n" + (
        "process.stdout.write(JSON.stringify(CASES.map(([l, s, k, kw]) => "
        "{ LANG = l; S = s ? { strings: STRINGS[s] } : null; return t(k, kw); })));")
    got = _node(code, tmp_path)
    assert re.fullmatch(r"1\D059 символів", got[0]) and got[1] == "21 символ"   # "1 059": a space as uk writes it
    assert got[2] == "Gemini: 3 запити сьогодні; сервіс не каже свій ліміт."
    assert got[3] == "Розкласти 3 файли в папці Downloads"
    assert got[4:7] == ["1 character", "1,000 characters", "1 characters"]
    assert got[7:] == [i18n.t("{n} requests today", "pl", n=22), i18n.t("{n} requests today", "pl", n=25)]
    assert got[7] != got[8]                                                     # "22 zapytania", "25 zapytań"
    assert "n: +r.used || 0 }) + \"\\n\" + t(\"Click for all limits\")" in JS   # no "undefined" in the tip


# ---------------------------------------------------------------- what people see
def _title(kind, lang, n, done=False, **d):
    return app.action_title(kind, {**d, "count": n}, "", lang, done=done)


def test_the_cards_read_right():
    assert [_title("pc_sort", "uk", n, place="downloads") for n in (1, 3, 5, 11, 21, 22)] == [
        "Розкласти 1 файл у папці Завантаження", "Розкласти 3 файли в папці Завантаження",
        "Розкласти 5 файлів у папці Завантаження", "Розкласти 11 файлів у папці Завантаження",
        "Розкласти 21 файл у папці Завантаження", "Розкласти 22 файли в папці Завантаження"]
    assert [_title("pc_move", "uk", n, True, to_place="documents", to=".") for n in (1, 2, 5)] == [
        "Переміщено 1 елемент у Документи", "Переміщено 2 елементи в Документи", "Переміщено 5 елементів у Документи"]
    assert [_title("pc_trash", "uk", n) for n in (1, 4, 12)] == [
        "Перемістити 1 елемент у Кошик", "Перемістити 4 елементи в Кошик", "Перемістити 12 елементів у Кошик"]
    assert [_title("mail_sort", "uk", n, True) for n in (1, 3, 25)] == [
        "Розкладено 1 лист по папках", "Розкладено 3 листи по папках", "Розкладено 25 листів по папках"]
    assert [_title("sys_look", "uk", n) for n in (2, 5, 21)] == [
        "Змінити 2 налаштування вигляду системи", "Змінити 5 налаштувань вигляду системи",
        "Змінити 21 налаштування вигляду системи"]
    assert [_title("pc_sort", "pl", n, True, place="downloads") for n in (1, 3, 5, 21, 22)] == [
        "Posortowano 1 plik w folderze Pobrane", "Posortowano 3 pliki w folderze Pobrane",
        "Posortowano 5 plików w folderze Pobrane", "Posortowano 21 plików w folderze Pobrane",
        "Posortowano 22 pliki w folderze Pobrane"]
    assert _title("pc_move", "pl", 2, to_place="documents", to=".") == "Przenieś 2 elementy do folderu Dokumenty"
    assert _title("github_push", "pl", 5, True, repo="lanterna") == "Wysłano 5 plików do repozytorium lanterna"
    assert [_title("pc_sort", "en", n, place="downloads") for n in (1, 2)] == [
        "Sort 1 file in Downloads", "Sort 2 files in Downloads"]
    assert [_title("pc_trash", "en", n, True) for n in (1, 2)] == [
        "Moved 1 item to the Recycle Bin", "Moved 2 items to the Recycle Bin"]
    assert _title("github_push", "en", 1, repo="lanterna") == "Push 1 file to lanterna"
    assert _title("pc_sort", "de", 1, place="downloads") == "1 Datei in Downloads sortieren"
    assert _title("pc_sort", "fr", 3, True, place="downloads") == "3 fichiers rangés dans Téléchargements"
    # the window builds the same titles from the same keys
    for kind, key in (("pc_sort", "Sort {count} files in {place}"), ("pc_move", "Move {count} items to {to}"),
                      ("pc_trash", "Move {count} items to the Recycle Bin"), ("mail_sort", "Sort {count} emails into folders"),
                      ("github_push", "Push {count} files to {repo}")):
        assert f'{kind}: "{key}"' in JS, kind


def test_the_other_counts_read_right():
    t = i18n.t
    assert [t("{n} files still downloading are left alone.", "uk", n=n) for n in (1, 3, 5)] == [
        "1 файл, який ще завантажується, не чіпаю.", "3 файли, які ще завантажуються, не чіпаю.",
        "5 файлів, які ще завантажуються, не чіпаю."]
    assert [t("{n} files are back where they were.", "en", n=n) for n in (1, 2)] == [
        "1 file is back where it was.", "2 files are back where they were."]
    assert [t("{n} new files in Downloads: sort them?", "uk", n=n) for n in (1, 3, 21)] == [
        "1 новий файл у Завантаженнях. Розкласти?", "3 нові файли в Завантаженнях. Розкласти?",
        "21 новий файл у Завантаженнях. Розкласти?"]
    assert [t("Key works, {n} models.", "pl", n=n) for n in (1, 3, 5)] == [
        "Klucz działa, 1 model.", "Klucz działa, 3 modele.", "Klucz działa, 5 modeli."]
    assert [t("Ready · {n} tools", "en", n=n) for n in (1, 2)] == ["Ready · 1 tool", "Ready · 2 tools"]
    assert t("What Lanterna remembers about you ({n} facts)", "uk", n=21) == "Що Lanterna пам'ятає про тебе (21 факт)"
    assert t("(tried {n} models)", "uk", n=3) == "(спробувано 3 моделі)"
    assert [t("older than {n} days", "en", n=n) for n in (1, 7)] == ["older than 1 day", "older than 7 days"]


def test_done_lines_in_every_form_still_count_as_set_up():
    for lang in i18n.LANGS:
        for f in i18n.forms("Changed {count} settings of the look", lang):     # "Змінено 3 налаштування …"
            assert chat._set_done("✅ " + f.format(count=7)), (lang, f)
    assert not chat._set_done("✅ Розкладено 3 файли в папці Завантаження")


def test_a_restored_backup_lists_each_count_in_its_form(tmp_path):
    rs = [{"chats": 1, "messages": 3, "facts": 0, "reminders": 5, "tasks": 0},
          {"chats": 2, "messages": 21, "facts": 1, "reminders": 0, "tasks": 12}]
    strings = {lang: i18n.catalog(lang) for lang in ("uk", "en")}
    code = STR_JS + T_JS + RESTORED_JS + f"\nconst STRINGS = {json.dumps(strings)}, RS = {json.dumps(rs)};\n" + (
        "process.stdout.write(JSON.stringify([['uk', 'en'].map(l => { LANG = l; S = { strings: STRINGS[l] }; "
        "return RS.map(restoredText); }), RESTORED]));")
    said, restored = _node(code, tmp_path)
    assert said == [["Відновлено: 1 чат, 3 повідомлення, 5 нагадувань.",
                     "Відновлено: 2 чати, 21 повідомлення, 1 факт пам'яті, 12 регулярних завдань."],
                    ["Restored: 1 chat, 3 messages, 5 reminders.",
                     "Restored: 2 chats, 21 messages, 1 memory fact, 12 regular tasks."]]
    assert [list(x) for x in tui.RESTORED] == restored                         # the terminal says the same
    for lang, lines in zip(("uk", "en"), said):
        for r, line in zip(rs, lines):
            parts = [i18n.t(k, lang, n=r[f]) for i, (k, f) in enumerate(tui.RESTORED) if i < 2 or r[f]]
            assert i18n.t("Restored: {list}.", lang, list=", ".join(parts)) == line
    tui_py = (SRC / "tui.py").read_text(encoding="utf-8")
    assert 'parts = [t(k, lang, n=r[f]) for i, (k, f) in enumerate(RESTORED) if i < 2 or r[f]]' in tui_py
    assert "toast(n ? restoredText(r) : t(" in JS


def test_the_stopgaps_of_b9_are_gone():
    gone = ["Sort the files in {place} ({count})", "Sorted the files in {place} ({count})", "Move to {to} ({count})",
            "Moved to {to} ({count})", "Move to the Recycle Bin ({count})", "Moved to the Recycle Bin ({count})",
            "Sort the emails into folders ({count})", "Sorted the emails into folders ({count})",
            "Files still downloading are left alone ({n}).",
            "Restored: {c} chats, {m} messages, {f} memory facts, {r} reminders, {k} regular tasks."]
    sources = [JS] + [(SRC / f).read_text(encoding="utf-8") for f in ("i18n.py", "app.py", "tui.py", "chat.py")]
    for key in gone:
        assert all(key not in s for s in sources), key
        assert all(key not in i18n.catalog(lang) for lang in i18n.LANGS), key
