import pytest


@pytest.fixture(autouse=True)
def _own_data_folder(tmp_path, monkeypatch):
    """Every test gets its own Lanterna data folder (settings, limits, backups), never the real one."""
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path / "home"))
    from lanterna import limits
    monkeypatch.setattr(limits, "TRACKER", limits.Limits())
