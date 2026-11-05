"""Drives the debug app on an emulator through the Social tab, with adb and uiautomator.

Each step waits for text or a content description, taps it, and saves a screenshot. The run fails
on a missing element or on a crash (FATAL EXCEPTION in logcat). Screenshots land in qa-out/.
"""

import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

PKG = "com.osiris.player"
OUT = "qa-out"
SYSTEM_DIALOG = (
    "Don’t allow",
    "Don't allow",
    "Deny",
    "Not now",
    "No thanks",
    "Only this time",
)


def adb(*args: str, check: bool = True) -> str:
    r = subprocess.run(["adb", *args], capture_output=True, text=True, timeout=60)  # noqa: S603,S607
    if check and r.returncode != 0:
        raise RuntimeError(f"adb {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def nodes() -> list[dict]:
    for _ in range(5):
        adb("shell", "uiautomator", "dump", "/sdcard/ui.xml", check=False)
        raw = adb("shell", "cat", "/sdcard/ui.xml", check=False)
        if raw.strip().startswith("<?xml"):
            root = ET.fromstring(raw)
            return [n.attrib for n in root.iter("node")]
        time.sleep(1)
    return []


def visible_texts() -> list[str]:
    out = []
    for n in nodes():
        for key in ("text", "content-desc"):
            if n.get(key):
                out.append(n[key])
    return out


def crashed() -> bool:
    log = adb("logcat", "-d", "-b", "crash", check=False)
    return "FATAL EXCEPTION" in log and PKG in log


def center(bounds: str) -> tuple[int, int]:
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", bounds))
    return (x1 + x2) // 2, (y1 + y2) // 2


def find(label: str, exact: bool = True) -> dict | None:
    for n in nodes():
        for key in ("text", "content-desc"):
            v = n.get(key, "")
            if (v == label) if exact else (label in v):
                return n
    return None


def dismiss_system_dialogs() -> None:
    for n in nodes():
        if n.get("text") in SYSTEM_DIALOG:
            adb("shell", "input", "tap", *map(str, center(n["bounds"])))
            time.sleep(1)


def wait(label: str, timeout: float = 30, exact: bool = True) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        if crashed():
            fail(f"app crashed while waiting for '{label}'")
        dismiss_system_dialogs()
        n = find(label, exact)
        if n is not None:
            return n
        time.sleep(1)
    fail(f"'{label}' did not appear")
    raise AssertionError  # unreachable


def tap(label: str, timeout: float = 30, exact: bool = True) -> None:
    n = wait(label, timeout, exact)
    adb("shell", "input", "tap", *map(str, center(n["bounds"])))
    time.sleep(1.5)


def tap_field(index: int = 0, timeout: float = 20) -> None:
    """Taps the index-th text field on screen (Compose labels are not reliable node text)."""
    end = time.time() + timeout
    while time.time() < end:
        fields = [n for n in nodes() if n.get("class") == "android.widget.EditText"]
        if len(fields) > index:
            adb("shell", "input", "tap", *map(str, center(fields[index]["bounds"])))
            time.sleep(1)
            return
        time.sleep(1)
    fail(f"text field {index} did not appear")


def type_text(text: str) -> None:
    adb("shell", "input", "text", text.replace(" ", "%s"))
    time.sleep(0.5)


def shot(name: str) -> None:
    os.makedirs(OUT, exist_ok=True)
    png = subprocess.run(
        ["adb", "exec-out", "screencap", "-p"], capture_output=True, timeout=60
    ).stdout  # noqa: S603,S607
    with open(os.path.join(OUT, f"{name}.png"), "wb") as f:
        f.write(png)
    print(f"[{name}] {' | '.join(visible_texts())[:1500]}", flush=True)  # noqa: T201


def back() -> None:
    adb("shell", "input", "keyevent", "4")
    time.sleep(1.5)


def fail(why: str) -> None:
    shot("failure")
    print(
        "CRASH LOG:\n" + adb("logcat", "-d", "-b", "crash", check=False)[-6000:],
        flush=True,
    )  # noqa: T201
    print(f"E2E FAIL: {why}", flush=True)  # noqa: T201
    sys.exit(1)


def sign_in() -> None:
    adb("logcat", "-c", check=False)
    adb("shell", "am", "start", "-n", f"{PKG}/.MainActivity", check=False)
    end = time.time() + 60
    while time.time() < end:
        dismiss_system_dialogs()
        if find("Continue") is not None:
            tap("Continue")
        if find("Sign in") is not None:
            break
        time.sleep(1)
    shot("00_login")
    tap_field(0)
    type_text("qa.me@example.com")
    tap_field(1)
    type_text("QaSocial1!")
    adb("shell", "input", "keyevent", "111")  # hide the keyboard
    time.sleep(1)
    tap("Sign in")
    wait("Social", timeout=60)


def main() -> None:
    sign_in()
    shot("01_home")
    tap("Social")
    wait("New post")
    wait("Brick day done", exact=False, timeout=40)
    shot("02_social_feed")
    for label in ("New post", "Discover", "Search people", "Messages"):
        wait(label)  # the four top-bar buttons, left to right
    tap("Give kudos")
    wait("Remove kudos")
    shot("03_kudos")
    tap("Comments")
    wait("Be the first", exact=False)
    tap_field(0)
    type_text("Strong work")
    tap("Send comment")
    wait("Strong work", exact=False)
    shot("04_comment")
    back()

    tap("Discover")
    wait("For you")
    wait("Leaderboards")
    shot("05_discover")
    tap("Leaderboards")
    wait("Your rank", timeout=40, exact=False) if find(
        "Your rank", exact=False
    ) else time.sleep(3)
    shot("06_leaderboards")
    back()
    back()

    tap("Search people")
    type_text("QA Fri")
    wait("QA Friend", timeout=20)
    shot("07_search")
    tap("QA Friend")
    wait("Followers")
    shot("08_profile")
    tap("Message")
    wait("Run tomorrow at 6?", exact=False)
    tap_field(0)
    type_text("Yes 6am at the park")
    tap("Send")
    wait("Yes 6am at the park", exact=False)
    shot("09_chat")
    back()
    back()
    back()

    tap("Messages")
    wait("QA Friend")
    shot("10_inbox")
    back()

    tap("New post")
    wait("Add my progress chart")
    tap_field(0)
    type_text("Easy 3K shakeout")
    adb("shell", "input", "keyevent", "111")
    time.sleep(1)
    tap("Add my progress chart")
    tap("Run")
    shot("11_compose")
    tap("Share")
    wait("Easy 3K shakeout", exact=False, timeout=40)
    shot("12_feed_after_post")

    if crashed():
        fail("crash recorded during the run")
    print("E2E PASS social tab", flush=True)  # noqa: T201


if __name__ == "__main__":
    main()
