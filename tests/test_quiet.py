"""Programs Lanterna starts (browser, file manager) must not write into its terminal."""
import subprocess
import sys
import time

from lanterna import quiet


def test_child_output_never_reaches_our_terminal(capfd, tmp_path):
    done = tmp_path / "done"
    code = ("import sys, pathlib; print('browser log line'); sys.stderr.write('ERROR: electron\\n'); "
            f"pathlib.Path({str(done)!r}).write_text('ok')")
    assert quiet.spawn([sys.executable, "-c", code])
    for _ in range(100):
        if done.exists():
            break
        time.sleep(0.05)
    assert done.exists()
    out, err = capfd.readouterr()
    assert "browser log line" not in out and "electron" not in err


def test_linux_links_go_through_xdg_open_detached(monkeypatch):
    calls = []
    monkeypatch.setattr(quiet.sys, "platform", "linux")
    monkeypatch.setattr(quiet.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(quiet.subprocess, "Popen", lambda args, **kw: calls.append((args, kw)))
    monkeypatch.setattr(quiet.webbrowser, "open", lambda url: (_ for _ in ()).throw(AssertionError("noisy path")))
    assert quiet.open_url("https://accounts.google.com/o/oauth2/auth?x=1")
    args, kw = calls[0]
    assert args == ["xdg-open", "https://accounts.google.com/o/oauth2/auth?x=1"]
    assert kw["start_new_session"] and kw["stdout"] is subprocess.DEVNULL and kw["stderr"] is subprocess.DEVNULL
    assert kw["stdin"] is subprocess.DEVNULL


def test_missing_program_is_not_a_crash():
    assert quiet.spawn(["lanterna-no-such-program-xyz"]) is False
