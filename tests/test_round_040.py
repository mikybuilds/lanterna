"""0.4.0 stage 1: tool result size per model, the page excerpt that fits the question, a web search for models
that can't call tools. No real network: fake pages and fake search results."""
import json
from types import SimpleNamespace

from lanterna.chat import RESULT_LIMIT, Conversation, ToolUse, needs_search, result_limit
from lanterna.discovery import Candidate
from lanterna.providers import ToolCall, ToolCalls
from lanterna.router import Router
from lanterna.tools import focus_excerpt, read_page

FILLER = [f"Menu item {i}: shop, blog, contacts, newsletter sign up" for i in range(300)]


# ---------------------------------------------------------------- page excerpt
def test_short_page_is_returned_whole():
    assert focus_excerpt("Hello\nworld", "anything", 100) == ("Hello\nworld", False)


def test_long_page_keeps_the_lines_about_the_question():
    answer = "To change text to upper case in Flowgorithm use the ToUpper function: ToUpper(name)."
    page = "\n".join(["Flowgorithm docs", *FILLER[:150], answer, *FILLER[150:]])
    text, cut = focus_excerpt(page, "flowgorithm upper case function", 1500)
    assert cut and len(text) <= 1500
    assert text.startswith("Flowgorithm docs")          # the head of the page stays
    assert answer in text
    assert "[…]" in text                                # gaps are marked


def test_page_with_no_matching_words_falls_back_to_its_start():
    page = "\n".join(FILLER)
    text, cut = focus_excerpt(page, "погода у Феррарі", 800)
    assert cut and text == page[:800]


def test_word_forms_still_match():
    page = "\n".join([*FILLER[:200], "Програма пише ім'я з великої літери.", *FILLER[200:]])
    text, _ = focus_excerpt(page, "як написати ім'я великою літерою", 1200)
    assert "з великої літери" in text


def test_read_page_uses_the_focus():
    answer = "Opening hours: Tuesday to Sunday 9:00-19:00."
    body = "<html><body>" + "".join(f"<p>{x}</p>" for x in [*FILLER[:200], answer, *FILLER[200:]]) + "</body></html>"
    resp = SimpleNamespace(status_code=200, headers={"content-type": "text/html"}, text=body, is_redirect=False)
    http = SimpleNamespace(get=lambda url: resp)
    out = read_page("https://example.org/museum", http=http, check_host=lambda h: True,
                    focus="museum opening hours sunday", limit=1500)
    assert answer in out and "only the parts that fit the question" in out


# ---------------------------------------------------------------- result size per model
def test_result_limit_per_provider():
    assert result_limit("groq") < result_limit("mistral") < result_limit("gemini")
    assert result_limit(None) == RESULT_LIMIT == result_limit("unknown")


def _fake_conv(provider, run, lacks=False, first=None):
    seen = []

    class FakeRouter:
        current = SimpleNamespace(label="test", provider=provider)

        def lacks_tools(self):
            return lacks

        def stream(self, msgs, **kw):
            seen.append([dict(m) for m in msgs])
            if first and len(seen) == 1:
                yield ToolCalls([ToolCall("c1", *first)])
            else:
                yield "Answer."

    box = SimpleNamespace(tools={"web_search": SimpleNamespace(label="🔎")}, store=SimpleNamespace(facts=lambda: []),
                          schemas=lambda ctx: [{"type": "function", "function": {"name": "web_search"}}], run=run)
    return Conversation(router=FakeRouter(), toolbox=box), seen, box


def test_groq_gets_a_shorter_tool_result_than_gemini():
    for provider in ("groq", "gemini"):
        conv, seen, _ = _fake_conv(provider, lambda n, a: "x" * 50000, first=("web_search", '{"query": "q"}'))
        list(conv.ask("find q"))
        tool = next(m for m in seen[-1] if m["role"] == "tool")
        assert len(tool["content"].split("\n\n[Lanterna")[0]) == result_limit(provider)


def test_read_page_gets_the_question_and_the_searches_as_focus():
    conv, _, box = _fake_conv("gemini", lambda n, a: "page", first=("read_page", '{"url": "https://e.org"}'))
    list(conv.ask("коли відкритий музей?"))
    assert "музей" in box.focus and box.page_limit < result_limit("gemini")


# ---------------------------------------------------------------- models without tools
def test_needs_search():
    for q in ("Які новини сьогодні?", "скільки коштує iPhone 17", "who won the match yesterday? latest score of",
              "quanto costa il biglietto", "що нового в Python 3.15 у 2026"):
        assert needs_search(q), q
    for q in ("привіт", "поясни, що таке рекурсія", "write a poem about the sea"):
        assert not needs_search(q), q


def test_model_without_tools_gets_search_results_first():
    ran = []
    conv, seen, _ = _fake_conv("ollama", lambda n, a: ran.append((n, a)) or "RESULT: Lazio 2-1 Roma", lacks=True)
    parts = list(conv.ask("хто виграв дербі вчора?"))
    assert ran and ran[0][0] == "web_search" and json.loads(ran[0][1])["query"].startswith("хто виграв")
    assert any(isinstance(p, ToolUse) and p.name == "web_search" for p in parts)
    user = seen[0][-1]
    assert user["role"] == "user" and "Lazio 2-1 Roma" in user["content"]
    assert conv.history[-2]["content"] == "хто виграв дербі вчора?"   # history keeps the user's own words


def test_no_search_for_plain_chat_or_models_with_tools():
    ran = []
    conv, _, _ = _fake_conv("ollama", lambda n, a: ran.append(n) or "r", lacks=True)
    list(conv.ask("поясни, що таке рекурсія"))
    conv, _, _ = _fake_conv("gemini", lambda n, a: ran.append(n) or "r", lacks=False)
    list(conv.ask("які новини сьогодні?"))
    assert ran == []


def test_router_knows_when_the_next_model_lacks_tools():
    r = Router([Candidate("ollama", "gemma3:4b", 50, tools=False), Candidate("ollama", "qwen3:8b", 40)])
    assert not r.lacks_tools()                           # with tools on offer the one that can call them answers
    assert Router([Candidate("ollama", "gemma3:4b", 50, tools=False)]).lacks_tools()   # only one that can't
    assert not Router([]).lacks_tools()
