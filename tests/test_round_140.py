"""Round 140 (1.1.10b2): Cloudflare Workers AI, a new free service.

- The key is the API token (from Cloudflare's "Workers AI" template); Lanterna finds the Account ID itself when
  Cloudflare names one account, or the user pastes it too (in any order). Kept as "<account ID>:<API token>".
- 10,000 free neurons a day for all its models (the day starts at 00:00 UTC). On Workers Paid more is simply billed,
  so Lanterna counts the neurons itself and stops at 9,000: Cloudflare never costs anything, on either plan.
- Only models whose ordinary answer costs few neurons are used; models that need a paid plan rest alone, while
  "today's neurons are used" rests the whole service until the next UTC day.
- Answers get max_tokens (Cloudflare's own default cuts them short).
"""
import json
import re
from pathlib import Path

import httpx
import pytest

from lanterna import gui, i18n, keys, neurons
from lanterna.discovery import Candidate, candidates_for
from lanterna.providers import CF_NEED_ACCOUNT, PROVIDERS, Client, ProviderError, _error, cloudflare_key
from lanterna.router import AllFailed, Router

CF = PROVIDERS["cloudflare"]
ACC = "0123456789abcdef0123456789abcdef"
TOKEN = "Wk_" + "z" * 20 + "-" + "Q9" * 8                  # 40 characters, like Cloudflare's API tokens
JS = (Path(gui.__file__).parent / "ui" / "app.js").read_text(encoding="utf-8")


def sse(*chunks, usage=None) -> bytes:
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in chunks]
    if usage:
        lines.append(f"data: {json.dumps({'choices': [], 'usage': usage})}\n\n")
    return ("".join(lines) + "data: [DONE]\n\n").encode()


def cf_client(handler) -> Client:
    return Client(CF, f"{ACC}:{TOKEN}", transport=httpx.MockTransport(handler))


def price(p_in, p_out):
    return [{"property_id": "price", "value": [{"unit": "per M input tokens", "price": p_in, "currency": "USD"},
                                               {"unit": "per M output tokens", "price": p_out, "currency": "USD"}]}]


# ---------------------------------------------------------------- the key
def test_requests_go_to_the_account_with_the_token_alone():
    seen = []

    def h(req):
        seen.append(req)
        return httpx.Response(200, content=sse("Hi"))
    assert cf_client(h).chat("@cf/openai/gpt-oss-120b", [{"role": "user", "content": "Hi"}]) == "Hi"
    req = seen[0]
    assert req.url.host == "api.cloudflare.com"
    assert req.url.path == f"/client/v4/accounts/{ACC}/ai/v1/chat/completions"
    assert req.headers["authorization"] == f"Bearer {TOKEN}"          # the account isn't part of the token
    with pytest.raises(ProviderError) as e:
        Client(CF, TOKEN)                                                # no Account ID: never sent half a key
    assert e.value.kind == "auth"


def test_the_token_alone_finds_the_one_account():
    seen = []

    def h(req):
        seen.append(req)
        return httpx.Response(200, json={"success": True, "result": [{"id": ACC, "name": "Me"}]})
    assert cloudflare_key(f"  {TOKEN}\n", transport=httpx.MockTransport(h)) == (f"{ACC}:{TOKEN}", "")
    assert seen[0].url.host == "api.cloudflare.com" and seen[0].url.path == "/client/v4/accounts"
    assert seen[0].headers["authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize("pasted", [f"{TOKEN} {ACC}", f"{ACC} {TOKEN}", f"{ACC}:{TOKEN}", f"{TOKEN}\n{ACC.upper()}",
                                    f'curl https://api.cloudflare.com/client/v4/accounts/{ACC}/ai/run/@cf/meta/x '
                                    f'-H "Authorization: Bearer {TOKEN}"'])
def test_both_values_in_any_order_need_no_request(pasted):
    def h(req):
        raise AssertionError("no request needed")
    assert cloudflare_key(pasted, transport=httpx.MockTransport(h)) == (f"{ACC}:{TOKEN}", "")


@pytest.mark.parametrize("answer,why", [
    (httpx.Response(200, json={"result": [{"id": ACC}, {"id": "f" * 32}]}), "need_account"),   # several accounts
    (httpx.Response(200, json={"result": []}), "need_account"),
    (httpx.Response(403, json={"errors": [{"code": 9109, "message": "Unauthorized"}]}), "need_account"),
    (httpx.Response(401, json={"errors": [{"code": 10000, "message": "Authentication error"}]}), "auth"),
])
def test_when_the_account_isnt_found(answer, why):
    assert cloudflare_key(TOKEN, transport=httpx.MockTransport(lambda r: answer)) == ("", why)


