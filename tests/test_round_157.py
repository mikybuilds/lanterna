"""Round 157 (1.1.11b11): local models from Hugging Face.

The user asked for a choice of local models like huggingface.co/models?sort=trending. Settings → Local models now
has «Більше моделей з Hugging Face»: folded until opened (only then a request goes out), a search, the site's sorts,
"only the ones that run on this computer", and for each model the sizes of its files with what runs where. Ollama
downloads the picked file itself (hf.co/<repo>:<file>.gguf, Hugging Face's own way), so nothing new runs here.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from lanterna import gui, hfhub, local
from lanterna.app import _MODEL_NAME

from test_tui import api  # noqa: F401  (the fixture)

UI = Path(hfhub.__file__).parent / "ui"
JS = (UI / "app.js").read_text(encoding="utf-8")

CARD = hfhub.Machine(vram_gb=12, ram_gb=32)        # a 12 GB graphics card, 32 GB of memory
LAPTOP = hfhub.Machine(vram_gb=0, ram_gb=16)       # no graphics card


def test_what_runs_where():
    assert hfhub.fit(5.0, CARD) == "gpu"           # 5 GB file: on the card
    assert hfhub.fit(16.6, CARD) == "ram"          # a 27B model in Q4_K_M: in memory, slower
    assert hfhub.fit(40.0, CARD) == "no"
    assert hfhub.fit(5.0, LAPTOP) == "ram" and hfhub.fit(12.0, LAPTOP) == "no"
    assert hfhub.fit(0, CARD) == ""                # unknown size: no claim


def test_the_quant_is_read_from_the_file_name():
    assert hfhub.quant_of("Qwen3.8-27B-UD-Q4_K_M.gguf") == "UD-Q4_K_M"
    assert hfhub.quant_of("Llama-3.2-3B-Instruct-IQ3_M.gguf") == "IQ3_M"
    assert hfhub.quant_of("model.Q8_0.gguf") == "Q8_0" and hfhub.quant_of("x-bf16.gguf") == "BF16"
    assert hfhub.quant_of("imatrix_unsloth.gguf") == "" and hfhub.quant_of("README.md") == ""


def page_rows():
    big = {"total": 70_000_000_000, "architecture": "llama", "context_length": 131072, "chat_template": "{{x}}"}
    small = {"total": 8_000_000_000, "architecture": "qwen3", "context_length": 40960, "chat_template": "{{x}}"}
    return [
        {"id": "unsloth/Qwen3-8B-GGUF", "gated": False, "pipeline_tag": "text-generation", "gguf": small,
         "downloads": 2_445_633, "likes": 1486, "lastModified": "2026-11-23T16:29:50.000Z"},
        {"id": "big/Llama-70B-GGUF", "gated": False, "pipeline_tag": "text-generation", "gguf": big, "downloads": 9,
         "likes": 1, "lastModified": "2026-11-01T00:00:00.000Z"},
        {"id": "meta/Gated-GGUF", "gated": "manual", "pipeline_tag": "text-generation", "gguf": small},
        {"id": "pics/Image-GGUF", "gated": False, "pipeline_tag": "text-to-image", "gguf": small},
        {"id": "x/NoTemplate-GGUF", "gated": False, "pipeline_tag": None, "gguf": {"total": 1_000_000_000}},
        {"id": "x/Vision-GGUF", "gated": False, "pipeline_tag": "image-text-to-text", "gguf": small},
        {"id": "x/Adult-GGUF", "gated": False, "pipeline_tag": "text-generation", "gguf": small,
         "tags": ["gguf", "not-for-all-audiences"]},
        {"id": "Qwen/Qwen3-Embedding-8B-GGUF", "gated": False, "pipeline_tag": None, "gguf": small,
         "tags": ["gguf", "feature-extraction"]},
        {"id": "x/Some-Reranker-GGUF", "gated": False, "pipeline_tag": None, "gguf": small},
    ]


def test_a_page_of_models_keeps_only_chat_models_that_can_be_downloaded():
    seen = []

    def h(req):
        seen.append(req)
        return httpx.Response(200, json=page_rows(), headers={
            "Link": '<https://huggingface.co/api/models?filter=gguf&cursor=eyJ4IjoxfQ%3D%3D>; rel="next"'})
    hub = hfhub.Hub(transport=httpx.MockTransport(h))
    r = hub.models(CARD, "qwen  3", "downloads")
    assert r["ok"] and [m["id"] for m in r["models"]] == ["unsloth/Qwen3-8B-GGUF", "x/Vision-GGUF"]
    assert r["hidden"] == 1 and r["next"] == "eyJ4IjoxfQ=="            # the 70B model doesn't fit: hidden
    m = r["models"][0]
    assert m["params_b"] == 8.0 and m["arch"] == "qwen3" and m["fit"] == "gpu" and m["est_gb"] == 4.8
    assert m["url"] == "https://huggingface.co/unsloth/Qwen3-8B-GGUF" and r["models"][1]["photos"]
    q = dict(seen[0].url.params)
    assert seen[0].url.host == "huggingface.co" and seen[0].url.path == "/api/models"
    assert q["filter"] == "gguf" and q["sort"] == "downloads" and q["search"] == "qwen 3" and q["direction"] == "-1"
    assert "tags" in seen[0].url.params.get_list("expand[]")             # adult and search-index models stay out
    assert "authorization" not in {k.lower() for k in seen[0].headers}       # no account, no key
    again = hub.models(CARD, "qwen 3", "downloads")                          # the same page: from memory
    assert len(seen) == 1 and again["models"] == r["models"]
    everything = hub.models(CARD, "qwen 3", "downloads", fits_only=False)
    assert [m["id"] for m in everything["models"]][:2] == ["unsloth/Qwen3-8B-GGUF", "big/Llama-70B-GGUF"]
    assert everything["models"][1]["fit"] == "no" and len(seen) == 1
    hub.models(CARD, "", "trending", cursor="eyJ4IjoxfQ==")
    assert dict(seen[-1].url.params)["cursor"] == "eyJ4IjoxfQ==" and dict(seen[-1].url.params)["sort"] == "trendingScore"


def test_errors_say_what_happened():
    def down(req):
        raise httpx.ConnectError("no internet", request=req)
    assert hfhub.Hub(transport=httpx.MockTransport(down)).models(CARD) == {"ok": False, "error": "net"}
    busy = hfhub.Hub(transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    assert busy.models(CARD) == {"ok": False, "error": "busy"}
    assert busy.files("a/b", CARD) == {"ok": False, "error": "busy"}
    assert hfhub.Hub(transport=httpx.MockTransport(lambda r: httpx.Response(404))).files("a/b", CARD)["error"] == "gone"


def repo(gated=False, params=27_320_697_856):
    gb = 1_000_000_000
    files = [("BF16/m-BF16-00001-of-00002.gguf", 50 * gb), ("MTP/mtp-m-Q4_0.gguf", 1.4 * gb),
             ("m-Q4_0.gguf", 16.06 * gb), ("m-Q8_0.gguf", 29.05 * gb), ("m-UD-IQ2_S.gguf", 8.42 * gb),
             ("m-UD-IQ3_XXS.gguf", 10.93 * gb), ("m-UD-Q4_K_M.gguf", 16.56 * gb), ("m-UD-Q6_K_M.gguf", 23.09 * gb),
             ("dspark-m-Q8_0.gguf", 0.5 * gb), ("imatrix_unsloth.gguf", 0.01 * gb), ("mmproj-F16.gguf", 0.93 * gb),
             ("m-Q5_K_M-00001-of-00002.gguf", 10 * gb), ("README.md", 2000)]
    return {"id": "unsloth/m-GGUF", "gated": gated, "gguf": {"total": params},
            "siblings": [{"rfilename": n, "size": int(s)} for n, s in files]}


def test_the_files_of_a_model_are_the_model_itself_with_the_usual_pick():
    seen = []

    def h(req):
        seen.append(req)
        return httpx.Response(200, json=repo())
    hub = hfhub.Hub(transport=httpx.MockTransport(h))
    r = hub.files("unsloth/m-GGUF", CARD)
    assert r["ok"] and [f["quant"] for f in r["files"]] == ["UD-IQ2_S", "UD-IQ3_XXS", "Q4_0", "UD-Q4_K_M", "UD-Q6_K_M", "Q8_0"]
    picked = r["files"][r["pick"]]
    assert picked["quant"] == "UD-Q4_K_M" and picked["fit"] == "ram"        # Hugging Face's default, in memory
    assert picked["name"] == "hf.co/unsloth/m-GGUF:m-UD-Q4_K_M.gguf"         # the exact file: no guessing by Ollama
    assert r["url"] == "https://huggingface.co/unsloth/m-GGUF"
    assert seen[0].url.path == "/api/models/unsloth/m-GGUF" and dict(seen[0].url.params)["blobs"] == "true"
    small = hfhub.Hub(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=repo(params=8_000_000_000))))
    gb = 1_000_000_000
    body = {"id": "u/s-GGUF", "gated": False, "gguf": {"total": 8_000_000_000},
            "siblings": [{"rfilename": f"s-{q}.gguf", "size": int(s * gb)} for q, s in
                         (("Q3_K_M", 4.0), ("Q4_K_M", 4.9), ("Q6_K", 6.6), ("Q8_0", 8.5))]}
    small = hfhub.Hub(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)))
    s = small.files("u/s-GGUF", CARD)
    assert s["files"][s["pick"]]["quant"] == "Q4_K_M" and s["files"][s["pick"]]["fit"] == "gpu"
    tiny_card = hfhub.Machine(vram_gb=6, ram_gb=8)
    s = small.files("u/s-GGUF", tiny_card)
    assert s["files"][s["pick"]]["quant"] == "Q3_K_M"                       # Q4_K_M is too big for the card


def test_gated_or_strange_names_never_reach_ollama():
    gated = hfhub.Hub(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=repo(gated="auto"))))
    assert gated.files("unsloth/m-GGUF", CARD) == {"ok": False, "error": "gated"}
    calls = []
    hub = hfhub.Hub(transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json=repo())))
    for bad in ("../etc", "a/b/c", "a", "a/b?x=1", "-a/b"):
        assert hub.files(bad, CARD) == {"ok": False, "error": "name"}
    assert not calls
    assert _MODEL_NAME.match("hf.co/unsloth/m-GGUF:m-UD-Q4_K_M.gguf") and _MODEL_NAME.match("qwen3:8b")
    for bad in ("hf.co/a/b/c", "hf.co/../x:y", "a b", "hf.co/a/b:x y"):
        assert not _MODEL_NAME.match(bad), bad


def test_the_window_may_call_it_and_sees_what_is_installed(api, monkeypatch):  # noqa: F811
    assert {"hf_models", "hf_files", "pull_model"} <= gui.METHODS
    monkeypatch.setattr(local, "installed", lambda: [local.LocalModel("hf.co/unsloth/Qwen3-8B-GGUF:Qwen3-8B-Q4_K_M.gguf", 4.9)])
    monkeypatch.setattr(api, "_machine", lambda: CARD)
    api._hf = hfhub.Hub(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=page_rows())))
    r = api.hf_models("", "trending", "", True)
    assert [m["installed"] for m in r["models"]] == [True, False]
    monkeypatch.setattr(local, "version", lambda: "0.13.0")
    started = []
    monkeypatch.setattr(api._downloads, "start", lambda name: started.append(name))
    assert api.pull_model("hf.co/unsloth/m-GGUF:m-UD-Q4_K_M.gguf") == {"ok": True}
    assert api.pull_model("hf.co/a/b/c") == {"ok": False, "error": "name"} and len(started) == 1
    api.set_local_model("chat", "hf.co/unsloth/m-GGUF:m-UD-Q4_K_M.gguf")
    assert api.settings.local_models["chat"] == "hf.co/unsloth/m-GGUF:m-UD-Q4_K_M.gguf"   # not cut at 80


def test_the_catalog_asks_nothing_until_it_is_opened():
    body = JS[JS.index("async function hfPanel("):JS.index("\nfunction keyRow(")]
    assert 'det.ontoggle = () => { if (det.open && !list.children.length) load(false); };' in body
    assert body.index("api.hf_models(") > body.index("const load = async")             # only inside load()
    assert '<details class="hf">' in body and "hfPanel($(\"#hf\", body)" in JS
    for name in set(re.findall(r"api\.([a-z_]+)\(", body)):
        assert name in gui.METHODS, name


@pytest.mark.skipif(not shutil.which("node"), reason="needs Node")
def test_long_model_names_read_short_in_the_lists():
    fn = JS[JS.index("function modelLabel("):JS.index("\nfunction hfRow(")]
    code = fn + "\nconsole.log(JSON.stringify(['hf.co/unsloth/Qwen3.8-27B-GGUF:Qwen3.8-27B-UD-Q4_K_M.gguf', 'qwen3:8b', " \
                "'huggingface.co/a/Some-Model-GGUF:some-model.q8_0.gguf'].map(modelLabel)))"
    out = subprocess.run(["node", "-e", code], capture_output=True, encoding="utf-8", timeout=30).stdout
    assert json.loads(out) == ["Qwen3.8-27B · UD-Q4_K_M", "qwen3:8b", "Some-Model · Q8_0"]
