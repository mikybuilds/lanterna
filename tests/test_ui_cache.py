from lanterna import gui


def test_ui_cache_dropped_once_per_ui_change(tmp_path):
    store = tmp_path / "webview"
    cache = store / "EBWebView" / "Default" / "Cache"
    keep = store / "EBWebView" / "Default" / "Local Storage"
    cache.mkdir(parents=True)
    keep.mkdir(parents=True)
    (cache / "data_1").write_text("old app.js")
    (keep / "x").write_text("keep")

    assert gui.fresh_ui_cache(store) is True          # first start after an update
    assert not cache.exists()
    assert (keep / "x").read_text() == "keep"          # nothing but the cache is touched

    cache.mkdir(parents=True)
    (cache / "data_1").write_text("current app.js")
    assert gui.fresh_ui_cache(store) is False          # same UI files: cache stays
    assert (cache / "data_1").exists()

    (store / "ui-stamp").write_text("older build")
    assert gui.fresh_ui_cache(store) is True
    assert not cache.exists()
