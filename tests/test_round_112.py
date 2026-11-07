"""Round 112: the model can look through earlier chats (saved on this computer) when the user refers to them."""
import json

from lanterna import sent, thinking, tools
from lanterna.store import Store


def _box(tmp_path):
    st = Store(tmp_path / "t.db")
    a = st.new_thread("Велосипед")
    st.add(a, "user", "Який ланцюг купити для велосипеда Shimano?")
    st.add(a, "assistant", "Для 9 швидкостей бери Shimano CN-HG53.")
    b = st.new_thread("Рецепт")
    st.add(b, "user", "Як спекти хліб?\n\n[File: рецепт.txt]\n```\nборошно 500 г\n```")
    st.add(b, "assistant", "Змішай борошно і воду.")
    return tools.Toolbox(st), a, b


def test_search_finds_the_chat_and_read_gives_its_text(tmp_path):
    box, a, b = _box(tmp_path)
    out = box.run("search_chats", json.dumps({"words": "ланцюг велосипеда"}))
    assert f"#{a} «Велосипед»" in out and "Рецепт" not in out
    text = box.run("read_chat", json.dumps({"id": a}))
    assert "CN-HG53" in text and text.startswith(f"Chat #{a} «Велосипед»")
    other = box.run("read_chat", json.dumps({"id": b}))
    assert "[file рецепт.txt]" in other and "500 г" not in other           # attached files: only their names
    assert "No earlier chat" in box.run("search_chats", json.dumps({"words": "космос"}))
    assert box.run("read_chat", '{"id": 999}').startswith("Error")


def test_a_long_chat_keeps_its_end(tmp_path):
    box, a, _ = _box(tmp_path)
    for i in range(300):
        box.store.add(a, "user", f"повідомлення {i} " + "слово " * 10)
    text = box.run("read_chat", json.dumps({"id": a}))
    assert "повідомлення 299" in text and len(text) < box.CHAT_LIMIT + 100


def test_offered_only_when_the_talk_is_about_earlier_chats(tmp_path):
    box, *_ = _box(tmp_path)
    names = lambda ctx: {s["function"]["name"] for s in box.schemas(ctx)}   # noqa: E731
    assert "search_chats" in names("що ти мені радив минулого разу про велосипед?")
    assert "search_chats" in names("what did we talk about last time?")
    assert "search_chats" not in names("яка погода завтра?")


def test_the_note_and_the_steps_say_so():
    rows = sent.build("M", False, 0, False, 0, [], 0, [("search_chats", '{"words": "велосипед"}'), ("read_chat", '{"id": 3}')])
    assert {"t": "Words looked up in your earlier chats on this computer: {q}", "v": {"q": "велосипед"}} in rows
    assert {"t": "The text of your earlier chat #{id}", "v": {"id": "3"}} in rows
    assert "search_chats" in thinking.TOOL_TEXT and "read_chat" in thinking.TOOL_TEXT
