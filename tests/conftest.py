import pytest


@pytest.fixture(autouse=True)
def _own_data_folder(tmp_path, monkeypatch):
    """Every test gets its own Lanterna data folder (settings, limits, backups), never the real one."""
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path / "home"))
    from lanterna import limits
    monkeypatch.setattr(limits, "TRACKER", limits.Limits())


@pytest.fixture(autouse=True)
def _no_background_loops(monkeypatch):
    """The app starts without its background loops (reminders, sync, health): they would outlive the test that
    started them and act in the next tests' data folders (LANTERNA_HOME is read each time), e.g. mark Lanterna as
    open there, so a reminder test found it "open" and showed nothing now and then."""
    from lanterna import app
    init = app.Api.__init__

    def without_loops(self, store=None, scheduler=True):
        init(self, store, scheduler=False)
    monkeypatch.setattr(app.Api, "__init__", without_loops)