def test_no_connection_and_nothing_pasted():
    def offline(req):
        raise httpx.ConnectError("offline")
    assert cloudflare_key(TOKEN, transport=httpx.MockTransport(offline)) == ("", "network")
    assert cloudflare_key("   ")[1] == "auth" and cloudflare_key(ACC)[1] == "auth"


def test_check_key_keeps_the_account_with_the_token(tmp_path, monkeypatch):
    from lanterna import app as appmod
    from lanterna.store import Store
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    saved = {}
    monkeypatch.setattr(keys, "set_key", lambda n, v: saved.__setitem__(n, v))
    accounts = {"result": [{"id": ACC}]}
    monkeypatch.setattr(appmod, "cloudflare_key",
                        lambda text: cloudflare_key(text, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=accounts))))
    real = Client
    seen = []

    def handler(r):
        seen.append(r.url.path)
        return httpx.Response(200, json={"success": True, "result": [{"id": "u1", "name": "@cf/openai/gpt-oss-120b"}],
                                         "result_info": {"page": 1, "per_page": 50, "total_count": 1}})
    monkeypatch.setattr(appmod, "Client", lambda p, key, **kw: real(p, key, transport=httpx.MockTransport(handler)))
    api = appmod.Api(store=Store(tmp_path / "t.db"), scheduler=False)
    r = api.check_key("cloudflare", TOKEN)
    assert r["ok"] is True and saved == {"cloudflare": f"{ACC}:{TOKEN}"}
    assert seen == [f"/client/v4/accounts/{ACC}/ai/models/search"]
    accounts["result"].append({"id": "f" * 32})                        # two accounts: the user says which
    saved.clear()
    assert api.check_key("cloudflare", TOKEN) == {"ok": False, "error": "need_account", "message": ""}
    assert not saved
    hint = next(p for p in api.state()["providers"] if p["id"] == "cloudflare")["key_hint"]
    assert hint == "Paste the API token (Workers AI template)"


# ---------------------------------------------------------------- models
def test_the_model_list_comes_in_pages_with_prices():
    pages = {
        "1": {"result": [{"id": "u1", "name": "@cf/openai/gpt-oss-120b", "properties": price(0.35, 0.75)},
                         {"id": "u2", "name": "@cf/odd/model", "properties": [
                             {"property_id": "price", "value": [{"unit": "per 512x512 tile", "price": 0.0001}]}]}],
              "result_info": {"page": 1, "per_page": 2, "count": 2, "total_count": 3}},
        "2": {"result": [{"id": "u3", "name": "@cf/google/gemma-4-26b-a4b-it", "properties": price(0.2, 0.6)}],
              "result_info": {"page": 2, "per_page": 2, "count": 1, "total_count": 3}},
    }
    seen = []

    def h(req):
        seen.append(req.url)
        assert req.url.path == f"/client/v4/accounts/{ACC}/ai/models/search"
        return httpx.Response(200, json={"success": True, **pages[req.url.params.get("page", "1")]})
    assert cf_client(h).list_models() == ["@cf/openai/gpt-oss-120b", "@cf/odd/model", "@cf/google/gemma-4-26b-a4b-it"]
    assert seen[0].params["task"] == "Text Generation" and len(seen) == 2
    assert neurons.price("@cf/google/gemma-4-26b-a4b-it") == (0.2, 0.6)          # the list's price wins
    assert neurons.price("@cf/odd/model") == neurons.DEAR                         # not per token: the dearest


def test_only_models_worth_their_neurons_are_taken():
    listed = ["@cf/openai/gpt-oss-120b", "@cf/google/gemma-4-26b-a4b-it", "@cf/qwen/qwen3-30b-a3b-fp8",
              "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/qwen/qwen3.8-27b", "@cf/someone/new-model",
              "@cf/moonshotai/kimi-k2.6", "@cf/zai-org/glm-5.2", "@cf/meta-llama/llama-2-7b-chat-hf-lora",
              "@cf/meta/llama-guard-3-8b"]
    items = [{"id": f"u{i}", "name": n} for i, n in enumerate(listed)]
    items.append({"id": "u99", "name": "@cf/small/room-7b", "properties": price(0.01, 0.01) +
                  [{"property_id": "context_window", "value": "7968"}]})
    c = cf_client(lambda r: httpx.Response(200, json={"result": items}))
    got = [x.model for x in candidates_for(c)]
    assert got == ["@cf/openai/gpt-oss-120b", "@cf/google/gemma-4-26b-a4b-it", "@cf/qwen/qwen3-30b-a3b-fp8"]
    # an ordinary answer on the dear ones would cost far more of the free neurons
    assert neurons.cost("@cf/qwen/qwen3.8-27b", *neurons.ANSWER) > neurons.MOST_PER_ANSWER


# ---------------------------------------------------------------- errors
def _cf_error(status, code, message):
    return _error(httpx.Response(status, json={"success": False, "errors": [{"code": code, "message": message}]}))


