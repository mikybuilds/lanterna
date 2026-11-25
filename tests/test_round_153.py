"""Round 153 (1.1.11b7): Lanterna's own tabs.

A new address goes only to a tab Lanterna opened: from one of the user's tabs it opens in a new tab of the Lanterna
group, so the user's page stays as it was, even when that tab sits in the group because Lanterna worked there.
Back, forward and reload stay in the tab (they are its own history). Closing one of the user's tabs is an important
step (a card unless the mode is Automatic); Lanterna's own tabs close without one.
Nothing here starts Chrome: the extension is a pretend one with tabs.
"""
from lanterna import browser


class _Chrome:
    """A pretend extension: the user's tab 7 is in front (in the Lanterna group: Lanterna read it once);
    the tabs Lanterna opens get 100, 101…"""

    def __init__(self):
        self.tabs = {7: {"id": 7, "title": "Notes", "url": "https://notes.example/draft", "active": True,
                         "lanterna": True}}
        self.calls = []
        self.next = 100

    def _pick(self, tab):
        if tab in (None, "", "active"):
            return next(t for t in self.tabs.values() if t["active"])
        if tab not in self.tabs:
            raise browser.BrowserError(f"no tab {tab}: call browser_tabs for the tabs there are now")
        return self.tabs[tab]

    def call(self, cmd, timeout=None, **a):
        self.calls.append((cmd, a))
        if cmd == "tabs":
            return {"tabs": [dict(t) for t in self.tabs.values()]}
        if cmd == "open":
            for t in self.tabs.values():
                t["active"] = False
            t = self.tabs[self.next] = {"id": self.next, "title": "", "url": a["url"], "active": True, "lanterna": True}
            self.next += 1
            return dict(t)
        t = self._pick(a.get("tab"))
        if cmd == "go" and "://" in a["to"]:
            t["url"] = a["to"]
        if cmd == "close":
            del self.tabs[t["id"]]
            return {"closed": t["id"]}
        return dict(t)


def _tools(mode="semi", answer="allow", ch=None):
    ch, asked = ch or _Chrome(), []
    t = browser.Tools(ch, mode=lambda: mode, site_ok=lambda s: False, never_site=lambda s: False,
                      ask=lambda d: asked.append(d) or answer, can_see=lambda: True, limit=lambda: 8000,
                      focus=lambda: "", allowed_file=lambda p: "")
    browser.begin_answer()
    return t, ch, asked


def _moves(ch):
    return [c for c, _ in ch.calls if c in ("go", "open")]


def test_an_address_from_the_users_tab_opens_in_a_tab_of_lanternas_own():
    t, ch, asked = _tools("semi")
    out = t.go("example.org/news")
    assert ch.tabs[7]["url"] == "https://notes.example/draft"                  # the user's page stays
    assert _moves(ch) == ["open"] and ch.tabs[100]["url"] == "https://example.org/news"
    assert out.startswith("Opened in a new tab of the Lanterna group (new addresses open in Lanterna's own tabs: "
                          "the user's tab keeps its page).") and "(tab 100)" in out
    assert not asked and t.opened == {100}
    t.go("example.org/more")                                                    # this answer goes on in its own tab
    assert ch.tabs[100]["url"] == "https://example.org/more" and len(ch.tabs) == 2 and _moves(ch) == ["open", "go"]
    t.go("example.org/again", tab=7)                                            # the user's tab, named: still a new one
    assert ch.tabs[7]["url"] == "https://notes.example/draft" and ch.tabs[101]["url"] == "https://example.org/again"


def test_back_forward_and_reload_stay_in_the_tab():
    t, ch, asked = _tools("semi")
    assert t.go("back").startswith("Done.") and t.go("reload").startswith("Done.")
    assert ("go", {"tab": None, "to": "back"}) in ch.calls and len(ch.tabs) == 1 and not asked


def test_the_new_tab_still_goes_through_the_card_and_the_checks():
    t, ch, asked = _tools("ask", answer="no")
    assert t.go("example.org") == browser.DENIED
    assert asked[0]["action"] == "open" and asked[0]["url"] == "https://example.org" and _moves(ch) == []
    t, ch, asked = _tools("full")
    assert "Only http and https" in t.go("javascript:alert(1)") and len(ch.tabs) == 1


def test_closing_one_of_the_users_tabs_asks_first_and_lanternas_own_do_not():
    t, ch, asked = _tools("semi", answer="no")
    assert t.close(7) == browser.DENIED and 7 in ch.tabs                      # in the group, but the user's
    assert asked[0]["action"] == "close" and asked[0]["reason"] == "close"
    t.open("example.org")
    asked.clear()
    assert t.close(100) == "Closed tab 100." and not asked and 100 not in ch.tabs and not t.opened
    t, ch, asked = _tools("full")                                               # Automatic: no cards at all
    assert t.close(7) == "Closed tab 7." and not asked


def test_the_tab_list_calls_lanternas_only_the_tabs_it_opened():
    t, _, _ = _tools("semi")
    t.open("example.org")
    rows = t.tabs().splitlines()
    assert rows[1] == "tab 7: «Notes» https://notes.example/draft"
    assert rows[2].startswith("tab 100: ") and rows[2].endswith("(active, Lanterna's)")


def test_after_a_restart_lanterna_keeps_off_its_old_tabs_too():
    t, ch, _ = _tools("semi")
    t.open("example.org")
    again, _, _ = _tools("semi", ch=ch)                                          # Lanterna started again: Chrome kept the tab
    again.go("example.org/b", tab=100)
    assert ch.tabs[100]["url"] == "https://example.org" and ch.tabs[101]["url"] == "https://example.org/b"


def test_the_model_is_told_where_new_addresses_go():
    assert "the user's tabs keep their pages" in browser.NOTE
    t, _, _ = _tools()
    go = next(x for x in browser.make_tools(t) if x.name == "browser_go")
    assert "goes only to a tab Lanterna opened" in go.description
