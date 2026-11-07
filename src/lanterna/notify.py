"""System notifications for reminders: a Windows toast or notify-send on Linux. Best effort, never raises."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Callable

# The message travels in an environment variable, so nothing in it is ever run as code.
_PS_TOAST = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$x = $t.GetElementsByTagName('text')
$x.Item(0).AppendChild($t.CreateTextNode($env:LANTERNA_TITLE)) > $null
$x.Item(1).AppendChild($t.CreateTextNode($env:LANTERNA_MSG)) > $null
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($t))
"""


# The Windows window app sets this to its tray icon's notification: it shows as Lanterna (not PowerShell),
# a click opens Lanterna, and it works where PowerShell is locked (school and office PCs).
TRAY: Callable[[str, str], bool] | None = None


def notify(title: str, message: str) -> bool:
    title, message = title[:80], message[:300]
    try:
        if sys.platform == "win32" and TRAY is not None and TRAY(title, message):
            return True
        if sys.platform == "win32":
            env = {**os.environ, "LANTERNA_TITLE": title, "LANTERNA_MSG": message}
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_TOAST], env=env,
                               capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return r.returncode == 0
        if shutil.which("notify-send"):
            return subprocess.run(["notify-send", "-a", "Lanterna", title, message], timeout=10).returncode == 0
        if sys.platform == "darwin" and shutil.which("osascript"):
            script = 'display notification (system attribute "LANTERNA_MSG") with title (system attribute "LANTERNA_TITLE")'
            env = {**os.environ, "LANTERNA_TITLE": title, "LANTERNA_MSG": message}
            return subprocess.run(["osascript", "-e", script], env=env, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        pass
    return False