def test_cloudflare_errors():
    day = _cf_error(429, 3036, "Account limited: you have used up your daily free allocation of 10,000 neurons")
    assert day.kind == "rate" and day.whole and 0 < day.retry_after <= 86400
    assert abs(day.retry_after - neurons.till_tomorrow()) < 5                   # until 00:00 UTC
    paid = _cf_error(403, 5035, "This model requires a Workers Paid plan")
    assert paid.kind == "bad_request" and not paid.whole                         # only that model is out
    assert _cf_error(403, 5016, "Accept the license first").kind == "bad_request"
    busy = _cf_error(429, 3040, "Capacity temporarily exceeded")
    assert busy.kind == "rate" and not busy.whole
    assert _cf_error(401, 10000, "Authentication error").kind == "auth"
    assert _cf_error(410, 5028, "This model is deprecated").kind == "bad_request"
    assert str(paid) == "This model requires a Workers Paid plan"
    # other services' errors read as before
    assert _error(httpx.Response(403, json={"error": {"message": "no"}})).kind == "auth"


# ---------------------------------------------------------------- the meter
BODY = {"messages": [{"role": "user", "content": "x" * 3000}], "max_tokens": 8192}
NOON = 1_700_000_000 - 1_700_000_000 % 86400 + 43200                            # 12:00 UTC on some day


def test_the_meter_holds_the_most_then_counts_what_was_used():
    m = "@cf/openai/gpt-oss-120b"
    call = neurons.Call(m, BODY, now=NOON)
    most = neurons.cost(m, call.tokens_in, 8192)
    assert neurons.used(NOON) == pytest.approx(most)
    call.done({"prompt_tokens": 1000, "completion_tokens": 200}, 0, "ok")
    assert neurons.used(NOON) == pytest.approx(neurons.cost(m, 1000, 200))
    neurons.Call(m, BODY, now=NOON).done(None, 0, "refused")                  # an error answer: nothing ran
    assert neurons.used(NOON) == pytest.approx(neurons.cost(m, 1000, 200))
    neurons.Call(m, BODY, now=NOON).done(None, 600, "ok")                     # no counts from the service: the text
    assert neurons.used(NOON) == pytest.approx(neurons.cost(m, 1000, 200) + neurons.cost(m, call.tokens_in, 201))
    before = neurons.used(NOON)
    neurons.Call(m, BODY, now=NOON).done(None, 10, "broken")                  # cut off: the most stays counted
    assert neurons.used(NOON) == pytest.approx(before + most)


def test_the_meter_stops_before_the_free_neurons_end():
    m = "@cf/openai/gpt-oss-120b"
    held = 0
    with pytest.raises(ProviderError) as e:
        for _ in range(100):
            neurons.Call(m, BODY, now=NOON)
            held += 1
    assert e.value.kind == "rate" and e.value.whole and e.value.retry_after == pytest.approx(43200)
    assert neurons.used(NOON) <= neurons.CAP < neurons.FREE and held > 5
    neurons.Call(m, BODY, now=NOON + 43200)                                    # the next UTC day starts again
    assert neurons.used(NOON + 43200) < 1000


def test_cloudflare_saying_the_day_is_used_stops_it_until_tomorrow():
    m = "@cf/openai/gpt-oss-120b"
    neurons.Call(m, BODY, now=NOON).done(None, 0, "out")
    assert neurons.used(NOON) == neurons.CAP
    with pytest.raises(ProviderError):
        neurons.Call(m, BODY, now=NOON)
    neurons.Call(m, BODY, now=NOON + 86400)


def test_a_photo_counts_as_a_picture_not_as_its_base64():
    photo = "data:image/jpeg;base64," + "A" * 900_000
    body = {"messages": [{"role": "user", "content": [{"type": "text", "text": "What is it?"},
                                                      {"type": "image_url", "image_url": {"url": photo}}]}]}
    assert neurons.PICTURE < neurons.request_tokens(body) < neurons.PICTURE + 100
    assert neurons.request_tokens({"messages": [{"role": "user", "content": "x" * 300}]}) > 100


def test_a_big_request_rests_only_that_model_for_a_minute():
    m = "@cf/openai/gpt-oss-120b"
    for _ in range(12):                                                        # most of the day is used
        neurons.Call(m, BODY, now=NOON)
    assert 1000 < neurons.CAP - neurons.used(NOON) < 3000
    long_doc = {"messages": [{"role": "user", "content": "x" * 300_000}]}
    with pytest.raises(ProviderError) as e:
        neurons.Call(m, long_doc, now=NOON)
    assert e.value.kind == "rate" and not e.value.whole and e.value.retry_after == 60
    neurons.Call(m, BODY, now=NOON)                                            # an ordinary one still fits


