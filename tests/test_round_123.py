"""Round 123: memory facts read like notes about you ("Любить підліткові фільми."), not "Вони люблять…",
and Markdown marks a model put in (*Fear*, **word**) don't show in Settings → Memory."""
from lanterna import chat, tools
from lanterna.store import Store, plain_fact


def test_paired_marks_go_and_lone_ones_stay():
    assert plain_fact("Сподобалися фільми *Fear* (1996), *Superbad* і *Project X*.") == \
        "Сподобалися фільми Fear (1996), Superbad і Project X."
    assert plain_fact("Uses **Python** and `git`, likes _Inception_") == "Uses Python and git, likes Inception"
    assert plain_fact("Works on my_bot_v2, rates it 5*, likes C* and a * b") == "Works on my_bot_v2, rates it 5*, likes C* and a * b"


def test_saved_without_marks_and_old_ones_shown_without(tmp_path):
    s = Store(tmp_path / "t.db")
    assert s.add_fact("Loves *Fight Club*") > 0
    assert s.add_fact("Loves Fight Club") == 0                     # the same fact
    with s._lock, s._db:                                           # a fact saved by an older version
        s._db.execute("INSERT INTO facts(uid, text, at) VALUES ('x', 'Has a *personal* website', 0)")
    assert [f["text"] for f in s.facts()] == ["Loves Fight Club", "Has a personal website"]
    assert s._db.execute("SELECT text FROM facts WHERE uid='x'").fetchone()[0] == "Has a *personal* website"   # kept


def test_prompts_ask_for_the_verb_first_and_plain_text():
    p = chat.MEMORY_PROMPT
    assert "starts with the verb" in p and "They…" in p and "Працює медсестрою." in p and "no Markdown" in p
    src = open(tools.__file__, encoding="utf-8").read()
    assert "starting with the " in src and "not 'They…' or 'The user…'" in src


def test_auto_memory_cleans_what_the_side_model_writes(tmp_path):
    s = Store(tmp_path / "t.db")
    got = chat.learn_facts(lambda msgs: "Любить фільми *Fear* і *Superbad*.\nNONE", "Я люблю Fear і Superbad", "", [])
    assert got == ["Любить фільми *Fear* і *Superbad*."]           # cleaned when it is saved
    for f in got:
        s.add_fact(f)
    assert [f["text"] for f in s.facts()] == ["Любить фільми Fear і Superbad."]
