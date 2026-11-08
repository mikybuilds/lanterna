"""Round 120: the update downloads through the API when GitHub's usual download link fails (504 on 8 November 2026),
and release notes show without Markdown marks."""
import hashlib

import httpx

from lanterna import HOMEPAGE, updates

BLOB = b"MZ fake installer"
NAME = "Lanterna-Setup-9.9.9.exe"
API = updates._ASSETS + "123"


def _info():
    return {"latest": "9.9.9", "newer": True, "assets": {NAME: f"{HOMEPAGE}/releases/download/v9.9.9/{NAME}"},
            "api_assets": {NAME: API}, "digests": {NAME: "sha256:" + hashlib.sha256(BLOB).hexdigest()}}


def _updater(tmp_path, handler):
    seen = []

    def h(req):
        seen.append((str(req.url), req.headers.get("accept", "")))
        return handler(req)
    return updates.Updater(transport=httpx.MockTransport(h), launch=lambda p, lang: None, quit_app=lambda: None,
                           folder=tmp_path), seen


def test_falls_back_to_the_api_when_github_says_504(tmp_path):
    asset = updates.setup_asset(_info())
    assert asset["mirror"] == API

    def h(req):
        if "/releases/download/" in str(req.url):
            return httpx.Response(504, text="<h1>504 Gateway Time-out</h1>")
        return httpx.Response(200, content=BLOB)
    u, seen = _updater(tmp_path, h)
    path = u.download(asset)
    assert path.read_bytes() == BLOB and u.done == len(BLOB)
    assert seen[1] == (API, "application/octet-stream")


def test_network_error_also_falls_back(tmp_path):
    def h(req):
        if "/releases/download/" in str(req.url):
            raise httpx.ConnectError("reset")
        return httpx.Response(200, content=BLOB)
    u, _ = _updater(tmp_path, h)
    assert u.download(updates.setup_asset(_info())).read_bytes() == BLOB


def test_the_api_copy_must_match_the_checksum_too(tmp_path):
    def h(req):
        return httpx.Response(504) if "/releases/download/" in str(req.url) else httpx.Response(200, content=b"evil")
    u, _ = _updater(tmp_path, h)
    try:
        u.download(updates.setup_asset(_info()))
        raise AssertionError("accepted a wrong file")
    except RuntimeError as e:
        assert "checksum" in str(e)


def test_a_404_is_not_retried_and_both_failing_says_so(tmp_path):
    u, seen = _updater(tmp_path, lambda req: httpx.Response(404))
    try:
        u.download(updates.setup_asset(_info()))
    except RuntimeError as e:
        assert "404" in str(e)
    assert len(seen) == 1
    u, seen = _updater(tmp_path, lambda req: httpx.Response(504))
    try:
        u.download(updates.setup_asset(_info()))
    except RuntimeError as e:
        assert "504" in str(e)
    assert len(seen) == 2


def test_only_this_projects_api_address_is_used():
    info = {**_info(), "api_assets": {NAME: "https://example.org/x.exe"}}
    assert "mirror" not in updates.setup_asset(info)


def test_check_reads_the_api_address():
    data = {"tag_name": "v9.9.9", "body": "## 9.9.9 — x\n\n**Fixed**\n- **Bold title:** text with `code` and [a link](https://x)\n",
            "assets": [{"name": NAME, "browser_download_url": f"{HOMEPAGE}/releases/download/v9.9.9/{NAME}", "url": API,
                        "digest": "sha256:" + "0" * 64}]}
    info = updates.check(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data)))
    assert info["api_assets"] == {NAME: API}
    assert info["notes"] == ["Bold title: text with code and a link"]