def test_unknown_models_count_at_the_dearest_price():
    assert neurons.price("@cf/nobody/knows") == neurons.DEAR
    assert not neurons.cheap_enough("@cf/nobody/knows")
    assert neurons.cheap_enough("@cf/openai/gpt-oss-120b") and neurons.cheap_enough("@cf/google/gemma-4-26b-a4b-it")


# ---------------------------------------------------------------- answers
def test_answers_get_max_tokens_and_are_counted():
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, content=sse("Hel", "lo", usage={"prompt_tokens": 900, "completion_tokens": 40}))
    c = cf_client(h)
    m = "@cf/openai/gpt-oss-120b"
    assert c.chat(m, [{"role": "user", "content": "Hi"}]) == "Hello"
    assert bodies[0]["max_tokens"] == neurons.MAX_OUT and bodies[0]["model"] == m
    assert neurons.used() == pytest.approx(neurons.cost(m, 900, 40))           # Cloudflare's own counts


def test_other_services_are_not_counted_or_capped():
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, content=sse("Hi"))
    Client(PROVIDERS["groq"], "k", transport=httpx.MockTransport(h)).chat("m", [])
    assert "max_tokens" not in bodies[0] and neurons.used() == 0


def test_a_refused_answer_gives_its_neurons_back_and_the_used_day_stops_all():
    asked = []

    def h(req):
        asked.append(1)
        return httpx.Response(429, json={"errors": [{"code": 3036, "message": "daily free allocation used"}]})
    c = cf_client(h)
    with pytest.raises(ProviderError) as e:
        c.chat("@cf/openai/gpt-oss-120b", [{"role": "user", "content": "Hi"}])
    assert e.value.whole and neurons.used() == neurons.CAP
    with pytest.raises(ProviderError):                                         # no request any more today
        c.chat("@cf/google/gemma-4-26b-a4b-it", [{"role": "user", "content": "Hi"}])
    assert len(asked) == 1


def test_a_ping_is_counted_too():
    def h(req):
        assert json.loads(req.content)["max_tokens"] == 8
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hi"}}],
                                         "usage": {"prompt_tokens": 9, "completion_tokens": 2}})
    cf_client(h).ping("@cf/openai/gpt-oss-120b")
    assert neurons.used() == pytest.approx(neurons.cost("@cf/openai/gpt-oss-120b", 9, 2))


def test_the_router_rests_the_whole_service_and_moves_on():
    neurons.Call("@cf/openai/gpt-oss-120b", BODY).done(None, 0, "out")         # today's neurons are gone
    groq = Client(PROVIDERS["groq"], "k", transport=httpx.MockTransport(lambda r: httpx.Response(200, content=sse("ok"))))
    cf = cf_client(lambda r: pytest.fail("Cloudflare isn't asked once its day is used"))
    cands = [Candidate("cloudflare", "@cf/openai/gpt-oss-120b", 90), Candidate("cloudflare", "@cf/google/gemma-4-26b-a4b-it", 85),
             Candidate("groq", "llama", 70)]
    r = Router(cands, client_for=lambda pid: {"groq": groq, "cloudflare": cf}[pid])
    assert "".join(p for p in r.stream([{"role": "user", "content": "Hi"}]) if isinstance(p, str)) == "ok"
    assert [c.model for c in r.available()] == ["llama"]                      # both Cloudflare models rest
    left = r.resting()
    assert left.get("cloudflare/@cf/google/gemma-4-26b-a4b-it", 0) > 3600 or neurons.till_tomorrow() < 3600


def test_all_cloudflare_models_used_up_is_a_plain_limit():
    neurons.Call("@cf/openai/gpt-oss-120b", BODY).done(None, 0, "out")
    cf = cf_client(lambda r: pytest.fail("not asked"))
    r = Router([Candidate("cloudflare", "@cf/openai/gpt-oss-120b", 90)], client_for=lambda pid: cf, sleep=lambda s: None)
    with pytest.raises(AllFailed) as e:
        list(r.stream([{"role": "user", "content": "Hi"}]))
    assert e.value.kind == "rate"


# ---------------------------------------------------------------- words
def test_every_language_has_the_new_words():
    for text in (CF.note, CF.key_hint, CF_NEED_ACCOUNT):
        for lang in i18n.LANGS:
            if lang != "en":
                assert text in i18n.catalog(lang), (lang, text)
                assert i18n.t(text, lang) != text, (lang, text)
    assert "Workers AI" in i18n.t(CF.key_hint, "uk")


def test_the_window_shows_the_hint_and_the_account_message():
    assert f't("{CF_NEED_ACCOUNT}")' in JS                                    # the same words, so they translate
    assert 'r.error === "need_account"' in JS
    assert re.search(r"key_hint \|\| \"Paste your key\"", JS)
