"""
macOS notification helper for --watch-linkedin.

Uses `display alert` via osascript rather than `terminal-notifier`/`display
notification`: both rely on the deprecated NSUserNotification framework, which
is non-functional on recent macOS (26+) — the notification silently never
appears and never even registers in System Settings > Notifications. A native
alert dialog with an "Open" button has no such dependency and reliably renders.

Values are always passed as separate argv entries (never interpolated into a
shell or AppleScript string), so a posting title/company can't break out and
inject commands.
"""
import subprocess

_OSASCRIPT_ALERT = """
on run argv
    set jobTitle to item 1 of argv
    set jobCompany to item 2 of argv
    display alert jobTitle message jobCompany buttons {"Dismiss", "Open"} default button "Open" giving up after 3600
    return button returned of result
end run
"""


def notify(title: str, subtitle: str, message: str, url: str) -> None:
    heading = f"{title}: {subtitle}" if subtitle else title
    result = subprocess.run(
        ["osascript", "-e", _OSASCRIPT_ALERT, "--", heading, message],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout.strip() == "Open":
        subprocess.run(["open", url], check=False)
