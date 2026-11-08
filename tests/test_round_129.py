"""Honest about actions: a model that only says it is "installing…, almost done" without doing anything.

A model that refuses tools no longer answers quietly without them when another one can use tools; every model is
told nothing happens between replies; and a reply that claims work while no tool ran gets a visible warning."""
from lanterna import chat
from lanterna.discovery import Candidate
from lanterna.providers import ProviderError, ToolCall, ToolCalls
from lanterna.router import Router, Switched
from lanterna.tools import Toolbox


class Fake:
    """A model service: model "plain" refuses tools; the others answer with the given replies in turn."""

    def __init__(self, replies):
        self.replies, self.seen = replies, []

    def stream_chat(self, model, messages, tools=None, tool_choice="auto"):
        self.seen.append((model, bool(tools), messages[0]["content"]))
        if model == "plain" and tools:
            raise ProviderError("bad_request", "Function calling is not enabled for this model", 400)
        yield from self.replies.pop(0)

    def close(self):
        pass


def router(fake, *models):
    return Router([Candidate("gemini", m, 90 - i) for i, m in enumerate(models)], client_for=lambda pid: fake)


TOOLS = [{"type": "function", "function": {"name": "calculate", "parameters": {"type": "object", "properties": {}}}}]


def test_a_model_without_tools_hands_over_to_one_with_tools():
    fake = Fake([["Done with tools."]])
    r = router(fake, "plain", "able")
    out = list(r.stream([{"role": "system", "content": "s"}], tools=TOOLS))
    assert any(isinstance(p, Switched) and p.to.model == "able" for p in out) and "Done with tools." in out
    assert ("gemini", "plain") in r.no_tools and not r.resting()          # not put to rest: fine for plain chats
    fake.replies.append(["Again."])
    out = list(r.stream([{"role": "system", "content": "s"}], tools=TOOLS))
    assert fake.seen[-1][:2] == ("able", True) and "Again." in out          # next time the able one goes first
    assert not r.lacks_tools()
    fake.replies.append(["Hi!"])
    list(r.stream([{"role": "system", "content": "s"}]))                   # no tools on offer: order as before
    assert fake.seen[-1][0] == "plain"


def test_with_no_model_that_can_it_still_answers_without_tools():
    fake = Fake([["Only words."]])
    r = router(fake, "plain")
    assert "Only words." in list(r.stream([{"role": "system", "content": "s"}], tools=TOOLS))
    assert r.lacks_tools()


def test_claims_of_work_are_recognised():
    for said in ["Я вже майже на фініші з першим етапом. Як тільки закінчу, відразу маякну! ⏳",
                 "Зараз якраз завершую налаштування конфігів і переходжу до зміни іконок.",
                 "✅ Checking installed apps...", "I'm installing the packages now, almost done.",
                 "I've installed GNOME Tweaks for you.", "Sto installando i pacchetti."]:
        assert chat.claims_action(said), said
    for said in ["Щоб встановити, відкрий термінал і введи: sudo dnf install gnome-tweaks",
                 "Ось вірш про осінь.", "Встановлюєш так: Налаштування → Вигляд.", "Готово! Ось твій список.",
                 "Можу встановити це, якщо скажеш."]:
        assert not chat.claims_action(said), said


def test_every_model_is_told_nothing_happens_between_replies():
    assert chat.HONEST_GUIDE in chat.system_prompt("Bo")
    fake = Fake([["Привіт!"]])
    s = chat.Conversation(router=router(fake, "able"), lang="uk")
    list(s.ask("привіт"))
    assert chat.NO_TOOLS_NOTE.strip() in fake.seen[-1][2]                  # no toolbox: it is told it has no tools


class NoStore:
    def facts(self):
        return []


def test_a_claim_without_any_tool_gets_a_warning(monkeypatch):
    fake = Fake([["Встановлюю пакети, вже майже на фініші! Маякну, як закінчу."]])
    s = chat.Conversation(router=router(fake, "able"), lang="uk", toolbox=Toolbox(NoStore()))
    out = "".join(p for p in s.ask("налаштуй мені систему") if isinstance(p, str))
    assert "⚠️" in out and "нічого не запускала" in out and s.history[-1]["content"].endswith(out.split("\n\n")[-1])


def test_no_warning_when_a_tool_really_ran():
    call = ToolCalls([ToolCall("c1", "calculate", '{"expression": "2+2"}')])
    # "almost done with the rest" after a mere calculation now gets the warning too (see test_round_130)
    fake = Fake([[call], ["Я вже порахував: 4. Перевіряю решту."]])
    s = chat.Conversation(router=router(fake, "able"), lang="uk", toolbox=Toolbox(NoStore()))
    out = "".join(p for p in s.ask("порахуй 2+2") if isinstance(p, str))
    assert "⚠️" not in out and "4" in out
